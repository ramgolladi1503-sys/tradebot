from __future__ import annotations

import streamlit as st

from config import config as cfg
from dashboard.loaders import (
    load_depth_snapshot,
    load_events,
    load_execution_analytics,
    load_feed_state,
    load_gemini_state,
    load_health_gate_report,
    load_reconciliation,
    load_risk_state,
)
from dashboard.renderers import (
    render_depth,
    render_execution,
    render_feed,
    render_gemini,
    render_recon,
    render_risk,
)


def _resolve_desk_id() -> str:
    query_desk = st.query_params.get("desk") if hasattr(st, "query_params") else None
    return str(query_desk or getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")


def main() -> None:
    st.set_page_config(page_title="Axiom Quant Console", layout="wide")
    desk_id = _resolve_desk_id()
    st.title("Axiom Quant Console")
    st.caption(f"Desk: {desk_id}")

    health_vm = load_health_gate_report(desk_id)
    events_vm = load_events(desk_id)
    recon_vm = load_reconciliation(desk_id)
    execution_vm = load_execution_analytics(desk_id)
    depth_vm = load_depth_snapshot(desk_id)
    feed_vm = load_feed_state(desk_id)
    risk_vm = load_risk_state(desk_id)
    gemini_vm = load_gemini_state(desk_id)

    tabs = st.tabs(
        [
            "Execution",
            "Reconciliation",
            "Depth",
            "Feed",
            "Risk",
            "Gemini",
            "Health",
            "Events",
        ]
    )

    with tabs[0]:
        render_execution(execution_vm)
    with tabs[1]:
        render_recon(recon_vm)
    with tabs[2]:
        render_depth(depth_vm)
    with tabs[3]:
        render_feed(feed_vm)
    with tabs[4]:
        render_risk(risk_vm)
    with tabs[5]:
        render_gemini(gemini_vm)
    with tabs[6]:
        render_feed(health_vm)
    with tabs[7]:
        if events_vm.status in {"missing", "error"}:
            st.caption(events_vm.message or "Events artifact unavailable.")
        elif events_vm.status == "empty":
            st.caption(events_vm.message or "No events found.")
        else:
            st.caption(f"Rows: {len(events_vm.rows)} | Path: {events_vm.path}")
            st.dataframe(events_vm.rows[-200:], use_container_width=True, hide_index=True)

