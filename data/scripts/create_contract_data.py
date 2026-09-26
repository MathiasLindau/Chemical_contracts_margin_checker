"""Write the compact contract table used by the daily price calculation.

The long contract text stays in data/contracts. This file keeps only the
fields the structured table and the price calculation read.

    python data/scripts/create_contract_data.py
"""

from __future__ import annotations

import csv
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
            if (folder / "data" / "market").is_dir():
                return folder
    raise SystemExit("Start this from the margin-checker folder.")


def source_file(root):
    candidates = (
        root / "data" / "chemical_contracts.csv",
        root / "data" / "contracts" / "chemical_contracts.csv",
    )
    for path in candidates:
        if path.exists():
            return path
    print("missing source contract table. Looked for:", flush=True)
    for path in candidates:
        print("  " + str(path), flush=True)
    return None


def compact_rows(contracts):
    rows = []
    for contract in contracts:
        rows.append({column: contract[column] for column in HEADER})
    return rows


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
    source = source_file(root)
    if source is None:
        return 1
    with source.open(encoding="utf-8", newline="") as handle:
        rows = compact_rows(list(csv.DictReader(handle)))
    path = root / "data" / "market" / "contract_data.csv"
    write_contracts(path, rows)
    print(f"wrote {path} contracts {len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
