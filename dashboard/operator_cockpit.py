from __future__ import annotations

import streamlit as st

from config import config as cfg
from dashboard.loaders import load_feed_state, load_health_gate_report, load_risk_state
from dashboard.metrics_runtime import build_dashboard_metrics
from dashboard.upstox_option_chain_reader import load_upstox_option_chain_snapshot


def _pill(label: str, state: str) -> str:
    good = str(state).lower() in {"ok", "live", "fresh", "healthy", "pass", "true"}
    return f"{'●' if good else '○'} {label}: {state}"


def _safe_attr(obj, name: str, default=None):
    return getattr(obj, name, default)


def _render_upstox_chain(snapshot) -> None:
    st.caption("SOURCE: UPSTOX · READ ONLY · independent of Kite/TradeBot runtime")
    if snapshot.status != "fresh":
        st.warning(f"Upstox option-chain snapshot: {snapshot.status}. {snapshot.message}")
        return
    payload = snapshot.payload
    roots = payload.get("chains") or {}
    root = st.selectbox("Underlying", [x for x in ("NIFTY", "BANKNIFTY", "SENSEX") if x in roots]) if roots else None
    if not root:
        st.caption("No option-chain rows in the current snapshot.")
        return
    chain = roots[root]
    st.caption(f"Expiry: {chain.get('expiry', 'UNKNOWN')} · snapshot age: {snapshot.age_sec:.2f}s")
    rows = chain.get("rows") or []
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No strike rows available.")


def main() -> None:
    st.set_page_config(page_title="TradeBot Operator Cockpit", layout="wide")
    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    st.title("TradeBot")
    st.caption("Operator Cockpit · truth surfaces only")

    feed = load_feed_state(desk_id)
    health = load_health_gate_report(desk_id)
    risk = load_risk_state(desk_id)
    upstox = load_upstox_option_chain_snapshot()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kite / Feed", str(_safe_attr(feed, "status", "UNKNOWN")).upper())
    c2.metric("System Health", str(_safe_attr(health, "status", "UNKNOWN")).upper())
    c3.metric("Risk", str(_safe_attr(risk, "status", "UNKNOWN")).upper())
    c4.metric("Upstox Capture", upstox.status.upper())

    st.divider()
    st.subheader("Market")
    market_cols = st.columns(3)
    for col, symbol in zip(market_cols, ("NIFTY", "BANKNIFTY", "SENSEX")):
        with col:
            st.markdown(f"### {symbol}")
            st.caption("Kite-backed chart/state adapter pending authoritative runtime binding")
            st.info("NO DISPLAY DATA" )

    st.subheader("Pipeline Pulse")
    st.code("KITE FEED → NORMALIZE → MARKET STATE → STRATEGIES → CANDIDATES → RANK → RISK → ADVISORY")
    st.caption("Checkpoint states remain fail-closed until each stage is bound to its authoritative runtime artifact.")

    st.subheader("Top Opportunities")
    try:
        metrics = build_dashboard_metrics()
        surfaced = metrics.get("surfaced_rows") or metrics.get("ranked_rows") or []
        if surfaced:
            st.dataframe(surfaced[:10], use_container_width=True, hide_index=True)
        else:
            st.caption("No authoritative surfaced opportunities in the current runtime evidence.")
    except Exception as exc:
        st.caption(f"Opportunity surface unavailable: {type(exc).__name__}")

    left, right = st.columns(2)
    with left:
        st.subheader("Kite / TradeBot")
        st.write(_pill("Feed", str(_safe_attr(feed, "status", "unknown"))))
        st.write(_pill("Health", str(_safe_attr(health, "status", "unknown"))))
        st.write(_pill("Risk", str(_safe_attr(risk, "status", "unknown"))))
    with right:
        st.subheader("Upstox Capture")
        st.write(_pill("Snapshot", upstox.status))
        st.caption("Observation only. Upstox health never substitutes for Kite health.")

    with st.expander("Upstox Option Chain", expanded=False):
        _render_upstox_chain(upstox)

    with st.expander("Engineering Diagnostics", expanded=False):
        st.caption("Legacy reconciliation, raw depth, events and debug surfaces remain diagnostics, not primary cockpit truth.")


if __name__ == "__main__":
    main()
