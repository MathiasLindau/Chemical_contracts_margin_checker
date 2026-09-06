"""Fill answers/evidence for evaluation_questions.json.

Structured answers come from the CSV. Unstructured and hybrid answers
are extracted by the LLM from the supplied contracts only.

Running this overwrites evaluation/evaluation_dataset.json. The
checked-in dataset already has reviewed hybrid adder math; do not
replace it unless you re-check those calculations.
"""

import glob
import json
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "chemical_contracts.csv"
MD_PATH = ROOT / "data" / "contracts"
QUESTIONS_PATH = ROOT / "evaluation" / "evaluation_questions.json"
OUT_PATH = ROOT / "evaluation" / "evaluation_dataset.json"


def ask(prompt):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
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


def generate_answers():

    df = pd.read_csv(CSV_PATH)
    docs = load_docs()

    with open(QUESTIONS_PATH, encoding="utf-8") as handle:
        dataset = json.load(handle)

    completed = []

    for i, item in enumerate(dataset, 1):

        question = item["question"]
        route = item["route"]
        ids = item["valid_contract_ids"]

        print(f"\n[{i}/{len(dataset)}] {question}")

        if route == "structured":

            ground_truth = item["ground_truth"]
            field = ground_truth["field"]
            answer = ground_truth["data"]

            item["answer"] = answer
            item["evidence"] = {
                "field": field,
                "value": answer,
            }
            completed.append(item)
            print(f"Structured: {field} = {answer}")

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
            completed.append(item)
            print("Unstructured answer generated")

        elif route == "hybrid":

            data = {}

            for contract_id in ids:

                csv_rows = df[
                    df["contract_id"] == contract_id
                ].to_dict("records")

                md_text = docs.get(contract_id, "")

                if not csv_rows or not md_text:
                    print(f"Missing data for {contract_id}. Skipping.")
                    data = None
                    break

                data[contract_id] = {
                    "csv": csv_rows[0],
                    "md": md_text,
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
            completed.append(item)
            print("Hybrid answer generated")

        else:
            print(f"Unknown route: {route}")

    with open(OUT_PATH, "w", encoding="utf-8") as handle:
        json.dump(completed, handle, indent=2, ensure_ascii=False)

    print(f"\n{len(completed)} answers saved to {OUT_PATH}")


if __name__ == "__main__":
    generate_answers()
