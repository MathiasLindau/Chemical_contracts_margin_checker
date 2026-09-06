import os
import unittest
from datetime import datetime, timezone

from src.margin_checker.db import (
    HISTORY_LIMIT,
    format_created_at,
)


class HistoryLimitTest(unittest.TestCase):

    def test_default_history_is_ten(self):
        self.assertEqual(HISTORY_LIMIT, 10)


class FormatCreatedAtTest(unittest.TestCase):

    def tearDown(self):
        os.environ.pop("DISPLAY_TZ", None)
        os.environ.pop("TZ", None)

    def test_converts_utc_to_berlin(self):
        os.environ["DISPLAY_TZ"] = "Europe/Berlin"
        created = datetime(2026, 9, 6, 17, 13, tzinfo=timezone.utc)
        self.assertEqual(format_created_at(created), "2026-09-06 19:13")

    def test_treats_naive_timestamps_as_utc(self):
        os.environ["DISPLAY_TZ"] = "Europe/Berlin"
        created = datetime(2026, 9, 6, 17, 13)
        self.assertEqual(format_created_at(created), "2026-09-06 19:13")


class RetrievalEvalWiringTest(unittest.TestCase):

    def test_retrieval_eval_includes_reranker(self):
        from pathlib import Path

        source = Path("evaluation/evaluate_retrieval.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("rerank_search", source)
        self.assertIn("RRF_CANDIDATES = 10", source)
        self.assertIn("Cross-Encoder", source)

    def test_app_uses_delete_and_local_time(self):
        from pathlib import Path

        source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn("delete_query_log", source)
        self.assertIn("delete_all_query_logs", source)
        self.assertIn("format_created_at", source)
        self.assertIn("HISTORY_LIMIT", source)


class ScoreRetrievedTest(unittest.TestCase):

    def test_hit_mrr_and_full_hit(self):
        from evaluation.evaluate_retrieval import score_retrieved

        hit, full_hit, mrr = score_retrieved(
            ["CON-2023-0007", "CON-2023-0005", "CON-2023-0001"],
            ["CON-2023-0005", "CON-2023-0007"],
        )
        self.assertEqual(hit, 1)
        self.assertEqual(full_hit, 1)
        self.assertEqual(mrr, 1.0)

    def test_miss(self):
        from evaluation.evaluate_retrieval import score_retrieved

        hit, full_hit, mrr = score_retrieved(
            ["CON-2023-0048"],
            ["CON-2023-0007"],
        )
        self.assertEqual((hit, full_hit, mrr), (0, 0, 0.0))


if __name__ == "__main__":
    unittest.main()
