# src/margin_checker/sources.py

import re


CONTRACT_ID_RE = re.compile(r"CON-\d{4}-\d{4}", re.IGNORECASE)


def _normalize_id(contract_id):
    if not contract_id:
        return ""
    return str(contract_id).strip().upper()


def source_key(source):
    contract_id = _normalize_id(source.get("contract_id"))
    if "chunk_text" in source:
        return ("text", contract_id, source.get("chunk_text") or "")
    return ("structured", contract_id, "")


RERANK_TABLE_NOTE = (
    "Cross-encoder rerank applies to contract-text search. "
    "This answer came from the price table."
)


def source_label(source, index):
    """Expander title. RRF and reranker scores appear only when a text chunk has them."""
    source = source or {}
    contract_id = source.get("contract_id")
    if "score" in source and contract_id:
        parts = [f"RRF: {float(source['score']):.5f}"]
        reranker_score = source.get("reranker_score")
        if reranker_score is not None:
            parts.append(f"Reranker: {float(reranker_score):.4f}")
        return f"{contract_id} ({', '.join(parts)})"
    if contract_id:
        return f"{contract_id} (structured)"
    return f"Structured Result {index}"


def rerank_applies_to_chunks(sources):
    return any(isinstance(source, dict) and "chunk_text" in source for source in (sources or []))


def cited_contract_ids(answer):
    seen = []
    found = set()
    for match in CONTRACT_ID_RE.findall(answer or ""):
        contract_id = _normalize_id(match)
        if contract_id and contract_id not in found:
            found.add(contract_id)
            seen.append(contract_id)
    return seen


def split_primary_secondary(answer, sources):
    """
    Primary = retrieved sources for contract IDs mentioned in the answer.
    Structured rows are preferred over text chunks for the same ID.
    Secondary = everything else that was retrieved.
    """

    sources = list(sources or [])
    cited = cited_contract_ids(answer)

    primary = []
    used = set()

    for contract_id in cited:
        matches = [
            source for source in sources
            if _normalize_id(source.get("contract_id")) == contract_id
        ]
        structured = [
            source for source in matches
            if "chunk_text" not in source
        ]
        text = [
            source for source in matches
            if "chunk_text" in source
        ]
        for source in structured + text:
            key = source_key(source)
            if key not in used:
                primary.append(source)
                used.add(key)

    secondary = []
    for source in sources:
        key = source_key(source)
        if key not in used:
            secondary.append(source)
            used.add(key)

    return primary, secondary