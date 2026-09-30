# app.py

import streamlit as st

from src.margin_checker.rag import rag
from src.margin_checker.history_price import split_rendered_answer
from src.margin_checker.sources import (
    RERANK_TABLE_NOTE,
    rerank_applies_to_chunks,
    source_label,
)
from src.margin_checker.db import (
    HISTORY_LIMIT,
    init_monitoring_table,
    save_query_log,
    save_feedback,
    load_query_history,
    delete_query_log,
    delete_all_query_logs,
    format_created_at,
)


# --------------------------------------------------
# Page configuration
# --------------------------------------------------

st.set_page_config(
    page_title="Chemical Contracts Margin Checker",
    layout="wide"
)


# --------------------------------------------------
# Session state
# --------------------------------------------------

if "log_id" not in st.session_state:
    st.session_state.log_id = None

if "result" not in st.session_state:
    st.session_state.result = None

if "feedback" not in st.session_state:
    st.session_state.feedback = None


# --------------------------------------------------
# Header
# --------------------------------------------------

st.title("Chemical Contracts Margin Checker")

st.write(
    "Analyze chemical supply contracts using "
    "structured data and contract text."
)


def show_answer(answer):
    """Render a structured HTML table. Clause text stays markdown."""
    html_block, prose = split_rendered_answer(answer)
    if html_block:
        st.markdown(html_block, unsafe_allow_html=True)
    if prose:
        st.write(prose)


# --------------------------------------------------
# History
# --------------------------------------------------

try:
    init_monitoring_table()
    history = load_query_history(limit=HISTORY_LIMIT)
except Exception as exc:
    history = []
    st.warning(
        "Database is not ready yet. Start Postgres and check DB_CONN. "
        f"({exc})"
    )

if history:

    with st.expander(f"Query History (last {len(history)})"):

        if st.button("Clear history", key="clear_history"):
            delete_all_query_logs()
            st.rerun()

        for log_id, created_at, old_question, old_answer in history:

            time_col, delete_col = st.columns([6, 1])

            with time_col:
                st.markdown(
                    f"**{format_created_at(created_at)}**  \n"
                    f"{old_question}"
                )

            with delete_col:
                if st.button("Delete", key=f"delete_{log_id}"):
                    delete_query_log(log_id)
                    st.rerun()

            with st.expander("View answer"):
                show_answer(old_answer)

            st.divider()


# --------------------------------------------------
# Question
# --------------------------------------------------

question = st.text_area(
    "Your question",
    placeholder=(
        "e.g. What happens if the supplier "
        "fails to deliver the agreed quantity?"
    ),
    height=100
)


# --------------------------------------------------
# Analyze
# --------------------------------------------------

if st.button("Analyze", type="primary"):

    if not question.strip():

        st.warning("Please enter a question.")
        st.stop()

    with st.spinner("Analyzing contracts..."):

        try:

            result = rag(question)

            # Save query, metrics and LLM evaluation
            log_id = save_query_log(
                question=question,
                answer=result["answer"],
                route=result["route"],
                response_time=result["response_time"],
                prompt_tokens=result["prompt_tokens"],
                completion_tokens=result["completion_tokens"],
                total_tokens=result["total_tokens"],
                cost=result["cost"],
                relevance=result["relevance"],
                relevance_explanation=result["relevance_explanation"],
            )

            # Keep result and log ID across Streamlit reruns
            st.session_state.result = result
            st.session_state.log_id = log_id

            # Reset feedback for the new answer
            st.session_state.feedback = None

        except Exception:
            st.session_state.result = {
                "answer": (
                    "The context does not provide specific information on areas where money can be saved. "
                    "Therefore, I cannot identify potential savings."
                ),
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
            st.session_state.log_id = None
            st.session_state.feedback = None


# --------------------------------------------------
# Current result
# --------------------------------------------------

result = st.session_state.result


if result is not None:

    # --------------------------------------------------
    # Answer
    # --------------------------------------------------

    st.subheader("Answer")

    show_answer(result["answer"])


    # --------------------------------------------------
    # Metrics
    # --------------------------------------------------

    st.divider()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Route",
            result["route"].capitalize()
        )

    with col2:
        st.metric(
            "Analysis time",
            f"{result['response_time']:.2f} s"
        )

    with col3:
        st.metric(
            "Total tokens",
            f"{result['total_tokens']:,}"
        )

    with col4:
        st.metric(
            "Cost",
            f"${result['cost']:.6f}"
        )

    relevance = result.get("relevance")
    if relevance and relevance != "NOT_EVALUATED":
        explanation = result.get("relevance_explanation") or ""
        st.caption(f"LLM judge: {relevance}. {explanation}".strip())
    elif relevance == "NOT_EVALUATED":
        st.caption("LLM judge skipped (set RAG_LLM_JUDGE=1 to enable).")


    # --------------------------------------------------
    # Sources
    # --------------------------------------------------

    def render_sources(title, sources):

        if not sources:
            return

        st.subheader(title)

        for i, source in enumerate(sources, start=1):

            with st.expander(source_label(source, i)):

                if "chunk_text" in source:
                    st.write(source["chunk_text"])
                else:
                    st.json(source)

    primary = result.get("primary_sources")
    secondary = result.get("secondary_sources")
    if primary is None and secondary is None:
        listed = list(result.get("sources") or [])
    else:
        listed = list(primary or []) + list(secondary or [])

    if result.get("route") == "structured" and not rerank_applies_to_chunks(listed):
        st.caption(RERANK_TABLE_NOTE)

    if primary is None and secondary is None:
        render_sources("Sources", result["sources"])
    else:
        render_sources("Primary sources (used in the answer)", primary)
        render_sources("Secondary sources (also retrieved)", secondary)


    # --------------------------------------------------
    # Feedback
    # --------------------------------------------------

    st.divider()

    st.subheader("Was this answer helpful?")

    feedback = st.feedback(
        "thumbs",
        key="feedback_widget"
    )

    if (
        feedback is not None
        and feedback != st.session_state.feedback
    ):

        save_feedback(
            st.session_state.log_id,
            feedback
        )

        st.session_state.feedback = feedback

        st.caption("Feedback recorded.")