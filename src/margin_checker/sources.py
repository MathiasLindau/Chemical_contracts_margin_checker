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
