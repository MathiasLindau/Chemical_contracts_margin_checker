import json
import unittest
from pathlib import Path
from unittest.mock import patch

from src.margin_checker.retrieval import (
    filter_chunks_by_contract_ids,
    run_bm25,
    run_hybrid,
    structured_contract_ids,
)


CHUNKS = [
    {
        "contract_id": "CON-2023-0007",
        "chunk_text": "Payment terms are net 45 days. Energy adder 3%.",
    },
    {
        "contract_id": "CON-2023-0007",
        "chunk_text": "Breach penalty applies if monthly volume is missed.",
    },
    {
        "contract_id": "CON-2023-0048",
        "chunk_text": "Unrelated logistics and demurrage clause.",
    },
    {
        "contract_id": "CON-2023-0017",
        "chunk_text": "Another contract payment terms net 30 days.",
    },
]


class StructuredContractIdsTest(unittest.TestCase):

    def test_collects_unique_ids_in_order(self):
        results = [
            {"contract_id": "CON-2023-0007", "base_price": 250},
            {"contract_id": "con-2023-0007", "base_price": 250},
            {"contract_id": "CON-2023-0005", "base_price": 500},
            {"field": "overall_adder", "average": 12.0},
        ]
        self.assertEqual(
            structured_contract_ids(results),
            ["CON-2023-0007", "CON-2023-0005"],
        )

    def test_empty_for_aggregations(self):
        self.assertEqual(
            structured_contract_ids([{"count": 50}]),
            [],
        )


class FilterChunksTest(unittest.TestCase):

    def test_keeps_only_requested_contracts(self):
        filtered = filter_chunks_by_contract_ids(
            CHUNKS,
            ["CON-2023-0007"],
        )
        self.assertEqual(
            {item["contract_id"] for item in filtered},
            {"CON-2023-0007"},
        )
        self.assertEqual(len(filtered), 2)

    def test_empty_filter_keeps_all(self):
        self.assertEqual(filter_chunks_by_contract_ids(CHUNKS, []), CHUNKS)


class RestrictedBm25Test(unittest.TestCase):

    def test_bm25_does_not_return_other_contracts(self):
        results = run_bm25(
            "payment terms",
            documents=CHUNKS,
            num_results=10,
            contract_ids=["CON-2023-0007"],
        )
        self.assertTrue(results)
        self.assertTrue(
            all(item["contract_id"] == "CON-2023-0007" for item in results)
        )

    def test_unknown_id_returns_empty(self):
        results = run_bm25(
            "payment terms",
            documents=CHUNKS,
            num_results=10,
            contract_ids=["CON-2099-9999"],
        )
        self.assertEqual(results, [])


class RestrictedHybridTest(unittest.TestCase):

    @patch("src.margin_checker.retrieval.run_vector")
    def test_hybrid_forwards_ids_and_drops_other_contracts(self, mock_vector):
        mock_vector.return_value = [
            {
                "contract_id": "CON-2023-0007",
                "chunk_text": "Payment terms are net 45 days. Energy adder 3%.",
                "score": 0.9,
            }
        ]

        results = run_hybrid(
            "payment terms",
            documents=CHUNKS,
            num_results=10,
            contract_ids=["CON-2023-0007"],
        )

        mock_vector.assert_called_once()
        self.assertEqual(
            mock_vector.call_args.kwargs["contract_ids"],
            ["CON-2023-0007"],
        )
        self.assertTrue(results)
        self.assertTrue(
            all(item["contract_id"] == "CON-2023-0007" for item in results)
        )


class PipelineWiringTest(unittest.TestCase):

    def test_hybrid_route_restricts_text_search(self):
        source = Path("src/margin_checker/rag.py").read_text(encoding="utf-8")
        self.assertIn("restrict_ids = structured_contract_ids", source)
        self.assertIn("contract_ids=restrict_ids or None", source)
        self.assertIn('RAG_LLM_JUDGE", "1"', source)

    def test_judge_defaults_on(self):
        source = Path("src/margin_checker/rag.py").read_text(encoding="utf-8")
        self.assertIn('os.getenv("RAG_LLM_JUDGE", "1")', source)
        env_example = Path(".env.example").read_text(encoding="utf-8")
        self.assertIn("RAG_LLM_JUDGE=1", env_example)

    def test_grafana_dashboard_is_checked_in(self):
        dashboard_path = Path("grafana/dashboards/query-monitoring.json")
        datasource_path = Path(
            "grafana/provisioning/datasources/datasources.yml"
        )
        compose = Path("docker-compose.yml").read_text(encoding="utf-8")
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))

        self.assertTrue(dashboard_path.is_file())
        self.assertTrue(datasource_path.is_file())
        self.assertEqual(dashboard["uid"], "margin-checker-query-logs")
        self.assertEqual(dashboard["title"], "Query Monitoring")
        self.assertIn("./grafana/provisioning", compose)
        self.assertIn("./grafana/dashboards", compose)
        self.assertIn("postgres-query-logs", datasource_path.read_text())


if __name__ == "__main__":
    unittest.main()
