"""Compare two answer-generation prompts on gold documents.

This is the course "LLM evaluation" row: two approaches, keep the winner.

It does **not** run retrieval. Each question gets the markdown (and CSV
rows, for hybrid) of `valid_contract_ids` — a perfect retriever — so the
score is about the prompt, not BM25/RRF.

    python evaluation/evaluate_llm.py

Needs OPENAI_API_KEY. About 30 unstructured + hybrid questions × 2
generations × 1 judge each. Skip structured (those answers come from Pandas).

The live app keeps `concise` unless you set RAG_ANSWER_PROMPT=extractive.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv()

ANSWER_PROMPT_CONCISE = "concise"
ANSWER_PROMPT_EXTRACTIVE = "extractive"

CSV_PATH = ROOT / "data" / "chemical_contracts.csv"
MD_PATH = ROOT / "data" / "contracts"
DATASET_PATH = ROOT / "evaluation" / "evaluation_dataset.json"
DEFAULT_OUT = ROOT / "evaluation" / "llm_prompt_comparison.json"

TEXT_ROUTES = ("unstructured", "hybrid")
POSITIVE = {
    "structured": "CORRECT",
    "unstructured": "RELEVANT",
    "hybrid": "RELEVANT",
}


def load_markdown():
    docs = {}
    for path in glob.glob(str(MD_PATH / "*.md")):
        contract_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as handle:
            docs[contract_id] = handle.read()
    return docs


def gold_context(item, docs, catalog):
    ids = [str(cid) for cid in item.get("valid_contract_ids") or []]
    texts = []
    for cid in ids:
        body = docs.get(cid)
        if body:
            texts.append(f"Contract: {cid}\n{body}")
    contract_text = "\n\n".join(texts) or "(No contract text found.)"

    if item.get("route") != "hybrid":
        return contract_text

    rows = catalog[
        catalog["contract_id"].astype(str).isin(ids)
    ].to_dict(orient="records")
    return (
        "STRUCTURED DATA:\n"
        + json.dumps(rows, default=str, indent=2)
        + "\n\nCONTRACT TEXT:\n"
        + contract_text
    )


def reference_for(item):
    route = item["route"]
    if route == "structured":
        return item["ground_truth"]
    return {
        "answer": item["answer"],
        "evidence": item["evidence"],
    }


def is_positive(route, label):
    return str(label).upper() == POSITIVE[route]


def summarize(rows, styles):
    by_style = {style: [] for style in styles}
    for row in rows:
        by_style[row["style"]].append(row)

    summary = {}
    for style, items in by_style.items():
        total = len(items)
        wins = sum(1 for row in items if row["positive"])
        summary[style] = {
            "n": total,
            "positive": wins,
            "rate": (wins / total) if total else 0.0,
        }
    return summary


def evaluate(limit=None, out_path=DEFAULT_OUT):
    from evaluation.evaluate_answer import evaluate_answer
    from src.margin_checker.rag import generate_answer_from_context

    with open(DATASET_PATH, encoding="utf-8") as handle:
        dataset = json.load(handle)

    items = [
        item for item in dataset
        if item.get("route") in TEXT_ROUTES
        and "answer" in item
        and "evidence" in item
        and item.get("valid_contract_ids")
    ]
    if limit is not None:
        items = items[:limit]

    docs = load_markdown()
    catalog = pd.read_csv(CSV_PATH)
    styles = [ANSWER_PROMPT_CONCISE, ANSWER_PROMPT_EXTRACTIVE]
    rows = []

    print("=" * 55)
    print("LLM PROMPT COMPARISON (gold documents, no retrieval)")
    print("=" * 55)

    for i, item in enumerate(items, 1):
        question = item["question"]
        route = item["route"]
        context = gold_context(item, docs, catalog)
        reference = reference_for(item)

        print(f"\n[{i}/{len(items)}] {route} | {question}")

        for style in styles:
            answer, _usage, _cost = generate_answer_from_context(
                question,
                context,
                style=style,
            )
            judgement = evaluate_answer(
                question,
                reference,
                answer,
                route,
            )
            label = judgement["evaluation"]
            row = {
                "question": question,
                "route": route,
                "style": style,
                "evaluation": label,
                "positive": is_positive(route, label),
                "explanation": judgement.get("explanation", ""),
            }
            rows.append(row)
            print(f"  {style:<12} {label}")

    summary = summarize(rows, styles)
    winner = max(styles, key=lambda name: (summary[name]["rate"], name == ANSWER_PROMPT_CONCISE))

    print("\n" + "=" * 55)
    print("SUMMARY")
    print("=" * 55)
    for style in styles:
        stats = summary[style]
        print(
            f"  {style:<12} {stats['positive']}/{stats['n']} "
            f"positive ({100 * stats['rate']:.1f}%)"
        )
    print(f"\nWinner: {winner}")
    print("The running app uses concise (RAG_ANSWER_PROMPT=concise).")
    print("\nMarkdown for README:\n")
    print(markdown_table(summary))

    payload = {
        "winner": winner,
        "kept_in_app": ANSWER_PROMPT_CONCISE,
        "summary": summary,
        "rows": rows,
    }
    out_path = Path(out_path)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return payload


def markdown_table(summary):
    lines = [
        "| Prompt | Positive (RELEVANT) | Rate |",
        "|---|---:|---:|",
    ]
    for style, stats in summary.items():
        lines.append(
            f"| {style} | {stats['positive']}/{stats['n']} | "
            f"{100 * stats['rate']:.1f}% |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare concise vs extractive answer prompts."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only the first N unstructured/hybrid questions (smoke test).",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Where to write JSON results.",
    )
    args = parser.parse_args()
    evaluate(limit=args.limit, out_path=args.out)
