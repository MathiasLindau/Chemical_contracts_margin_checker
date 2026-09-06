"""Generate evaluation_questions.json from CSV + Markdown contracts.

This is a generator, not the published eval set. Running it overwrites
evaluation/evaluation_questions.json. Do not replace the checked-in
evaluation_dataset.json unless you also re-run answer generation and
re-check the hybrid adder math.
"""

import argparse
import glob
import json
import os
import random
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "chemical_contracts.csv"
MD_PATH = ROOT / "data" / "contracts"
OUT_PATH = ROOT / "evaluation" / "evaluation_questions.json"


def ask(prompt):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print("Invalid JSON returned by LLM:")
        print(content[:3000])
        raise


def load_docs():
    docs = {}
    for path in glob.glob(str(MD_PATH / "*.md")):
        contract_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as handle:
            docs[contract_id] = handle.read()
    return docs


def generate_questions(n=50):
    df = pd.read_csv(CSV_PATH)
    docs = load_docs()
    dataset = []

    structured_fields = [
        "base_price",
        "energy_adder_percentage",
        "raw_material_adder_percentage",
        "min_monthly_volume_tons",
        "max_monthly_volume_tons",
        "max_transport_duration_days",
        "payment_terms_days",
        "min_shelf_life_days",
        "demurrage_days_included",
        "breach_penalty_amount",
        "customer_name",
        "product_name",
        "currency",
    ]

    styles = [
        "simple",
        "specific",
        "vague",
        "informal",
        "1-2 typos",
        "paraphrased",
        "comparison",
        "cost-focused",
        "risk-focused",
        "customer-focused",
        "product-focused",
        "volume-focused",
        "adder-focused",
        "penalty-focused",
    ]

    while len(dataset) < n:

        route = random.choice(["structured", "unstructured", "hybrid"])
        style = random.choice(styles)

        if route == "structured":

            row = df.sample(1).iloc[0]
            ids = [row.contract_id]
            context = row.to_dict()

            question = ask(f"""
Generate ONE realistic supply-chain user question.

The question MUST be answerable using exactly ONE of these CSV fields:

{json.dumps(structured_fields, ensure_ascii=False)}

Selected contract data:
{json.dumps(context, ensure_ascii=False)}

Style:
{style}

Rules:
- Ask about exactly ONE CSV field.
- Do not require calculations.
- Do not require information from the MD contract.
- Do not combine multiple fields.
- Do not mention Contract IDs.
- Even if the style is "comparison", stay on one field of this one contract.
- Use only information contained in the CSV.

Return JSON:
{{
    "question": "...",
    "field": "one field from the allowed list"
}}
""")

            field = question.get("field")
            text = (question.get("question") or "").strip()
            if field not in structured_fields or not text:
                continue

            item = {
                "question": text,
                "route": "structured",
                "valid_contract_ids": ids,
                "ground_truth": {
                    "type": "csv",
                    "field": field,
                    "data": context[field],
                },
            }

        elif route == "unstructured":

            row = df.sample(1).iloc[0]
            ids = [row.contract_id]
            context = docs.get(row.contract_id, "")

            if not context:
                continue

            question = ask(f"""
Generate ONE realistic supply-chain user question.

Route: unstructured
Style: {style}

The question MUST require information from the contract text.
Do not ask for CSV-only fields such as price, volume, adders,
penalties or customer name unless that information is explicitly
part of the contract text.

Prefer clauses such as delivery failure, force majeure, shelf life,
demurrage, payment wording, or other narrative terms.

Do not mention Contract IDs.
Use only the supplied contract.

Return JSON:
{{"question":"..."}}

CONTRACT:
{context}
""")

            text = (question.get("question") or "").strip()
            if not text:
                continue

            item = {
                "question": text,
                "route": "unstructured",
                "valid_contract_ids": ids,
            }

        else:

            selected = df.sample(2)
            ids = selected.contract_id.tolist()

            context = [
                {
                    "csv": selected[
                        selected.contract_id == contract_id
                    ].to_dict("records")[0],
                    "md": docs.get(contract_id, ""),
                }
                for contract_id in ids
            ]

            if any(not item["md"] for item in context):
                continue

            question = ask(f"""
Generate ONE realistic supply-chain user question.

Route: hybrid
Style: {style}

The question MUST require:
1. information from the CSV,
2. information from the MD contract text,
3. information from BOTH selected contracts.

The question must not be answerable from CSV alone
or MD alone.

Do not mention Contract IDs.
Use only the supplied information.

Return JSON:
{{"question":"..."}}

DATA:
{json.dumps(context, ensure_ascii=False)}
""")

            text = (question.get("question") or "").strip()
            if not text:
                continue

            item = {
                "question": text,
                "route": "hybrid",
                "valid_contract_ids": ids,
            }

        dataset.append(item)
        print(f"{len(dataset)}/{n}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(dataset, handle, indent=2, ensure_ascii=False)

    print(f"{len(dataset)} questions saved to {OUT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate evaluation_questions.json (does not write answers)."
    )
    parser.add_argument("-n", type=int, default=50, help="Number of questions")
    args = parser.parse_args()
    generate_questions(n=args.n)
