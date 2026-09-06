import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv()
client = OpenAI()


def evaluate_answer(question, reference, answer, route):

    if route == "structured":
        prompt = f"""
Evaluate the generated answer against the deterministic ground truth.

QUESTION:
{question}

GROUND TRUTH:
{json.dumps(reference, ensure_ascii=False)}

GENERATED ANSWER:
{json.dumps(answer, ensure_ascii=False)}

Rules:
- CORRECT = answer matches the ground truth.
- PARTLY_CORRECT = some information is correct, but information is missing or wrong.
- INCORRECT = answer is materially wrong.
- Do not use outside knowledge.

Return JSON:
{{
    "evaluation": "CORRECT",
    "explanation": "brief explanation"
}}
"""

    else:
        prompt = f"""
Evaluate whether the generated answer correctly answers the question
and is supported by the reference answer and evidence.

QUESTION:
{question}

REFERENCE ANSWER:
{json.dumps(reference["answer"], ensure_ascii=False)}

REFERENCE EVIDENCE:
{json.dumps(reference["evidence"], ensure_ascii=False)}

GENERATED ANSWER:
{json.dumps(answer, ensure_ascii=False)}

Rules:
- RELEVANT = answer correctly addresses the question and is supported
  by the reference answer/evidence.
- PARTLY_RELEVANT = answer is partly correct but misses important
  information or contains some incorrect information.
- NOT_RELEVANT = answer is materially wrong, unsupported, or does not
  answer the question.
- Do not use outside knowledge.
- Do not judge wording or style.

Return JSON:
{{
    "evaluation": "RELEVANT",
    "explanation": "brief explanation"
}}
"""

    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"}
    )

    return json.loads(r.choices[0].message.content)


def generated_answer_for(item, live):
    if not live:
        return item["answer"]

    from src.margin_checker.rag import rag

    result = rag(item["question"])
    return result["answer"]


def evaluate(live=False):

    with open(ROOT / "evaluation" / "evaluation_dataset.json", encoding="utf-8") as f:
        tests = json.load(f)

    results = {
        "structured": [],
        "unstructured": [],
        "hybrid": []
    }

    for item in tests:

        route = item["route"]

        if route == "structured":
            if "ground_truth" not in item:
                continue

            reference = item["ground_truth"]

        else:
            if "answer" not in item or "evidence" not in item:
                continue

            reference = {
                "answer": item["answer"],
                "evidence": item["evidence"]
            }

        generated = generated_answer_for(item, live=live)

        evaluation = evaluate_answer(
            item["question"],
            reference,
            generated,
            route
        )

        results[route].append(evaluation["evaluation"])

        print(
            f"{route:<12} | "
            f"{evaluation['evaluation']:<18} | "
            f"{item['question']}"
        )

    print("\n" + "=" * 55)
    print("ANSWER EVALUATION" + (" (LIVE RAG)" if live else " (STORED ANSWERS)"))
    print("=" * 55)

    for route, evaluations in results.items():

        if not evaluations:
            continue

        print(f"\n{route.upper()}")

        labels = (
            ["CORRECT", "PARTLY_CORRECT", "INCORRECT"]
            if route == "structured"
            else ["RELEVANT", "PARTLY_RELEVANT", "NOT_RELEVANT"]
        )

        total = len(evaluations)

        for label in labels:
            count = evaluations.count(label)
            print(
                f"  {label:<18}: "
                f"{count}/{total} "
                f"({100 * count / total:.1f}%)"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate stored dataset answers or the live RAG pipeline."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run the live RAG pipeline for each question instead of judging stored answers.",
    )
    args = parser.parse_args()
    evaluate(live=args.live)
