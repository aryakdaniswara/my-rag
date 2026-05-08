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
from scraper_api.presets import get_preset, list_presets


class ScraperMappingTests(unittest.TestCase):
    def test_ui_presets_are_available_and_overrideable(self):
        presets = list_presets()
        self.assertIn("simak", presets)
        self.assertIn("ui_ac_id", presets)
        self.assertEqual(presets["simak"]["domain"], "simak.ui.ac.id")

        custom = get_preset(
            "simak",
            {
                "domain": "example.org",
                "folder": "external_example",
                "seeds": ["https://example.org/"],
            },
        )
        self.assertEqual(custom["domain"], "example.org")
        self.assertEqual(custom["folder"], "external_example")
        self.assertEqual(custom["seeds"], ["https://example.org/"])

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
