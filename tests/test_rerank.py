import unittest

from src.margin_checker.rerank import rerank_results


class FakeReranker:
    """Assigns a known score per chunk so ranking is deterministic."""

    def __init__(self, scores_by_text):
        self.scores_by_text = scores_by_text
        self.pairs = None

    def predict(self, pairs):
        self.pairs = [list(pair) for pair in pairs]
        return [self.scores_by_text[pair[1]] for pair in self.pairs]


class RerankResultsTest(unittest.TestCase):

    def setUp(self):
        self.candidates = [
            {
                "contract_id": "CON-2023-0006",
                "chunk_text": "Acetone 1050 USD",
                "score": 0.01639,
            },
            {
                "contract_id": "CON-2023-0048",
                "chunk_text": "Unrelated logistics clause",
                "score": 0.01639,
            },
            {
                "contract_id": "CON-2023-0031",
                "chunk_text": "PLA Resin 980 EUR",
                "score": 0.01613,
            },
            {
                "contract_id": "CON-2023-0007",
                "chunk_text": "Silica Sand 250 EUR Building Materials Co.",
                "score": 0.01582,
            },
        ]
        self.reranker = FakeReranker({
            "Acetone 1050 USD": 4.3318,
            "Unrelated logistics clause": 0.12,
            "PLA Resin 980 EUR": 6.9124,
            "Silica Sand 250 EUR Building Materials Co.": 8.4210,
        })

    def test_reranker_reorders_by_query_document_score(self):
        ranked = rerank_results(
            "Which contract is cheapest?",
            self.candidates,
            top_k=3,
            reranker=self.reranker,
        )

        self.assertEqual(
            [item["contract_id"] for item in ranked],
            ["CON-2023-0007", "CON-2023-0031", "CON-2023-0006"],
        )

    def test_preserves_rrf_score_and_adds_reranker_score(self):
        ranked = rerank_results(
            "Which contract is cheapest?",
            self.candidates,
            top_k=3,
            reranker=self.reranker,
        )

        top = ranked[0]
        self.assertEqual(top["contract_id"], "CON-2023-0007")
        self.assertEqual(top["score"], 0.01582)
        self.assertAlmostEqual(top["reranker_score"], 8.4210)
        self.assertIn("chunk_text", top)

    def test_returns_only_top_k(self):
        ranked = rerank_results(
            "Which contract is cheapest?",
            self.candidates,
            top_k=3,
            reranker=self.reranker,
        )
        self.assertEqual(len(ranked), 3)
        ids = [item["contract_id"] for item in ranked]
        self.assertNotIn("CON-2023-0048", ids)

    def test_scores_question_chunk_pairs(self):
        query = "Which contract is cheapest?"
        rerank_results(
            query,
            self.candidates,
            top_k=3,
            reranker=self.reranker,
        )
        self.assertEqual(len(self.reranker.pairs), 4)
        self.assertTrue(
            all(pair[0] == query for pair in self.reranker.pairs)
        )

    def test_reranker_failure_keeps_rrf_order(self):

        class BrokenReranker:
            def predict(self, pairs):
                raise RuntimeError("model unavailable")

        ranked = rerank_results(
            "Which contract is cheapest?",
            self.candidates,
            top_k=3,
            reranker=BrokenReranker(),
        )

        self.assertEqual(
            [item["contract_id"] for item in ranked],
            ["CON-2023-0006", "CON-2023-0048", "CON-2023-0031"],
        )
        self.assertTrue(
            all(item["reranker_score"] is None for item in ranked)
        )
        self.assertEqual(
            rerank_results("anything", [], top_k=3, reranker=self.reranker),
            [],
        )

    def test_ui_label_includes_both_scores(self):
        ranked = rerank_results(
            "Which contract is cheapest?",
            self.candidates,
            top_k=3,
            reranker=self.reranker,
        )
        source = ranked[0]
        parts = [f"RRF: {source['score']:.5f}"]
        parts.append(f"Reranker: {source['reranker_score']:.4f}")
        label = f"{source['contract_id']} ({', '.join(parts)})"
        self.assertEqual(
            label,
            "CON-2023-0007 (RRF: 0.01582, Reranker: 8.4210)",
        )


class PipelineWiringTest(unittest.TestCase):

    def test_rag_uses_rrf_pool_then_rerank(self):
        from pathlib import Path

        source = Path("src/margin_checker/rag.py").read_text(encoding="utf-8")
        self.assertIn("RRF_CANDIDATES = 10", source)
        self.assertIn("RERANK_TOP_K = 3", source)
        self.assertIn("num_results=RRF_CANDIDATES", source)
        self.assertIn("rerank_results(", source)
        self.assertIn("top_k=RERANK_TOP_K", source)
        self.assertNotIn("num_results=3", source)


if __name__ == "__main__":
    unittest.main()
