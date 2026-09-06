# src/margin_checker/retrieval.py

from minsearch import Index

from src.margin_checker.db import load_contract_chunks, connect


BI_ENCODER_MODEL = "all-MiniLM-L6-v2"

_bi_encoder = None
_cached_chunks = None
_bm25_index = None


def get_bi_encoder():
    """Load the bi-encoder once, on first vector search."""
    global _bi_encoder
    if _bi_encoder is None:
        from sentence_transformers import SentenceTransformer
        _bi_encoder = SentenceTransformer(BI_ENCODER_MODEL)
    return _bi_encoder


def get_cached_chunks():
    """Load contract chunks once per process."""
    global _cached_chunks
    if _cached_chunks is None:
        _cached_chunks = load_contract_chunks()
    return _cached_chunks


def get_bm25_index(documents):
    """Fit BM25 once; rebuilding it on every query is expensive."""
    global _bm25_index
    if _bm25_index is None:
        index = Index(
            text_fields=["chunk_text"],
            keyword_fields=["contract_id"]
        )
        index.fit(documents)
        _bm25_index = index
    return _bm25_index


def vec_to_str(vector):
    return "[" + ",".join(str(x) for x in vector) + "]"


# --------------------------------------------------
# BM25
# --------------------------------------------------

def run_bm25(query, documents=None, num_results=3):

    if documents is None:
        documents = get_cached_chunks()

    index = get_bm25_index(documents)

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

    query_vector = get_bi_encoder().encode(query)
    vector = vec_to_str(query_vector)

    with connect() as conn:

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
        documents = get_cached_chunks()

    pool_size = max(num_results, 10)
    vector_results = run_vector(query, num_results=pool_size)
    bm25_results = run_bm25(query, documents, num_results=pool_size)

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