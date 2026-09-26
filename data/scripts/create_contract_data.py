"""Liest data/contracts/*.md und schreibt data/market/contract_data.csv.

Jede Markdown-Datei ist ein Vertrag. Die Endziffer der Vertragsnummer
sagt, welches der sechs Layouts es ist. Speichern, dann im Projektordner:

    python -u data/scripts/create_contract_data.py
"""

import csv
import sys
from pathlib import Path

COLUMNS = [
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
]


def project_root():
    starts = [Path.cwd(), Path(__file__).resolve().parent]
    for start in starts:
        for folder in [start, *start.parents]:
            if (folder / "data" / "contracts").is_dir():
                return folder
    raise SystemExit("data/contracts nicht gefunden. Im Projektordner starten.")


def between(text, left, right):
    start = text.find(left)
    if start < 0:
        raise RuntimeError(left)
    start += len(left)
    end = text.find(right, start)
    if end < 0:
        raise RuntimeError(right)
    return text[start:end].strip()


def money(piece):
    price, currency = piece.split()[:2]
    return price, currency


def texas(text):
    price, currency = money(between(text, "**Base Price:** ", " per"))
    return {
        "customer_name": between(text, "and **", "**"),
        "product_name": between(text, "**Product:** ", "\n"),
        "base_price": price,
        "currency": currency,
        "min_monthly_volume_tons": between(text, "Minimum monthly volume of ", " tons"),
        "max_monthly_volume_tons": between(text, "up to a maximum of ", " tons"),
        "energy_adder_percentage": between(text, "**Energy Adder:** ", "%"),
        "raw_material_adder_percentage": between(text, "**Raw Material Adder:** ", "%"),
        "payment_terms_days": between(text, "Net ", " days"),
        "max_transport_duration_days": between(text, "**Max Transport Duration:** ", " days"),
        "min_shelf_life_days": between(text, "**Minimum Shelf Life:** ", " days"),
        "demurrage_days_included": between(text, "**Demurrage / Free Container Days:** ", " days"),
        "breach_penalty_amount": between(text, "penalty of **", " "),
    }


def german(text):
    price, currency = money(between(text, "Basispreis ", "/t"))
    return {
        "customer_name": between(text, "Käufer: **", "**"),
        "product_name": between(text, "Geliefert wird **", "**"),
        "base_price": price,
        "currency": currency,
        "min_monthly_volume_tons": between(text, "zwischen ", " t"),
        "max_monthly_volume_tons": between(text, "floor) und ", " t"),
        "energy_adder_percentage": between(text, "Energiezuschlag ", " Prozent"),
        "raw_material_adder_percentage": between(text, "Rohstoffzuschlag ", " Prozent"),
        "payment_terms_days": between(text, "Zahlungsziel: ", " Tage"),
        "max_transport_duration_days": between(text, "Maximale Transportzeit ", " Tage"),
        "min_shelf_life_days": between(text, "mindestens ", " Tage"),
        "demurrage_days_included": between(text, "demurrage-frei: ", " Tage"),
        "breach_penalty_amount": between(text, "Vertragsstrafe von **", " "),
    }


def english(text):
    price, currency = money(between(text, "base price is ", " per"))
    shelf = between(text, "at least ", " days")
    return {
        "customer_name": between(text, "and **", "**"),
        "product_name": between(text, "The product is ", "."),
        "base_price": price,
        "currency": currency,
        "min_monthly_volume_tons": between(text, "less than ", " metric"),
        "max_monthly_volume_tons": between(text, "not exceed ", " metric"),
        "energy_adder_percentage": between(text, "energy adder of ", "%"),
        "raw_material_adder_percentage": between(text, "feedstock adder of ", "%"),
        "payment_terms_days": between(text, "due ", " days"),
        "max_transport_duration_days": between(text, "Transit shall not exceed ", " days"),
        "min_shelf_life_days": shelf,
        "demurrage_days_included": between(text, "at least " + shelf + " days. ", " laytime"),
        "breach_penalty_amount": between(text, "liquidated at **", " "),
    }


def singapore(text):
    price, currency = money(between(text, "Unit price ", "/MT"))
    return {
        "customer_name": between(text, "Buyer: **", "**"),
        "product_name": between(text, "## Goods\n", ","),
        "base_price": price,
        "currency": currency,
        "min_monthly_volume_tons": between(text, "minimum ", " MT"),
        "max_monthly_volume_tons": between(text, "upside to ", " MT"),
        "energy_adder_percentage": between(text, "Energy cost recovery ", "%"),
        "raw_material_adder_percentage": between(text, "Raw-material recovery ", "%"),
        "payment_terms_days": between(text, "Payment within ", " days"),
        "max_transport_duration_days": between(text, "Maximum transit ", " days"),
        "min_shelf_life_days": between(text, "Minimum remaining life ", " days"),
        "demurrage_days_included": between(text, "Free time ", " days"),
        "breach_penalty_amount": between(text, "damages of **", " "),
    }


def purchase_order(text):
    price, currency = money(between(text, "Price ", "/t"))
    return {
        "customer_name": between(text, "Buyer **", "**"),
        "product_name": between(text, "SKU: ", "."),
        "base_price": price,
        "currency": currency,
        "energy_adder_percentage": between(text, "plus energy ", "%"),
        "raw_material_adder_percentage": between(text, "plus raw materials ", "%"),
        "min_monthly_volume_tons": between(text, "below ", " t"),
        "max_monthly_volume_tons": between(text, "above ", " t"),
        "payment_terms_days": between(text, "Net ", "."),
        "max_transport_duration_days": between(text, "Lead time cap ", " days"),
        "min_shelf_life_days": between(text, "Shelf-life gate ", " days"),
        "demurrage_days_included": between(text, "Free storage ", " days"),
        "breach_penalty_amount": between(text, "penalty **", " "),
    }


def reach(text):
    low, high = between(text, "Contracted band: ", " tons").split("–")
    price, currency = money(between(text, "## Formula price\n", " per"))
    return {
        "customer_name": between(text, "and **", "**"),
        "product_name": between(text, "## Substance\n", "."),
        "base_price": price,
        "currency": currency,
        "energy_adder_percentage": between(text, "energy component of ", "%"),
        "raw_material_adder_percentage": between(text, "feedstock component of ", "%"),
        "min_monthly_volume_tons": low.strip(),
        "max_monthly_volume_tons": high.strip(),
        "payment_terms_days": between(text, "due in ", " days"),
        "max_transport_duration_days": between(text, "Transit limit ", " days"),
        "min_shelf_life_days": between(text, "shelf life ", " days"),
        "demurrage_days_included": between(text, "Demurrage allowance ", " days"),
        "breach_penalty_amount": between(text, "damages: **", " "),
    }


READERS = [texas, german, english, singapore, purchase_order, reach]


def contract_files(folder):
    return sorted(Path(folder).glob("CON-*.md"))


def parse_contract(path):
    text = Path(path).read_text(encoding="utf-8")
    kind = int(path.stem.split("-")[-1]) % 6
    row = READERS[kind](text)
    row["contract_id"] = path.stem
    return row


def main():
    print("create_contract_data start", flush=True)
    root = project_root()
    folder = root / "data" / "contracts"
    files = contract_files(folder)
    print(f"found {len(files)} files in {folder}", flush=True)
    if not files:
        print("keine CON-*.md in data/contracts", flush=True)
        return 1
    rows = []
    for path in files:
        try:
            rows.append(parse_contract(path))
        except RuntimeError as exc:
            print(f"fehler {path.name}: {exc}", flush=True)
            return 1
    out = root / "data" / "market" / "contract_data.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out} contracts {len(rows)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
