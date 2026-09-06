import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from minsearch import Index

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv()

DB_CONN = os.getenv(
    "DB_CONN",
    "postgresql://postgres:password@localhost:5432/contracts_db",
)

RRF_CANDIDATES = 10
RERANK_TOP_K = 3
_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def vec_to_str(v):
    return "[" + ",".join(str(x) for x in v) + "]"


def load_docs():
    with psycopg.connect(DB_CONN) as conn:
        rows = conn.execute(
            "SELECT contract_id, chunk_text FROM contract_chunks"
        ).fetchall()

    return [
        {
            "contract_id": r[0],
            "chunk_text": r[1]
        }
        for r in rows
    ]


def vector_search(q, n=3):
    v = vec_to_str(get_model().encode(q))

    with psycopg.connect(DB_CONN) as conn:
        rows = conn.execute("""
            SELECT contract_id
            FROM contract_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (v, n)).fetchall()

    return [r[0] for r in rows]


def bm25_search(q, index, n=3):
    return [
        d["contract_id"]
        for d in index.search(q, num_results=n)
    ]


def hybrid_search(q, index, n=3):
    results = {}

    for rank, cid in enumerate(vector_search(q, 5), 1):
        results[cid] = results.get(cid, 0) + 1 / (60 + rank)

    for rank, cid in enumerate(bm25_search(q, index, 5), 1):
        results[cid] = results.get(cid, 0) + 1 / (60 + rank)

    return [
        cid
        for cid, _ in sorted(
            results.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]
    ]


def rerank_search(q, documents, n=RERANK_TOP_K):
    """Production text path: RRF top 10, then Cross-Encoder top 3."""
    from src.margin_checker.retrieval import run_hybrid
    from src.margin_checker.rerank import rerank_results

    candidates = run_hybrid(
        q,
        documents,
        num_results=RRF_CANDIDATES,
    )
    ranked = rerank_results(q, candidates, top_k=n)
    return [item["contract_id"] for item in ranked]


def score_retrieved(retrieved, valid):
    ranks = [
        retrieved.index(cid) + 1
        for cid in valid
        if cid in retrieved
    ]
    hit = 1 if ranks else 0
    mrr = 1 / min(ranks) if ranks else 0.0
    full_hit = 1 if all(cid in retrieved for cid in valid) else 0
    return hit, full_hit, mrr


def evaluate():
    docs = load_docs()

    index = Index(
        text_fields=["chunk_text"],
        keyword_fields=["contract_id"]
    )
    index.fit(docs)

    with open(ROOT / "evaluation" / "evaluation_questions.json", encoding="utf-8") as f:
        tests = json.load(f)

    metrics = {
        name: {"hits": 0, "full_hits": 0, "mrr": 0.0}
        for name in ["vector", "bm25", "hybrid", "rerank"]
    }

    for item in tests:
        q = item["question"]
        valid = item["valid_contract_ids"]

        searches = {
            "vector": vector_search(q),
            "bm25": bm25_search(q, index),
            "hybrid": hybrid_search(q, index),
            "rerank": rerank_search(q, docs),
        }

        for name, retrieved in searches.items():
            hit, full_hit, mrr = score_retrieved(retrieved, valid)
            metrics[name]["hits"] += hit
            metrics[name]["full_hits"] += full_hit
            metrics[name]["mrr"] += mrr

    labels = {
        "vector": "VECTOR",
        "bm25": "BM25",
        "hybrid": "HYBRID (RRF@3)",
        "rerank": "RERANK (RRF@10 + Cross-Encoder@3)",
    }

    print("=" * 45)
    print("RETRIEVAL EVALUATION")
    print("=" * 45)

    n = len(tests)
    for name, m in metrics.items():
        print(f"{labels[name]}:")
        print(f"  Hit@3:      {100 * m['hits'] / n:.1f}%")
        print(f"  Full Hit@3: {100 * m['full_hits'] / n:.1f}%")
        print(f"  MRR@3:      {m['mrr'] / n:.4f}")


if __name__ == "__main__":
    evaluate()
