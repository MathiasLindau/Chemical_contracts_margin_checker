"""Period comparisons on contract_price_history.csv.

A supply-chain question can name any day, month, or year. The calculation
uses only dates that are actually stored. A missing period comes back as a
note, with no invented price.
"""

import html
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from src.margin_checker.daily_prices import load_history_frame
from src.margin_checker.structured import STRUCTURED_ROW_CAP

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "januar": 1, "februar": 2, "maerz": 3, "mai": 5, "juni": 6, "juli": 7,
    "oktober": 10, "dezember": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?:\s+(20\d{2}))?"
)
COMPARE_OPS = {"compare", "comparison", "diff", "difference", "compare_periods"}
PRICE_FIELDS = {
    "indicative_price_per_ton",
    "raw_amount",
    "energy_amount",
    "raw_gap",
    "energy_gap",
    "raw_gap_at_max_volume",
    "uplift_vs_base",
    "financing_per_ton",
    "logistics_amount",
    "base_price",
}
NOT_PROFIT = "This is a movement of the ton price, not a profit margin."
RAW_NOTE = (
    "Negative raw_gap means the raw-material amount is below the contract "
    "percentage at the January 2023 index. Energy_gap uses the gas index the "
    "same way. Financing and logistics are not included. " + NOT_PROFIT
)
FX_NOTE = (
    "EURUSD converts only the logistics trip of USD contracts. The product "
    "price per ton is not converted. A lower EURUSD reduces that USD trip cost. "
    + NOT_PROFIT
)
# A lower cost or a negative price change is green. A higher cost is red.
CHEAPER_COLOR = "#157a3a"
DEARER_COLOR = "#b42318"
ANSWER_OPEN = '<div class="structured-answer" style="overflow-x:auto;max-width:100%;">'
ANSWER_CLOSE = "</div>"
_TABLE_STYLE = "border-collapse:collapse;font-size:14px;width:auto;max-width:100%;"
_TH_STYLE = "text-align:left;padding:4px 10px;border-bottom:2px solid #ccc;white-space:nowrap;"
_TD_STYLE = "text-align:left;padding:4px 10px;border-bottom:1px solid #eee;white-space:nowrap;vertical-align:top;"


def _norm(value):
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _blank(value):
    return _norm(value) in {"", "null", "none", "nan"}


def _is_index_name(value):
    """January 2023 and index_2023 name the raw-material index, not a price day."""
    text = _norm(value).replace("_", " ").replace("-", " ")
    text = " ".join(text.split())
    if not text:
        return False
    if text in {
        "index",
        "index 2023",
        "2023 index",
        "january 2023",
        "januar 2023",
        "jan 2023",
        "january 2023 index",
        "januar 2023 index",
        "jan 2023 index",
        "index january 2023",
        "raw index",
        "raw material index",
    }:
        return True
    if "index" in text and "2023" in text:
        return True
    if text.startswith("january 2023") or text.startswith("januar 2023") or text.startswith("jan 2023"):
        return True
    return False


def numeric_threshold(value):
    """Float threshold, or None when the question did not give a number."""
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def threshold_mask(frame, column, operation, value):
    """Boolean mask for a numeric filter. None when value is not a number."""
    import pandas as pd

    threshold = numeric_threshold(value)
    if threshold is None or column not in frame.columns:
        return None
    series = pd.to_numeric(frame[column], errors="coerce")
    if operation == "filter_above":
        return series > threshold
    return series < threshold


def sort_by_number(frame, column, ascending):
    """Sort a numeric column. Text columns stay in text order."""
    import pandas as pd

    out = frame.copy()
    numeric = pd.to_numeric(out[column], errors="coerce")
    if numeric.notna().any():
        out["_sort_value"] = numeric
    else:
        out["_sort_value"] = out[column]
    out = out.sort_values("_sort_value", ascending=ascending, na_position="last")
    return out.drop(columns="_sort_value")


def _money(value):
    import pandas as pd

    if value is None or pd.isna(value):
        return None
    return round(float(value), 2)


def _rate(value):
    import pandas as pd

    if value is None or pd.isna(value):
        return None
    return round(float(value), 4)


def _days_of(frame):
    if frame is None or len(frame) == 0 or "price_day" not in frame.columns:
        return []
    return sorted({day for day in frame["price_day"].tolist() if day is not None and str(day) != "NaT"})


def _stored_label(days):
    if not days:
        return "none"
    if len(days) <= 12:
        return " ".join(day.isoformat() for day in days)
    months = sorted({day.strftime("%Y-%m") for day in days})
    if len(months) <= 24:
        return " ".join(months)
    return " ".join(str(day.year) for day in days if day.month == 1 and day.day == 1) or " ".join(
        sorted({str(day.year) for day in days})
    )


def _one_day(day):
    return {"label": day.isoformat(), "start": day, "end": day, "note": ""}


def _month_bounds(year, month, note=""):
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return {"label": f"{year:04d}-{month:02d}", "start": start, "end": end, "note": note}


def _year_bounds(year):
    return {"label": str(year), "start": date(year, 1, 1), "end": date(year, 12, 31), "note": ""}


def _year_for_month(month, days):
    years = sorted({day.year for day in days if day.month == month})
    if years:
        return years[-1], ""
    anchor = days[-1].year if days else date.today().year
    return anchor, f"{date(anchor, month, 1).strftime('%B %Y')} was used because the question did not name a year."


def resolve_period(token, days):
    """Turn a period name into an inclusive date range."""
    text = _norm(token)
    if _is_index_name(token) or _is_index_name(text):
        return {
            "label": "January 2023 index",
            "start": None,
            "end": None,
            "note": "January 2023 is the raw-material index, not a price-history period.",
            "index": True,
        }
    if not days:
        return {"label": text or "latest", "start": None, "end": None, "note": "contract_price_history.csv has no price dates."}
    anchor = days[-1]
    if text in {"today", "latest", "latest day", "current", "heute", "jetzt", "aktuell"}:
        return _one_day(anchor)
    if text in {"yesterday", "gestern"}:
        return _one_day(anchor - timedelta(days=1))
    if text in {"previous", "previous day", "previous_day", "vortag", "vorheriger tag", "letzter tag"}:
        if len(days) < 2:
            return {
                "label": "previous",
                "start": None,
                "end": None,
                "note": "contract_price_history.csv stores only " + _stored_label(days) + ". A previous day is not stored.",
            }
        return _one_day(days[-2])
    if text in {"this month", "this_month", "current month", "dieser monat", "diesen monat", "aktueller monat"}:
        return _month_bounds(anchor.year, anchor.month)
    if text in {"last month", "last_month", "previous month", "letzter monat", "letzten monat", "vormonat"}:
        year, month = anchor.year, anchor.month - 1
        if month == 0:
            year, month = year - 1, 12
        return _month_bounds(year, month)
    if text in {"this year", "this_year", "dieses jahr"}:
        return _year_bounds(anchor.year)
    if text in {"last year", "last_year", "letztes jahr", "vorjahr"}:
        return _year_bounds(anchor.year - 1)
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", text):
        return _one_day(date.fromisoformat(text))
    if re.fullmatch(r"20\d{2}-\d{2}", text):
        year, month = int(text[:4]), int(text[5:7])
        return _month_bounds(year, month)
    if re.fullmatch(r"20\d{2}", text):
        return _year_bounds(int(text))
    for sep in (" to ", " bis ", ".."):
        if sep in text:
            left, right = text.split(sep, 1)
            start = resolve_period(left.strip(), days)
            end = resolve_period(right.strip(), days)
            if start["start"] is None or end["end"] is None:
                return {
                    "label": text,
                    "start": None,
                    "end": None,
                    "note": start["note"] or end["note"] or f"Unrecognised period: {text}",
                }
            return {"label": start["label"] + " to " + end["label"], "start": start["start"], "end": end["end"], "note": ""}
    found = MONTH_PATTERN.findall(text)
    if len(found) == 1:
        month = MONTHS[found[0][0]]
        if found[0][1]:
            year, note = int(found[0][1]), ""
        else:
            year, note = _year_for_month(month, days)
        return _month_bounds(year, month, note)
    return {"label": text, "start": None, "end": None, "note": f"Unrecognised period: {token}"}


def _find_months(text):
    found = []
    for name, year in MONTH_PATTERN.findall(text):
        found.append((MONTHS[name], int(year) if year else None))
    return found


def _asks_period(text):
    phrases = (
        "yesterday", "gestern", "previous day", "vortag", "last month", "letzter monat",
        "letzten monat", "vormonat", "last year", "letztes jahr", "vorjahr", "this month",
        "dieser monat", "monatsmittel",
    )
    if any(phrase in text for phrase in phrases):
        return True
    compared = any(word in text for word in (" vs ", " versus ", "compared", "differenz", "difference", "gegenueber"))
    if re.search(r"\b20\d{2}\b", text) and compared:
        return True
    if _find_months(text) and any(word in text for word in ("average", "durchschnitt", "mean", "mittel", " vs ", "versus", "compared", "differenz", "difference", "gegenueber")):
        return True
    if len(_iso_dates(text)) >= 2:
        return True
    return False


def _iso_dates(text):
    return re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)


def _asks_raw_index(text):
    """Raw material against the 2023 index, even without the word customer."""
    has_raw = "raw" in text or "rohstoff" in text
    has_index = "index" in text or "2023" in text
    return has_raw and has_index


def _asks_fx(text):
    if "eurusd" in text or "exchange rate" in text or "wechselkurs" in text:
        return True
    pair = ("eur" in text and "usd" in text) or "eur to usd" in text
    topic = any(word in text for word in ("logistic", "freight", "exchange", " fx ", "trip"))
    return pair and topic


def _asks_customer_raw_saving(text):
    has_customer = "customer" in text or "kunde" in text
    has_raw = "raw" in text or "rohstoff" in text
    has_save = any(word in text for word in ("save", "saving", "cost", "kosten", "index"))
    return has_customer and has_raw and has_save


def _asks_raw_pattern(text):
    has_split = any(word in text for word in ("maize", "brent", "mais"))
    has_raw = any(word in text for word in ("raw", "adder", "rohstoff"))
    return has_split and has_raw


def _asks_open_cost_scan(text):
    """Vague cost questions. A named customer, index, or FX question is handled earlier."""
    phrases = (
        "where can we",
        "wo koennen wir",
        "save money",
        "cost saving",
        "cost savings",
        "kosten senken",
        "geld sparen",
        "where to save",
    )
    if any(phrase in text for phrase in phrases):
        return True
    words = text.split()
    if len(words) <= 8 and any(word in text for word in ("cost", "kosten", "saving", "sparen", "margin", "marge")):
        return True
    return False


def looks_open(query):
    """True only for a vague cost question. Other wording keeps its own rule."""
    return _asks_open_cost_scan(" " + _norm(query) + " ")


def needs_history(query):
    """True when the price history can answer, even if the router picked contract text."""
    return prepare_history_spec(query, {}) is not None


def _fill_periods(text, spec):
    if _blank(spec.get("baseline_period")) and ("yesterday" in text or "gestern" in text):
        spec["baseline_period"] = "yesterday"
        if _blank(spec.get("period")):
            spec["period"] = "latest"
    elif _blank(spec.get("baseline_period")) and ("previous day" in text or "vortag" in text):
        spec["baseline_period"] = "previous"
        if _blank(spec.get("period")):
            spec["period"] = "latest"
    elif _blank(spec.get("baseline_period")) and any(phrase in text for phrase in ("last month", "letzter monat", "letzten monat", "vormonat")):
        spec["baseline_period"] = "last_month"
        if _blank(spec.get("period")):
            spec["period"] = "this_month"
    elif _blank(spec.get("baseline_period")) and any(phrase in text for phrase in ("last year", "letztes jahr", "vorjahr")):
        spec["baseline_period"] = "last_year"
        if _blank(spec.get("period")):
            spec["period"] = "this_year"
    months = _find_months(text)
    if len(months) >= 2 and (_blank(spec.get("period")) or _blank(spec.get("baseline_period"))):
        first, second = months[0], months[1]
        first_token = _month_token(first)
        second_token = _month_token(second)
        if _blank(spec.get("period")) and not _is_index_name(first_token):
            spec["period"] = first_token
        if _blank(spec.get("baseline_period")) and not _is_index_name(second_token):
            spec["baseline_period"] = second_token
    years = re.findall(r"\b(20\d{2})\b", text)
    if len(months) < 2 and len(years) >= 2 and (_blank(spec.get("period")) or _blank(spec.get("baseline_period"))):
        if _blank(spec.get("period")):
            spec["period"] = years[0]
        if _blank(spec.get("baseline_period")):
            spec["baseline_period"] = years[1]
    elif len(months) == 1 and _blank(spec.get("period")) and _blank(spec.get("baseline_period")):
        token = _month_token(months[0])
        if not _is_index_name(token):
            spec["period"] = token
    if _blank(spec.get("aggregation")) and any(word in text for word in ("average", "durchschnitt", "mean", "mittel")):
        spec["aggregation"] = "mean"
    if _blank(spec.get("group_by")) and "customer" in text and _blank(spec.get("product_name")):
        spec["group_by"] = "customer_name"
    current = _norm(spec.get("field"))
    asks_base = "base price" in text or "basispreis" in text
    if current not in PRICE_FIELDS or (current == "base_price" and not asks_base):
        spec["field"] = "indicative_price_per_ton"


def _month_token(pair):
    month, year = pair
    names = [name for name, number in MONTHS.items() if number == month]
    names.sort(key=len, reverse=True)
    label = names[0] if names else f"{month:02d}"
    if year:
        return f"{label} {year}"
    return label


def prepare_history_spec(query, specification):
    """Return a history specification, or None when the latest-day table can answer."""
    spec = dict(specification or {})
    text = " " + _norm(query) + " "
    operation = _norm(spec.get("operation"))
    if operation in COMPARE_OPS:
        spec["operation"] = "compare_periods"
    if _asks_fx(text):
        spec["operation"] = "compare_periods"
        spec["field"] = "eurusd"
        spec["period"] = "latest"
        spec["baseline_period"] = "index_2023"
        spec["group_by"] = "currency"
        return spec
    if _asks_customer_raw_saving(text):
        spec["operation"] = "bottom_n"
        spec["field"] = "raw_gap_at_max_volume" if "volume" in text else "raw_gap"
        spec["group_by"] = "customer_name"
        if _is_index_name(spec.get("baseline_period")):
            spec["baseline_period"] = None
        if _blank(spec.get("period")) or _is_index_name(spec.get("period")):
            dates = _iso_dates(text)
            spec["period"] = dates[-1] if dates else "latest"
        if _blank(spec.get("n")):
            spec["n"] = 8
        return spec
    if _asks_raw_pattern(text):
        spec["operation"] = "period_stats"
        spec["period"] = spec.get("period") if not _blank(spec.get("period")) else "latest"
        if _is_index_name(spec.get("period")):
            spec["period"] = "latest"
        spec["field"] = "raw_gap"
        spec["group_by"] = "raw_instrument"
        if _is_index_name(spec.get("baseline_period")):
            spec["baseline_period"] = None
        return spec
    if _asks_raw_index(text):
        dates = _iso_dates(text)
        spec["operation"] = "cost_scan"
        spec["field"] = "indicative_price_per_ton"
        if len(dates) >= 2:
            spec["baseline_period"] = dates[0]
            spec["period"] = dates[1]
        else:
            spec["period"] = "latest"
            spec["baseline_period"] = "previous"
        return spec
    dates = _iso_dates(text)
    if len(dates) >= 2:
        spec["operation"] = "compare_periods"
        spec["baseline_period"] = dates[0]
        spec["period"] = dates[1]
        spec["field"] = "indicative_price_per_ton"
        return spec
    if _asks_open_cost_scan(text) or operation == "cost_scan":
        spec["operation"] = "cost_scan"
        spec["field"] = "indicative_price_per_ton"
        spec["period"] = "latest"
        spec["baseline_period"] = "previous"
        return spec
    period_requested = (
        _asks_period(text)
        or not _blank(spec.get("period"))
        or not _blank(spec.get("baseline_period"))
        or spec.get("operation") in {"compare_periods", "period_stats"}
    )
    if not period_requested:
        return None
    _fill_periods(text, spec)
    if spec.get("operation") not in {"top_n", "bottom_n", "compare_periods", "period_stats"}:
        spec["operation"] = "compare_periods" if not _blank(spec.get("baseline_period")) else "period_stats"
    if _blank(spec.get("period")) and _blank(spec.get("baseline_period")):
        spec["period"] = "latest"
        spec["baseline_period"] = "previous"
        spec["history_default"] = (
            "No period was named. The latest stored day is compared with the previous stored day."
        )
    return spec


def _with_days(frame):
    import pandas as pd

    out = frame.copy()
    if "price_date" in out.columns:
        out["price_day"] = pd.to_datetime(out["price_date"], errors="coerce").dt.date
    else:
        out["price_day"] = None
    return out


def _add_metrics(frame):
    import pandas as pd

    out = frame.copy()
    for column in (
        "indicative_price_per_ton", "base_price", "raw_amount", "energy_amount",
        "raw_adder_percentage", "energy_adder_percentage", "financing_per_ton",
        "logistics_amount", "max_monthly_volume_tons", "logistics_eur_per_trip",
    ):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    if "raw_adder_percentage" not in out.columns and "raw_material_adder_percentage" in out.columns:
        out["raw_adder_percentage"] = pd.to_numeric(out["raw_material_adder_percentage"], errors="coerce")
    if {"raw_amount", "base_price", "raw_adder_percentage"} <= set(out.columns):
        out["raw_gap"] = (out["raw_amount"] - out["base_price"] * out["raw_adder_percentage"] / 100).round(2)
    else:
        out["raw_gap"] = pd.NA
    if {"energy_amount", "base_price", "energy_adder_percentage"} <= set(out.columns):
        out["energy_gap"] = (out["energy_amount"] - out["base_price"] * out["energy_adder_percentage"] / 100).round(2)
    else:
        out["energy_gap"] = pd.NA
    if "max_monthly_volume_tons" in out.columns:
        out["raw_gap_at_max_volume"] = (out["raw_gap"] * out["max_monthly_volume_tons"]).round(2)
    else:
        out["raw_gap_at_max_volume"] = pd.NA
    if {"indicative_price_per_ton", "base_price"} <= set(out.columns):
        out["uplift_vs_base"] = (out["indicative_price_per_ton"] - out["base_price"]).round(2)
    return out


def _attach_volume(frame, contracts):
    if contracts is None or "max_monthly_volume_tons" not in getattr(contracts, "columns", []):
        return frame
    if "contract_id" not in frame.columns:
        return frame
    volume = contracts[["contract_id", "max_monthly_volume_tons"]].drop_duplicates("contract_id")
    out = frame.drop(columns=["max_monthly_volume_tons"], errors="ignore")
    return out.merge(volume, on="contract_id", how="left")


def _filter_frame(frame, spec):
    out = frame
    for column in ("product_name", "customer_name", "currency", "raw_instrument"):
        value = spec.get(column)
        if _blank(value) or column not in out.columns:
            continue
        out = out[out[column].astype(str).str.lower() == _norm(value)]
    return out


def _infer_name(query, frame, column):
    if frame is None or column not in frame.columns:
        return None
    text = _norm(query)
    hits = []
    for name in frame[column].dropna().astype(str).unique():
        if name and _norm(name) in text:
            hits.append(name)
    if len(hits) == 1:
        return hits[0]
    return None


def _latest_slice(frame):
    days = _days_of(frame)
    if not days:
        return frame.iloc[0:0], None
    latest = days[-1]
    return frame[frame["price_day"] == latest], latest


def _as_of_slice(frame, spec):
    """One stored day for a customer ranking. An index name is not that day."""
    token = spec.get("period")
    if _blank(token) or _norm(token) in {
        "latest", "today", "current", "heute", "jetzt", "aktuell", "latest day",
    }:
        latest, day = _latest_slice(frame)
        if day is None:
            return latest, None, "No price date is stored."
        return latest, day, ""
    resolved = resolve_period(token, _days_of(frame))
    if resolved.get("start") is None:
        note = resolved.get("note") or f"No prices are stored for {resolved.get('label')}."
        return frame.iloc[0:0], None, note
    sliced = _slice_period(frame, resolved)
    found = _days_of(sliced)
    if not found:
        stored = _stored_label(_days_of(frame))
        return (
            frame.iloc[0:0],
            None,
            f"No prices are stored for {resolved.get('label')}. Stored dates: {stored}.",
        )
    day = found[-1]
    return sliced[sliced["price_day"] == day], day, ""


def _slice_period(frame, resolved):
    if resolved is None or resolved.get("start") is None:
        return frame.iloc[0:0]
    return frame[(frame["price_day"] >= resolved["start"]) & (frame["price_day"] <= resolved["end"])]


def _note_row(field, note, stored, period=None, baseline=None):
    return {
        "field": field,
        "period": None if period is None else period.get("label"),
        "baseline_period": None if baseline is None else baseline.get("label"),
        "period_value": None,
        "baseline_value": None,
        "change": None,
        "history_note": note,
        "stored_dates": stored,
    }


def _read_csv(path):
    import pandas as pd

    file = Path(path)
    if not file.exists():
        return pd.DataFrame()
    return pd.read_csv(file)


def _fx_levels(api_rows, index_rows):
    import pandas as pd

    if api_rows is None:
        api_rows = _read_csv("data/market/api_price.csv")
    if index_rows is None:
        index_rows = _read_csv("data/market/index_2023.csv")
    current, current_day = None, None
    if api_rows is not None and len(api_rows) and "usd_for_one_eur" in api_rows.columns:
        ordered = api_rows.copy()
        if "pulled_on_date" in ordered.columns:
            ordered = ordered.sort_values("pulled_on_date")
        last = ordered.iloc[-1]
        current = pd.to_numeric(pd.Series([last["usd_for_one_eur"]]), errors="coerce").iloc[0]
        current_day = str(last["pulled_on_date"]) if "pulled_on_date" in ordered.columns else "latest"
    index_value, index_day = None, "2023-01"
    if index_rows is not None and len(index_rows) and "instrument" in index_rows.columns:
        match = index_rows[index_rows["instrument"].astype(str).str.upper() == "EURUSD"]
        if len(match):
            index_value = pd.to_numeric(match["baseline_value"], errors="coerce").iloc[0]
            if "baseline_date" in match.columns:
                index_day = str(match["baseline_date"].iloc[0])
    return current, current_day, index_value, index_day


def _fx_report(frame, api_rows, index_rows):
    current, current_day, index_value, index_day = _fx_levels(api_rows, index_rows)
    trip = 975.0
    if frame is not None and len(frame) and "logistics_eur_per_trip" in frame.columns:
        import pandas as pd

        values = pd.to_numeric(frame["logistics_eur_per_trip"], errors="coerce").dropna()
        if len(values):
            trip = float(values.iloc[0])
    rows = []
    if current is None or index_value is None:
        rows.append({
            "field": "eurusd",
            "history_note": "EURUSD is missing from api_price.csv or index_2023.csv. " + FX_NOTE,
        })
    else:
        rows.append({
            "field": "eurusd",
            "period": current_day,
            "period_value": _rate(current),
            "baseline_period": "index " + index_day,
            "baseline_value": _rate(index_value),
            "change": _rate(float(current) - float(index_value)),
            "usd_trip_now": _money(trip * float(current)),
            "usd_trip_at_index": _money(trip * float(index_value)),
            "usd_trip_extra_vs_index": _money(trip * float(current) - trip * float(index_value)),
            "history_note": FX_NOTE,
        })
    if frame is not None and len(frame) and "currency" in frame.columns and "logistics_amount" in frame.columns:
        latest, latest_day = _latest_slice(frame)
        for currency, group in latest.groupby(latest["currency"].astype(str)):
            rows.append({
                "field": "logistics_amount",
                "currency": currency,
                "period": None if latest_day is None else latest_day.isoformat(),
                "period_value": _money(group["logistics_amount"].mean()),
                "n_contracts": int(group["contract_id"].nunique()) if "contract_id" in group.columns else int(len(group)),
                "history_note": "Logistics is a cost per trip, not part of the ton price.",
            })
    return rows


def _customer_gap_rows(frame, spec):
    latest, latest_day, missing = _as_of_slice(frame, spec)
    if latest_day is None:
        return [_note_row("raw_gap", missing or "No price date is stored.", _stored_label(_days_of(frame)))]
    work = latest[latest["raw_gap"].notna() & (latest["raw_gap"] < 0)].copy()
    sort_column = "raw_gap_at_max_volume" if spec.get("field") == "raw_gap_at_max_volume" and work["raw_gap_at_max_volume"].notna().any() else "raw_gap"
    work = work.sort_values(sort_column, ascending=True)
    limit = int(spec.get("n") or 8)
    stored = _stored_label(_days_of(frame))
    note = RAW_NOTE + " Saved dates: " + stored + "."
    if len(_days_of(frame)) < 2:
        note += " Only one price date is stored, so this is today's cross-section."
    rows = []
    for _, item in work.head(limit).iterrows():
        rows.append({
            "field": spec.get("field") or "raw_gap",
            "contract_id": item.get("contract_id"),
            "customer_name": item.get("customer_name"),
            "product_name": item.get("product_name"),
            "currency": item.get("currency"),
            "raw_instrument": item.get("raw_instrument"),
            "period": latest_day.isoformat(),
            "raw_gap_per_ton": _money(item.get("raw_gap")),
            "max_monthly_volume_tons": _money(item.get("max_monthly_volume_tons")),
            "raw_gap_at_max_volume": _money(item.get("raw_gap_at_max_volume")),
            "history_note": note,
        })
    if not rows:
        return [_note_row("raw_gap", "No contract has a raw-material cost below the January 2023 index. " + note, stored)]
    return rows


def _instrument_rows(frame):
    import pandas as pd

    days = _days_of(frame)
    if not days:
        return [_note_row("raw_gap", "No price date is stored.", "none")]
    per_contract = (
        frame.groupby("contract_id", as_index=False)
        .agg(
            raw_instrument=("raw_instrument", "first"),
            currency=("currency", "first"),
            raw_gap=("raw_gap", "mean"),
            energy_gap=("energy_gap", "mean"),
            raw_amount=("raw_amount", "mean"),
            energy_amount=("energy_amount", "mean"),
        )
    )
    latest, latest_day = _latest_slice(frame)
    previous_day = days[-2] if len(days) > 1 else None
    previous = frame[frame["price_day"] == previous_day] if previous_day else frame.iloc[0:0]
    rows = []
    note = RAW_NOTE + " Saved dates: " + _stored_label(days) + "."
    if previous_day is None:
        note += " Only one price date is stored, so this is a cross-section across contracts."
    grouped = per_contract.groupby(["raw_instrument", "currency"], dropna=False)
    for key, group in grouped:
        instrument, currency = key
        change = None
        if previous_day is not None and len(latest):
            now = latest[(latest["raw_instrument"] == instrument) & (latest["currency"] == currency)]["raw_gap"].mean()
            then = previous[(previous["raw_instrument"] == instrument) & (previous["currency"] == currency)]["raw_gap"].mean()
            if pd.notna(now) and pd.notna(then):
                change = _money(now - then)
        rows.append({
            "field": "raw_gap",
            "raw_instrument": instrument,
            "currency": currency,
            "period": None if latest_day is None else latest_day.isoformat(),
            "previous_day": None if previous_day is None else previous_day.isoformat(),
            "n_contracts": int(group["contract_id"].nunique()),
            "n_days": len(days),
            "raw_gap_per_ton_mean": _money(group["raw_gap"].mean()),
            "energy_gap_per_ton_mean": _money(group["energy_gap"].mean()),
            "raw_amount_mean": _money(group["raw_amount"].mean()),
            "energy_amount_mean": _money(group["energy_amount"].mean()),
            "raw_gap_change_vs_previous_day": change,
            "history_note": note,
        })
    rows.sort(key=lambda item: (item["raw_gap_per_ton_mean"] is None, item["raw_gap_per_ton_mean"]))
    return rows


def _choose_how(spec, period, baseline):
    requested = _norm(spec.get("aggregation"))
    if requested in {"mean", "min", "max", "last", "first"}:
        return requested
    spans = []
    for item in (period, baseline):
        if item and item.get("start") and item.get("end"):
            spans.append((item["end"] - item["start"]).days)
    if spans and max(spans) <= 1:
        return "last"
    return "mean"


def _aggregate_contracts(frame, field, how):
    import pandas as pd

    labels = frame.groupby("contract_id", as_index=False).agg(
        customer_name=("customer_name", "first") if "customer_name" in frame.columns else ("contract_id", "first"),
        product_name=("product_name", "first") if "product_name" in frame.columns else ("contract_id", "first"),
        currency=("currency", "first") if "currency" in frame.columns else ("contract_id", "first"),
        raw_instrument=("raw_instrument", "first") if "raw_instrument" in frame.columns else ("contract_id", "first"),
    )
    ordered = frame.sort_values("price_day")
    if how == "last":
        reduced = ordered.groupby("contract_id", as_index=False).tail(1)[["contract_id", field]]
    elif how == "first":
        reduced = ordered.groupby("contract_id", as_index=False).head(1)[["contract_id", field]]
    elif how == "min":
        reduced = ordered.groupby("contract_id", as_index=False)[field].min()
    elif how == "max":
        reduced = ordered.groupby("contract_id", as_index=False)[field].max()
    else:
        reduced = ordered.groupby("contract_id", as_index=False)[field].mean()
    merged = labels.merge(reduced, on="contract_id", how="left")
    merged[field] = pd.to_numeric(merged[field], errors="coerce")
    return merged


def _group_keys(spec, per_contract, field):
    keys = []
    group = spec.get("group_by")
    if not _blank(group) and group in per_contract.columns:
        keys.append(group)
    if (
        field in PRICE_FIELDS
        and "currency" not in keys
        and "currency" in per_contract.columns
        and per_contract["currency"].nunique(dropna=True) > 1
        and _blank(spec.get("currency"))
    ):
        keys.append("currency")
    return keys


def _product_label(group):
    if "product_name" not in group.columns:
        return None
    names = sorted({str(name) for name in group["product_name"].dropna().tolist()})
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return ", ".join(names)
    return None


def _limit_rows(rows, operation, n, value_key):
    def sort_value(item, reverse):
        value = item.get(value_key)
        if value is None:
            return (1, 0)
        return (0, -value if reverse else value)

    if operation == "top_n":
        ordered = sorted(rows, key=lambda item: sort_value(item, True))
        return ordered[: int(n or 8)]
    if operation == "bottom_n":
        ordered = sorted(rows, key=lambda item: sort_value(item, False))
        return ordered[: int(n or 8)]
    if len(rows) <= 12:
        return sorted(rows, key=lambda item: sort_value(item, False))
    ordered = sorted(rows, key=lambda item: sort_value(item, False))
    return ordered[:4] + ordered[-4:]


def _compare_rows(frame, spec, field, query):
    days = _days_of(frame)
    stored = _stored_label(days)
    spec = dict(spec)
    index_note = None
    if _is_index_name(spec.get("baseline_period")):
        spec["baseline_period"] = None
        index_note = "January 2023 is the raw-material index, not a price-history period."
    period = resolve_period(spec.get("period") or "latest", days)
    if period.get("index"):
        index_note = period.get("note") or index_note
    baseline = None
    if not _blank(spec.get("baseline_period")):
        baseline = resolve_period(spec.get("baseline_period"), days)
        if baseline.get("index"):
            index_note = baseline.get("note") or index_note
            baseline = None
    if _blank(spec.get("product_name")):
        inferred = _infer_name(query, frame, "product_name")
        if inferred:
            frame = frame[frame["product_name"].astype(str) == inferred]
            spec = dict(spec)
            spec["product_name"] = inferred
    if len(frame) == 0:
        return [_note_row(field, "No contract matches that product or customer. Stored dates: " + stored, stored, period, baseline)]
    how = _choose_how(spec, period, baseline)
    period_slice = _slice_period(frame, period)
    baseline_slice = _slice_period(frame, baseline) if baseline else frame.iloc[0:0]
    notes = [index_note, spec.get("history_default"), period.get("note"), None if baseline is None else baseline.get("note")]
    if len(period_slice) == 0:
        notes.append(f"No prices are stored for {period.get('label')}. Stored dates: {stored}.")
    if baseline is not None and len(baseline_slice) == 0:
        notes.append(f"No prices are stored for {baseline.get('label')}. Stored dates: {stored}.")
    note = " ".join(item for item in notes if item)
    if field not in frame.columns:
        return [_note_row(field, f"The history table has no {field}. " + note, stored, period, baseline)]
    if len(period_slice) == 0 and (baseline is None or len(baseline_slice) == 0):
        return [_note_row(field, note or "No prices are stored for that period.", stored, period, baseline)]

    def values(slice_frame):
        if len(slice_frame) == 0:
            return slice_frame
        return _aggregate_contracts(slice_frame, field, how)

    left = values(period_slice)
    right = values(baseline_slice) if baseline is not None else None
    if right is None:
        base = left
        value_name = "period_value"
    elif len(left) == 0:
        base = right
        value_name = "baseline_value"
    else:
        import pandas as pd

        side = right[["contract_id", field]].rename(columns={field: "_baseline"})
        base = left.merge(side, on="contract_id", how="outer")
        labels = pd.concat([left, right], ignore_index=True)
        label_columns = [
            column for column in ("customer_name", "product_name", "currency", "raw_instrument")
            if column in labels.columns
        ]
        if label_columns:
            names = labels.groupby("contract_id", as_index=False)[label_columns].first()
            base = base.drop(columns=label_columns, errors="ignore").merge(names, on="contract_id", how="left")
        value_name = "both"
    if len(base) == 0:
        return [_note_row(field, note or "No contracts match.", stored, period, baseline)]
    keys = _group_keys(spec, base, field)
    groups = base.groupby(keys, dropna=False) if keys else [(None, base)]
    rows = []
    for key, group in groups:
        key_values = {}
        if keys:
            key_tuple = key if isinstance(key, tuple) else (key,)
            key_values = dict(zip(keys, key_tuple))
        period_value = group[field].mean() if field in group.columns else None
        baseline_value = group["_baseline"].mean() if "_baseline" in group.columns else None
        if value_name == "baseline_value":
            baseline_value = group[field].mean()
            period_value = None
        change = None
        change_percent = None
        if period_value is not None and baseline_value not in (None,) and baseline is not None:
            import pandas as pd

            if pd.notna(period_value) and pd.notna(baseline_value):
                change = float(period_value) - float(baseline_value)
                if float(baseline_value) != 0:
                    change_percent = change / float(baseline_value) * 100
        row = {
            "field": field,
            "aggregation": how,
            "period": period.get("label"),
            "baseline_period": None if baseline is None else baseline.get("label"),
            "period_value": _money(period_value),
            "baseline_value": _money(baseline_value),
            "change": _money(change),
            "change_percent": _money(change_percent),
            "n_contracts": int(group["contract_id"].nunique()) if "contract_id" in group.columns else int(len(group)),
            "n_days_period": len(_days_of(period_slice)),
            "n_days_baseline": 0 if baseline is None else len(_days_of(baseline_slice)),
            "history_note": (note + " " if note else "") + f"Aggregation is {how}. change = period minus baseline. " + NOT_PROFIT,
        }
        row.update(key_values)
        if "product_name" not in row:
            row["product_name"] = _product_label(group)
        if not keys and "currency" in group.columns and group["currency"].nunique(dropna=True) == 1:
            row["currency"] = group["currency"].iloc[0]
        rows.append(row)
    value_key = "change" if baseline is not None else "period_value"
    return _limit_rows(rows, spec.get("operation"), spec.get("n"), value_key)


def spec_from_model_json(payload, query=""):
    """Accept a rewriter JSON object. Unknown shapes fall back to the cost scan."""
    if not isinstance(payload, dict):
        return {
            "operation": "cost_scan",
            "field": "indicative_price_per_ton",
            "period": "latest",
            "baseline_period": "previous",
        }
    if _norm(payload.get("operation")) == "cost_scan" or _norm(payload.get("intent")) == "cost_scan":
        return {
            "operation": "cost_scan",
            "field": "indicative_price_per_ton",
            "period": "latest",
            "baseline_period": "previous",
        }
    prepared = prepare_history_spec(query, payload)
    if prepared is not None:
        return prepared
    return {
        "operation": "cost_scan",
        "field": "indicative_price_per_ton",
        "period": "latest",
        "baseline_period": "previous",
    }


def _mark(rows, section):
    marked = []
    for row in rows:
        item = dict(row)
        item["section"] = section
        marked.append(item)
    return marked


def _cost_scan(frame, query, spec=None):
    """Ton price between two stored days, plus the raw-material gap."""
    spec = spec or {}
    period = spec.get("period") or "latest"
    baseline = spec.get("baseline_period") or "previous"
    price_spec = {
        "field": "indicative_price_per_ton",
        "period": period,
        "baseline_period": baseline,
        "group_by": "contract_id",
        "n": 5,
    }
    fell = _compare_rows(frame, dict(price_spec, operation="bottom_n"), "indicative_price_per_ton", query)
    rose = _compare_rows(frame, dict(price_spec, operation="top_n"), "indicative_price_per_ton", query)
    fell = [row for row in fell if row.get("change") is not None and row["change"] < 0]
    rose = [row for row in rose if row.get("change") is not None and row["change"] > 0]
    has_change = any(row.get("change") is not None for row in fell + rose)
    if has_change:
        price_rows = _mark(fell, "price_fell_vs_previous_day") + _mark(rose, "price_rose_vs_previous_day")
    else:
        stored = _stored_label(_days_of(frame))
        price_rows = [{
            "section": "price_vs_history",
            "field": "indicative_price_per_ton",
            "period": period,
            "baseline_period": baseline,
            "change": None,
            "stored_dates": stored,
            "history_note": (
                "Today's price cannot be compared with an earlier day because that day is not stored. "
                "Saved dates: " + stored + ". The raw-material gap versus the January 2023 index is the cost signal. "
                + NOT_PROFIT
            ),
        }]
    raw_rows = _mark(
        _customer_gap_rows(frame, {"field": "raw_gap_at_max_volume", "n": 5}),
        "raw_material_below_index",
    )
    pattern_rows = _mark(_instrument_rows(frame), "raw_instrument")
    rows = price_rows + raw_rows + pattern_rows
    if rows:
        intro = (
            "Open cost scan. The ton-price change uses " + str(period) + " minus " + str(baseline) + ". "
            "A negative raw_gap is a raw-material cost below the January 2023 index. " + NOT_PROFIT
        )
        rows[0]["history_note"] = intro + " " + str(rows[0].get("history_note") or "")
        rows[0]["scan"] = "cost_saving"
    return rows


_SECTION_LABELS = {
    "price_fell_vs_previous_day": "Ton price fell versus the previous stored day",
    "price_rose_vs_previous_day": "Ton price rose versus the previous stored day",
    "raw_material_below_index": "Raw material below the January 2023 index",
    "raw_instrument": "Raw-material pattern",
    "price_vs_history": "Ton price versus the previous stored day",
}


def _shown(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "nat"}:
        return None
    return text


_FIELD_HEADER = {
    "indicative_price_per_ton": "Ton price",
    "base_price": "Base price",
    "price_change": "Change",
    "uplift_vs_base": "Versus base",
    "raw_gap": "Raw gap",
    "raw_gap_at_max_volume": "Volume gap",
    "energy_gap": "Energy gap",
    "energy_amount": "Energy",
    "raw_amount": "Raw amount",
    "financing_per_ton": "Financing",
    "logistics_amount": "Trip cost",
    "eurusd": "EURUSD",
    "max_monthly_volume_tons": "Volume",
    "breach_penalty_amount": "Penalty",
}
_GAP_FIELDS = {"raw_gap", "raw_gap_at_max_volume", "energy_gap"}
_IDENTITY = (
    ("contract_id", "Contract"),
    ("customer_name", "Customer"),
    ("product_name", "Product"),
    ("currency", "Currency"),
)


def _esc(value):
    return html.escape(str(value), quote=True)


def _parse_number(value):
    shown = _shown(value)
    if shown is None:
        return None
    try:
        number = float(shown)
    except ValueError:
        return None
    if number != number:
        return None
    return number


def _format_number(number):
    text = f"{float(number):.4f}".rstrip("0").rstrip(".")
    if text in {"", "-0"}:
        return "0"
    return text


def _figure(value, colored=False):
    """Bold a key figure. Color a real increase red and a real decrease green."""
    number = _parse_number(value)
    if number is None:
        shown = _shown(value)
        if shown is None:
            return "not stored"
        return f"<strong>{_esc(shown)}</strong>"
    text = _esc(_format_number(number))
    if colored and number != 0:
        color = CHEAPER_COLOR if number < 0 else DEARER_COLOR
        return f'<strong style="color:{color}">{text}</strong>'
    return f"<strong>{text}</strong>"


def _text_cell(value):
    shown = _shown(value)
    if shown is None:
        return ""
    return _esc(shown)


def _has(rows, key):
    return any(_shown(row.get(key)) is not None for row in rows)


def _row_kind(row):
    if not isinstance(row, dict) or row.get("error") or row.get("truncated"):
        return "skip"
    if row.get("field") == "eurusd" or row.get("usd_trip_now") is not None:
        return "fx"
    if row.get("field") == "logistics_amount" and not _shown(row.get("contract_id")):
        return "logistics"
    if _shown(row.get("raw_gap_per_ton")) is not None or _shown(row.get("raw_gap_at_max_volume")) is not None:
        return "gap"
    if _shown(row.get("raw_gap_per_ton_mean")) is not None:
        return "instrument"
    if any(key in row for key in ("average", "sum", "count")) and "period_value" not in row:
        return "agg"
    if any(key in row for key in ("period_value", "baseline_value", "change")):
        return "period"
    if _shown(row.get("contract_id")) or _shown(row.get("product_name")):
        return "catalog"
    return "skip"


def _table(headers, body_rows):
    head = "".join(f'<th style="{_TH_STYLE}">{_esc(header)}</th>' for header in headers)
    rendered = []
    for cells in body_rows:
        tds = "".join(f'<td style="{_TD_STYLE}">{cell}</td>' for cell in cells)
        rendered.append(f"<tr>{tds}</tr>")
    return (
        f'<table style="{_TABLE_STYLE}"><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(rendered)}</tbody></table>"
    )


def _identity_headers(rows, with_instrument=False):
    headers = [(key, label) for key, label in _IDENTITY if _has(rows, key)]
    if with_instrument and _has(rows, "raw_instrument"):
        headers.append(("raw_instrument", "Instrument"))
    return headers


def _fill(rows, columns):
    body = []
    for row in rows:
        cells = []
        for key, _label, kind in columns:
            if kind == "text":
                cells.append(_text_cell(row.get(key)))
            elif kind == "figure":
                cells.append(_figure(row.get(key), colored=False))
            else:
                cells.append(_figure(row.get(key), colored=True))
        body.append(cells)
    return body


def _period_table(rows):
    columns = [(key, label, "text") for key, label in _identity_headers(rows)]
    fields = []
    for row in rows:
        field = _norm(row.get("field"))
        if field and field not in fields:
            fields.append(field)
    header = _FIELD_HEADER.get(fields[0], "Value") if len(fields) == 1 else "Value"
    colored_level = len(fields) == 1 and fields[0] in _GAP_FIELDS
    if any("period_value" in row for row in rows):
        columns.append(("period_value", header, "delta" if colored_level else "figure"))
    if any(_shown(row.get("baseline_period")) or _shown(row.get("baseline_value")) for row in rows):
        columns.append(("baseline_value", "Baseline", "figure"))
    if any("change" in row for row in rows):
        columns.append(("change", "Change", "delta"))
    if not columns:
        return None
    return _table([label for _key, label, _kind in columns], _fill(rows, columns))


def _gap_table(rows):
    columns = [(key, label, "text") for key, label in _identity_headers(rows)]
    if any("raw_gap_per_ton" in row for row in rows):
        columns.append(("raw_gap_per_ton", "Raw gap", "delta"))
    if any("max_monthly_volume_tons" in row for row in rows):
        columns.append(("max_monthly_volume_tons", "Volume", "figure"))
    if any("raw_gap_at_max_volume" in row for row in rows):
        columns.append(("raw_gap_at_max_volume", "Volume gap", "delta"))
    if not columns:
        return None
    return _table([label for _key, label, _kind in columns], _fill(rows, columns))


def _instrument_table(rows):
    columns = []
    if _has(rows, "raw_instrument"):
        columns.append(("raw_instrument", "Instrument", "text"))
    if _has(rows, "currency"):
        columns.append(("currency", "Currency", "text"))
    columns.append(("raw_gap_per_ton_mean", "Raw gap", "delta"))
    if any("raw_gap_change_vs_previous_day" in row for row in rows):
        columns.append(("raw_gap_change_vs_previous_day", "Change", "delta"))
    if _has(rows, "n_contracts"):
        columns.append(("n_contracts", "Contracts", "figure"))
    return _table([label for _key, label, _kind in columns], _fill(rows, columns))


def _fx_table(rows):
    columns = [
        ("period_value", "Rate", "figure"),
        ("baseline_value", "January 2023 index", "figure"),
        ("change", "Change", "delta"),
        ("usd_trip_now", "USD trip", "figure"),
        ("usd_trip_at_index", "Trip at index", "figure"),
        ("usd_trip_extra_vs_index", "Trip difference", "delta"),
    ]
    body = []
    for row in rows:
        body.append(["EURUSD"] + [_figure(row.get(key), colored=(kind == "delta")) for key, _label, kind in columns])
    headers = ["Rate pair"] + [label for _key, label, _kind in columns]
    return _table(headers, body)


def _logistics_table(rows):
    columns = []
    if _has(rows, "currency"):
        columns.append(("currency", "Currency", "text"))
    value_key = "period_value" if any("period_value" in row for row in rows) else "logistics_amount"
    columns.append((value_key, "Trip cost", "figure"))
    return _table([label for _key, label, _kind in columns], _fill(rows, columns))


def _agg_label(row):
    field = _FIELD_HEADER.get(_norm(row.get("field")), _shown(row.get("field")) or "Value")
    if "average" in row:
        return f"Average {field}"
    if "sum" in row:
        return f"Sum of {field}"
    return f"Count of {field}"


def _agg_table(rows):
    body = []
    for row in rows:
        if "average" in row:
            value = row.get("average")
        elif "sum" in row:
            value = row.get("sum")
        else:
            value = row.get("count")
        body.append([
            _esc(_agg_label(row)),
            _figure(value, colored=False),
            _figure(row.get("n_contracts"), colored=False),
        ])
    return _table(["Measure", "Value", "Contracts"], body)


def _catalog_columns(rows, query):
    text = _norm(query)
    columns = [(key, label, "text") for key, label in _identity_headers(rows)]
    if _has(rows, "indicative_price_per_ton"):
        columns.append(("indicative_price_per_ton", "Ton price", "figure"))
    elif _has(rows, "price_latest"):
        columns.append(("price_latest", "Ton price", "figure"))
    if _has(rows, "base_price") and ("base" in text or not _has(rows, "indicative_price_per_ton")):
        columns.append(("base_price", "Base price", "figure"))
    if _has(rows, "price_change"):
        columns.append(("price_change", "Change", "delta"))
    if _has(rows, "uplift_vs_base") and any(word in text for word in ("base", "uplift", "basis")):
        columns.append(("uplift_vs_base", "Versus base", "delta"))
    extras = (
        ("financing_per_ton", "Financing", ("financ", "interest", "payment term"), "figure"),
        ("logistics_amount", "Trip cost", ("logistic", "transport", "freight", "trip"), "figure"),
        ("max_monthly_volume_tons", "Volume", ("volume",), "figure"),
        ("min_monthly_volume_tons", "Min volume", ("volume",), "figure"),
        ("breach_penalty_amount", "Penalty", ("penalty", "breach"), "figure"),
        ("_overall_adder", "Overall adder", ("adder",), "figure"),
        ("energy_adder_percentage", "Energy adder", ("energy adder",), "figure"),
        ("raw_material_adder_percentage", "Raw adder", ("raw adder", "rohstoff"), "figure"),
    )
    for key, label, words, kind in extras:
        if _has(rows, key) and any(word in text for word in words):
            columns.append((key, label, kind))
    return columns


def _render_group(kind, rows, query):
    if kind == "gap":
        return _gap_table(rows)
    if kind == "instrument":
        return _instrument_table(rows)
    if kind == "fx":
        return _fx_table(rows)
    if kind == "logistics":
        return _logistics_table(rows)
    if kind == "agg":
        return _agg_table(rows)
    if kind == "period":
        return _period_table(rows)
    if kind == "catalog":
        columns = _catalog_columns(rows, query)
        if not any(kind_name != "text" for _key, _label, kind_name in columns):
            return None
        return _table([label for _key, label, _kind in columns], _fill(rows, columns))
    return None


def _note_html(notes):
    lines = []
    seen = set()
    for note in notes:
        for sentence in re.split(r"(?<=[.])\s+", str(note).strip()):
            sentence = sentence.strip()
            if not sentence or sentence in seen:
                continue
            seen.add(sentence)
            lines.append(f'<p style="margin:4px 0;font-size:14px;">{_esc(sentence)}</p>')
    return "".join(lines)


def combine_hybrid_answer(rendered, clause):
    """Put the number table in front of clause text. Clause text stays as the model wrote it."""
    clause = str(clause or "").strip()
    if rendered and clause:
        return str(rendered) + "\n\n" + clause
    if rendered:
        return str(rendered)
    return clause or None


def split_rendered_answer(answer):
    """Separate the structured HTML table from any following clause text."""
    text = str(answer or "")
    start = text.find(ANSWER_OPEN)
    if start < 0:
        return None, text.strip()
    end = text.find(ANSWER_CLOSE, start)
    if end < 0:
        return None, text.strip()
    end += len(ANSWER_CLOSE)
    html_block = text[start:end]
    prose = (text[:start] + text[end:]).strip()
    return html_block, prose


def render_rows(rows, query=""):
    """Turn calculated rows into an HTML table. The model does not rewrite these numbers."""
    notes = []
    groups = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("truncated") and "match_count" in row:
            shown = row.get("returned") or STRUCTURED_ROW_CAP
            notes.append(f"Showing {shown} of {row.get('match_count')}.")
            continue
        note = _shown(row.get("history_note"))
        if note and note not in notes:
            notes.append(note)
        kind = _row_kind(row)
        if kind == "skip":
            continue
        key = (str(row.get("section") or ""), kind)
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(row)
    blocks = []
    for (section, kind), group in groups:
        visible = group[:STRUCTURED_ROW_CAP]
        if len(group) > STRUCTURED_ROW_CAP:
            notes.append(f"Showing {STRUCTURED_ROW_CAP} of {len(group)}.")
        label = _SECTION_LABELS.get(section)
        table = _render_group(kind, visible, query)
        if table is None:
            continue
        if label:
            blocks.append(f'<p style="margin:8px 0 4px;"><strong>{_esc(label)}</strong></p>')
        blocks.append(table)
    if not blocks and not notes:
        return None
    return ANSWER_OPEN + "".join(blocks) + _note_html(notes) + ANSWER_CLOSE


def run_history_query(history, specification, contracts=None, api_rows=None, index_rows=None, query=""):
    """Answer one history specification from the saved price days."""
    import pandas as pd

    spec = dict(specification or {})
    field = _norm(spec.get("field")) or "indicative_price_per_ton"
    aliases = {
        "price_change": "indicative_price_per_ton",
        "price": "indicative_price_per_ton",
        "ton_price": "indicative_price_per_ton",
        "fx": "eurusd",
        "exchange_rate": "eurusd",
    }
    field = aliases.get(field, field)
    spec["field"] = field
    if history is None or len(getattr(history, "index", [])) == 0:
        frame = load_history_frame()
    else:
        frame = history.copy()
    frame = _attach_volume(frame, contracts)
    if frame is None or len(frame) == 0:
        if field == "eurusd":
            return _fx_report(pd.DataFrame(), api_rows, index_rows)
        return [_note_row(field, "contract_price_history.csv has no rows.", "none")]
    frame = _with_days(_add_metrics(frame))
    if spec.get("operation") == "cost_scan":
        return _cost_scan(frame, query, spec)
    if field == "eurusd":
        return _fx_report(frame, api_rows, index_rows)
    frame = _filter_frame(frame, spec)
    if len(frame) == 0:
        return [_note_row(field, "No contract matches that product, customer, or currency.", _stored_label(_days_of(_with_days(history if history is not None else frame))))]
    asked = " " + _norm(query) + " "
    if _asks_customer_raw_saving(asked):
        spec["group_by"] = "customer_name"
        spec["operation"] = "bottom_n"
        if "volume" in asked:
            field = "raw_gap_at_max_volume"
        elif field not in {"raw_gap", "raw_gap_at_max_volume"}:
            field = "raw_gap"
        spec["field"] = field
        if _blank(spec.get("n")):
            spec["n"] = STRUCTURED_ROW_CAP
    ranking = spec.get("group_by") == "customer_name" and field in {"raw_gap", "raw_gap_at_max_volume"}
    if _is_index_name(spec.get("baseline_period")) and (
        ranking or spec.get("group_by") == "raw_instrument"
    ):
        spec["baseline_period"] = None
    if ranking and (_blank(spec.get("period")) or _is_index_name(spec.get("period"))):
        dates = _iso_dates(asked)
        spec["period"] = dates[-1] if dates else "latest"
    if spec.get("group_by") == "raw_instrument" and _is_index_name(spec.get("period")):
        spec["period"] = "latest"
    if spec.get("group_by") == "raw_instrument" and field in {"raw_gap", "raw_amount", "energy_amount", "energy_gap"} and _blank(spec.get("baseline_period")):
        return _instrument_rows(frame)
    if spec.get("group_by") == "customer_name" and field in {"raw_gap", "raw_gap_at_max_volume"} and _blank(spec.get("baseline_period")):
        return _customer_gap_rows(frame, spec)
    return _compare_rows(frame, spec, field, query)