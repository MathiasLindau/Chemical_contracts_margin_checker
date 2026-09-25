"""Refresh the market tables from sources that return a number with no key.

Run on a business day. Monthly series stay on their last published month
until the source updates. Nothing is invented.

    python -m src.margin_checker.market_refresh

Writes data/market/prices.csv, product_index_map.csv, index_baselines.csv.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "market"
CONTRACTS = ROOT / "data" / "chemical_contracts.csv"

BRENT_PRODUCTS = {
    "polyethylene", "high density polyethylene", "low density polyethylene",
    "polypropylene", "polystyrene", "polyethylene terephthalate", "pvc resin",
    "benzene", "toluene", "mixed xylenes", "styrene monomer",
    "styrene acrylonitrile", "acrylonitrile butadiene styrene",
    "phenol", "methanol", "bio-naphtha", "mtbe", "n-butanol",
    "monoethylene glycol", "diethylene glycol", "vinyl acetate monomer",
    "aniline", "caprolactam", "adipic acid", "formaldehyde", "acetone",
    "chloroform", "nylon 66",
}
MAIZE_PRODUCTS = {
    "ethanol", "glucose syrup 42de", "citric acid", "lactic acid 88%",
    "glycerin", "sorbitol 70%", "maltodextrin", "gelatin", "pla resin",
}
WB_COLUMNS = {
    "BRENT": "Crude oil, Brent",
    "GAS_EU": "Natural gas, Europe",
    "MAIZE": "Maize",
}
WB_UNITS = {"BRENT": "USD/bbl", "GAS_EU": "USD/mmbtu", "MAIZE": "USD/t"}


def _sofr_on(day):
    row = json.loads(get(
        "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json"
        f"?startDate={day}&endDate={day}"
    ))["refRates"][0]
    return row["effectiveDate"], float(row["percentRate"])


def get(url, headers=None):
    request = Request(url, headers={"User-Agent": "margin-checker", **(headers or {})})
    with urlopen(request, timeout=30) as response:
        return response.read()


def ecb(flow, start=None, end=None, last_n=None):
    params = []
    if start:
        params.append("startPeriod=" + start)
    if end:
        params.append("endPeriod=" + end)
    if last_n:
        params.append("lastNObservations=" + str(last_n))
    url = "https://data-api.ecb.europa.eu/service/data/" + flow
    if params:
        url += "?" + "&".join(params)
    text = get(url, {"Accept": "text/csv"}).decode("utf-8")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("TIME_PERIOD") and row.get("OBS_VALUE"):
            rows.append((row["TIME_PERIOD"], float(row["OBS_VALUE"])))
    return rows


def observation(as_of, instrument, value, unit, currency, frequency, source):
    return {
        "as_of_date": as_of,
        "instrument": instrument,
        "value": value,
        "unit": unit,
        "currency": currency,
        "frequency": frequency,
        "source": source,
    }


def raw_instrument(product):
    name = product.strip().lower()
    if name in BRENT_PRODUCTS:
        return "BRENT"
    if name in MAIZE_PRODUCTS:
        return "MAIZE"
    return "UNMAPPED"


def rate_instrument(currency):
    if str(currency).upper() == "EUR":
        return "EURIBOR_3M"
    if str(currency).upper() == "USD":
        return "SOFR"
    return "UNMAPPED"


def pink_sheet():
    page = get("https://www.worldbank.org/en/research/commodity-markets").decode("utf-8", "replace")
    match = re.search(r"https://thedocs\.worldbank\.org/[^\"']+CMO-Historical-Data-Monthly\.xlsx", page)
    if not match:
        raise RuntimeError("World Bank workbook link missing")
    book = load_workbook(io.BytesIO(get(match.group(0))), read_only=True, data_only=True)
    rows = list(book["Monthly Prices"].iter_rows(values_only=True))
    header = None
    labels = None
    for index, row in enumerate(rows):
        text = [str(cell).strip() if cell else "" for cell in row]
        if "Crude oil, Brent" in text:
            header = index
            labels = text
            break
    if labels is None:
        raise RuntimeError("Pink Sheet header not found")
    parsed = {name: [] for name in WB_COLUMNS}
    for row in rows[header + 1:]:
        if not row or not re.fullmatch(r"\d{4}M\d{2}", str(row[0] or "")):
            continue
        as_of = f"{row[0][:4]}-{row[0][5:7]}-01"
        for instrument, label in WB_COLUMNS.items():
            value = row[labels.index(label)]
            if value in (None, "", "…", "..."):
                continue
            parsed[instrument].append((as_of, float(value)))
    return parsed


def indicative_price(base, energy_adder, raw_adder, gas_now, gas_base, raw_now, raw_base):
    """Contract adder percents, scaled by the market move since the baseline."""
    energy = (energy_adder / 100.0) * (gas_now / gas_base)
    raw = 0.0 if raw_base in (None, 0) or raw_now is None else (raw_adder / 100.0) * (raw_now / raw_base)
    return base * (1.0 + energy + raw)


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    prices = []
    latest = {}

    def keep(rows, instrument, unit, currency, frequency, source, limit=8):
        chosen = rows[-limit:]
        for as_of, value in chosen:
            prices.append(observation(as_of, instrument, value, unit, currency, frequency, source))
        latest[instrument] = observation(chosen[-1][0], instrument, chosen[-1][1], unit, currency, frequency, source)

    keep(ecb("EXR/D.USD.EUR.SP00.A", last_n=8), "EURUSD", "USD/EUR", "USD", "daily", "ECB")
    keep(ecb("FM/D.U2.EUR.4F.KR.DFR.LEV", last_n=3), "ECB_DEPOSIT", "percent", "EUR", "on_change", "ECB")
    keep(ecb("FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA", last_n=6), "EURIBOR_3M", "percent", "EUR", "monthly", "ECB")

    sofr = json.loads(get("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json"))["refRates"][0]
    keep([(sofr["effectiveDate"], float(sofr["percentRate"]))], "SOFR", "percent", "USD", "daily", "NYFED")

    wb = pink_sheet()
    for instrument, series in wb.items():
        keep(series, instrument, WB_UNITS[instrument], "USD", "monthly", "WORLD_BANK", limit=6)

    baselines_2023 = {
        "EURUSD": ecb("EXR/D.USD.EUR.SP00.A", start="2023-01-02", end="2023-01-06")[0],
        "ECB_DEPOSIT": ecb("FM/D.U2.EUR.4F.KR.DFR.LEV", start="2023-01-01", end="2023-01-31")[-1],
        "EURIBOR_3M": next(pair for pair in ecb("FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA", start="2023-01", end="2023-03") if pair[0].startswith("2023-01")),
        "SOFR": _sofr_on("2023-01-03"),
    }
    for instrument, series in wb.items():
        baselines_2023[instrument] = next(pair for pair in series if pair[0] == "2023-01-01")

    contracts = list(csv.DictReader(CONTRACTS.open(encoding="utf-8")))
    products = sorted({row["product_name"] for row in contracts})
    product_map = []
    for product in products:
        product_map.append({
            "product_name": product,
            "energy_instrument": "GAS_EU",
            "raw_material_instrument": raw_instrument(product),
            "rate_rule": "SOFR if currency USD, else EURIBOR_3M",
            "fx_instrument": "EURUSD",
        })

    baseline_rows = []
    for contract in contracts:
        instruments = ["EURUSD", "GAS_EU"]
        rate_name = rate_instrument(contract["currency"])
        raw_name = raw_instrument(contract["product_name"])
        if rate_name != "UNMAPPED":
            instruments.append(rate_name)
        if raw_name != "UNMAPPED":
            instruments.append(raw_name)
        for instrument in instruments:
            as_of, value = baselines_2023[instrument]
            if value is None:
                continue
            point = latest[instrument]
            baseline_rows.append({
                "contract_id": contract["contract_id"],
                "instrument": instrument,
                "baseline_date": as_of,
                "baseline_value": value,
                "unit": point["unit"],
                "source": point["source"],
                "note": "2023-01 proxy, contracts have no signature date",
            })

    fields = ["as_of_date", "instrument", "value", "unit", "currency", "frequency", "source"]
    write_csv(OUT / "prices.csv", prices, fields)
    write_csv(OUT / "market_latest.csv", list(latest.values()), fields)
    write_csv(
        OUT / "product_index_map.csv",
        product_map,
        ["product_name", "energy_instrument", "raw_material_instrument", "rate_rule", "fx_instrument"],
    )
    write_csv(
        OUT / "index_baselines.csv",
        baseline_rows,
        ["contract_id", "instrument", "baseline_date", "baseline_value", "unit", "source", "note"],
    )

    example = next(row for row in contracts if row["contract_id"] == "CON-2023-0003")
    gas_now = latest["GAS_EU"]["value"]
    gas_base = baselines_2023["GAS_EU"][1]
    maize_now = latest["MAIZE"]["value"]
    maize_base = baselines_2023["MAIZE"][1]
    price = indicative_price(
        float(example["base_price"]),
        float(example["energy_adder_percentage"]),
        float(example["raw_material_adder_percentage"]),
        gas_now, gas_base, maize_now, maize_base,
    )
    eur = price / latest["EURUSD"]["value"]
    print(f"latest EURUSD {latest['EURUSD']['as_of_date']} {latest['EURUSD']['value']}")
    print(f"latest GAS_EU {latest['GAS_EU']['as_of_date']} {gas_now} base {gas_base}")
    print(f"latest MAIZE {latest['MAIZE']['as_of_date']} {maize_now} base {maize_base}")
    print(f"CON-2023-0003 indicative {price:.2f} USD/t  ({eur:.2f} EUR/t)")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
