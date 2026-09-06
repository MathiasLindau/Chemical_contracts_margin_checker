import unittest

import pandas as pd

from src.margin_checker.structured import (
    STRUCTURED_ROW_CAP,
    apply_catalog_filters,
    cap_structured_rows,
)
from src.margin_checker.retrieval import (
    hybrid_text_contract_ids,
    match_named_contracts,
    structured_contract_ids,
)


CATALOG = pd.DataFrame([
    {
        "contract_id": "CON-2023-0007",
        "customer_name": "Building Materials Co.",
        "product_name": "Silica Sand",
        "base_price": 250.0,
    },
    {
        "contract_id": "CON-2023-0033",
        "customer_name": "Wood Chemicals Inc.",
        "product_name": "Phenol",
        "base_price": 1100.0,
    },
    {
        "contract_id": "CON-2023-0048",
        "customer_name": "Packaging and Chemicals Inc.",
        "product_name": "Polystyrene",
        "base_price": 800.0,
    },
])


class NamedContractMatchTest(unittest.TestCase):

    def test_matches_product_name(self):
        ids = match_named_contracts(
            "What is the average price for Phenol and the payment terms?",
            CATALOG,
        )
        self.assertEqual(ids, ["CON-2023-0033"])

    def test_ignores_generic_questions(self):
        ids = match_named_contracts(
            "What is the average base price across all contracts?",
            CATALOG,
        )
        self.assertEqual(ids, [])


class HybridTextScopeTest(unittest.TestCase):

    def test_aggregation_without_ids_skips_text(self):
        ids = hybrid_text_contract_ids(
            [{"field": "base_price", "average": 700.0, "scope": "all_contracts"}],
            query="What is the average price and typical payment terms?",
            catalog=CATALOG,
        )
        self.assertEqual(ids, [])

    def test_named_product_on_aggregation_restricts(self):
        ids = hybrid_text_contract_ids(
            [{"field": "base_price", "average": 1100.0}],
            query="Average Phenol price and its payment terms?",
            catalog=CATALOG,
        )
        self.assertEqual(ids, ["CON-2023-0033"])

    def test_full_catalog_id_list_skips_text(self):
        ids = hybrid_text_contract_ids(
            [{"contract_id": row} for row in CATALOG["contract_id"]],
            catalog=CATALOG,
        )
        self.assertEqual(ids, [])

    def test_nested_contract_ids_on_filtered_average(self):
        ids = hybrid_text_contract_ids(
            [{
                "average": 250.0,
                "contract_ids": ["CON-2023-0007"],
                "scope": "filtered",
            }],
            catalog=CATALOG,
        )
        self.assertEqual(ids, ["CON-2023-0007"])

    def test_caps_text_search_ids(self):
        extra = pd.concat(
            [
                CATALOG,
                pd.DataFrame([
                    {
                        "contract_id": f"CON-2023-{i:04d}",
                        "customer_name": f"Buyer {i}",
                        "product_name": f"Product {i}",
                    }
                    for i in range(60, 80)
                ]),
            ],
            ignore_index=True,
        )
        subset = extra["contract_id"].tolist()[:12]
        rows = [{"contract_id": cid} for cid in subset]
        ids = hybrid_text_contract_ids(rows, catalog=extra)
        self.assertEqual(len(ids), 5)
        self.assertTrue(set(ids).issubset(set(subset)))

    def test_generic_question_does_not_invent_filters(self):
        filtered = apply_catalog_filters(
            CATALOG,
            {"field": "base_price", "operation": "lookup"},
            "Show me every contract",
        )
        self.assertEqual(len(filtered), len(CATALOG))

    def test_lookup_filter_by_product(self):
        filtered = apply_catalog_filters(
            CATALOG,
            {
                "field": "base_price",
                "operation": "lookup",
                "product_name": "Phenol",
            },
            "lookup Phenol",
        )
        self.assertEqual(
            filtered["contract_id"].tolist(),
            ["CON-2023-0033"],
        )

    def test_row_cap_adds_truncation_note(self):
        rows = [{"contract_id": f"CON-{i}"} for i in range(20)]
        capped = cap_structured_rows(rows)
        self.assertEqual(capped[0]["truncated"], True)
        self.assertEqual(capped[0]["match_count"], 20)
        self.assertEqual(len(capped), STRUCTURED_ROW_CAP + 1)

    def test_structured_ids_read_nested_lists(self):
        self.assertEqual(
            structured_contract_ids([
                {"contract_ids": ["CON-2023-0007", "CON-2023-0033"]},
            ]),
            ["CON-2023-0007", "CON-2023-0033"],
        )


if __name__ == "__main__":
    unittest.main()
