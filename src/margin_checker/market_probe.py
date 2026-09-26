"""Print the latest free market values. One failure does not stop the rest.

    python -m src.margin_checker.market_probe
"""

from __future__ import annotations

import csv
import io
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TIMEOUT = 30
ECB = (
    ("fx", "EURUSD", "EXR/D.USD.EUR.SP00.A", "USD/EUR", "business day"),
    ("rate", "ECB_DEPOSIT", "FM/D.U2.EUR.4F.KR.DFR.LEV", "percent", "when changed"),
    ("rate", "EURIBOR_3M", "FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA", "percent", "monthly"),
)
WB = (
    ("raw", "BRENT", "Crude oil, Brent", "USD/bbl"),
    ("energy", "GAS_EU", "Natural gas, Europe", "USD/mmbtu"),
    ("raw", "MAIZE", "Maize", "USD/t"),
)


def http_get(url, headers=None):
    request = Request(url, headers={"User-Agent": "margin-checker", **(headers or {})})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()
    except URLError as exc:
        return 0, str(exc.reason).encode()


def show(group, name, when, value, unit, cadence):
    print(f"{group:<8} {name:<14} {when:<12} {value:<12} {unit:<12} {cadence}", flush=True)


def skip(name, reason):
    print(f"skip     {name:<14} {reason}", flush=True)


def guard(name, fn):
    try:
        fn()
    except Exception as exc:
        skip(name, f"{exc.__class__.__name__}: {exc}"[:140])


def pink_sheet_table(rows):
    header = labels = None
    for index, row in enumerate(rows):
        text = [str(cell).strip() if cell else "" for cell in row]
        if "Crude oil, Brent" in text:
            header, labels = index, text
            break
    if labels is None:
        raise RuntimeError("Pink Sheet header not found")
    last = None
    for row in rows[header + 1:]:
        if row and re.fullmatch(r"\d{4}M\d{2}", str(row[0] or "")):
            last = row
    if last is None:
        raise RuntimeError("Pink Sheet has no month rows")
    updated = str(rows[3][0]) if len(rows) > 3 and rows[3] and rows[3][0] else ""
    return labels, last, updated


def fetch_ecb():
    for group, name, key, unit, cadence in ECB:
        status, body = http_get(
            "https://data-api.ecb.europa.eu/service/data/" + key + "?lastNObservations=1",
            {"Accept": "text/csv"},
        )
        if status != 200:
            raise RuntimeError("HTTP " + str(status))
        row = list(csv.DictReader(io.StringIO(body.decode())))[-1]
        show(group, name, row["TIME_PERIOD"], row["OBS_VALUE"], unit, cadence)


def fetch_sofr():
    status, body = http_get("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json")
    if status != 200:
        raise RuntimeError("HTTP " + str(status))
    row = json.loads(body)["refRates"][0]
    show("rate", "SOFR", row["effectiveDate"], row["percentRate"], "percent", "business day")


def fetch_worldbank():
    from openpyxl import load_workbook

    print("loading World Bank workbook...", flush=True)
    status, page = http_get("https://www.worldbank.org/en/research/commodity-markets")
    if status != 200:
        raise RuntimeError("page HTTP " + str(status))
    match = re.search(
        r"https://thedocs\.worldbank\.org/[^\"']+CMO-Historical-Data-Monthly\.xlsx",
        page.decode("utf-8", "replace"),
    )
    if not match:
        raise RuntimeError("workbook link missing")
    status, blob = http_get(match.group(0))
    if status != 200:
        raise RuntimeError("workbook HTTP " + str(status))
    rows = list(load_workbook(io.BytesIO(blob), read_only=True, data_only=True)["Monthly Prices"].iter_rows(values_only=True))
    labels, last, updated = pink_sheet_table(rows)
    for group, name, label, unit in WB:
        if label not in labels:
            skip(name, "column missing")
            continue
        show(group, name, str(last[0]), last[labels.index(label)], unit, "monthly " + updated)


def probe():
    print(f"{'group':<8} {'series':<14} {'as_of':<12} {'value':<12} {'unit':<12} cadence", flush=True)
    guard("ECB", fetch_ecb)
    guard("SOFR", fetch_sofr)
    guard("WORLD_BANK", fetch_worldbank)
    print("done", flush=True)


if __name__ == "__main__":
    probe()
