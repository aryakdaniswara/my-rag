import unittest

from generation.sources import build_public_sources
from retrieval.retriever import Retriever


class RetrieverSourceMetadataTests(unittest.TestCase):
    def test_rrf_preserves_source_url_for_public_sources(self):
        retriever = object.__new__(Retriever)
        dense_results = [
            {
                "id": 1,
                "entity": {
                    "text": "Registration information",
                    "doc_id": "page-html-register",
                    "chunk_index": 0,
                    "pdf_url": None,
                    "page_url": None,
                    "source_url": "https://admission.ui.ac.id/register",
                    "scraped_at": "2026-05-08T06:13:55Z",
                    "breadcrumb": "",
                    "page_number": None,
                },
            }
        ]

        docs = retriever._apply_rrf(dense_results, sparse_results=[], k=60)

        self.assertEqual(
            docs[0].metadata["source_url"],
            "https://admission.ui.ac.id/register",
        )
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


if __name__ == "__main__":
    unittest.main()
