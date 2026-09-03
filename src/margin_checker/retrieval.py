# src/margin_checker/retrieval.py

import psycopg
from minsearch import Index
from sentence_transformers import SentenceTransformer

from src.margin_checker.db import load_contract_chunks, DB_CONN


model = SentenceTransformer("all-MiniLM-L6-v2")


def vec_to_str(vector):
    return "[" + ",".join(str(x) for x in vector) + "]"


# --------------------------------------------------
# BM25
# --------------------------------------------------

def run_bm25(query, documents=None, num_results=3):

    if documents is None:
        documents = load_contract_chunks()

    index = Index(
        text_fields=["chunk_text"],
        keyword_fields=["contract_id"]
    )

    index.fit(documents)

    results = index.search(
        query=query,
        num_results=num_results
    )

    return [
        {
            "contract_id": doc["contract_id"],
            "chunk_text": doc["chunk_text"]
        }
        for doc in results
    ]


# --------------------------------------------------
# Vector Search
# --------------------------------------------------

def run_vector(query, num_results=3):

    query_vector = model.encode(query)
    vector = vec_to_str(query_vector)

    with psycopg.connect(DB_CONN) as conn:

        rows = conn.execute(
            """
            SELECT
                contract_id,
                chunk_text,
                1 - (embedding <=> %s::vector) AS score
            FROM contract_chunks
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector, vector, num_results)
        ).fetchall()

    return [
        {
            "contract_id": row[0],
            "chunk_text": row[1],
            "score": row[2]
        }
        for row in rows
    ]


# --------------------------------------------------
# Hybrid Search - Reciprocal Rank Fusion
# --------------------------------------------------

def run_hybrid(query, documents=None, num_results=3):

    if documents is None:
        documents = load_contract_chunks()

    vector_results = run_vector(query, num_results=5)
    bm25_results = run_bm25(query, documents, num_results=5)

    scores = {}
    lookup = {}

    for rank, doc in enumerate(vector_results, start=1):

        key = (
            doc["contract_id"],
            doc["chunk_text"]
        )

        lookup[key] = doc
        scores[key] = scores.get(key, 0.0) + 1 / (60 + rank)

    for rank, doc in enumerate(bm25_results, start=1):

        key = (
            doc["contract_id"],
            doc["chunk_text"]
        )

        lookup[key] = doc
        scores[key] = scores.get(key, 0.0) + 1 / (60 + rank)

    ranked = sorted(
        scores.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return [
        {
            "contract_id": lookup[key]["contract_id"],
            "chunk_text": lookup[key]["chunk_text"],
            "score": score
        }
        for key, score in ranked[:num_results]
    ]