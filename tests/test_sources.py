import unittest

from src.margin_checker.sources import split_primary_secondary


class SplitPrimarySecondaryTest(unittest.TestCase):

    def test_cited_structured_source_is_primary(self):
        answer = (
            "The cheapest option is Building Materials Co. "
            "(CON-2023-0007) at 250 EUR."
        )
        sources = [
            {
                "contract_id": "CON-2023-0048",
                "chunk_text": "logistics",
                "score": 0.01639,
                "reranker_score": -11.2,
            },
            {
                "contract_id": "CON-2023-0007",
                "customer_name": "Building Materials Co.",
                "base_price": 250.0,
            },
        ]

        primary, secondary = split_primary_secondary(answer, sources)

        self.assertEqual(
            [item["contract_id"] for item in primary],
            ["CON-2023-0007"],
        )
        self.assertEqual(
            [item["contract_id"] for item in secondary],
            ["CON-2023-0048"],
        )

    def test_prefers_structured_row_before_text_for_same_id(self):
        answer = "See CON-2023-0007."
        sources = [
            {
                "contract_id": "CON-2023-0007",
                "chunk_text": "clause",
                "score": 0.01,
            },
            {
                "contract_id": "CON-2023-0007",
                "base_price": 250.0,
            },
        ]

        primary, secondary = split_primary_secondary(answer, sources)

        self.assertEqual(len(primary), 2)
        self.assertNotIn("chunk_text", primary[0])
        self.assertIn("chunk_text", primary[1])
        self.assertEqual(secondary, [])


if __name__ == "__main__":
    unittest.main()
