"""Print the latest value from sources that answered without a key.

One failed source does not stop the others. Nothing is written.

    python -m src.margin_checker.market_probe
"""

from __future__ import annotations

import csv
import io
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = "margin-checker-market-probe"
TIMEOUT = 30

ECB_SERIES = (
    ("EURUSD", "EXR/D.USD.EUR.SP00.A", "USD/EUR", "business day", "ECB"),
    ("ECB_DEPOSIT", "FM/D.U2.EUR.4F.KR.DFR.LEV", "percent", "when changed", "ECB policy rate"),
    ("EURIBOR_3M", "FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA", "percent", "monthly average", "ECB, not the live EMMI fixing"),
)

WORLD_BANK = (
    ("BRENT_WB", "Crude oil, Brent", "USD/bbl", "raw"),
    ("GAS_EU_WB", "Natural gas, Europe", "USD/mmbtu", "energy"),
    ("MAIZE_WB", "Maize", "USD/t", "raw"),
)


def http_get(url, headers=None):
    request = Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()
    except URLError as exc:
        return 0, str(exc.reason).encode()


def show(category, name, when, value, unit, cadence, note):
    print(
        f"{category:<8} {name:<14} {when:<12} {value:<12} {unit:<12} {cadence:<16} {note}",
        flush=True,
    )


def skip(name, reason):
    print(f"skip     {name:<14} {reason}", flush=True)


def run(name, fetch):
    try:
        fetch()
    except Exception as exc:
        skip(name, exc.__class__.__name__ + ": " + str(exc)[:120])


def ecb_last(flow_key):
    status, body = http_get(
        "https://data-api.ecb.europa.eu/service/data/" + flow_key + "?lastNObservations=1",
        {"Accept": "text/csv"},
    )
    if status != 200:
        raise RuntimeError("HTTP " + str(status))
    row = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))[-1]
    return row["TIME_PERIOD"], row["OBS_VALUE"]


def fetch_ecb():
    for name, flow_key, unit, cadence, note in ECB_SERIES:
        when, value = ecb_last(flow_key)
        show("rate" if name != "EURUSD" else "fx", name, when, value, unit, cadence, note)


def fetch_sofr():
    status, body = http_get("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json")
    if status != 200:
        raise RuntimeError("HTTP " + str(status))
    row = json.loads(body)["refRates"][0]
    show("rate", "SOFR", row["effectiveDate"], str(row["percentRate"]), "percent", "business day", "NY Fed")


def fetch_tbill():
    status, body = http_get(
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
        "v2/accounting/od/avg_interest_rates?sort=-record_date"
        "&filter=security_desc:eq:Treasury%20Bills&page[size]=1"
    )
    if status != 200:
        raise RuntimeError("HTTP " + str(status))
    row = json.loads(body)["data"][0]
    show(
        "rate",
        "US_TBILL_AVG",
        row["record_date"],
        row["avg_interest_rate_amt"],
        "percent",
        "monthly",
        "average coupon on outstanding bills, not a market yield",
    )


def fetch_brent_imf():
    status, body = http_get(
        "https://api.imf.org/external/sdmx/3.0/data/dataflow/"
        "IMF.RES/PCPS/9.0.0/G001.POILBRE.USD.M?startPeriod=2026-01",
        {"Accept": "application/json"},
    )
    if status != 200:
        raise RuntimeError("HTTP " + str(status))
    payload = json.loads(body)
    times = payload["data"]["structures"][0]["dimensions"]["observation"][0]["values"]
    obs = list(payload["data"]["dataSets"][0]["series"].values())[0]["observations"]
    newest = max(range(len(times)), key=lambda index: times[index]["value"])
    show("raw", "BRENT_IMF", times[newest]["value"], obs[str(newest)][0], "USD/bbl", "monthly", "IMF")


def pink_sheet_table(rows):
    """Return header labels and the newest YYYYMmm row."""
    header_index = None
    labels = None
    for index, row in enumerate(rows):
        text = [str(cell).strip() if cell else "" for cell in row]
        if "Crude oil, Brent" in text:
            header_index = index
            labels = text
            break
    if labels is None:
        raise RuntimeError("Pink Sheet header not found")
    last = None
    for row in rows[header_index + 1:]:
        if row and re.fullmatch(r"\d{4}M\d{2}", str(row[0] or "")):
            last = row
    if last is None:
        raise RuntimeError("Pink Sheet has no month rows")
    updated = ""
    if len(rows) > 3 and rows[3] and rows[3][0]:
        updated = str(rows[3][0])
    return labels, last, updated


def fetch_worldbank():
    from openpyxl import load_workbook

    status, page = http_get("https://www.worldbank.org/en/research/commodity-markets")
    if status != 200:
        raise RuntimeError("page HTTP " + str(status))
    match = re.search(
        r"https://thedocs\.worldbank\.org/[^\"']+CMO-Historical-Data-Monthly\.xlsx",
        page.decode("utf-8", "replace"),
    )
    if not match:
        raise RuntimeError("monthly workbook link missing")
    status, blob = http_get(match.group(0))
    if status != 200:
        raise RuntimeError("workbook HTTP " + str(status))
    book = load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    rows = list(book["Monthly Prices"].iter_rows(values_only=True))
    labels, last, updated = pink_sheet_table(rows)
    for name, label, unit, category in WORLD_BANK:
        if label not in labels:
            skip(name, "column missing")
            continue
        show(category, name, str(last[0]), str(last[labels.index(label)]), unit, "monthly", updated or "World Bank")


def probe():
    print(
        f"{'group':<8} {'series':<14} {'as_of':<12} {'value':<12} {'unit':<12} {'cadence':<16} note",
        flush=True,
    )
    run("ECB", fetch_ecb)
    run("SOFR", fetch_sofr)
    run("US_TBILL_AVG", fetch_tbill)
    run("BRENT_IMF", fetch_brent_imf)
    print("loading World Bank workbook...", flush=True)
    run("WORLD_BANK", fetch_worldbank)
    print("done", flush=True)


if __name__ == "__main__":
    probe()
