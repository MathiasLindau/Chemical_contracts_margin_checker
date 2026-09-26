"""Price each contract from its own fields, the 2023 index, today's API row, and the road tariff.

The product chooses the raw-material series.
UNMAPPED products keep raw ratio 1. They do not read a raw API value.
Gas is read for every product.
The currency chooses the interest series. GBP and CHF read no rate.
Logistics is the fixed 500 km trip for every contract.

    python data/scripts/calculate_contract_price.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

def project_root():
    starts = [Path.cwd(), Path(__file__).resolve().parent]
    for start in starts:
        for folder in [start, *start.parents]:
            if (folder / "data" / "market").is_dir():
                return folder
    raise SystemExit("Start this from the margin-checker folder.")


ROOT = project_root()
MARKET = ROOT / "data" / "market"
OUT = MARKET / "contract_price.csv"

API_COLUMNS = {
    "EURUSD": "usd_for_one_eur",
    "GAS_EU": "eu_natural_gas_usd_per_mmbtu",
    "BRENT": "brent_crude_usd_per_barrel",
    "MAIZE": "maize_usd_per_metric_ton",
    "SOFR": "sofr_percent_per_year",
    "EURIBOR_3M": "euribor_3m_percent_per_year",
}
RATE_BY_CURRENCY = {"USD": "SOFR", "EUR": "EURIBOR_3M"}

HEADER = (
    "contract_id",
    "customer_name",
    "product_name",
    "currency",
    "base_price",
    "energy_rule",
    "energy_index_2023",
    "energy_api_now",
    "energy_ratio",
    "energy_adder_percentage",
    "energy_amount",
    "raw_rule",
    "raw_instrument",
    "raw_index_2023",
    "raw_api_now",
    "raw_ratio",
    "raw_adder_percentage",
    "raw_amount",
    "rate_rule",
    "rate_instrument",
    "rate_percent",
    "payment_terms_days",
    "financing_per_ton",
    "logistics_eur_per_trip",
    "fx_rule",
    "logistics_amount",
    "logistics_currency",
    "demurrage_eur_per_container_day",
    "demurrage_amount",
    "indicative_price_per_ton",
    "calculation_rule",
)


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def latest_api_row(rows):
    data = [row for row in rows if row.get("pulled_on_date", "").startswith("20")]
    if not data:
        raise RuntimeError("api_price.csv has no data row")
    return data[-1]


def index_value(index_rows, instrument):
    for row in index_rows:
        if row["instrument"] == instrument:
            return float(row["baseline_value"])
    raise RuntimeError("missing 2023 index for " + instrument)


def api_value(api_row, instrument):
    column = API_COLUMNS[instrument]
    value = api_row.get(column, "")
    if str(value).strip() == "":
        raise RuntimeError("api_price.csv has no " + column)
    return float(value)


def logistics_price(rows, item):
    for row in rows:
        if row["item"] == item:
            return float(row["price"])
    raise RuntimeError("logistics_price.csv has no " + item)


def money(value):
    return f"{value:.2f}"


def ratio_text(value):
    return f"{value:.6f}"


def price_one(contract, product_map, index_rows, api_row, trip_eur, demurrage_per_day):
    product = contract["product_name"]
    if product not in product_map:
        raise RuntimeError("no product map for " + product)
    mapped = product_map[product]
    base = float(contract["base_price"])
    energy_adder = float(contract["energy_adder_percentage"])
    raw_adder = float(contract["raw_material_adder_percentage"])
    days = float(contract["payment_terms_days"])
    currency = contract["currency"].upper()

    gas_index = index_value(index_rows, "GAS_EU")
    gas_now = api_value(api_row, "GAS_EU")
    energy_ratio = gas_now / gas_index
    energy_amount = base * (energy_adder / 100.0) * energy_ratio

    raw_instrument = mapped["raw_material_instrument"]
    if raw_instrument in ("BRENT", "MAIZE"):
        raw_rule = "api"
        raw_index = index_value(index_rows, raw_instrument)
        raw_now = api_value(api_row, raw_instrument)
        raw_ratio = raw_now / raw_index
    else:
        raw_rule = "static"
        raw_instrument = "NONE"
        raw_index = 1.0
        raw_now = 1.0
        raw_ratio = 1.0
    raw_amount = base * (raw_adder / 100.0) * raw_ratio
    indicative = base + energy_amount + raw_amount

    rate_instrument = RATE_BY_CURRENCY.get(currency)
    if rate_instrument:
        rate_rule = "api"
        rate_percent = api_value(api_row, rate_instrument)
        financing = indicative * (days / 365.0) * (rate_percent / 100.0)
    else:
        rate_rule = "static"
        rate_instrument = "NONE"
        rate_percent = 0.0
        financing = 0.0

    fx = api_value(api_row, "EURUSD")
    if currency == "USD":
        fx_rule = "api"
        logistics_amount = trip_eur * fx
        logistics_currency = "USD"
    elif currency == "EUR":
        fx_rule = "api"
        logistics_amount = trip_eur
        logistics_currency = "EUR"
    else:
        fx_rule = "static"
        logistics_amount = trip_eur
        logistics_currency = "EUR"

    rule = "+".join([
        "energy_api",
        "raw_" + raw_rule,
        "rate_" + rate_rule,
        "logistics_fixed",
    ])
    return {
        "contract_id": contract["contract_id"],
        "customer_name": contract["customer_name"],
        "product_name": product,
        "currency": currency,
        "base_price": money(base),
        "energy_rule": "api",
        "energy_index_2023": ratio_text(gas_index),
        "energy_api_now": ratio_text(gas_now),
        "energy_ratio": ratio_text(energy_ratio),
        "energy_adder_percentage": contract["energy_adder_percentage"],
        "energy_amount": money(energy_amount),
        "raw_rule": raw_rule,
        "raw_instrument": raw_instrument,
        "raw_index_2023": ratio_text(raw_index),
        "raw_api_now": ratio_text(raw_now),
        "raw_ratio": ratio_text(raw_ratio),
        "raw_adder_percentage": contract["raw_material_adder_percentage"],
        "raw_amount": money(raw_amount),
        "rate_rule": rate_rule,
        "rate_instrument": rate_instrument,
        "rate_percent": ratio_text(rate_percent),
        "payment_terms_days": contract["payment_terms_days"],
        "financing_per_ton": money(financing),
        "logistics_eur_per_trip": money(trip_eur),
        "fx_rule": fx_rule,
        "logistics_amount": money(logistics_amount),
        "logistics_currency": logistics_currency,
        "demurrage_eur_per_container_day": money(demurrage_per_day),
        "demurrage_amount": money(0.0),
        "indicative_price_per_ton": money(indicative),
        "calculation_rule": rule,
    }


def build_rows(contracts, product_rows, index_rows, api_rows, logistics_rows):
    product_map = {row["product_name"]: row for row in product_rows}
    api_row = latest_api_row(api_rows)
    trip = logistics_price(logistics_rows, "road_bulk_ftl_reference_trip")
    demurrage = logistics_price(logistics_rows, "demurrage_bulk_container")
    return [
        price_one(contract, product_map, index_rows, api_row, trip, demurrage)
        for contract in contracts
    ]


def write_prices(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


def contracts_file():
    candidates = (
        MARKET / "contract_data.csv",
        ROOT / "data" / "chemical_contracts.csv",
        ROOT / "data" / "contracts" / "chemical_contracts.csv",
    )
    for path in candidates:
        if path.exists():
            return path
    print("missing contract table. Looked for:", flush=True)
    for path in candidates:
        print("  " + str(path), flush=True)
    return None


def main():
    print("calculate_contract_price start", flush=True)
    contracts = contracts_file()
    required = [
        MARKET / "product_index_map.csv",
        MARKET / "index_2023.csv",
        MARKET / "api_price.csv",
        MARKET / "logistics_price.csv",
    ]
    missing = [path for path in required if not path.exists()]
    if contracts is None or missing:
        for path in missing:
            print("missing " + str(path), flush=True)
        return 1
    print("contracts " + str(contracts), flush=True)
    rows = build_rows(
        read_csv(contracts),
        read_csv(MARKET / "product_index_map.csv"),
        read_csv(MARKET / "index_2023.csv"),
        read_csv(MARKET / "api_price.csv"),
        read_csv(MARKET / "logistics_price.csv"),
    )
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    write_prices(path, rows)
    print(f"wrote {path} rows {len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
