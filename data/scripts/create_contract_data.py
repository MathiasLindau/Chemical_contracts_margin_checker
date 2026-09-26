print("create_contract_data start", flush=True)

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
    print("data/contracts nicht gefunden", flush=True)
    print("cwd " + str(Path.cwd()), flush=True)
    print("file " + str(Path(__file__).resolve()), flush=True)
    raise SystemExit(1)


def cut(text, left, right):
    start = text.find(left)
    if start < 0:
        raise RuntimeError(left)
    start += len(left)
    end = text.find(right, start)
    if end < 0:
        raise RuntimeError(right)
    return text[start:end].strip()


def money(text, left, right):
    price, currency = cut(text, left, right).split()[:2]
    return price, currency


def read_contract(text):
    title = text.splitlines()[0]
    if "MASTER AGREEMENT" in title:
        price, currency = money(text, "**Base Price:** ", " per")
        return {
            "customer_name": cut(text, "and **", "**"),
            "product_name": cut(text, "**Product:** ", "\n"),
            "base_price": price,
            "currency": currency,
            "energy_adder_percentage": cut(text, "**Energy Adder:** ", "%"),
            "raw_material_adder_percentage": cut(text, "**Raw Material Adder:** ", "%"),
            "min_monthly_volume_tons": cut(text, "Minimum monthly volume of ", " tons"),
            "max_monthly_volume_tons": cut(text, "up to a maximum of ", " tons"),
            "max_transport_duration_days": cut(text, "**Max Transport Duration:** ", " days"),
            "payment_terms_days": cut(text, "Net ", " days"),
            "min_shelf_life_days": cut(text, "**Minimum Shelf Life:** ", " days"),
            "demurrage_days_included": cut(text, "**Demurrage / Free Container Days:** ", " days"),
            "breach_penalty_amount": cut(text, "penalty of **", " "),
        }
    if "Rahmenvertrag" in title:
        price, currency = money(text, "Basispreis ", "/t")
        return {
            "customer_name": cut(text, "Käufer: **", "**"),
            "product_name": cut(text, "Geliefert wird **", "**"),
            "base_price": price,
            "currency": currency,
            "energy_adder_percentage": cut(text, "Energiezuschlag ", " Prozent"),
            "raw_material_adder_percentage": cut(text, "Rohstoffzuschlag ", " Prozent"),
            "min_monthly_volume_tons": cut(text, "zwischen ", " t"),
            "max_monthly_volume_tons": cut(text, "floor) und ", " t"),
            "max_transport_duration_days": cut(text, "Maximale Transportzeit ", " Tage"),
            "payment_terms_days": cut(text, "Zahlungsziel: ", " Tage"),
            "min_shelf_life_days": cut(text, "mindestens ", " Tage"),
            "demurrage_days_included": cut(text, "demurrage-frei: ", " Tage"),
            "breach_penalty_amount": cut(text, "Vertragsstrafe von **", " "),
        }
    if "Chemical Supply Agreement" in title:
        price, currency = money(text, "base price is ", " per")
        shelf = cut(text, "at least ", " days")
        return {
            "customer_name": cut(text, "and **", "**"),
            "product_name": cut(text, "The product is ", "."),
            "base_price": price,
            "currency": currency,
            "energy_adder_percentage": cut(text, "energy adder of ", "%"),
            "raw_material_adder_percentage": cut(text, "feedstock adder of ", "%"),
            "min_monthly_volume_tons": cut(text, "less than ", " metric"),
            "max_monthly_volume_tons": cut(text, "not exceed ", " metric"),
            "max_transport_duration_days": cut(text, "Transit shall not exceed ", " days"),
            "payment_terms_days": cut(text, "due ", " days"),
            "min_shelf_life_days": shelf,
            "demurrage_days_included": cut(text, "at least " + shelf + " days. ", " laytime"),
            "breach_penalty_amount": cut(text, "liquidated at **", " "),
        }
    if "International Sale Contract" in title:
        price, currency = money(text, "Unit price ", "/MT")
        return {
            "customer_name": cut(text, "Buyer: **", "**"),
            "product_name": cut(text, "## Goods\n", ","),
            "base_price": price,
            "currency": currency,
            "energy_adder_percentage": cut(text, "Energy cost recovery ", "%"),
            "raw_material_adder_percentage": cut(text, "Raw-material recovery ", "%"),
            "min_monthly_volume_tons": cut(text, "minimum ", " MT"),
            "max_monthly_volume_tons": cut(text, "upside to ", " MT"),
            "max_transport_duration_days": cut(text, "Maximum transit ", " days"),
            "payment_terms_days": cut(text, "Payment within ", " days"),
            "min_shelf_life_days": cut(text, "Minimum remaining life ", " days"),
            "demurrage_days_included": cut(text, "Free time ", " days"),
            "breach_penalty_amount": cut(text, "damages of **", " "),
        }
    if "purchase-order" in title:
        price, currency = money(text, "Price ", "/t")
        return {
            "customer_name": cut(text, "Buyer **", "**"),
            "product_name": cut(text, "SKU: ", "."),
            "base_price": price,
            "currency": currency,
            "energy_adder_percentage": cut(text, "plus energy ", "%"),
            "raw_material_adder_percentage": cut(text, "plus raw materials ", "%"),
            "min_monthly_volume_tons": cut(text, "below ", " t"),
            "max_monthly_volume_tons": cut(text, "above ", " t"),
            "max_transport_duration_days": cut(text, "Lead time cap ", " days"),
            "payment_terms_days": cut(text, "Net ", "."),
            "min_shelf_life_days": cut(text, "Shelf-life gate ", " days"),
            "demurrage_days_included": cut(text, "Free storage ", " days"),
            "breach_penalty_amount": cut(text, "penalty **", " "),
        }
    if "REACH-aligned" in title:
        low, high = cut(text, "Contracted band: ", " tons").split("–")
        price, currency = money(text, "## Formula price\n", " per")
        return {
            "customer_name": cut(text, "and **", "**"),
            "product_name": cut(text, "## Substance\n", "."),
            "base_price": price,
            "currency": currency,
            "energy_adder_percentage": cut(text, "energy component of ", "%"),
            "raw_material_adder_percentage": cut(text, "feedstock component of ", "%"),
            "min_monthly_volume_tons": low.strip(),
            "max_monthly_volume_tons": high.strip(),
            "max_transport_duration_days": cut(text, "Transit limit ", " days"),
            "payment_terms_days": cut(text, "due in ", " days"),
            "min_shelf_life_days": cut(text, "shelf life ", " days"),
            "demurrage_days_included": cut(text, "Demurrage allowance ", " days"),
            "breach_penalty_amount": cut(text, "damages: **", " "),
        }
    raise RuntimeError(title)


def contract_files(folder):
    return sorted(Path(folder).glob("CON-*.md"))


def parse_contract(path):
    row = read_contract(Path(path).read_text(encoding="utf-8"))
    row["contract_id"] = Path(path).stem
    return row


def main():
    root = project_root()
    folder = root / "data" / "contracts"
    files = contract_files(folder)
    print("ordner " + str(folder), flush=True)
    print("dateien " + str(len(files)), flush=True)
    if not files:
        print("keine CON-*.md", flush=True)
        return 1
    rows = []
    for path in files:
        try:
            rows.append(parse_contract(path))
        except RuntimeError as exc:
            print("fehler " + path.name + " " + str(exc), flush=True)
            return 1
    out = root / "data" / "market" / "contract_data.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print("wrote " + str(out), flush=True)
    print("zeilen " + str(len(rows)), flush=True)
    print(rows[0]["contract_id"] + " " + rows[0]["customer_name"] + " " + rows[0]["product_name"], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
