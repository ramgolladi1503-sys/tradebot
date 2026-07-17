from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="TradeBot Agentic Research", layout="wide")
st.title("TradeBot Agentic Strategy Research")
st.caption("Read-only manager + independent critic + deterministic judge. No broker or order authority.")
repo_root = Path(st.text_input("TradeBot repository root", ".")).expanduser().resolve()
runs_root = repo_root / "agentic_research" / "runs"
if not runs_root.exists():
    st.info("No research runs found.")
    st.stop()
run_ids = sorted([path.name for path in runs_root.iterdir() if path.is_dir()], reverse=True)
selected = st.selectbox("Research run", run_ids)
run_dir = runs_root / selected
files = sorted(run_dir.glob("*.json"))
st.write({"research_id": selected, "artifact_count": len(files), "read_only": True})
summary_tab, critic_tab, trace_tab, artifacts_tab = st.tabs(["Decision", "Independent critic", "Trace", "Artifacts"])
with summary_tab:
    path = run_dir / "certification_result.json"
    st.json(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else st.info("Decision not produced yet.")
with critic_tab:
    path = run_dir / "run_adversarial_review.json"
    st.json(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else st.info("Critic not run yet.")
with trace_tab:
    path = run_dir / "trace.jsonl"
    if path.exists():
        st.dataframe([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()], use_container_width=True)
    else:
        st.info("No trace events yet.")
with artifacts_tab:
    for path in files:
        with st.expander(path.name):
            st.json(json.loads(path.read_text(encoding="utf-8")))
