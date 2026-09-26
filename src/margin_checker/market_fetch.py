"""Pull market series and write the price tables.

Free, no key (these are what `prices.csv` contains after a run):

- ECB, daily EURUSD. Reference rate, business days, usually the same day.
- World Bank Pink Sheet, monthly Brent, European natural gas, maize.
  The workbook is refreshed in the first days of the next month, so the
  newest row is the previous month.

Optional, skipped with a note when the variable is missing:

- EIA_API_KEY: daily Brent (RBRTE), USD/bbl
- FRED_API_KEY: daily Brent series DCOILBRENTEU
- ENTSOE_SECURITY_TOKEN: day-ahead power prices (XML, hourly)

Container freight and the Baltic Dry Index are licensed. This script
does not call them.

    python -m src.margin_checker.market_fetch
"""

from __future__ import annotations

import csv
import io
import os
import re
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
MARKET_DIR = ROOT / "data" / "market"
CONTRACTS_PATH = ROOT / "data" / "chemical_contracts.csv"

ECB_SERIES = "D.USD.EUR.SP00.A"
ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/"
    + ECB_SERIES
)
WB_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
USER_AGENT = "margin-checker-market-fetch"

# Contract ids are CON-2023-*. January 2023 is the shared signing proxy
# until each contract has its own date.
BASELINE_MONTH = "2023M01"
BASELINE_FX_START = "2023-01-02"
BASELINE_FX_END = "2023-01-06"

RECENT_ECB = 8
RECENT_MONTHS = 8

WB_SERIES = {
    "BRENT": "Crude oil, Brent",
    "NATURAL_GAS_EU": "Natural gas, Europe",
    "MAIZE": "Maize",
}

# Petrochemicals follow Brent. The Pink Sheet has no public naphtha column.
BRENT_PRODUCTS = {
    "polyethylene",
    "high density polyethylene",
    "low density polyethylene",
    "polypropylene",
    "polystyrene",
    "polyethylene terephthalate",
    "pvc resin",
    "benzene",
    "toluene",
    "mixed xylenes",
    "styrene monomer",
    "styrene acrylonitrile",
    "acrylonitrile butadiene styrene",
    "phenol",
    "methanol",
    "bio-naphtha",
    "mtbe",
    "n-butanol",
    "monoethylene glycol",
    "diethylene glycol",
    "vinyl acetate monomer",
    "aniline",
    "caprolactam",
    "adipic acid",
    "formaldehyde",
    "acetone",
    "chloroform",
    "nylon 66",
}
MAIZE_PRODUCTS = {
    "ethanol",
    "glucose syrup 42de",
    "citric acid",
    "lactic acid 88%",
    "glycerin",
    "sorbitol 70%",
    "maltodextrin",
    "gelatin",
    "pla resin",
}

PRICE_FIELDS = [
    "as_of_date",
    "instrument",
    "value",
    "unit",
    "currency",
    "frequency",
    "source",
    "source_series_id",
    "license_status",
]
MAP_FIELDS = [
    "product_name",
    "energy_instrument",
    "raw_material_instrument",
    "freight_instrument",
]
BASELINE_FIELDS = [
    "contract_id",
    "instrument",
    "baseline_date",
    "baseline_value",
    "unit",
    "currency",
    "source",
    "note",
]
INVENTORY_FIELDS = [
    "instrument",
    "what_it_represents",
    "provider",
    "api_or_download_url",
    "frequency",
    "unit",
    "currency",
    "api_key_required",
    "free_for_demo",
    "license_risk",
    "status",
]

INVENTORY = [
    {
        "instrument": "EURUSD",
        "what_it_represents": "US dollar per 1 euro",
        "provider": "ECB",
        "api_or_download_url": "https://data.ecb.europa.eu/help/api/overview",
        "frequency": "daily",
        "unit": "USD/EUR",
        "currency": "USD",
        "api_key_required": "no",
        "free_for_demo": "yes",
        "license_risk": "low",
        "status": "use",
    },
    {
        "instrument": "BRENT",
        "what_it_represents": "Brent crude oil",
        "provider": "World Bank Pink Sheet",
        "api_or_download_url": WB_PAGE,
        "frequency": "monthly",
        "unit": "USD/bbl",
        "currency": "USD",
        "api_key_required": "no",
        "free_for_demo": "yes",
        "license_risk": "low",
        "status": "use",
    },
    {
        "instrument": "NATURAL_GAS_EU",
        "what_it_represents": "European natural gas",
        "provider": "World Bank Pink Sheet",
        "api_or_download_url": WB_PAGE,
        "frequency": "monthly",
        "unit": "USD/mmbtu",
        "currency": "USD",
        "api_key_required": "no",
        "free_for_demo": "yes",
        "license_risk": "low",
        "status": "use",
    },
    {
        "instrument": "MAIZE",
        "what_it_represents": "Maize / corn",
        "provider": "World Bank Pink Sheet",
        "api_or_download_url": WB_PAGE,
        "frequency": "monthly",
        "unit": "USD/t",
        "currency": "USD",
        "api_key_required": "no",
        "free_for_demo": "yes",
        "license_risk": "low",
        "status": "use",
    },
    {
        "instrument": "BRENT_EIA",
        "what_it_represents": "Europe Brent spot, daily",
        "provider": "EIA",
        "api_or_download_url": "https://www.eia.gov/opendata/documentation.php",
        "frequency": "daily",
        "unit": "USD/bbl",
        "currency": "USD",
        "api_key_required": "yes",
        "free_for_demo": "yes_with_free_key",
        "license_risk": "low",
        "status": "needs_key",
    },
    {
        "instrument": "ENERGY_EU",
        "what_it_represents": "European day-ahead electricity",
        "provider": "ENTSO-E",
        "api_or_download_url": "https://web-api.tp.entsoe.eu/api",
        "frequency": "hourly",
        "unit": "EUR/MWh",
        "currency": "EUR",
        "api_key_required": "token",
        "free_for_demo": "yes_after_email_approval",
        "license_risk": "medium",
        "status": "needs_token",
    },
    {
        "instrument": "CONTAINER_FREIGHT",
        "what_it_represents": "Container freight index",
        "provider": "Baltic / FBX / SCFI",
        "api_or_download_url": "https://www.balticexchange.com/en/data-services/Methodology/market-data.html",
        "frequency": "daily_or_weekly",
        "unit": "index",
        "currency": "",
        "api_key_required": "licence",
        "free_for_demo": "no",
        "license_risk": "high",
        "status": "not_free",
    },
    {
        "instrument": "BDI",
        "what_it_represents": "Dry-bulk freight, not containers",
        "provider": "Baltic Exchange",
        "api_or_download_url": "https://www.balticexchange.com/en/data-services/Methodology/market-data.html",
        "frequency": "daily",
        "unit": "index",
        "currency": "",
        "api_key_required": "licence",
        "free_for_demo": "no",
        "license_risk": "high",
        "status": "not_free",
    },
]


def http_get(url, headers=None, timeout=60):
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def month_code_to_date(code):
    """World Bank period `2026M08` -> first day of that month."""
    match = re.fullmatch(r"(\d{4})M(\d{2})", str(code).strip())
    if not match:
        raise ValueError(f"Not a World Bank month code: {code!r}")
    year, month = int(match.group(1)), int(match.group(2))
    return date(year, month, 1).isoformat()


def clean_unit(raw):
    text = str(raw or "").strip().lower()
    text = text.replace("($/", "").replace(")", "").replace("$/", "")
    if text in {"bbl"}:
        return "USD/bbl"
    if text in {"mmbtu"}:
        return "USD/mmbtu"
    if text in {"mt", "t"}:
        return "USD/t"
    return str(raw or "").strip()


def raw_instrument(product_name):
    name = product_name.strip().lower()
    if name in BRENT_PRODUCTS:
        return "BRENT"
    if name in MAIZE_PRODUCTS:
        return "MAIZE"
    return "UNMAPPED"


def parse_ecb_csv(text):
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        period = (row.get("TIME_PERIOD") or "").strip()
        value = (row.get("OBS_VALUE") or "").strip()
        if not period or not value:
            continue
        rows.append(
            {
                "as_of_date": period,
                "instrument": "EURUSD",
                "value": float(value),
                "unit": "USD/EUR",
                "currency": "USD",
                "frequency": "daily",
                "source": "ECB",
                "source_series_id": "EXR." + ECB_SERIES,
                "license_status": "public",
            }
        )
    rows.sort(key=lambda item: item["as_of_date"])
    return rows


def fetch_ecb(start=None, end=None, last_n=None):
    params = []
    if start:
        params.append("startPeriod=" + start)
    if end:
        params.append("endPeriod=" + end)
    if last_n:
        params.append("lastNObservations=" + str(last_n))
    url = ECB_URL + ("?" + "&".join(params) if params else "")
    status, body = http_get(url, headers={"Accept": "text/csv"})
    if status != 200:
        raise RuntimeError(f"ECB HTTP {status}: {body[:200]!r}")
    return parse_ecb_csv(body.decode("utf-8"))


def discover_worldbank_monthly_url():
    status, body = http_get(WB_PAGE)
    if status != 200:
        raise RuntimeError(f"World Bank page HTTP {status}")
    html = body.decode("utf-8", "replace")
    match = re.search(
        r"https://thedocs\.worldbank\.org/[^\"']+CMO-Historical-Data-Monthly\.xlsx",
        html,
    )
    if not match:
        raise RuntimeError("Monthly Pink Sheet link not found on the World Bank page")
    return match.group(0)


def parse_worldbank_monthly(xlsx_bytes):
    workbook = load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    sheet = workbook["Monthly Prices"]
    rows = list(sheet.iter_rows(values_only=True))
    names = list(rows[4])
    units = list(rows[5])
    columns = {}
    for instrument, label in WB_SERIES.items():
        columns[instrument] = names.index(label)

    updated = ""
    if rows[3] and rows[3][0]:
        updated = str(rows[3][0])

    parsed = []
    for row in rows[6:]:
        period = row[0]
        if not period or not re.fullmatch(r"\d{4}M\d{2}", str(period)):
            continue
        as_of = month_code_to_date(str(period))
        for instrument, index in columns.items():
            value = row[index]
            if value in (None, "", "…", "..."):
                continue
            parsed.append(
                {
                    "as_of_date": as_of,
                    "instrument": instrument,
                    "value": float(value),
                    "unit": clean_unit(units[index]),
                    "currency": "USD",
                    "frequency": "monthly",
                    "source": "WORLD_BANK",
                    "source_series_id": WB_SERIES[instrument],
                    "license_status": "public",
                    "_period": str(period),
                    "_updated": updated,
                }
            )
    return parsed


def fetch_worldbank():
    url = discover_worldbank_monthly_url()
    status, body = http_get(url, timeout=90)
    if status != 200:
        raise RuntimeError(f"Pink Sheet HTTP {status}")
    rows = parse_worldbank_monthly(body)
    return url, rows


def probe_note(status, body, ok_note):
    if status == 200:
        return ok_note
    text = body.decode("utf-8", "replace")
    if "API_KEY_MISSING" in text:
        return "API_KEY_MISSING"
    if "api_key is not set" in text:
        return "api_key is not set"
    if status == 401:
        return "token missing or rejected"
    return "HTTP " + str(status)


def probe_gated():
    """One request each. No key means we only learn the rejection."""
    probes = []

    eia_key = os.getenv("EIA_API_KEY", "").strip()
    eia_url = (
        "https://api.eia.gov/v2/petroleum/pri/spt/data/"
        "?frequency=daily&data[0]=value&facets[series][]=RBRTE&length=1"
    )
    if eia_key:
        eia_url += "&api_key=" + eia_key
    status, body = http_get(eia_url)
    probes.append(
        {
            "instrument": "BRENT_EIA",
            "http_status": status,
            "key_present": bool(eia_key),
            "note": probe_note(status, body, "daily Europe Brent"),
        }
    )

    fred_key = os.getenv("FRED_API_KEY", "").strip()
    fred_url = (
        "https://api.stlouisfed.org/fred/series/observations"
        "?series_id=DCOILBRENTEU&file_type=json&limit=1&sort_order=desc"
    )
    if fred_key:
        fred_url += "&api_key=" + fred_key
    status, body = http_get(fred_url)
    probes.append(
        {
            "instrument": "FRED_DCOILBRENTEU",
            "http_status": status,
            "key_present": bool(fred_key),
            "note": probe_note(status, body, "daily Brent"),
        }
    )

    token = os.getenv("ENTSOE_SECURITY_TOKEN", "").strip()
    entsoe_url = (
        "https://web-api.tp.entsoe.eu/api?documentType=A44"
        "&in_Domain=10Y1001A1001A82H&out_Domain=10Y1001A1001A82H"
        "&periodStart=202609240000&periodEnd=202609250000"
    )
    if token:
        entsoe_url += "&securityToken=" + token
    status, body = http_get(entsoe_url)
    probes.append(
        {
            "instrument": "ENERGY_EU",
            "http_status": status,
            "key_present": bool(token),
            "note": probe_note(status, body, "day-ahead prices"),
        }
    )
    return probes


def load_contracts():
    with CONTRACTS_PATH.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def product_map_rows(contracts):
    products = sorted({row["product_name"] for row in contracts})
    return [
        {
            "product_name": product,
            "energy_instrument": "NATURAL_GAS_EU",
            "raw_material_instrument": raw_instrument(product),
            "freight_instrument": "UNMAPPED",
        }
        for product in products
    ]


def baseline_rows(contracts, points):
    """One baseline per contract and instrument, January 2023 proxy."""
    by_instrument = {}
    for row in points:
        by_instrument.setdefault(row["instrument"], row)

    rows = []
    for contract in contracts:
        instruments = ["EURUSD", "NATURAL_GAS_EU"]
        raw_name = raw_instrument(contract["product_name"])
        if raw_name != "UNMAPPED":
            instruments.append(raw_name)
        for instrument in instruments:
            point = by_instrument.get(instrument)
            if point is None:
                continue
            rows.append(
                {
                    "contract_id": contract["contract_id"],
                    "instrument": instrument,
                    "baseline_date": point["as_of_date"],
                    "baseline_value": point["value"],
                    "unit": point["unit"],
                    "currency": point["currency"],
                    "source": point["source"],
                    "note": "shared_2023_01_proxy",
                }
            )
    return rows


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def recent(rows, limit):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["instrument"], []).append(row)
    kept = []
    for instrument in grouped:
        ordered = sorted(grouped[instrument], key=lambda item: item["as_of_date"])
        kept.extend(ordered[-limit:])
    kept.sort(key=lambda item: (item["instrument"], item["as_of_date"]))
    return kept


def value_on_period(rows, instrument, period):
    matches = [
        row for row in rows
        if row["instrument"] == instrument and row.get("_period") == period
    ]
    if not matches:
        raise RuntimeError(f"No {instrument} row for {period}")
    return matches[0]


def main():
    print("ECB EURUSD (no key)...")
    fx_recent = fetch_ecb(last_n=RECENT_ECB)
    fx_baseline = fetch_ecb(start=BASELINE_FX_START, end=BASELINE_FX_END)
    if not fx_recent or not fx_baseline:
        raise RuntimeError("ECB returned no observations")
    print(
        f"  latest {fx_recent[-1]['as_of_date']} = {fx_recent[-1]['value']} USD/EUR"
        f"  |  baseline {fx_baseline[0]['as_of_date']} = {fx_baseline[0]['value']}"
    )

    print("World Bank Pink Sheet (no key)...")
    wb_url, wb_rows = fetch_worldbank()
    updated = wb_rows[0].get("_updated", "") if wb_rows else ""
    print(f"  {wb_url}")
    print(f"  {updated}")
    for instrument in WB_SERIES:
        series = [row for row in wb_rows if row["instrument"] == instrument]
        last = series[-1]
        print(
            f"  {instrument} latest {last['as_of_date']} = {last['value']} {last['unit']}"
        )

    prices = recent(fx_recent, RECENT_ECB) + recent(wb_rows, RECENT_MONTHS)
    baselines_points = [fx_baseline[0]]
    for instrument in WB_SERIES:
        baselines_points.append(value_on_period(wb_rows, instrument, BASELINE_MONTH))

    contracts = load_contracts()
    mapping = product_map_rows(contracts)
    baselines = baseline_rows(contracts, baselines_points)

    write_csv(MARKET_DIR / "api_inventory.csv", INVENTORY_FIELDS, INVENTORY)
    write_csv(MARKET_DIR / "prices.csv", PRICE_FIELDS, prices)
    write_csv(MARKET_DIR / "product_index_map.csv", MAP_FIELDS, mapping)
    write_csv(MARKET_DIR / "index_baselines.csv", BASELINE_FIELDS, baselines)

    print("Gated sources (expect failure without a key)...")
    probes = probe_gated()
    write_csv(
        MARKET_DIR / "source_probe.csv",
        ["instrument", "http_status", "key_present", "note"],
        probes,
    )
    for probe in probes:
        print(
            f"  {probe['instrument']}: HTTP {probe['http_status']}"
            f" key={probe['key_present']}"
        )

    mapped = sum(1 for row in mapping if row["raw_material_instrument"] != "UNMAPPED")
    print(
        f"Wrote prices={len(prices)} map={len(mapping)}"
        f" (raw mapped {mapped}) baselines={len(baselines)}"
    )


if __name__ == "__main__":
    main()
