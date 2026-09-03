import os
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List

# 1. Define the schema for a chemical supply chain contract
class ChemicalContract(BaseModel):
    contract_id: str = Field(description="Unique contract identifier, e.g., 'CON-2026-001'")
    customer_name: str = Field(description="Name of the industrial chemical buyer")
    product_name: str = Field(description="Chemical product, e.g., 'Ethylene Glycol', 'Sulfuric Acid'")
    base_price: float = Field(description="Base price per metric ton")
    currency: str = Field(description="Contract currency, e.g., 'EUR' or 'USD'")
    energy_adder_percentage: float = Field(description="Percentage adder on base price for energy")
    raw_material_adder_percentage: float = Field(description="Percentage adder on base price for raw materials")
    min_monthly_volume_tons: float = Field(description="Minimum delivery volume per month in tons")
    max_monthly_volume_tons: float = Field(description="Maximum delivery volume per month in tons")
    max_transport_duration_days: int = Field(description="Maximum allowed transport/lead time in days")
    payment_terms_days: int = Field(description="Payment terms after delivery in days, e.g., 30, 60")
    min_shelf_life_days: int = Field(description="Minimum required shelf life upon delivery in days")
    demurrage_days_included: int = Field(description="Free container holding / demurrage days included")
    breach_penalty_amount: float = Field(description="Financial penalty amount for breach of contract or short delivery")
    force_majeure_clause: str = Field(description="Brief summary of Force Majeure conditions")

class ChemicalDataset(BaseModel):
    contracts: List[ChemicalContract]

# 2. Initialize OpenAI client
openai_client = OpenAI()

# 3. Define the prompt for generating diverse B2B contracts
prompt = """
Generate a realistic dataset of 50 diverse B2B supply chain contracts in the chemical industry 
between a major chemical producer and various industrial clients. 
Ensure high variance across parameters: some contracts should have strict penalties and fixed prices, 
others flexible volume ranges (min/max), energy/raw material adders, and tight logistical constraints 
like short shelf life or limited demurrage days.
""".strip()

print("Generiere Verträge über OpenAI API...")
completion = openai_client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": prompt}],
    response_format=ChemicalDataset,
)

dataset = completion.choices[0].message.parsed
contracts = dataset.contracts

# 4. Speichern als CSV/Excel (wie bisher)
df = pd.DataFrame([contract.model_dump() for contract in contracts])
os.makedirs("data", exist_ok=True)
df.to_csv("data/chemical_contracts.csv", index=False)

# 5. NEU: Automatisch Markdown-Dateien für jedes Contract erstellen
contracts_dir = "data/contracts"
os.makedirs(contracts_dir, exist_ok=True)

for c in contracts:
    md_content = f"""# MASTER AGREEMENT FOR CHEMICAL SALES ({c.contract_id})

This Master Agreement for Chemical Sales ("Agreement") is entered into by and between CarbonFree Chemicals SPE I LLC and **{c.customer_name}**.

## 1. Scope, Pricing & Dynamic Adders
- **Product:** {c.product_name}
- **Base Price:** {c.base_price} {c.currency} per metric ton.
- **Volume Commitments:** Minimum monthly volume of {c.min_monthly_volume_tons} tons up to a maximum of {c.max_monthly_volume_tons} tons.
- **Energy Adder:** {c.energy_adder_percentage}% surcharge on base price for energy fluctuations.
- **Raw Material Adder:** {c.raw_material_adder_percentage}% surcharge on base price for raw material cost adjustments.
- **Payment Terms:** Net {c.payment_terms_days} days from the date of invoice.

## 2. Logistical Constraints & Terms
- **Max Transport Duration:** {c.max_transport_duration_days} days.
- **Minimum Shelf Life:** {c.min_shelf_life_days} days upon delivery.
- **Demurrage / Free Container Days:** {c.demurrage_days_included} days included.

## 3. Breach of Contract and Penalties
In the event of a material breach, short delivery, or failure to meet the agreed minimum monthly volume without a valid justification, the defaulting party shall be subject to a liquidated financial penalty of **{c.breach_penalty_amount} {c.currency}**.

## 4. Force Majeure Clauses
{c.force_majeure_clause}

## 5. Governing Law
This Agreement shall be governed by and construed in accordance with the laws of the State of Texas, without regard to conflict of law principles.
"""
    file_path = os.path.join(contracts_dir, f"{c.contract_id}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

print(f"Erfolgreich {len(contracts)} Verträge als CSV und als Markdown-Dateien in '{contracts_dir}/' generiert!")