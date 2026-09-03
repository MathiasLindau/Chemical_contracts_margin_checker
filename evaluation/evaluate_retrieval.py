import json
import psycopg
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from minsearch import Index

load_dotenv()

model = SentenceTransformer("all-MiniLM-L6-v2")
DB_CONN = "postgresql://postgres:password@localhost:5432/contracts_db"


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
    v = vec_to_str(model.encode(q))

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


def evaluate():
    docs = load_docs()

    index = Index(
        text_fields=["chunk_text"],
        keyword_fields=["contract_id"]
    )
    index.fit(docs)

    with open("evaluation/evaluation_questions.json", encoding="utf-8") as f:
        tests = json.load(f)

    metrics = {
        name: {"hits": 0, "full_hits": 0, "mrr": 0}
        for name in ["vector", "bm25", "hybrid"]
    }

    for item in tests:
        q = item["question"]
        valid = item["valid_contract_ids"]

        searches = {
            "vector": vector_search(q),
            "bm25": bm25_search(q, index),
            "hybrid": hybrid_search(q, index)
        }

        for name, retrieved in searches.items():

            ranks = [
                retrieved.index(cid) + 1
                for cid in valid
                if cid in retrieved
            ]

            if ranks:
                metrics[name]["hits"] += 1
                metrics[name]["mrr"] += 1 / min(ranks)

            if all(cid in retrieved for cid in valid):
                metrics[name]["full_hits"] += 1

    print("=" * 45)
    print("📊 RETRIEVAL EVALUATION")
    print("=" * 45)

    for name, m in metrics.items():
        print(f"{name.upper()}:")
        print(f"  Hit@3:      {100 * m['hits'] / len(tests):.1f}%")
        print(f"  Full Hit@3: {100 * m['full_hits'] / len(tests):.1f}%")
        print(f"  MRR@3:      {m['mrr'] / len(tests):.4f}")


if __name__ == "__main__":
    evaluate()