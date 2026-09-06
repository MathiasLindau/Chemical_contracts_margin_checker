# src/margin_checker/retrieval.py

from minsearch import Index

from src.margin_checker.db import load_contract_chunks, connect


def normalize_contract_id(contract_id):
    if not contract_id:
        return ""
    return str(contract_id).strip().upper()


def filter_chunks_by_contract_ids(documents, contract_ids):
    """Keep chunks whose contract_id is in the structured-hit set."""
    allowed = {
        normalize_contract_id(contract_id)
        for contract_id in (contract_ids or [])
        if normalize_contract_id(contract_id)
    }
    if not allowed:
        return list(documents or [])
    return [
        document for document in (documents or [])
        if normalize_contract_id(document.get("contract_id")) in allowed
    ]


HYBRID_TEXT_MAX_CONTRACTS = 5


def structured_contract_ids(results):
    """Contract IDs returned by structured CSV retrieval."""
    ids = []
    seen = set()

    def add(contract_id):
        normalized = normalize_contract_id(contract_id)
        if normalized and normalized not in seen:
            seen.add(normalized)
            ids.append(normalized)

    for row in results or []:
        if not isinstance(row, dict):
            continue
        add(row.get("contract_id"))
        extra = row.get("contract_ids") or row.get("sample_contract_ids") or []
        if isinstance(extra, str):
            extra = [extra]
        for contract_id in extra:
            add(contract_id)
    return ids


def match_named_contracts(query, catalog):
    """IDs whose product or customer name appears in the question."""
    question = (query or "").lower()
    if not question or catalog is None or len(catalog) == 0:
        return []

    rows = catalog.to_dict(orient="records")
    rows.sort(
        key=lambda row: max(
            len(str(row.get("product_name") or "")),
            len(str(row.get("customer_name") or "")),
        ),
        reverse=True,
    )
    ids = []
    seen = set()
    for row in rows:
        product = str(row.get("product_name") or "").strip().lower()
        customer = str(row.get("customer_name") or "").strip().lower()
        matched = (
            (len(product) >= 4 and product in question)
            or (len(customer) >= 4 and customer in question)
        )
        contract_id = normalize_contract_id(row.get("contract_id"))
        if matched and contract_id and contract_id not in seen:
            seen.add(contract_id)
            ids.append(contract_id)
    return ids


def hybrid_text_contract_ids(
    structured_results,
    query=None,
    catalog=None,
    corpus_size=None,
    limit=HYBRID_TEXT_MAX_CONTRACTS,
):
    """
    IDs allowed for hybrid text search.

    Empty means skip text search — never search the whole catalog
    for an aggregation or an unfiltered lookup.
    """
    ids = structured_contract_ids(structured_results)
    if not ids:
        ids = match_named_contracts(query, catalog)

    if corpus_size is None and catalog is not None:
        corpus_size = len(catalog)

    if not ids:
        return []
    if corpus_size and len(ids) >= corpus_size:
        return []
    return ids[:limit]


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

def run_bm25(query, documents=None, num_results=3, contract_ids=None):

    if documents is None:
        documents = get_cached_chunks()

    if contract_ids:
        documents = filter_chunks_by_contract_ids(documents, contract_ids)
        if not documents:
            return []
        index = Index(
            text_fields=["chunk_text"],
            keyword_fields=["contract_id"]
        )
        index.fit(documents)
    else:
        if not documents:
            return []
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

def run_vector(query, num_results=3, contract_ids=None):

    query_vector = get_bi_encoder().encode(query)
    vector = vec_to_str(query_vector)

    ids = [
        normalize_contract_id(contract_id)
        for contract_id in (contract_ids or [])
        if normalize_contract_id(contract_id)
    ]

    with connect() as conn:

        if ids:
            placeholders = ",".join(["%s"] * len(ids))
            rows = conn.execute(
                f"""
                SELECT
                    contract_id,
                    chunk_text,
                    1 - (embedding <=> %s::vector) AS score
                FROM contract_chunks
                WHERE contract_id IN ({placeholders})
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector, *ids, vector, num_results)
            ).fetchall()
        else:
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

def run_hybrid(query, documents=None, num_results=3, contract_ids=None):

    if documents is None:
        documents = get_cached_chunks()

    pool_size = max(num_results, 10)
    vector_results = run_vector(
        query,
        num_results=pool_size,
        contract_ids=contract_ids
    )
    bm25_results = run_bm25(
        query,
        documents,
        num_results=pool_size,
        contract_ids=contract_ids
    )

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