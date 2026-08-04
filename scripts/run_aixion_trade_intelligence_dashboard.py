from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dashboard_input_not_object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the read-only Aixion dashboard.")
    parser.add_argument("--session-report", required=True)
    parser.add_argument("--campaign-report")
    args = parser.parse_args()
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError("streamlit_not_installed") from exc
    session = _load(args.session_report)
    campaign = _load(args.campaign_report) if args.campaign_report else None
    st.set_page_config(page_title="Aixion Trade Intelligence", layout="wide")
    st.title("Aixion Trade Intelligence")
    st.caption("Read-only evidence dashboard. No broker or execution authority.")
    manifest = session.get("manifest") if isinstance(session.get("manifest"), dict) else {}
    funnel = session.get("candidate_funnel") if isinstance(session.get("candidate_funnel"), dict) else {}
    readiness = session.get("outcome_readiness") if isinstance(session.get("outcome_readiness"), dict) else {}
    first, second, third, fourth = st.columns(4)
    first.metric("Session", manifest.get("session_id") or "unknown")
    second.metric("Verdict", manifest.get("verdict") or "unknown")
    third.metric("Events", manifest.get("event_count") or 0)
    fourth.metric("Candidates", funnel.get("candidate_count") or 0)
    st.subheader("Data truth")
    st.json(manifest)
    st.subheader("Candidate funnel")
    st.json(funnel)
    st.subheader("Outcome readiness")
    st.json(readiness)
    st.subheader("Runtime timeline")
    st.dataframe(session.get("runtime_timeline") or [], use_container_width=True)
    if campaign is not None:
        st.subheader("Multi-session campaign")
        st.json(campaign)
    st.warning("Dashboard evidence is diagnostic. It does not certify profitability, promote strategies, or place orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
