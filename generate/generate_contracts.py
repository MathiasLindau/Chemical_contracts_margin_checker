"""Build 100 chemical contracts with varied clause language.

Keeps CON-2023-0001..0050 CSV values (evaluation IDs stay valid) and
adds CON-2023-0051..0100. Markdown is rewritten from several templates
so chunks are not near-copies of the same Texas master-agreement shell.

Does not call OpenAI. Run from the repo root:

    python generate/generate_contracts.py
"""

from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "chemical_contracts.csv"
MD_DIR = ROOT / "data" / "contracts"

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
    "force_majeure_clause",
]

EXTRA_CUSTOMERS = [
    "Nordic Pulp AB",
    "Osaka Battery Metals KK",
    "Rhine Catalyst GmbH",
    "Andes Fertilizer SA",
    "Mersey Coatings Ltd",
    "Siberian Gas Chem",
    "Gulf Alkali Trading",
    "Piraeus Resins SA",
    "Lusaka Agro Inputs",
    "Quebec Waterworks Inc",
    "Busan Electronics Materials",
    "Lisbon Cork Chemicals",
    "Zurich Fine Organics AG",
    "Mumbai Colorants Pvt",
    "Cape Polymer Converters",
    "Dublin Pharma Excipients",
    "Valencia Food Acids SL",
    "Gdansk Port Chemicals",
    "Montreal Pulp Bleach Inc",
    "Jakarta Oleochemicals PT",
    "Helsinki Biofuels Oy",
    "Brisbane Mining Reagents",
    "Santiago Copper Leach SA",
    "Vienna Specialty Gases",
    "Riga Paint Vehicles SIA",
    "Casablanca Phosphates",
    "Seoul Display Chemicals",
    "Toronto Water Treatment",
    "Lyon Aroma Intermediates",
    "Porto Textile Auxiliaries",
    "Bergen Fish Oil Refiners",
    "Athens Construction Chem",
    "Tallinn Wood Adhesives",
    "Sofia Glass Batch EOOD",
    "Nairobi Crop Protection",
    "Bogota Sugar Ethanol SAS",
    "Warsaw Household Care",
    "Prague Foundry Fluxes",
    "Budapest Rubber Additives",
    "Bucharest Insulation Foam",
    "Kuala Lumpur Palm Kernel",
    "Manila Surfactant Blend",
    "Auckland Dairy Hygiene",
    "Reykjavik Geothermal Fluids",
    "Amman Dead Sea Minerals",
    "Doha LNG Treating Co",
    "Muscat Desalination Chem",
    "Colombo Rubber Latex Ltd",
    "Ho Chi Minh Plasticizers",
    "Lagos Soap Noodles Ltd",
]

EXTRA_PRODUCTS = [
    "Methanol",
    "Styrene Monomer",
    "Benzene",
    "Toluene",
    "Mixed Xylenes",
    "Monoethylene Glycol",
    "Diethylene Glycol",
    "Acrylic Acid",
    "Vinyl Acetate Monomer",
    "High Density Polyethylene",
    "Low Density Polyethylene",
    "Acrylonitrile Butadiene Styrene",
    "Styrene Acrylonitrile",
    "Adipic Acid",
    "Caprolactam",
    "Aniline",
    "Chlorine",
    "Caustic Soda Flake",
    "Phosphoric Acid",
    "Sulfuric Acid",
    "Nitric Acid",
    "Anhydrous Ammonia",
    "Melamine",
    "Formaldehyde",
    "Isopropanol",
    "n-Butanol",
    "Ethyl Acetate",
    "Bio-Naphtha",
    "Lithium Carbonate",
    "Nickel Sulfate",
    "Cobalt Sulfate",
    "Sodium Hypochlorite",
    "Polyaluminium Chloride",
    "Aluminium Sulfate",
    "Liquid Hydrogen",
    "Liquid Nitrogen",
    "Food-Grade CO2",
    "Argon",
    "Silicone Fluid 350",
    "Carbon Black N330",
    "Linear Alkylbenzene",
    "SLES 70%",
    "LABSA",
    "Sorbitol 70%",
    "Glucose Syrup 42DE",
    "Lactic Acid 88%",
    "Glacial Acetic Acid",
    "Hydrogen Peroxide 50%",
    "Sodium Percarbonate",
    "Potassium Hydroxide",
]


def extra_rows(start=51, count=50):
    rng = random.Random(2023)
    rows = []
    for offset in range(count):
        i = start + offset
        energy = rng.choice([0, 0, 1.5, 2.5, 4, 6, 8, 11, 14, 18])
        raw = rng.choice([0, 1, 2, 3.5, 5, 7, 9, 12, 16])
        min_vol = rng.choice([5, 10, 15, 25, 40, 60, 80, 120, 200, 350])
        max_vol = min_vol + rng.choice([10, 20, 40, 80, 150, 250, 400])
        currency = rng.choice(["USD", "USD", "EUR", "EUR", "GBP", "CHF"])
        rows.append({
            "contract_id": f"CON-2023-{i:04d}",
            "customer_name": EXTRA_CUSTOMERS[offset],
            "product_name": EXTRA_PRODUCTS[offset],
            "base_price": float(rng.choice([
                85, 140, 220, 310, 480, 670, 890, 1150, 1480, 2100, 3600, 4100,
            ])),
            "currency": currency,
            "energy_adder_percentage": float(energy),
            "raw_material_adder_percentage": float(raw),
            "min_monthly_volume_tons": float(min_vol),
            "max_monthly_volume_tons": float(max_vol),
            "max_transport_duration_days": int(rng.choice([2, 4, 6, 8, 11, 16, 21, 28, 40])),
            "payment_terms_days": int(rng.choice([0, 7, 14, 21, 30, 45, 60, 75, 90])),
            "min_shelf_life_days": int(rng.choice([30, 60, 90, 120, 180, 270, 365, 540, 730])),
            "demurrage_days_included": int(rng.choice([0, 1, 2, 3, 5, 7, 10, 14, 21])),
            "breach_penalty_amount": float(rng.choice([
                500, 1200, 2500, 4000, 7500, 12000, 18000, 25000, 40000, 55000,
            ])),
            "force_majeure_clause": FORCE_MAJEURE[offset % len(FORCE_MAJEURE)],
        })
    return rows


FORCE_MAJEURE = [
    "Named windstorms, named floods, and canal closures that block the nominated load port for more than 72 hours.",
    "Grid failure at the producing plant lasting over 48 hours, documented by the local TSO.",
    "Sanctions, export-control listings, or a government allocation order covering the product.",
    "Pandemic lockdowns that close the buyer's receiving terminal or the seller's jetty.",
    "Cyber incident that disables the seller's order-to-cash or TMS systems for more than 24 hours.",
    "Low-water restrictions on the Rhine or Mississippi that cut barge drafts below the booked quantity.",
    "Fire, explosion, or catastrophic mechanical failure of the dedicated production line.",
    "War, blockade, or piracy on the intended ocean route, including Red Sea diversion beyond 14 days.",
    "Raw-material declaration of force majeure by the seller's sole qualified upstream supplier.",
    "Labor strike at the load terminal that the seller cannot reasonably workaround by an alternate berth.",
]


def template_id(contract_id: str) -> int:
    try:
        return int(str(contract_id).split("-")[-1]) % 6
    except ValueError:
        return 0


def render_markdown(row: dict) -> str:
    cid = row["contract_id"]
    style = template_id(cid)
    if style == 0:
        return _texas_master(row)
    if style == 1:
        return _german_rahmen(row)
    if style == 2:
        return _english_supply(row)
    if style == 3:
        return _singapore_siac(row)
    if style == 4:
        return _purchase_order(row)
    return _reach_longform(row)


def _texas_master(c):
    return f"""# MASTER AGREEMENT FOR CHEMICAL SALES ({c['contract_id']})

This Master Agreement for Chemical Sales ("Agreement") is entered into by and between CarbonFree Chemicals SPE I LLC and **{c['customer_name']}**.

## 1. Scope, Pricing & Dynamic Adders
- **Product:** {c['product_name']}
- **Base Price:** {c['base_price']} {c['currency']} per metric ton.
- **Volume Commitments:** Minimum monthly volume of {c['min_monthly_volume_tons']} tons up to a maximum of {c['max_monthly_volume_tons']} tons.
- **Energy Adder:** {c['energy_adder_percentage']}% surcharge on base price for energy fluctuations.
- **Raw Material Adder:** {c['raw_material_adder_percentage']}% surcharge on base price for raw material cost adjustments.
- **Payment Terms:** Net {c['payment_terms_days']} days from the date of invoice.

## 2. Logistical Constraints & Terms
- **Max Transport Duration:** {c['max_transport_duration_days']} days.
- **Minimum Shelf Life:** {c['min_shelf_life_days']} days upon delivery.
- **Demurrage / Free Container Days:** {c['demurrage_days_included']} days included.

## 3. Breach of Contract and Penalties
In the event of a material breach, short delivery, or failure to meet the agreed minimum monthly volume without a valid justification, the defaulting party shall be subject to a liquidated financial penalty of **{c['breach_penalty_amount']} {c['currency']}**.

## 4. Force Majeure Clauses
{c['force_majeure_clause']}

## 5. Governing Law
This Agreement shall be governed by and construed in accordance with the laws of the State of Texas, without regard to conflict of law principles.
"""


def _german_rahmen(c):
    return f"""# Rahmenvertrag Chemikalienlieferung ({c['contract_id']})

Verkäufer: CarbonFree Chemicals SPE I LLC. Käufer: **{c['customer_name']}**. Erfüllungsort ist Hamburg unless the parties nominate another tank terminal in writing.

## A. Produkt und Mengen
Geliefert wird **{c['product_name']}**. Die monatliche Abnahme liegt zwischen {c['min_monthly_volume_tons']} t (take-or-pay floor) und {c['max_monthly_volume_tons']} t. Nominierungen erfolgen jeweils bis zum fünften Werktag.

## B. Preisformel
Basispreis {c['base_price']} {c['currency']}/t. Energiezuschlag {c['energy_adder_percentage']} Prozent, Rohstoffzuschlag {c['raw_material_adder_percentage']} Prozent, jeweils auf den Basispreis. Fakturierung unter Incoterms® 2020 FCA Hamburg.

## C. Zahlung und Verzug
Zahlungsziel: {c['payment_terms_days']} Tage netto ab Rechnungsdatum. Bei Zahlungsverzug 9 Prozentpunkte über dem EZB-Basiszinssatz.

## D. Logistik
Maximale Transportzeit {c['max_transport_duration_days']} Tage. Restlaufzeit bei Anlieferung mindestens {c['min_shelf_life_days']} Tage. Liegezeit / demurrage-frei: {c['demurrage_days_included']} Tage.

## E. Vertragsstrafe
Wird die Mindestmenge unentschuldigt unterschritten, fällt eine pauschalierte Vertragsstrafe von **{c['breach_penalty_amount']} {c['currency']}** an, neben etwaigem Schadensersatz.

## F. Höhere Gewalt
{c['force_majeure_clause']}

## G. Recht
Es gilt deutsches Recht. Gerichtsstand Hamburg. UN-Kaufrecht (CISG) ist ausgeschlossen.
"""


def _english_supply(c):
    return f"""# Chemical Supply Agreement {c['contract_id']}

Between CarbonFree Chemicals SPE I LLC (Supplier) and **{c['customer_name']}** (Buyer). This is a term contract, not a spot confirmation.

## Product specification
The product is {c['product_name']}. Monthly nominations shall not be less than {c['min_monthly_volume_tons']} metric tons and shall not exceed {c['max_monthly_volume_tons']} metric tons.

## Price and indexation
The firm base price is {c['base_price']} {c['currency']} per metric ton. An energy adder of {c['energy_adder_percentage']}% and a feedstock adder of {c['raw_material_adder_percentage']}% apply to that base. Adders are calculated monthly from the Supplier's published formula.

## Payment
Invoices are due {c['payment_terms_days']} days after the invoice date. Title passes on payment in full; risk passes on delivery.

## Logistics and quality window
Transit shall not exceed {c['max_transport_duration_days']} days. Remaining shelf life on arrival must be at least {c['min_shelf_life_days']} days. {c['demurrage_days_included']} laytime days are included; thereafter demurrage accrues at the terminal tariff.

## Liquidated damages
Failure to take or supply the minimum monthly quantity is liquidated at **{c['breach_penalty_amount']} {c['currency']}**, which the parties agree is a genuine pre-estimate of loss.

## Force majeure
{c['force_majeure_clause']}

## Law
English law. Exclusive jurisdiction of the courts of England and Wales. Arbitration is not required unless both parties later agree in writing.
"""


def _singapore_siac(c):
    return f"""# International Sale Contract — {c['contract_id']}

Seller: CarbonFree Chemicals SPE I LLC. Buyer: **{c['customer_name']}**. Seat of arbitration: Singapore.

## Goods
{c['product_name']}, commercial grade, unless a tighter spec is attached as Schedule 1.

## Quantity band
Take-or-pay minimum {c['min_monthly_volume_tons']} MT/month. Optional upside to {c['max_monthly_volume_tons']} MT/month subject to Seller's confirmation within two business days.

## Commercial terms
Unit price {c['base_price']} {c['currency']}/MT. Energy cost recovery {c['energy_adder_percentage']}%. Raw-material recovery {c['raw_material_adder_percentage']}%. Settlement currency is the contract currency.

## Credit
Payment within {c['payment_terms_days']} days. Seller may require a standby letter of credit if exposure exceeds three months of the minimum volume.

## Delivery discipline
Maximum transit {c['max_transport_duration_days']} days. Minimum remaining life {c['min_shelf_life_days']} days. Free time {c['demurrage_days_included']} days.

## Default money
Liquidated damages of **{c['breach_penalty_amount']} {c['currency']}** apply to an uncured volume shortfall.

## Excused non-performance
{c['force_majeure_clause']}

## Dispute board
SIAC Rules, one arbitrator, English language. Singapore law governs.
"""


def _purchase_order(c):
    return f"""# Call-off / purchase-order terms {c['contract_id']}

Buyer **{c['customer_name']}** issues monthly POs against these terms. Seller is CarbonFree Chemicals SPE I LLC.

## Line item
SKU: {c['product_name']}. Price {c['base_price']} {c['currency']}/t plus energy {c['energy_adder_percentage']}% plus raw materials {c['raw_material_adder_percentage']}%.

## Volume collar
Do not release POs below {c['min_monthly_volume_tons']} t or above {c['max_monthly_volume_tons']} t in any calendar month without a signed amendment.

## Commercial
Net {c['payment_terms_days']}. Short-supply or short-lift penalty **{c['breach_penalty_amount']} {c['currency']}**.

## Warehouse clock
Lead time cap {c['max_transport_duration_days']} days. Shelf-life gate {c['min_shelf_life_days']} days. Free storage {c['demurrage_days_included']} days.

## Excuses
{c['force_majeure_clause']}

## Boilerplate
New York law. Notices by email to the addresses on the latest PO. No other terms on a Buyer PO reverse side apply.
"""


def _reach_longform(c):
    return f"""# REACH-aligned supply file {c['contract_id']}

Parties: CarbonFree Chemicals SPE I LLC (only representative / manufacturer) and **{c['customer_name']}** (downstream user).

## Substance
{c['product_name']}. The SDS and exposure scenario in force on the loading date form part of this contract.

## Offtake
Contracted band: {c['min_monthly_volume_tons']}–{c['max_monthly_volume_tons']} tons per month. The buyer shall not resell into embargoed destinations.

## Formula price
{c['base_price']} {c['currency']} per ton, plus an energy component of {c['energy_adder_percentage']}% and a feedstock component of {c['raw_material_adder_percentage']}%. A separate carbon surcharge may be quoted but is not included here.

## Money terms
Invoice due in {c['payment_terms_days']} days. Audit rights on adder source data once per year.

## HSE logistics
Transit limit {c['max_transport_duration_days']} days. Minimum remaining shelf life {c['min_shelf_life_days']} days. Demurrage allowance {c['demurrage_days_included']} days. ADR/IMDG docs travel with the cargo.

## Non-performance
Volume default liquidated damages: **{c['breach_penalty_amount']} {c['currency']}**. Recall costs sit with the party that caused the non-conformance.

## FM
{c['force_majeure_clause']}

## Forum
Dutch law, Rotterdam court, CISG excluded. Sustainability certificates (ISCC/REDcert) are provided only if listed on the invoice.
"""


def build_dataset():
    existing = pd.read_csv(CSV_PATH)
    existing = existing[COLUMNS]
    keep = existing[existing["contract_id"].str.match(r"CON-2023-00(0[1-9]|[1-4][0-9]|50)$")].copy()
    if len(keep) < 50:
        keep = existing.head(50).copy()
    extra = pd.DataFrame(extra_rows())
    extra = extra[~extra["contract_id"].isin(keep["contract_id"])]
    combined = pd.concat([keep, extra], ignore_index=True)
    combined = combined.drop_duplicates(subset=["contract_id"]).sort_values("contract_id")
    return combined[COLUMNS]


def write_markdown(df: pd.DataFrame):
    MD_DIR.mkdir(parents=True, exist_ok=True)
    for stale in MD_DIR.glob("CON-*.md"):
        stale.unlink()
    for row in df.to_dict(orient="records"):
        path = MD_DIR / f"{row['contract_id']}.md"
        path.write_text(render_markdown(row), encoding="utf-8")


def main():
    df = build_dataset()
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)
    write_markdown(df)
    templates = df["contract_id"].map(template_id)
    print(
        f"Wrote {len(df)} contracts to {CSV_PATH} and {MD_DIR} "
        f"({templates.nunique()} markdown templates)."
    )


if __name__ == "__main__":
    main()
