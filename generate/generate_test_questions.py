import os, random, json, glob
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

CSV_PATH = "data/chemical_contracts.csv"
MD_PATH = "data/contracts"


def ask(prompt):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        response_format={"type": "json_object"}
    )
    return json.loads(r.choices[0].message.content)


def load_docs():
    return {
        os.path.splitext(os.path.basename(p))[0]:
        open(p, encoding="utf-8").read()
        for p in glob.glob(f"{MD_PATH}/*.md")
    }


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
        "currency"
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
        "penalty-focused"
    ]

    while len(dataset) < n:

        route = random.choice(
            ["structured", "unstructured", "hybrid"]
        )
        style = random.choice(styles)

        # ============================================================
        # STRUCTURED
        # ============================================================
        if route == "structured":

            row = df.sample(1).iloc[0]
            ids = [row.contract_id]
            context = row.to_dict()

            q = ask(f"""
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
- Use only information contained in the CSV.

Return JSON:
{{
    "question": "...",
    "field": "one field from the allowed list"
}}
""")

            field = q["field"]

            if field not in structured_fields:
                continue

            item = {
                "question": q["question"],
                "route": "structured",
                "valid_contract_ids": ids,
                "ground_truth": {
                    "type": "csv",
                    "field": field,
                    "data": context[field]
                }
            }

        # ============================================================
        # UNSTRUCTURED
        # ============================================================
        elif route == "unstructured":

            row = df.sample(1).iloc[0]
            ids = [row.contract_id]
            context = docs.get(row.contract_id, "")

            if not context:
                continue

            q = ask(f"""
Generate ONE realistic supply-chain user question.

Route: unstructured
Style: {style}

The question MUST require information from the contract text.
Do not ask for CSV-only fields such as price, volume, adders,
penalties or customer name unless that information is explicitly
part of the contract text.

Do not mention Contract IDs.
Use only the supplied contract.

Return JSON:
{{"question":"..."}}

CONTRACT:
{context}
""")

            item = {
                "question": q["question"],
                "route": "unstructured",
                "valid_contract_ids": ids
            }

        # ============================================================
        # HYBRID
        # ============================================================
        else:

            selected = df.sample(2)
            ids = selected.contract_id.tolist()

            context = [
                {
                    "csv": selected[
                        selected.contract_id == contract_id
                    ].to_dict("records")[0],
                    "md": docs.get(contract_id, "")
                }
                for contract_id in ids
            ]

            if any(not x["md"] for x in context):
                continue

            q = ask(f"""
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

            item = {
                "question": q["question"],
                "route": "hybrid",
                "valid_contract_ids": ids
            }

        # ============================================================
        # SAVE
        # ============================================================
        dataset.append(item)

        print(f"{len(dataset)}/{n}")

    with open("evaluation/evaluation_questions.json", "w", encoding="utf-8") as f:
        json.dump(
            dataset,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"✅ {len(dataset)} questions saved.")


if __name__ == "__main__":
    generate_questions()