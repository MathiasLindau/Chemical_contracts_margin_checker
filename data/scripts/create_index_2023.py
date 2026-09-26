"""Write the January 2023 index. That month is index 100 for every series.

These are the observations already returned by ECB, the NY Fed, and the
World Bank. The contract files have no signature date, so every contract
uses this month as its start.

    python data/scripts/create_index_2023.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "market" / "index_2023.csv"

HEADER = ("instrument", "baseline_date", "baseline_value", "unit", "source")

# January 2023, the first published value in that month.
INDEX_2023 = (
    ("EURUSD", "2023-01-02", "1.0683", "USD for 1 EUR", "ECB"),
    ("GAS_EU", "2023-01-01", "20.18", "USD per mmBtu", "World Bank"),
    ("BRENT", "2023-01-01", "83.1", "USD per barrel", "World Bank"),
    ("MAIZE", "2023-01-01", "302.8", "USD per metric ton", "World Bank"),
    ("SOFR", "2023-01-03", "4.31", "percent per year", "NY Fed"),
    ("EURIBOR_3M", "2023-01", "2.3448636", "percent per year", "ECB"),
)


def index_rows():
    return [
        dict(zip(HEADER, row))
        for row in INDEX_2023
    ]


def write_index(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(index_rows())
    return path


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    write_index(path)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
