# src/margin_checker/structured.py

from src.margin_checker.retrieval import match_named_contracts

STRUCTURED_ROW_CAP = 8


def apply_catalog_filters(df, specification, query):
    """Optional product / customer / currency filters from the interpreter."""
    filtered = df

    product = specification.get("product_name")
    customer = specification.get("customer_name")
    currency = specification.get("currency")

    if product:
        filtered = filtered[
            filtered["product_name"].astype(str).str.lower()
            == str(product).strip().lower()
        ]
    if customer:
        filtered = filtered[
            filtered["customer_name"].astype(str).str.lower()
            == str(customer).strip().lower()
        ]
    if currency:
        filtered = filtered[
            filtered["currency"].astype(str).str.lower()
            == str(currency).strip().lower()
        ]

    if len(filtered) == len(df):
        named = match_named_contracts(query, df)
        if named:
            allowed = {item.upper() for item in named}
            filtered = df[
                df["contract_id"].astype(str).str.upper().isin(allowed)
            ]

    return filtered


def cap_structured_rows(rows, match_count=None):
    match_count = match_count if match_count is not None else len(rows)
    capped = rows[:STRUCTURED_ROW_CAP]
    if match_count > STRUCTURED_ROW_CAP:
        capped = [
            {
                "match_count": match_count,
                "returned": len(capped),
                "truncated": True,
            }
        ] + capped
    return capped
