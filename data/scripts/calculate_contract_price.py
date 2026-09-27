print("calculate_contract_price start", flush=True)

import csv
import sys
from pathlib import Path

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
    "price_date",
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


def project_root():
    starts = [Path.cwd(), Path(__file__).resolve().parent]
    for start in starts:
        for folder in [start, *start.parents]:
            if (folder / "data" / "market").is_dir():
                return folder
    print("data/market nicht gefunden", flush=True)
    print("cwd " + str(Path.cwd()), flush=True)
    raise SystemExit(1)


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def api_days(rows):
    by_date = {}
    for row in rows:
        day = str(row.get("pulled_on_date", ""))
        if day.startswith("20"):
            by_date[day] = row
    if not by_date:
        raise RuntimeError("api_price.csv hat keine Datenzeile")
    return [by_date[day] for day in sorted(by_date)]


def latest_api_row(rows):
    return api_days(rows)[-1]


def index_value(index_rows, instrument):
    for row in index_rows:
        if row["instrument"] == instrument:
            return float(row["baseline_value"])
    raise RuntimeError("index_2023.csv hat kein " + instrument)


def api_value(api_row, instrument):
    column = API_COLUMNS[instrument]
    value = api_row.get(column, "")
    if str(value).strip() == "":
        raise RuntimeError("api_price.csv hat kein " + column)
    return float(value)


def logistics_price(rows, item):
    for row in rows:
        if row["item"] == item:
            return float(row["price"])
    raise RuntimeError("logistics_price.csv hat kein " + item)


def money(value):
    return f"{value:.2f}"


def ratio_text(value):
    return f"{value:.6f}"


def price_one(contract, product_map, index_rows, api_row, trip_eur, demurrage_per_day):
    product = contract["product_name"]
    if product not in product_map:
        raise RuntimeError("product_index hat kein " + product)
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
        "price_date": str(api_row.get("pulled_on_date", "")),
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


def main():
    root = project_root()
    market = root / "data" / "market"
    product_index = market / "product_index.csv"
    if not product_index.exists():
        product_index = market / "product_index_map.csv"
    files = {
        "contracts": market / "contract_data.csv",
        "api": market / "api_price.csv",
        "logistics": market / "logistics_price.csv",
        "index": market / "index_2023.csv",
        "product_index": product_index,
    }
    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        print("datei fehlt", flush=True)
        for path in missing:
            print(path, flush=True)
        return 1
    for name, path in files.items():
        print(name + " " + str(path), flush=True)
    contracts = read_csv(files["contracts"])
    product_map = {row["product_name"]: row for row in read_csv(files["product_index"])}
    index_rows = read_csv(files["index"])
    logistics_rows = read_csv(files["logistics"])
    trip = 0.0
    demurrage = 0.0
    for row in logistics_rows:
        if row["item"] == "road_bulk_ftl_reference_trip":
            trip = float(row["price"])
        if row["item"] == "demurrage_bulk_container":
            demurrage = float(row["price"])
    history = []
    for api_row in api_days(read_csv(files["api"])):
        for contract in contracts:
            history.append(price_one(contract, product_map, index_rows, api_row, trip, demurrage))
    latest_day = history[-1]["price_date"]
    latest = [row for row in history if row["price_date"] == latest_day]
    out = market / "contract_price.csv"
    history_path = market / "contract_price_history.csv"
    for path, table in ((out, latest), (history_path, history)):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADER)
            writer.writeheader()
            writer.writerows(table)
    days = []
    for row in history:
        if row["price_date"] not in days:
            days.append(row["price_date"])
    first = latest[0]
    print("api tage " + " ".join(days), flush=True)
    print("wrote " + str(out) + " tag " + first["price_date"] + " zeilen " + str(len(latest)), flush=True)
    print("wrote " + str(history_path) + " zeilen " + str(len(history)), flush=True)
    print(first["contract_id"] + " " + first["indicative_price_per_ton"] + " " + first["currency"], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())