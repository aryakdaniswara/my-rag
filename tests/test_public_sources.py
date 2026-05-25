import unittest
from dataclasses import dataclass
from typing import Any, Dict

from generation.sources import build_public_sources


@dataclass
class FakeRetrievedDoc:
    metadata: Dict[str, Any]


class PublicSourceTests(unittest.TestCase):
    def test_duplicate_pdf_sources_merge_pages(self):
        docs = [
            FakeRetrievedDoc(
                {
                    "pdf_url": "https://simak.ui.ac.id/a.pdf",
                    "page_url": "https://simak.ui.ac.id/sk-biaya/",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page_number": 6,
                }
            ),
            FakeRetrievedDoc(
                {
                    "pdf_url": "https://simak.ui.ac.id/a.pdf",
                    "page_url": "https://simak.ui.ac.id/sk-biaya/",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page_number": 7,
                }
            ),
            FakeRetrievedDoc(
                {
                    "pdf_url": "https://simak.ui.ac.id/a.pdf",
                    "page_url": "https://simak.ui.ac.id/sk-biaya/",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page_number": 6,
                }
            ),
        ]

        self.assertEqual(
            build_public_sources(docs),
            [
                {
                    "pdf_url": "https://simak.ui.ac.id/a.pdf",
                    "page_url": "https://simak.ui.ac.id/sk-biaya/",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page": 6,
                    "pages": [6, 7],
                }
            ],
        )

    def test_duplicate_html_sources_have_empty_pages(self):
        docs = [
            FakeRetrievedDoc(
                {
                    "pdf_url": None,
                    "page_url": "https://simak.ui.ac.id/sk-biaya/",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page_number": None,
                }
            ),
            FakeRetrievedDoc(
                {
                    "pdf_url": None,
                    "page_url": "https://simak.ui.ac.id/sk-biaya/",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page_number": None,
                }
            ),
        ]

        self.assertEqual(
            build_public_sources(docs),
            [
                {
                    "pdf_url": None,
                    "page_url": "https://simak.ui.ac.id/sk-biaya/",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page": None,
                    "pages": [],
                }
            ],
        )

    def test_html_sources_fall_back_to_source_url(self):
        docs = [
            FakeRetrievedDoc(
                {
                    "source_url": "https://admission.ui.ac.id/register",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page_number": None,
                }
            ),
            FakeRetrievedDoc(
                {
                    "source_url": "https://admission.ui.ac.id/register",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page_number": None,
                }
            ),
        ]

        self.assertEqual(
            build_public_sources(docs),
            [
                {
                    "pdf_url": None,
                    "page_url": "https://admission.ui.ac.id/register",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page": None,
                    "pages": [],
                }
            ],
        )

    def test_mixed_pdf_and_html_sources_stay_separate(self):
        docs = [
            FakeRetrievedDoc(
                {
                    "pdf_url": "https://simak.ui.ac.id/a.pdf",
                    "page_url": "https://simak.ui.ac.id/sk-biaya/",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page_number": 6,
                }
            ),
            FakeRetrievedDoc(
                {
                    "pdf_url": None,
                    "page_url": "https://simak.ui.ac.id/jadwal/",
                    "scraped_at": "2026-05-08T06:20:11Z",
                    "page_number": None,
                }
            ),
        ]

        self.assertEqual(
            build_public_sources(docs),
            [
                {
                    "pdf_url": "https://simak.ui.ac.id/a.pdf",
                    "page_url": "https://simak.ui.ac.id/sk-biaya/",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page": 6,
                    "pages": [6],
                },
                {
                    "pdf_url": None,
                    "page_url": "https://simak.ui.ac.id/jadwal/",
                    "scraped_at": "2026-05-08T06:20:11Z",
                    "page": None,
                    "pages": [],
                },
            ],
        )

    def test_missing_url_fields_return_consistent_source(self):
        docs = [
            FakeRetrievedDoc({"page_number": 3}),
            FakeRetrievedDoc({"scraped_at": "2026-05-08T06:13:55Z"}),
        ]

        self.assertEqual(
            build_public_sources(docs),
            [
                {
                    "pdf_url": None,
                    "page_url": None,
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "page": None,
                    "pages": [],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
