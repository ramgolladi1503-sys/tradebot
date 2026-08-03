"""Standalone Streamlit UI for citation-first TradeBot evidence search."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.tradebot_rag import ask_index, default_index_path, index_status
from core.tradebot_rag_operations import BuildLockError, build_index_safely, doctor_index

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = default_index_path(REPO_ROOT)

st.set_page_config(page_title="TradeBot Evidence RAG", layout="wide")
st.title("TradeBot Evidence RAG")
st.caption(
    "Read-only repository evidence search. Answers are extracted from indexed sources and include line citations. "
    "This tool does not produce trade recommendations or call broker APIs."
)

with st.sidebar:
    st.subheader("Index")
    status = index_status(INDEX_PATH)
    if status.get("exists"):
        st.success(f"{status['document_count']} documents / {status['chunk_count']} chunks")
        st.caption(f"Last built: {status.get('last_built_at_utc') or 'unknown'}")
    else:
        st.warning("Index not built")

    if st.button("Build / refresh index", use_container_width=True):
        try:
            with st.spinner("Indexing README.md, docs/, and research/..."):
                report = build_index_safely(REPO_ROOT, INDEX_PATH)
        except BuildLockError as exc:
            st.error(str(exc))
        else:
            st.success(
                f"Indexed {report.indexed_files}; unchanged {report.unchanged_files}; "
                f"removed {report.removed_files}; chunks {report.chunk_count}."
            )
            st.rerun()

    if st.button("Run integrity check", use_container_width=True, disabled=not status.get("exists")):
        with st.spinner("Checking index integrity..."):
            doctor = doctor_index(INDEX_PATH)
        if doctor.healthy:
            st.success("Index integrity is healthy.")
        else:
            failed = [check.name for check in doctor.checks if not check.passed]
            st.error("Integrity failed: " + ", ".join(failed))
        with st.expander("Integrity details"):
            st.json(doctor.to_dict())

    top_k = st.slider("Retrieved evidence", min_value=3, max_value=15, value=8)
    path_prefix = st.selectbox("Limit sources", ("All", "docs", "research", "README.md"))

question = st.text_area(
    "Question",
    placeholder="Example: Why was a strategy rejected, and which evidence supports the verdict?",
    height=110,
)
ask = st.button("Search evidence", type="primary", disabled=not question.strip())

if ask:
    if not INDEX_PATH.exists():
        st.error("Build the index first.")
    else:
        prefix = None if path_prefix == "All" else path_prefix
        answer = ask_index(INDEX_PATH, question, top_k=top_k, path_prefix=prefix)
        if answer.refusal_reason:
            st.warning(answer.answer)
        else:
            st.markdown(answer.answer)
        st.caption(f"Retrieval confidence: {answer.confidence}")

        st.subheader("Retrieved evidence")
        for hit in answer.hits:
            title = f"{hit.path}:L{hit.start_line}-L{hit.end_line} · score {hit.score:.3f}"
            with st.expander(title):
                if hit.section:
                    st.caption(f"Section: {hit.section}")
                st.code(hit.text, language=None)
