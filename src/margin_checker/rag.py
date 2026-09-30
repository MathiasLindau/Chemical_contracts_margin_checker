import json
import os
import time

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from src.margin_checker.router import classify_query
from src.margin_checker.retrieval import (
    run_hybrid,
    get_cached_chunks,
    hybrid_text_contract_ids,
)
from src.margin_checker.daily_prices import (
    attach_history_comparison,
    history_gap_summary,
    load_price_history,
    load_structured_frame,
)
try:
    from src.margin_checker.history_price import (
        looks_open,
        needs_history,
        prepare_history_spec,
        combine_hybrid_answer,
        render_rows,
        run_history_query,
        sort_by_number,
        spec_from_model_json,
        threshold_mask,
    )
except ImportError:
    def looks_open(query):
        return False

    def needs_history(query):
        return False

    def prepare_history_spec(query, specification):
        return None

    def combine_hybrid_answer(rendered, clause):
        clause = str(clause or "").strip()
        if rendered and clause:
            return str(rendered) + "\n\n" + clause
        return rendered or clause or None

    def render_rows(rows, query=""):
        return None

    def run_history_query(*args, **kwargs):
        return []

    def sort_by_number(frame, column, ascending):
        return frame.sort_values(by=column, ascending=ascending, na_position="last")

    def spec_from_model_json(payload, query=""):
        return None

    def threshold_mask(frame, column, operation, value):
        return None
from src.margin_checker.structured import (
    STRUCTURED_ROW_CAP,
    apply_catalog_filters,
    cap_structured_rows,
)
from src.margin_checker.rerank import rerank_results
from src.margin_checker.sources import split_primary_secondary


load_dotenv()

client = OpenAI(timeout=45.0, max_retries=1)

EMPTY_ANSWER = (
    "The context does not provide specific information on areas where money can be saved. "
    "Therefore, I cannot identify potential savings."
)

FACT_KEYS = (
    "indicative_price_per_ton",
    "base_price",
    "period_value",
    "baseline_value",
    "change",
    "raw_gap_per_ton",
    "raw_gap_at_max_volume",
    "raw_gap_per_ton_mean",
    "energy_gap_per_ton_mean",
    "energy_amount",
    "raw_amount",
    "financing_per_ton",
    "logistics_amount",
    "average",
    "sum",
    "count",
    "usd_trip_now",
    "usd_trip_at_index",
    "price_latest",
    "price_earlier",
    "uplift_vs_base",
)

MODEL = "gpt-4o-mini"
RRF_CANDIDATES = 10
RERANK_TOP_K = 3


# --------------------------------------------------
# Cost calculation
# --------------------------------------------------

def calculate_cost(usage):
    if usage is None:
        return 0.0
    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0
    return prompt / 1_000_000 * 0.15 + completion / 1_000_000 * 0.60


class EmptyUsage:
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0


def _empty_usage():
    return EmptyUsage()


def _accumulate(bucket, usage):
    if usage is None:
        return
    bucket["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
    bucket["completion"] += getattr(usage, "completion_tokens", 0) or 0
    bucket["cost"] += calculate_cost(usage)


def _as_int(value, default):
    try:
        if value is None or str(value).strip().lower() in {"", "null", "none"}:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _row_has_fact(row):
    if not isinstance(row, dict) or row.get("error"):
        return False
    if str(row.get("chunk_text") or "").strip():
        return True
    for key in FACT_KEYS:
        value = row.get(key)
        if value is None or value == "":
            continue
        return True
    return False


def _has_context(results):
    if isinstance(results, dict):
        rows = list(results.get("structured") or []) + list(results.get("text") or [])
    elif isinstance(results, list):
        rows = results
    else:
        return False
    for row in rows:
        if _row_has_fact(row):
            return True
    return False


def _safe_text_search(query, documents, contract_ids):
    try:
        if not documents:
            return []
        found = run_hybrid(
            query,
            documents,
            num_results=RRF_CANDIDATES,
            contract_ids=contract_ids,
        )
        return rerank_results(query, found, top_k=RERANK_TOP_K) or []
    except Exception:
        return []


# --------------------------------------------------
# Structured query interpretation
# --------------------------------------------------

def interpret_structured_query(query):

    try:
        return _interpret_structured_query(query)
    except Exception:
        return {}, _empty_usage()


def _interpret_structured_query(query):

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
- indicative_price_per_ton
- price_date
- energy_amount
- raw_amount
- financing_per_ton
- logistics_amount
- price_change
- uplift_vs_base
- raw_gap
- energy_gap
- raw_gap_at_max_volume
- eurusd

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
- compare_periods
- period_stats

Rules:

- "highest", "most expensive", "largest" → top_n
- "lowest", "cheapest", "smallest" → bottom_n
- "highest price", "lowest price", "base price", "contract price" → field = base_price, unless the question compares today's price with that base
- "today's price", "current price", "price per ton", "what is the price" → field = indicative_price_per_ton
- "price date", "as of", "which day" → field = price_date
- "versus the base price", "compared with the contract price", "uplift", "gegenüber dem Basispreis" on today's price only → field = uplift_vs_base, compare_to = base
- A past day, yesterday, last month, a month, a year, an average, or a difference between two times → operation = compare_periods
- period is the focus, often the later time. baseline_period is the earlier time.
- "yesterday" / "gestern" → period = latest, baseline_period = yesterday
- "previous day" → period = latest, baseline_period = previous
- "last month" / "letzter Monat" → period = this_month, baseline_period = last_month
- "April vs May" → period = april, baseline_period = may
- "2025 vs 2024" → period = 2025, baseline_period = 2024
- "average" / "Durchschnitt" → aggregation = mean
- "which customer saved" on raw material versus the 2023 index → field = raw_gap, group_by = customer_name, operation = bottom_n
- If the question also says volume → field = raw_gap_at_max_volume
- Maize versus Brent versus no raw index → field = raw_gap, group_by = raw_instrument, operation = period_stats
- EURUSD, exchange rate, or logistics in EUR versus USD → field = eurusd, group_by = currency, baseline_period = index_2023
- Never use operation "compare". Use compare_periods.
- A named single date on today's table only, with no month or year comparison → compare_to = that date as YYYY-MM-DD
- price_change, raw_gap, and uplift_vs_base are ton-price movements, not profit.
- financing_per_ton only when the question asks about financing, interest, or the cost of the payment term
- logistics_amount only when the question asks about logistics, transport, freight, or the trip
- Do not add financing_per_ton or logistics_amount to indicative_price_per_ton
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
- If the question names a product, set product_name.
- If the question names a customer, set customer_name.
- If the question names a currency, set currency.
- lookup MUST include product_name or customer_name.
- Never use lookup to return the entire catalog.

Return ONLY valid JSON:

{
    "field": "base_price",
    "operation": "top_n",
    "n": 3,
    "value": null,
    "product_name": null,
    "customer_name": null,
    "currency": null,
    "compare_to": null,
    "period": null,
    "baseline_period": null,
    "aggregation": null,
    "group_by": null,
    "raw_instrument": null
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

    try:
        return _find_structured_contracts(query)
    except Exception:
        return [], _empty_usage()


def _find_structured_contracts(query):

    df = load_structured_frame()

    specification, usage = interpret_structured_query(query)
    prepared = prepare_history_spec(query, specification)
    if prepared is None and looks_open(query):
        prepared = spec_from_model_json({"operation": "cost_scan"}, query)
    if prepared is not None:
        return run_history_query(
            load_price_history(),
            prepared,
            contracts=df,
            query=query,
        ), usage

    field = specification["field"]
    operation = specification["operation"]
    n = specification.get("n")
    value = specification.get("value")

    working = apply_catalog_filters(df, specification, query)

    # ----------------------------------------------
    # Create calculated fields
    # ----------------------------------------------

    if field in ("price_change", "uplift_vs_base"):
        compare_to = "base" if field == "uplift_vs_base" else specification.get("compare_to")
        working = attach_history_comparison(working, load_price_history(), compare_to)
        if field == "price_change" and operation != "lookup":
            gap = history_gap_summary(working)
            if gap is not None:
                gap["scope"] = "filtered" if len(working) < len(df) else "all_contracts"
                return [gap], usage

    if field == "overall_adder":

        working = working.copy()
        working["_overall_adder"] = (
            working["energy_adder_percentage"]
            + working["raw_material_adder_percentage"]
        )

        sort_field = "_overall_adder"

    else:

        sort_field = field

    # ----------------------------------------------
    # Validate field
    # ----------------------------------------------

    if sort_field not in working.columns:
        return [], usage

    scoped = len(working) < len(df)

    def aggregation_row(payload):
        row = dict(payload)
        row["n_contracts"] = int(len(working))
        row["scope"] = "filtered" if scoped else "all_contracts"
        if scoped and len(working) <= STRUCTURED_ROW_CAP:
            row["contract_ids"] = [
                str(item) for item in working["contract_id"].tolist()
            ]
        return [row]

    # ----------------------------------------------
    # Minimum
    # ----------------------------------------------

    if operation == "min":

        if working.empty:
            results = []
        else:
            result = sort_by_number(working, sort_field, ascending=True).iloc[0]
            results = [
                result.to_dict()
            ]

    # ----------------------------------------------
    # Maximum
    # ----------------------------------------------

    elif operation == "max":

        if working.empty:
            results = []
        else:
            result = sort_by_number(working, sort_field, ascending=False).iloc[0]
            results = [
                result.to_dict()
            ]

    # ----------------------------------------------
    # Bottom N
    # ----------------------------------------------

    elif operation == "bottom_n":

        n = _as_int(n, 1)

        results = (
            sort_by_number(working, sort_field, ascending=True)
            .head(n)
            .to_dict(orient="records")
        )

    # ----------------------------------------------
    # Top N
    # ----------------------------------------------

    elif operation == "top_n":

        n = _as_int(n, 1)

        results = (
            sort_by_number(working, sort_field, ascending=False)
            .head(n)
            .to_dict(orient="records")
        )

    # ----------------------------------------------
    # Filter above
    # ----------------------------------------------

    elif operation == "filter_above":

        mask = threshold_mask(working, sort_field, operation, value)
        if mask is None:
            results = [{
                "error": "threshold_not_numeric",
                "field": field,
                "value": value,
                "message": "The comparison value has to be a number.",
            }]
        else:
            matched = sort_by_number(working.loc[mask], sort_field, ascending=False)
            results = cap_structured_rows(
                matched.to_dict(orient="records"),
                match_count=len(matched),
            )

    # ----------------------------------------------
    # Filter below
    # ----------------------------------------------

    elif operation == "filter_below":

        mask = threshold_mask(working, sort_field, operation, value)
        if mask is None:
            results = [{
                "error": "threshold_not_numeric",
                "field": field,
                "value": value,
                "message": "The comparison value has to be a number.",
            }]
        else:
            matched = sort_by_number(working.loc[mask], sort_field, ascending=True)
            results = cap_structured_rows(
                matched.to_dict(orient="records"),
                match_count=len(matched),
            )

    # ----------------------------------------------
    # Average
    # ----------------------------------------------

    elif operation == "average":

        series = pd.to_numeric(working[sort_field], errors="coerce")
        results = aggregation_row({
            "field": field,
            "average": float(series.mean()) if series.notna().any() else None,
        })

    # ----------------------------------------------
    # Sum
    # ----------------------------------------------

    elif operation == "sum":

        series = pd.to_numeric(working[sort_field], errors="coerce")
        results = aggregation_row({
            "field": field,
            "sum": float(series.sum()) if series.notna().any() else None,
        })

    # ----------------------------------------------
    # Count
    # ----------------------------------------------

    elif operation == "count":

        results = aggregation_row({
            "count": int(pd.to_numeric(working[sort_field], errors="coerce").count()),
        })

    # ----------------------------------------------
    # Lookup
    # ----------------------------------------------

    elif operation == "lookup":

        if len(working) == len(df):
            results = [{
                "error": "lookup_requires_entity",
                "message": (
                    "Lookup did not name a product or customer, "
                    "so the full catalog was not returned."
                ),
            }]
        else:
            results = cap_structured_rows(
                working.to_dict(orient="records"),
                match_count=len(working),
            )

    else:

        results = [{
            "error": "unsupported_operation",
            "operation": operation,
            "message": f"Unsupported structured operation: {operation}",
        }]

    # ----------------------------------------------
    # Add explicit ranking
    # ----------------------------------------------

    if operation in ["top_n", "bottom_n"]:

        for rank, result in enumerate(results, 1):
            if isinstance(result, dict):
                result["_rank"] = rank

    return results, usage


# --------------------------------------------------
# Final answer generation
# --------------------------------------------------

def _structured_rows(results):
    if isinstance(results, dict):
        return list(results.get("structured") or [])
    if isinstance(results, list):
        return results
    return []


def generate_answer(query, route, results):

    if route != "unstructured":
        rendered = render_rows(_structured_rows(results), query)
        text_rows = list(results.get("text") or []) if isinstance(results, dict) else []
        if rendered and (route == "structured" or not text_rows):
            return rendered, _empty_usage(), 0.0
        if route == "structured":
            return EMPTY_ANSWER, _empty_usage(), 0.0

    if not _has_context(results):
        return EMPTY_ANSWER, _empty_usage(), 0.0

    try:
        answer, usage, cost = _generate_answer(query, route, results)
        if route == "hybrid":
            rendered = render_rows(_structured_rows(results), query)
            answer = combine_hybrid_answer(rendered, answer) or answer
        return answer, usage, cost
    except Exception:
        rendered = render_rows(_structured_rows(results), query)
        return rendered or EMPTY_ANSWER, _empty_usage(), 0.0


def _generate_answer(query, route, results):

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
        ) or (
            "(No contract-text search. Structured result is an aggregation "
            "or catalog-wide set; clauses from other agreements were not used.)"
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

If the context has no usable number and no contract text, answer exactly:
The context does not provide specific information on areas where money can be saved. Therefore, I cannot identify potential savings.

Be concise and specific.
Mention contract IDs when relevant.

For structured questions, respect the ranking and values
provided in the context.
The ton price is indicative_price_per_ton.
Mention financing_per_ton only when the question asks about financing or the payment term.
Mention logistics_amount only when the question asks about transport or logistics.
Do not add financing or logistics to the ton price.
price_change is the latest indicative_price_per_ton minus the earlier day in contract_price_history.
uplift_vs_base is the latest indicative price minus the contract base_price.
For a history row, period_value and baseline_value are the aggregates for those periods.
change is period_value minus baseline_value.
raw_gap_per_ton is the raw-material amount minus the contract percentage at the January 2023 index. Negative means a lower raw-material cost.
raw_gap_at_max_volume is that per-ton gap times max_monthly_volume_tons.
EURUSD changes only the USD logistics trip. Do not convert the ton price.
Prefer these history rows over contract text for prices, adders, and exchange rates.
A cost scan has sections. price_fell_vs_previous_day and price_rose_vs_previous_day compare today's ton price with the previous stored day.
raw_material_below_index lists raw-material cost below the January 2023 index.
Say which section a number comes from.
All of these are movements of price or cost, not a profit margin.
If history_note is present, repeat it and do not invent a missing period.

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

    try:
        return _evaluate_relevance(question, answer, route, sources)
    except Exception:
        return {
            "relevance": "UNKNOWN",
            "explanation": "Judge skipped.",
        }, _empty_usage()


def _evaluate_relevance(question, answer, route, sources):

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


def _use_llm_judge(with_judge):
    if with_judge is not None:
        return bool(with_judge)
    return os.getenv("RAG_LLM_JUDGE", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _collect_sources(route, results):
    if isinstance(results, dict):
        return list(results.get("text") or []) + list(results.get("structured") or [])
    if isinstance(results, list):
        return results
    return []


def _safe_failure():
    return {
        "answer": EMPTY_ANSWER,
        "sources": [],
        "primary_sources": [],
        "secondary_sources": [],
        "route": "structured",
        "response_time": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost": 0.0,
        "relevance": "UNKNOWN",
        "relevance_explanation": "Query failed safely.",
    }


def rag(query, with_judge=None):
    try:
        return _run_rag(query, with_judge)
    except Exception:
        return _safe_failure()


def _run_rag(query, with_judge=None):

    start = time.perf_counter()
    bucket = {"prompt": 0, "completion": 0, "cost": 0.0}
    route = "structured"
    results = []
    answer = EMPTY_ANSWER
    evaluation = {
        "relevance": "UNKNOWN",
        "explanation": "",
    }

    # --------------------------------------------------
    # 1. Query routing. A failed route still continues.
    # --------------------------------------------------

    try:
        route, usage = classify_query(query)
        _accumulate(bucket, usage)
    except Exception:
        route = "structured"

    try:
        if route != "structured" and needs_history(query):
            route = "structured"
    except Exception:
        pass

    # --------------------------------------------------
    # 2. Retrieval. An empty stage does not stop the next one.
    # --------------------------------------------------

    try:
        if route == "structured":
            results, usage = find_structured_contracts(query)
            _accumulate(bucket, usage)
        else:
            try:
                documents = get_cached_chunks()
            except Exception:
                documents = []

            if route == "unstructured":
                results = _safe_text_search(query, documents, None)
            else:
                try:
                    structured_results, usage = find_structured_contracts(query)
                    _accumulate(bucket, usage)
                except Exception:
                    structured_results = []
                text_results = []
                if documents and structured_results:
                    try:
                        restrict_ids = hybrid_text_contract_ids(
                            structured_results,
                            query=query,
                            catalog=load_structured_frame(),
                        )
                    except Exception:
                        restrict_ids = []
                    if restrict_ids:
                        text_results = _safe_text_search(query, documents, restrict_ids)
                results = {
                    "structured": structured_results or [],
                    "text": text_results or [],
                }
    except Exception:
        results = []

    # --------------------------------------------------
    # 3. Answer. No usable rows means the standard sentence.
    # --------------------------------------------------

    if _has_context(results):
        try:
            answer, usage, _cost = generate_answer(query, route, results)
            _accumulate(bucket, usage)
            if not str(answer or "").strip():
                answer = EMPTY_ANSWER
        except Exception:
            answer = EMPTY_ANSWER
    else:
        answer = EMPTY_ANSWER

    # --------------------------------------------------
    # 4. Judge. A failed judge keeps the answer.
    # --------------------------------------------------

    judge_sources = _collect_sources(route, results)
    if _has_context(results) and _use_llm_judge(with_judge):
        try:
            evaluation, eval_usage = evaluate_relevance(
                query,
                answer,
                route,
                judge_sources,
            )
            _accumulate(bucket, eval_usage)
        except Exception:
            evaluation = {
                "relevance": "UNKNOWN",
                "explanation": "Judge skipped.",
            }
    elif not _use_llm_judge(with_judge):
        evaluation = {
            "relevance": "NOT_EVALUATED",
            "explanation": "LLM judge skipped (RAG_LLM_JUDGE=0).",
        }

    # --------------------------------------------------
    # 5. Sources
    # --------------------------------------------------

    try:
        primary_sources, secondary_sources = split_primary_secondary(
            answer,
            judge_sources,
        )
    except Exception:
        primary_sources, secondary_sources = [], []

    return {
        "answer": answer,
        "sources": primary_sources + secondary_sources,
        "primary_sources": primary_sources,
        "secondary_sources": secondary_sources,
        "route": route,
        "response_time": time.perf_counter() - start,
        "prompt_tokens": bucket["prompt"],
        "completion_tokens": bucket["completion"],
        "total_tokens": bucket["prompt"] + bucket["completion"],
        "cost": bucket["cost"],
        "relevance": evaluation.get("relevance", "UNKNOWN"),
        "relevance_explanation": evaluation.get("explanation", ""),
    }