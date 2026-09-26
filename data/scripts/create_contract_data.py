"""Build data/market/contract_data.csv from the files in data/contracts.

Each contract is one Markdown file, for example data/contracts/CON-2023-0003.md.
A single chemical_contracts.csv is optional. This script does not need it.

Save this file, then run it from the margin-checker folder:

    python -u data/scripts/create_contract_data.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

HEADER = (
    "contract_id",
    "customer_name",
    "product_name",
    "base_price",
    "currency",
    "energy_adder_percentage",
    "raw_material_adder_percentage",
    "min_monthly_volume_tons",
    "max_monthly_volume_tons",
    "max_transport_duration_days",
    "payment_terms_days",
    "min_shelf_life_days",
    "demurrage_days_included",
    "breach_penalty_amount",
)


def project_root():
    starts = [Path.cwd(), Path(__file__).resolve().parent]
    for start in starts:
        for folder in [start, *start.parents]:
            if (folder / "data" / "contracts").is_dir():
                return folder
    raise SystemExit("Start this from the margin-checker folder.")


def grab(text, patterns, label):
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if match:
            return match
    raise RuntimeError(label)


def parse_contract(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".csv":
        row = next(csv.DictReader(text.splitlines()))
        row["contract_id"] = row.get("contract_id") or path.stem
        return {column: row[column] for column in HEADER}

    customer = grab(text, [r"\*\*([^*]+)\*\*"], "customer").group(1).strip()
    product = grab(text, [
        r"\*\*Product:\*\*\s*([^\n]+)",
        r"Geliefert wird \*\*([^*]+)\*\*",
        r"The product is ([^.]+)\.",
        r"SKU:\s*([^.]+)\.",
        r"## Substance\s+([^.]+)\.",
        r"## Goods\s+([^,\n]+)",
    ], "product").group(1).strip()
    price = grab(text, [
        r"Base Price:\*\*\s*([0-9.]+)\s+([A-Z]{3})",
        r"Basispreis\s+([0-9.]+)\s+([A-Z]{3})",
        r"firm base price is\s+([0-9.]+)\s+([A-Z]{3})",
        r"Unit price\s+([0-9.]+)\s+([A-Z]{3})",
        r"Price\s+([0-9.]+)\s+([A-Z]{3})",
        r"\b([0-9.]+)\s+([A-Z]{3})\s+per ton",
    ], "price")
    energy = grab(text, [
        r"Energy Adder:\*\*\s*([0-9.]+)\s*%",
        r"Energiezuschlag\s+([0-9.]+)\s+Prozent",
        r"energy adder of\s+([0-9.]+)\s*%",
        r"Energy cost recovery\s+([0-9.]+)\s*%",
        r"plus energy\s+([0-9.]+)\s*%",
        r"energy component of\s+([0-9.]+)\s*%",
    ], "energy").group(1)
    raw = grab(text, [
        r"Raw Material Adder:\*\*\s*([0-9.]+)\s*%",
        r"Rohstoffzuschlag\s+([0-9.]+)\s+Prozent",
        r"feedstock adder of\s+([0-9.]+)\s*%",
        r"Raw-material recovery\s+([0-9.]+)\s*%",
        r"raw materials\s+([0-9.]+)\s*%",
        r"feedstock component of\s+([0-9.]+)\s*%",
    ], "raw").group(1)
    band = grab(text, [
        r"Minimum monthly volume of\s+([0-9.]+)\s+tons up to a maximum of\s+([0-9.]+)",
        r"zwischen\s+([0-9.]+)\s+t\s.*?und\s+([0-9.]+)\s+t",
        r"not be less than\s+([0-9.]+)\s+metric tons and shall not exceed\s+([0-9.]+)",
        r"minimum\s+([0-9.]+)\s+MT/month\..*?upside to\s+([0-9.]+)",
        r"below\s+([0-9.]+)\s+t or above\s+([0-9.]+)",
        r"([0-9.]+)[–-]([0-9.]+)\s+tons per month",
    ], "volume")
    payment = grab(text, [
        r"Net\s+([0-9.]+)\s+days",
        r"Zahlungsziel:\s*([0-9.]+)\s+Tage",
        r"due\s+([0-9.]+)\s+days after",
        r"Payment within\s+([0-9.]+)\s+days",
        r"Net\s+([0-9.]+)\.",
        r"due in\s+([0-9.]+)\s+days",
    ], "payment").group(1)
    transport = grab(text, [
        r"Max Transport Duration:\*\*\s*([0-9.]+)",
        r"Maximale Transportzeit\s+([0-9.]+)",
        r"Transit shall not exceed\s+([0-9.]+)",
        r"Maximum transit\s+([0-9.]+)",
        r"Lead time cap\s+([0-9.]+)",
        r"Transit limit\s+([0-9.]+)",
    ], "transport").group(1)
    shelf = grab(text, [
        r"Minimum Shelf Life:\*\*\s*([0-9.]+)",
        r"mindestens\s+([0-9.]+)\s+Tage",
        r"at least\s+([0-9.]+)\s+days",
        r"Minimum remaining life\s+([0-9.]+)",
        r"Shelf-life gate\s+([0-9.]+)",
        r"Minimum remaining shelf life\s+([0-9.]+)",
    ], "shelf").group(1)
    demurrage = grab(text, [
        r"Demurrage / Free Container Days:\*\*\s*([0-9.]+)",
        r"demurrage-frei:\s*([0-9.]+)",
        r"([0-9.]+)\s+laytime days",
        r"Free time\s+([0-9.]+)",
        r"Free storage\s+([0-9.]+)",
        r"Demurrage allowance\s+([0-9.]+)",
    ], "demurrage").group(1)
    penalty = grab(text, [
        r"penalty of \*\*([0-9.]+)",
        r"Vertragsstrafe von \*\*([0-9.]+)",
        r"liquidated at \*\*([0-9.]+)",
        r"damages of \*\*([0-9.]+)",
        r"penalty \*\*([0-9.]+)",
        r"damages: \*\*([0-9.]+)",
    ], "penalty").group(1)
    return {
        "contract_id": path.stem,
        "customer_name": customer,
        "product_name": product,
        "base_price": price.group(1),
        "currency": price.group(2),
        "energy_adder_percentage": energy,
        "raw_material_adder_percentage": raw,
        "min_monthly_volume_tons": band.group(1),
        "max_monthly_volume_tons": band.group(2),
        "max_transport_duration_days": transport,
        "payment_terms_days": payment,
        "min_shelf_life_days": shelf,
        "demurrage_days_included": demurrage,
        "breach_penalty_amount": penalty,
    }


def contract_files(folder):
    files = [
        path for path in folder.iterdir()
        if path.suffix.lower() in {".md", ".csv"} and path.stem.startswith("CON-")
    ]
    return sorted(files, key=lambda path: path.name)


def write_contracts(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    print("create_contract_data start", flush=True)
    root = project_root()
    folder = root / "data" / "contracts"
    files = contract_files(folder)
    print(f"found {len(files)} files in {folder}", flush=True)
    if not files:
        print("no CON-*.md or CON-*.csv files in data/contracts", flush=True)
        return 1
    rows = []
    for path in files:
        try:
            rows.append(parse_contract(path))
        except RuntimeError as exc:
            print(f"skip {path.name} {exc}", flush=True)
            return 1
    out = root / "data" / "market" / "contract_data.csv"
    write_contracts(out, rows)
    print(f"wrote {out} contracts {len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
