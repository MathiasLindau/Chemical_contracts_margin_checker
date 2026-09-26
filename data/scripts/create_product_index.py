"""Write which API series each product uses.

Energy is European gas for every product. The product name chooses the
raw material: Brent, maize, or none. The currency later chooses the rate.

    python data/scripts/create_product_index.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "data" / "chemical_contracts.csv"
OUT = ROOT / "data" / "market" / "product_index_map.csv"

HEADER = (
    "product_name",
    "energy_instrument",
    "raw_material_instrument",
    "rate_rule",
    "fx_instrument",
)

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


def raw_instrument(product):
    name = product.strip().lower()
    if name in BRENT_PRODUCTS:
        return "BRENT"
    if name in MAIZE_PRODUCTS:
        return "MAIZE"
    return "UNMAPPED"


def index_rows(contracts):
    products = sorted({row["product_name"] for row in contracts})
    return [
        {
            "product_name": product,
            "energy_instrument": "GAS_EU",
            "raw_material_instrument": raw_instrument(product),
            "rate_rule": "SOFR if currency USD, else EURIBOR_3M",
            "fx_instrument": "EURUSD",
        }
        for product in products
    ]


def write_index(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


def main():
    print("create_product_index start", flush=True)
    if not CONTRACTS.exists():
        print("missing " + str(CONTRACTS), flush=True)
        return 1
    with CONTRACTS.open(encoding="utf-8", newline="") as handle:
        contracts = list(csv.DictReader(handle))
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    rows = index_rows(contracts)
    write_index(path, rows)
    print(f"wrote {path} products {len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
