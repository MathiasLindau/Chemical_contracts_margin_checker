"""Write the fixed 2-year road logistics tariff.

No API. One logistics partner, road only, one bulk container per truck.
The sales contract still holds demurrage_days_included. This file is the
price per day after those free days, and the price per kilometre for the trip.

    python data/scripts/create_logistics_price.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "market" / "logistics_price.csv"

HEADER = (
    "item",
    "price",
    "unit",
    "currency",
    "valid_from",
    "valid_to",
    "what_it_is",
)

# Chemical road bulk sits above ordinary truck freight.
# Ordinary EU FTL contracts are about 1.30 to 1.60 EUR/km.
# An ADR bulk container is about 1.80 to 2.20 EUR/km. 1.95 is the middle.
# Container demurrage after free days is about 75 to 175 EUR per day. 150 is the middle.
VALID_FROM = "2026-01-01"
VALID_TO = "2027-12-31"
ROAD_BULK_FTL_EUR_PER_KM = "1.95"
REFERENCE_DISTANCE_KM = "500"
DEMURRAGE_EUR_PER_CONTAINER_DAY = "150"


def reference_trip_eur():
    return f"{float(ROAD_BULK_FTL_EUR_PER_KM) * float(REFERENCE_DISTANCE_KM):.2f}"


def tariff_rows():
    return [
        {
            "item": "road_bulk_ftl",
            "price": ROAD_BULK_FTL_EUR_PER_KM,
            "unit": "EUR per km",
            "currency": "EUR",
            "valid_from": VALID_FROM,
            "valid_to": VALID_TO,
            "what_it_is": "2-year contract, road only, one chemical bulk container per full truck",
        },
        {
            "item": "road_bulk_ftl_reference_trip",
            "price": reference_trip_eur(),
            "unit": f"EUR per trip of {REFERENCE_DISTANCE_KM} km",
            "currency": "EUR",
            "valid_from": VALID_FROM,
            "valid_to": VALID_TO,
            "what_it_is": "same tariff times 500 km, so one FTL trip has a single euro amount",
        },
        {
            "item": "demurrage_bulk_container",
            "price": DEMURRAGE_EUR_PER_CONTAINER_DAY,
            "unit": "EUR per container per day",
            "currency": "EUR",
            "valid_from": VALID_FROM,
            "valid_to": VALID_TO,
            "what_it_is": "charged for each day after demurrage_days_included in the sales contract",
        },
    ]


def write_tariff(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(tariff_rows())
    return path


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    write_tariff(path)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
