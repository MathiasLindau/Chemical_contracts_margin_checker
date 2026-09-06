# src/margin_checker/rerank.py

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_reranker = None


def get_reranker():
    """Load the Cross-Encoder once, on first rerank."""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker


def rerank_results(query, candidates, top_k=3, reranker=None):
    """
    Reorder RRF candidates by Cross-Encoder(query, chunk) relevance.

    Preserves the original RRF value in ``score`` and adds
    ``reranker_score``. Returns the top_k documents.
    """

    if not candidates:
        return []

    encoder = reranker if reranker is not None else get_reranker()

    pairs = [
        (query, candidate.get("chunk_text") or "")
        for candidate in candidates
    ]

    raw_scores = encoder.predict(pairs)

    ranked = []
    for candidate, raw_score in zip(candidates, raw_scores):
        item = dict(candidate)
        item["reranker_score"] = float(raw_score)
        ranked.append(item)

    ranked.sort(
        key=lambda item: item["reranker_score"],
        reverse=True
    )

    return ranked[:top_k]
