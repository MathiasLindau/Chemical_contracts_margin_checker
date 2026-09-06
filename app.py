# app.py

import streamlit as st

from src.margin_checker.rag import rag
from src.margin_checker.db import (
    init_monitoring_table,
    save_query_log,
    save_feedback,
    load_query_history,
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


# --------------------------------------------------
# History
# --------------------------------------------------

try:
    init_monitoring_table()
    history = load_query_history(limit=20)
except Exception as exc:
    history = []
    st.warning(
        "Database is not ready yet. Start Postgres and check DB_CONN. "
        f"({exc})"
    )

if history:

    with st.expander("Query History"):

        for log_id, created_at, old_question, old_answer in history:

            st.markdown(
                f"**{created_at.strftime('%Y-%m-%d %H:%M')}**  \n"
                f"{old_question}"
            )

            with st.expander("View answer"):
                st.write(old_answer)

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

        except Exception as e:

            st.error(f"An error occurred: {e}")
            st.stop()


# --------------------------------------------------
# Current result
# --------------------------------------------------

result = st.session_state.result


if result is not None:

    # --------------------------------------------------
    # Answer
    # --------------------------------------------------

    st.subheader("Answer")

    st.write(result["answer"])


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


    # --------------------------------------------------
    # Sources
    # --------------------------------------------------

    def source_label(source, index):

        contract_id = source.get("contract_id")

        if "score" in source and contract_id:

            parts = [f"RRF: {source['score']:.5f}"]
            reranker_score = source.get("reranker_score")
            if reranker_score is not None:
                parts.append(f"Reranker: {reranker_score:.4f}")

            return f"{contract_id} ({', '.join(parts)})"

        if contract_id:
            return f"{contract_id} (structured)"

        return f"Structured Result {index}"

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