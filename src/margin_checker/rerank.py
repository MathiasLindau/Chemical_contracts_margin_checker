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


def _as_score_list(raw_scores, expected):
    if raw_scores is None:
        return [None] * expected

    if hasattr(raw_scores, "tolist"):
        raw_scores = raw_scores.tolist()

    if isinstance(raw_scores, (int, float)):
        raw_scores = [float(raw_scores)]

    scores = [float(score) for score in raw_scores]
    if len(scores) != expected:
        raise ValueError(
            f"Reranker returned {len(scores)} scores for {expected} candidates."
        )
    return scores


def rerank_results(query, candidates, top_k=3, reranker=None):
    """
    Reorder RRF candidates by Cross-Encoder(query, chunk) relevance.

    Preserves the original RRF value in ``score`` and adds
    ``reranker_score``. Returns the top_k documents.

    If the reranker fails, RRF order is kept so the app still answers.
    """

    if not candidates:
        return []

    pairs = [
        [query, candidate.get("chunk_text") or ""]
        for candidate in candidates
    ]

    try:
        encoder = reranker if reranker is not None else get_reranker()
        raw_scores = encoder.predict(pairs)
        scores = _as_score_list(raw_scores, len(candidates))
    except Exception:
        scores = [None] * len(candidates)

    ranked = []
    for candidate, score in zip(candidates, scores):
        item = dict(candidate)
        item["reranker_score"] = score
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            item["reranker_score"] is not None,
            item["reranker_score"] if item["reranker_score"] is not None else 0.0,
        ),
        reverse=True,
    )

    return ranked[:top_k]
