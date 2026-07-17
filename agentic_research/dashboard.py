from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="TradeBot Agentic Research", layout="wide")
st.title("TradeBot Agentic Strategy Research")
st.caption("Read-only research and certification sidecar. No broker or order authority.")
repo_root = Path(st.text_input("TradeBot repository root", ".")).expanduser().resolve()
runs_root = repo_root / "agentic_research" / "runs"
if not runs_root.exists():
    st.info("No research runs found.")
else:
    run_ids = sorted([path.name for path in runs_root.iterdir() if path.is_dir()], reverse=True)
    selected = st.selectbox("Research run", run_ids)
    run_dir = runs_root / selected
    files = sorted(run_dir.glob("*.json"))
    st.write({"research_id": selected, "artifact_count": len(files), "read_only": True})
    for path in files:
        with st.expander(path.name, expanded=path.name in {"certification_result.json", "certification_bundle.json"}):
            st.json(json.loads(path.read_text(encoding="utf-8")))
