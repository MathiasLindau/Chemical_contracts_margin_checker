import json
import time

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from src.margin_checker.router import classify_query
from src.margin_checker.retrieval import run_hybrid
from src.margin_checker.rerank import rerank_results
from src.margin_checker.db import load_contract_chunks


load_dotenv()

client = OpenAI()

CSV_PATH = "data/chemical_contracts.csv"
MODEL = "gpt-4o-mini"
RRF_CANDIDATES = 10
RERANK_TOP_K = 3


# --------------------------------------------------
# Cost calculation
# --------------------------------------------------

def calculate_cost(usage):
    return (
        usage.prompt_tokens / 1_000_000 * 0.15
        + usage.completion_tokens / 1_000_000 * 0.60
    )


# --------------------------------------------------
# Structured query interpretation
# --------------------------------------------------

def interpret_structured_query(query):

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": """
You convert a structured chemical contract question
into a deterministic Pandas operation.

Available fields:

- base_price
- energy_adder_percentage
- raw_material_adder_percentage
- overall_adder
- min_monthly_volume_tons
- max_monthly_volume_tons
- max_transport_duration_days
- payment_terms_days
- min_shelf_life_days
- demurrage_days_included
- breach_penalty_amount
- customer_name
- product_name
- currency

Allowed operations:

- lookup
- min
- max
- top_n
- bottom_n
- filter_above
- filter_below
- average
- sum
- count

Rules:

- "highest", "most expensive", "largest" → top_n
- "lowest", "cheapest", "smallest" → bottom_n
- "highest price" → field = base_price
- "lowest price" → field = base_price
- "highest adder" → field = overall_adder
- "lowest adder" → field = overall_adder
- "overall adder" means:
  energy_adder_percentage + raw_material_adder_percentage
- "highest volume" → field = max_monthly_volume_tons
- "lowest volume" → field = min_monthly_volume_tons
- "above X" → filter_above
- "below X" → filter_below
- "average" → average
- "total" → sum
- "how many" → count
- Use n=null if not required.
- Use value=null if not required.

Return ONLY valid JSON:

{
    "field": "base_price",
    "operation": "top_n",
    "n": 3,
    "value": null
}
"""
            },
            {
                "role": "user",
                "content": query
            }
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )

    result = json.loads(
        response.choices[0].message.content
    )

    return result, response.usage


# --------------------------------------------------
# Deterministic structured retrieval
# --------------------------------------------------

def find_structured_contracts(query):

    df = pd.read_csv(CSV_PATH)

    specification, usage = interpret_structured_query(query)

    field = specification["field"]
    operation = specification["operation"]
    n = specification.get("n")
    value = specification.get("value")

    # ----------------------------------------------
    # Create calculated fields
    # ----------------------------------------------

    if field == "overall_adder":

        df["_overall_adder"] = (
            df["energy_adder_percentage"]
            + df["raw_material_adder_percentage"]
        )

        sort_field = "_overall_adder"

    else:

        sort_field = field

    # ----------------------------------------------
    # Validate field
    # ----------------------------------------------

    if sort_field not in df.columns:

        raise ValueError(
            f"Invalid structured field: {field}"
        )

    # ----------------------------------------------
    # Minimum
    # ----------------------------------------------

    if operation == "min":

        result = df.loc[
            df[sort_field].idxmin()
        ]

        results = [
            result.to_dict()
        ]

    # ----------------------------------------------
    # Maximum
    # ----------------------------------------------

    elif operation == "max":

        result = df.loc[
            df[sort_field].idxmax()
        ]

        results = [
            result.to_dict()
        ]

    # ----------------------------------------------
    # Bottom N
    # ----------------------------------------------

    elif operation == "bottom_n":

        n = int(n or 1)

        results = (
            df.sort_values(
                by=sort_field,
                ascending=True
            )
            .head(n)
            .to_dict(orient="records")
        )

    # ----------------------------------------------
    # Top N
    # ----------------------------------------------

    elif operation == "top_n":

        n = int(n or 1)

        results = (
            df.sort_values(
                by=sort_field,
                ascending=False
            )
            .head(n)
            .to_dict(orient="records")
        )

    # ----------------------------------------------
    # Filter above
    # ----------------------------------------------

    elif operation == "filter_above":

        results = (
            df[df[sort_field] > value]
            .sort_values(
                by=sort_field,
                ascending=False
            )
            .to_dict(orient="records")
        )

    # ----------------------------------------------
    # Filter below
    # ----------------------------------------------

    elif operation == "filter_below":

        results = (
            df[df[sort_field] < value]
            .sort_values(
                by=sort_field,
                ascending=True
            )
            .to_dict(orient="records")
        )

    # ----------------------------------------------
    # Average
    # ----------------------------------------------

    elif operation == "average":

        results = [{
            "field": field,
            "average": float(
                df[sort_field].mean()
            )
        }]

    # ----------------------------------------------
    # Sum
    # ----------------------------------------------

    elif operation == "sum":

        results = [{
            "field": field,
            "sum": float(
                df[sort_field].sum()
            )
        }]

    # ----------------------------------------------
    # Count
    # ----------------------------------------------

    elif operation == "count":

        results = [{
            "count": int(
                df[sort_field].count()
            )
        }]

    # ----------------------------------------------
    # Lookup
    # ----------------------------------------------

    elif operation == "lookup":

        results = df.to_dict(
            orient="records"
        )

    else:

        raise ValueError(
            f"Unsupported structured operation: {operation}"
        )

    # ----------------------------------------------
    # Add explicit ranking
    # ----------------------------------------------

    if operation in ["top_n", "bottom_n"]:

        for rank, result in enumerate(results, 1):
            result["_rank"] = rank

    return results, usage


# --------------------------------------------------
# Final answer generation
# --------------------------------------------------

def generate_answer(query, route, results):

    if route == "structured":

        context = json.dumps(
            results,
            default=str,
            indent=2
        )

    elif route == "unstructured":

        context = "\n\n".join(
            f"Contract: {r['contract_id']}\n{r['chunk_text']}"
            for r in results
        )

    else:

        structured = json.dumps(
            results["structured"],
            default=str,
            indent=2
        )

        text = "\n\n".join(
            f"Contract: {r['contract_id']}\n{r['chunk_text']}"
            for r in results["text"]
        )

        context = (
            f"STRUCTURED DATA:\n{structured}\n\n"
            f"CONTRACT TEXT:\n{text}"
        )

    prompt = f"""
You are a contract analysis assistant for procurement
and supply-chain professionals.

Answer the question based ONLY on the provided context.

Do not invent information.

If the context is insufficient, say so.

Be concise and specific.
Mention contract IDs when relevant.

For structured questions, respect the ranking and values
provided in the context.

QUESTION:
{query}

CONTEXT:
{context}
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    usage = response.usage

    return (
        response.choices[0].message.content,
        usage,
        calculate_cost(usage)
    )


# --------------------------------------------------
# LLM-as-a-Judge
# --------------------------------------------------

def evaluate_relevance(question, answer, route, sources):

    # --------------------------------------------------
    # Prepare sources for evaluation
    # --------------------------------------------------

    if route == "structured":

        source_context = "\n\n".join(
            json.dumps(
                source,
                default=str,
                indent=2
            )
            for source in sources
        )

    elif route == "unstructured":

        source_context = "\n\n".join(
            f"Contract: {source['contract_id']}\n"
            f"{source['chunk_text']}"
            for source in sources
        )

    else:

        # --------------------------------------------------
        # Hybrid sources contain two different structures:
        #
        # 1. Text sources:
        #    contract_id + chunk_text
        #
        # 2. Structured sources:
        #    CSV fields such as contract_id,
        #    customer_name, volume, penalty, etc.
        #
        # Therefore we must not assume that every
        # hybrid source contains chunk_text.
        # --------------------------------------------------

        source_parts = []

        for source in sources:

            if "chunk_text" in source:

                source_parts.append(
                    f"Contract: {source['contract_id']}\n"
                    f"{source['chunk_text']}"
                )

            else:

                source_parts.append(
                    json.dumps(
                        source,
                        default=str,
                        indent=2
                    )
                )

        source_context = "\n\n".join(
            source_parts
        )

    prompt = f"""
You are an expert evaluator for a contract RAG system.

Evaluate whether the generated answer:

1. correctly answers the user's question,
2. is supported by the retrieved sources,
3. does not contradict the retrieved sources.

Use ONLY the question, retrieved sources, and generated answer.
Do not use outside knowledge.

Classify the answer as exactly one of:

RELEVANT
PARTLY_RELEVANT
NON_RELEVANT

ROUTE:
{route}

QUESTION:
{question}

RETRIEVED SOURCES:
{source_context}

GENERATED ANSWER:
{answer}

Return ONLY valid JSON:

{{
    "relevance": "RELEVANT",
    "explanation": "brief explanation"
}}
"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )

    try:

        evaluation = json.loads(
            response.choices[0].message.content
        )

    except json.JSONDecodeError:

        evaluation = {
            "relevance": "UNKNOWN",
            "explanation": "Failed to parse evaluation."
        }

    return evaluation, response.usage


# --------------------------------------------------
# Complete RAG pipeline
# --------------------------------------------------

def rag(query):

    start = time.perf_counter()

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    total_cost = 0.0

    # --------------------------------------------------
    # 1. Query routing
    # --------------------------------------------------

    route, usage = classify_query(query)

    total_prompt_tokens += usage.prompt_tokens
    total_completion_tokens += usage.completion_tokens
    total_tokens += usage.total_tokens
    total_cost += calculate_cost(usage)

    # --------------------------------------------------
    # 2. Retrieval
    # --------------------------------------------------

    if route == "structured":

        results, usage = find_structured_contracts(query)

        total_prompt_tokens += usage.prompt_tokens
        total_completion_tokens += usage.completion_tokens
        total_tokens += usage.total_tokens
        total_cost += calculate_cost(usage)

    else:

        documents = load_contract_chunks()

        # --------------------------------------------------
        # Unstructured
        # BM25 + Vector + RRF → Cross-Encoder top 3
        # --------------------------------------------------

        if route == "unstructured":

            results = run_hybrid(
                query,
                documents,
                num_results=RRF_CANDIDATES
            )
            results = rerank_results(
                query,
                results,
                top_k=RERANK_TOP_K
            )

        # --------------------------------------------------
        # Hybrid
        # CSV + BM25 + Vector + RRF → Cross-Encoder top 3
        # Structured retrieval is unchanged.
        # --------------------------------------------------

        else:

            structured_results, usage = (
                find_structured_contracts(query)
            )

            total_prompt_tokens += usage.prompt_tokens
            total_completion_tokens += usage.completion_tokens
            total_tokens += usage.total_tokens
            total_cost += calculate_cost(usage)

            text_results = run_hybrid(
                query,
                documents,
                num_results=RRF_CANDIDATES
            )
            text_results = rerank_results(
                query,
                text_results,
                top_k=RERANK_TOP_K
            )

            results = {
                "structured": structured_results,
                "text": text_results
            }

    # --------------------------------------------------
    # 3. Generate final answer
    # --------------------------------------------------

    answer, usage, cost = generate_answer(
        query,
        route,
        results
    )

    total_prompt_tokens += usage.prompt_tokens
    total_completion_tokens += usage.completion_tokens
    total_tokens += usage.total_tokens
    total_cost += cost

    # --------------------------------------------------
    # 4. LLM Judge
    # --------------------------------------------------

    if route == "structured":

        judge_sources = results

    elif route == "unstructured":

        judge_sources = results

    else:

        judge_sources = (
            results["text"]
            + results["structured"]
        )

    evaluation, eval_usage = evaluate_relevance(
        query,
        answer,
        route,
        judge_sources
    )

    total_prompt_tokens += eval_usage.prompt_tokens
    total_completion_tokens += eval_usage.completion_tokens
    total_tokens += eval_usage.total_tokens
    total_cost += calculate_cost(eval_usage)

    # --------------------------------------------------
    # 5. Response time
    # --------------------------------------------------

    response_time = time.perf_counter() - start

    # --------------------------------------------------
    # 6. Sources
    # --------------------------------------------------

    if route == "structured":

        sources = results

    elif route == "unstructured":

        sources = results

    else:

        sources = (
            results["text"]
            + results["structured"]
        )

    # --------------------------------------------------
    # 7. Return
    # --------------------------------------------------

    return {
        "answer": answer,
        "sources": sources,
        "route": route,

        "response_time": response_time,

        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_tokens,

        "cost": total_cost,

        "relevance": evaluation.get(
            "relevance",
            "UNKNOWN"
        ),

        "relevance_explanation": evaluation.get(
            "explanation",
            ""
        )
    }