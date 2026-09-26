"""Join the daily contract price onto the structured contract table."""

DAILY_PRICE_COLUMNS = (
    "indicative_price_per_ton",
    "financing_per_ton",
    "logistics_amount",
    "logistics_currency",
    "energy_ratio",
    "raw_ratio",
    "raw_rule",
    "rate_rule",
    "calculation_rule",
    "demurrage_amount",
)


def attach_daily_prices(contracts, prices):
    """Left-join today's price columns onto the contract rows."""
    import pandas as pd

    if prices is None or len(prices) == 0 or "contract_id" not in getattr(prices, "columns", []):
        return contracts
    keep = ["contract_id"] + [
        name for name in DAILY_PRICE_COLUMNS if name in prices.columns
    ]
    slim = prices[keep].drop_duplicates("contract_id")
    return contracts.merge(slim, on="contract_id", how="left")
