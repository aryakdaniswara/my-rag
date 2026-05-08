import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from ingestion.pipeline import IngestionPipeline
from scraper_api.service import (
    ScrapeConfig,
    ScrapeJob,
    ScraperJobManager,
    inject_source_url_meta,
    is_allowed_path,
    sanitize_pdf_filename,
    url_to_abs_folder,
    url_to_folder_path,
)
from scraper_api.sites import (
    config_from_configured_site,
    config_from_urls,
    folder_from_domain,
    is_ui_domain,
)


class ScraperMappingTests(unittest.TestCase):
    def test_url_job_config_derives_domain_folder_and_paths(self):
        config = config_from_urls(
            [
                "https://simak.ui.ac.id/jadwal-seleksi/",
                "https://simak.ui.ac.id/sk-biaya-pendidikan-ui/",
            ],
            dry_run=True,
        )
        self.assertEqual(config["domain"], "simak.ui.ac.id")
        self.assertEqual(config["folder"], "simak")
        self.assertEqual(
            config["allowed_paths"],
            ["/jadwal-seleksi/", "/sk-biaya-pendidikan-ui/"],
        )
        self.assertTrue(config["dry_run"])

    def test_url_job_config_blocks_external_by_default(self):
        with self.assertRaises(ValueError):
            config_from_urls(["https://example.org/"])

        config = config_from_urls(["https://example.org/"], allow_external=True)
        self.assertEqual(config["domain"], "example.org")
        self.assertEqual(config["folder"], "example_org")

    def test_ui_domain_helpers(self):
        self.assertTrue(is_ui_domain("simak.ui.ac.id"))
        self.assertTrue(is_ui_domain("ui.ac.id"))
        self.assertFalse(is_ui_domain("example.org"))
        self.assertEqual(folder_from_domain("www.ui.ac.id"), "ui_ac_id")

    def test_configured_site_uses_built_in_settings(self):
        config = config_from_configured_site(
            "https://simak.ui.ac.id/",
            dry_run=True,
        )
        self.assertEqual(config["domain"], "simak.ui.ac.id")
        self.assertEqual(config["folder"], "simak")
        self.assertIn("/jadwal-seleksi/", config["allowed_paths"])
        self.assertIn("/berita/", config["disallowed_paths"])
        self.assertEqual(config["max_depth"], 4)
        self.assertEqual(config["max_parallelism"], 2)
        self.assertTrue(config["dry_run"])

    def test_new_helpdesk_sites_are_configured(self):
        international = config_from_configured_site("https://international.ui.ac.id/")
        admission = config_from_configured_site("https://admission.ui.ac.id/")
        enrollment = config_from_configured_site("https://enrollment.ui.ac.id/")

        self.assertEqual(international["folder"], "international")
        self.assertIn("/prospective-students/", international["allowed_paths"])
        self.assertIn("/undergraduate-program/", international["allowed_paths"])
        self.assertIn("/graduate-program/", international["allowed_paths"])
        self.assertIn("/knb/", international["allowed_paths"])

        self.assertEqual(admission["folder"], "admission")
        self.assertEqual(admission["max_depth"], 2)
        self.assertEqual(admission["max_parallelism"], 1)

        self.assertEqual(enrollment["folder"], "enrollment")
        self.assertEqual(enrollment["max_depth"], 1)
        self.assertEqual(enrollment["max_parallelism"], 1)

    def test_url_to_folder_path_matches_old_scraper_shape(self):
        self.assertEqual(
            url_to_folder_path("https://simak.ui.ac.id/program/s1-reguler/"),
            Path("program") / "s1_reguler",
        )
        self.assertEqual(
            url_to_folder_path("https://www.ui.ac.id/"),
            Path("index"),
        )
        self.assertEqual(
            url_to_folder_path(
                "https://beasiswa.ui.ac.id/web/index.html../apps/site/beranda?action=x"
            ),
            Path("web") / "index_html" / "apps" / "site" / "beranda",
        )

    def test_allowed_paths_use_url_prefixes(self):
        self.assertTrue(
            is_allowed_path(
                "https://simak.ui.ac.id/sk-biaya-pendidikan-ui/",
                ["/sk-biaya"],
            )
        )
        self.assertFalse(
            is_allowed_path("https://simak.ui.ac.id/tentang-simak/", ["/sk-biaya"])
        )
        self.assertTrue(is_allowed_path("https://simak.ui.ac.id/anything", []))

    def test_pdf_filename_sanitization(self):
        self.assertEqual(
            sanitize_pdf_filename(
                "https://www.ui.ac.id/docs/SK%20Tarif%20UKT%202026.pdf"
            ),
            "SK_Tarif_UKT_2026.pdf",
        )
        self.assertEqual(sanitize_pdf_filename("https://www.ui.ac.id/"), "document.pdf")

    def test_inject_source_url_meta(self):
        injected = inject_source_url_meta(
            b"<html><head><title>x</title></head><body></body></html>",
            "https://www.ui.ac.id/",
        ).decode("utf-8")
        self.assertIn('meta name="source-url"', injected)
        self.assertIn('content="https://www.ui.ac.id/"', injected)

    def test_extract_links_skips_malformed_hrefs(self):
        manager = ScraperJobManager()
        links = manager._extract_links(
            '<a href="http://[bad">bad</a><a href="/ok/">ok</a>',
            "https://simak.ui.ac.id/",
        )
        self.assertEqual(links, ["https://simak.ui.ac.id/ok/"])


class ScraperSaveContractTests(unittest.TestCase):
    def test_save_page_and_pdf_metadata_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = ScrapeConfig(
                domain="www.ui.ac.id",
                folder="ui_ac_id",
                seeds=["https://www.ui.ac.id/skbp2026/"],
                output_dir=tmp,
            ).normalized()
            manager = ScraperJobManager()
            job = ScrapeJob(job_id="job", config=config)

            page_response = httpx.Response(
                200,
                headers={"content-type": "text/html; charset=UTF-8"},
                content=b"<html><head></head><body>hello</body></html>",
            )
            pdf_response = httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF-1.4",
            )

            asyncio.run(
                manager._save_page(job, "https://www.ui.ac.id/skbp2026/", page_response)
            )
            asyncio.run(
                manager._save_pdf(
                    job,
                    "https://www.ui.ac.id/docs/SK%20Tarif.pdf",
                    "https://www.ui.ac.id/skbp2026/",
                    pdf_response,
                )
            )

            folder = url_to_abs_folder(
                "https://www.ui.ac.id/skbp2026/", tmp, "ui_ac_id"
            )
            self.assertTrue((folder / "page.html").exists())
            self.assertTrue((folder / "page.meta.json").exists())
            self.assertTrue((folder / "SK_Tarif.pdf").exists())
            self.assertTrue((folder / "SK_Tarif.pdf.meta.json").exists())

            page_meta = json.loads((folder / "page.meta.json").read_text())
            pdf_meta = json.loads((folder / "SK_Tarif.pdf.meta.json").read_text())
            self.assertEqual(page_meta["source_url"], "https://www.ui.ac.id/skbp2026/")
            self.assertEqual(page_meta["domain"], "www.ui.ac.id")
            self.assertEqual(pdf_meta["pdf_url"], "https://www.ui.ac.id/docs/SK%20Tarif.pdf")
            self.assertEqual(pdf_meta["page_url"], "https://www.ui.ac.id/skbp2026/")
            self.assertEqual(pdf_meta["filename"], "SK_Tarif.pdf")
            self.assertEqual(pdf_meta["status_code"], 200)
            self.assertEqual(pdf_meta["content_type"], "application/pdf")

    def test_dry_run_writes_no_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = ScrapeConfig(
                domain="www.ui.ac.id",
                folder="ui_ac_id",
                seeds=["https://www.ui.ac.id/"],
                output_dir=tmp,
                dry_run=True,
            ).normalized()
            manager = ScraperJobManager()
            job = ScrapeJob(job_id="job", config=config)
            response = httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"<html></html>",
            )

            asyncio.run(manager._save_page(job, "https://www.ui.ac.id/", response))

            self.assertFalse((Path(tmp) / "ui_ac_id").exists())
            self.assertEqual(job.pages_visited, 1)

    def test_ingestion_metadata_loader_reads_scraper_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            page_path = folder / "page.html"
            page_path.write_text("<html></html>", encoding="utf-8")
            (folder / "page.meta.json").write_text(
                json.dumps({"source_url": "https://www.ui.ac.id/", "domain": "www.ui.ac.id"}),
                encoding="utf-8",
            )
            (folder / "page.html.meta.json").write_text(
                json.dumps({"pdf_url": "https://www.ui.ac.id/a.pdf"}),
                encoding="utf-8",
            )

            pipeline = IngestionPipeline.__new__(IngestionPipeline)
            metadata = pipeline._load_external_metadata(str(page_path))

            self.assertEqual(metadata["source_url"], "https://www.ui.ac.id/")
            self.assertEqual(metadata["domain"], "www.ui.ac.id")
            self.assertEqual(metadata["pdf_url"], "https://www.ui.ac.id/a.pdf")


if __name__ == "__main__":
    unittest.main()
