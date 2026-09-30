"""Join the daily contract price onto the structured contract table."""

from pathlib import Path

CONTRACT_CANDIDATES = (
    Path("data/market/contract_data.csv"),
    Path("data/chemical_contracts.csv"),
)
PRICE_PATH = Path("data/market/contract_price.csv")
HISTORY_PATH = Path("data/market/contract_price_history.csv")

DAILY_PRICE_COLUMNS = (
    "price_date",
    "indicative_price_per_ton",
    "financing_per_ton",
    "logistics_amount",
    "logistics_currency",
    "energy_amount",
    "raw_amount",
    "energy_ratio",
    "raw_ratio",
    "raw_instrument",
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
    slim = prices[keep]
    if "price_date" in slim.columns:
        slim = slim.sort_values("price_date")
    slim = slim.drop_duplicates("contract_id", keep="last")
    return contracts.merge(slim, on="contract_id", how="left")


def contract_table_path():
    for path in CONTRACT_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError(
        "missing contract table. Looked for data/market/contract_data.csv "
        "and data/chemical_contracts.csv"
    )


def load_structured_frame(contract_path=None, price_path=None):
    """Contract rows plus today's price columns when contract_price.csv exists."""
    import pandas as pd

    path = Path(contract_path) if contract_path else contract_table_path()
    frame = pd.read_csv(path)
    prices = Path(price_path) if price_path else PRICE_PATH
    if prices.exists():
        frame = attach_daily_prices(frame, pd.read_csv(prices))
    return frame


def load_price_history(path=None):
    """Every saved day from contract_price_history.csv. Empty frame if missing."""
    import pandas as pd

    history_path = Path(path) if path else HISTORY_PATH
    if not history_path.exists():
        return pd.DataFrame()
    return pd.read_csv(history_path)


def load_history_frame(history_path=None, contract_path=None):
    """History rows plus monthly volume from the contract table.

    Volume is not in the price history. Cost questions that use the maximum
    monthly volume need it beside the daily price.
    """
    import pandas as pd

    frame = load_price_history(history_path)
    if frame is None or len(frame) == 0 or "contract_id" not in frame.columns:
        return frame
    frame = frame.copy()
    if "raw_adder_percentage" not in frame.columns and "raw_material_adder_percentage" in frame.columns:
        frame["raw_adder_percentage"] = frame["raw_material_adder_percentage"]
    path = Path(contract_path) if contract_path else None
    if path is None:
        try:
            path = contract_table_path()
        except FileNotFoundError:
            path = None
    if path is None or not path.exists():
        return frame
    contracts = pd.read_csv(path)
    if "max_monthly_volume_tons" not in contracts.columns or "contract_id" not in contracts.columns:
        return frame
    volume = contracts[["contract_id", "max_monthly_volume_tons"]].drop_duplicates("contract_id")
    frame = frame.drop(columns=["max_monthly_volume_tons"], errors="ignore")
    return frame.merge(volume, on="contract_id", how="left")


def _history_dates(history):
    if history is None or len(history) == 0 or "price_date" not in getattr(history, "columns", []):
        return []
    dates = {
        str(value)
        for value in history["price_date"].tolist()
        if str(value) not in {"", "nan", "None"}
    }
    return sorted(dates)


def resolve_compare_to(dates, compare_to):
    """Earlier side of a comparison: a history date, the contract base, or a gap note."""
    token = str(compare_to or "previous").strip().lower()
    stored = " ".join(dates) if dates else "no price date"
    one_day = (
        "contract_price_history.csv stores only "
        + stored
        + ". A change versus an earlier day needs another saved API day."
    )
    if token in {"base", "base_price", "contract_base"}:
        return "base", ""
    if token in {"previous", "yesterday", "prior", "last", "none", "null"}:
        if len(dates) < 2:
            return None, one_day
        return dates[-2], ""
    if token in {"earliest", "first", "oldest"}:
        if len(dates) < 2:
            return None, one_day
        return dates[0], ""
    if token in dates:
        return token, ""
    return None, (
        "The requested date is not in contract_price_history.csv. Stored dates: "
        + stored
        + "."
    )


def attach_history_comparison(contracts, history, compare_to="previous"):
    """Add the ton-price movement versus an earlier history day or the contract base.

    price_change is the latest indicative price minus the earlier price.
    uplift_vs_base is today's indicative price minus base_price.
    Neither figure is a profit margin.
    """
    import pandas as pd

    frame = contracts.copy()
    dates = _history_dates(history)
    target, note = resolve_compare_to(dates, compare_to)
    frame["history_dates"] = " ".join(dates)
    frame["history_note"] = note

    latest_date = dates[-1] if dates else None
    if latest_date is not None:
        latest = history.copy()
        latest["price_date"] = latest["price_date"].astype(str)
        latest = (
            latest.loc[latest["price_date"] == latest_date, ["contract_id", "indicative_price_per_ton"]]
            .drop_duplicates("contract_id", keep="last")
            .rename(columns={"indicative_price_per_ton": "price_latest"})
        )
        latest["price_date_latest"] = latest_date
        frame = frame.merge(latest, on="contract_id", how="left")
    else:
        frame["price_latest"] = pd.NA
        frame["price_date_latest"] = pd.NA

    if target == "base":
        if "indicative_price_per_ton" in frame.columns:
            frame["price_latest"] = frame["indicative_price_per_ton"]
        if "price_date" in frame.columns:
            frame["price_date_latest"] = frame["price_date"]
        frame["price_earlier"] = frame["base_price"] if "base_price" in frame.columns else pd.NA
        frame["price_date_earlier"] = "base_price"
        frame["history_note"] = ""
    elif target is None:
        frame["price_earlier"] = pd.NA
        frame["price_date_earlier"] = pd.NA
    else:
        earlier = history.copy()
        earlier["price_date"] = earlier["price_date"].astype(str)
        earlier = (
            earlier.loc[earlier["price_date"] == target, ["contract_id", "indicative_price_per_ton"]]
            .drop_duplicates("contract_id", keep="last")
            .rename(columns={"indicative_price_per_ton": "price_earlier"})
        )
        earlier["price_date_earlier"] = target
        frame = frame.merge(earlier, on="contract_id", how="left")

    frame["price_latest"] = pd.to_numeric(frame["price_latest"], errors="coerce")
    frame["price_earlier"] = pd.to_numeric(frame["price_earlier"], errors="coerce")
    frame["price_change"] = (frame["price_latest"] - frame["price_earlier"]).round(2)
    earlier_nonzero = frame["price_earlier"].where(frame["price_earlier"] != 0)
    frame["price_change_percent"] = ((frame["price_change"] / earlier_nonzero) * 100).round(2)

    if "base_price" in frame.columns:
        base = pd.to_numeric(frame["base_price"], errors="coerce")
        indicative = frame["price_latest"]
        if "indicative_price_per_ton" in frame.columns:
            indicative = pd.to_numeric(frame["indicative_price_per_ton"], errors="coerce")
            indicative = indicative.fillna(frame["price_latest"])
        frame["uplift_vs_base"] = (indicative - base).round(2)
    else:
        frame["uplift_vs_base"] = pd.NA
    return frame


def history_gap_summary(frame):
    """One explanation row when no earlier history day can be compared."""
    if frame is None or len(frame) == 0 or "price_change" not in frame.columns:
        return None
    if frame["price_change"].notna().any():
        return None
    note = ""
    dates = ""
    if "history_note" in frame.columns:
        note = str(frame["history_note"].iloc[0])
    if "history_dates" in frame.columns:
        dates = str(frame["history_dates"].iloc[0])
    return {
        "field": "price_change",
        "history_dates": dates,
        "history_note": note,
        "n_contracts": int(len(frame)),
    }