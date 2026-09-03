import os
import json
import glob
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
        temperature=0,
        response_format={"type": "json_object"}
    )

    content = r.choices[0].message.content

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print("❌ Invalid JSON returned by LLM:")
        print(content[:3000])
        raise


def load_docs():
    return {
        os.path.splitext(os.path.basename(p))[0]:
        open(p, encoding="utf-8").read()
        for p in glob.glob(f"{MD_PATH}/*.md")
    }


def generate_answers():

    df = pd.read_csv(CSV_PATH)
    docs = load_docs()

    with open("evaluation_questions.json", encoding="utf-8") as f:
        dataset = json.load(f)

    for i, item in enumerate(dataset, 1):

        question = item["question"]
        route = item["route"]
        ids = item["valid_contract_ids"]

        print(f"\n[{i}/{len(dataset)}] {question}")

        # ============================================================
        # STRUCTURED
        # Ground Truth kommt direkt aus CSV.
        # KEIN LLM.
        # ============================================================
        if route == "structured":

            gt = item["ground_truth"]

            field = gt["field"]
            answer = gt["data"]

            item["answer"] = answer
            item["evidence"] = {
                "field": field,
                "value": answer
            }

            print(f"✓ Structured: {field} = {answer}")

        # ============================================================
        # UNSTRUCTURED
        # LLM extrahiert ausschließlich aus MD.
        # ============================================================
        elif route == "unstructured":

            data = {
                contract_id: docs.get(contract_id, "")
                for contract_id in ids
            }

            result = ask(f"""
Extract the answer to the question using ONLY the supplied
contract text.

Question:
{question}

Contract text:
{json.dumps(data, ensure_ascii=False)}

Rules:
- Use ONLY the contract text.
- Do not use outside knowledge.
- Do not invent information.
- Do not make assumptions.
- Do not calculate.
- Do not give recommendations.
- Only state information explicitly supported by the contract.
- If the information is not stated, say so.
- Evidence must directly support the answer.

Return JSON:
{{
    "answer": "...",
    "evidence": "..."
}}
""")

            item["answer"] = result["answer"]
            item["evidence"] = result["evidence"]

            print("✓ Unstructured answer generated")

        # ============================================================
        # HYBRID
        # LLM verwendet CSV + MD.
        # ============================================================
        elif route == "hybrid":

            data = {}

            for contract_id in ids:

                csv_rows = df[
                    df["contract_id"] == contract_id
                ].to_dict("records")

                md_text = docs.get(contract_id, "")

                if not csv_rows or not md_text:
                    print(
                        f"⚠️ Missing data for {contract_id}. Skipping."
                    )
                    data = None
                    break

                data[contract_id] = {
                    "csv": csv_rows[0],
                    "md": md_text
                }

            if data is None:
                continue

            result = ask(f"""
Answer the question using ONLY the supplied CSV and
contract text.

Question:
{question}

Data:
{json.dumps(data, ensure_ascii=False)}

Rules:
- Use ONLY the supplied data.
- Do not use outside knowledge.
- Do not invent information.
- Do not make assumptions.
- Do not introduce exchange rates.
- Do not invent calculations.
- Both contracts must be considered.
- Every statement must be supported by the supplied data.
- Evidence must directly support the answer.
- If information is missing, say so.

Return JSON:
{{
    "answer": "...",
    "evidence": "..."
}}
""")

            item["answer"] = result["answer"]
            item["evidence"] = result["evidence"]

            print("✓ Hybrid answer generated")

        else:
            print(f"⚠️ Unknown route: {route}")
            continue

    # ================================================================
    # SAVE
    # ================================================================
    with open("evaluation/evaluation_dataset.json", "w", encoding="utf-8") as f:
        json.dump(
            dataset,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\n✅ Answers saved to evaluation_dataset.json")


if __name__ == "__main__":
    generate_answers()