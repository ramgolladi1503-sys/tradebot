from __future__ import annotations

from datetime import datetime
import pandas as pd
import streamlit as st

from config import config as cfg
from dashboard.loaders import load_events, load_feed_state, load_health_gate_report, load_reconciliation, load_risk_state
from dashboard.metrics_runtime import build_dashboard_metrics
from dashboard.operator_truth import load_index_series, load_market_state, load_strategy_monitor, load_top_opportunities, pipeline_pulse
from dashboard.upstox_option_chain_reader import load_upstox_option_chain_snapshot


def _status(obj) -> str:
    return str(getattr(obj, "status", "UNKNOWN") or "UNKNOWN").upper()


def _pill(state: str) -> str:
    return "●" if state.lower() in {"ok", "live", "fresh", "healthy", "pass", "safe"} else ("◌" if state.lower() == "unknown" else "○")


def _render_market_card(symbol: str, series: list[dict], state: dict) -> None:
    st.markdown(f"### {symbol}")
    if series:
        frame = pd.DataFrame(series)
        frame["time"] = pd.to_datetime(frame["ts"], unit="s")
        st.line_chart(frame.set_index("time")["price"], height=180)
        st.caption(f"KITE · {series[-1]['price']:.2f}")
    else:
        st.info("Kite index series unavailable")
    zone = str(state.get("zone") or "UNKNOWN")
    st.markdown(f"**{zone}**")
    levels = state.get("levels") or {}
    if zone == "BULLISH":
        trend, reversal = levels.get("bull_trend_price"), levels.get("bull_reversal_price")
    elif zone == "BEARISH":
        trend, reversal = levels.get("bear_trend_price"), levels.get("bear_reversal_price")
    else:
        trend = levels.get("bull_trend_price") or levels.get("bear_trend_price")
        reversal = levels.get("bull_reversal_price") or levels.get("bear_reversal_price")
    st.caption(f"Trend: {trend if trend is not None else '—'} · Reversal: {reversal if reversal is not None else '—'}")
    blockers = state.get("blockers") or []
    if blockers:
        st.caption("Blocked: " + ", ".join(map(str, blockers[:3])))


def _render_upstox_chain(snapshot) -> None:
    st.caption("SOURCE: UPSTOX · READ ONLY · independent of Kite/TradeBot runtime")
    if snapshot.status != "fresh":
        st.warning(f"Upstox option-chain snapshot: {snapshot.status}. {snapshot.message}")
        return
    roots = snapshot.payload.get("chains") or {}
    choices = [x for x in ("NIFTY", "BANKNIFTY", "SENSEX") if x in roots]
    root = st.selectbox("Underlying", choices) if choices else None
    if not root:
        st.caption("No option-chain rows in current snapshot.")
        return
    chain = roots[root]
    st.caption(f"Expiry: {chain.get('expiry', 'UNKNOWN')} · age: {snapshot.age_sec:.2f}s · source: UPSTOX FULL MODE")
    rows = chain.get("rows") or []
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No strike rows available.")


def main() -> None:
    st.set_page_config(page_title="TradeBot Operator Cockpit", layout="wide")
    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    feed = load_feed_state(desk_id)
    health = load_health_gate_report(desk_id)
    risk = load_risk_state(desk_id)
    upstox = load_upstox_option_chain_snapshot()
    metrics = build_dashboard_metrics(desk_id=desk_id)
    market_state = load_market_state()
    series = load_index_series(desk_id=desk_id)

    top_l, top_r = st.columns([4, 1])
    top_l.title("TradeBot")
    top_l.caption("Operator Cockpit · truth surfaces only")
    top_r.caption(datetime.now().astimezone().strftime("%H:%M:%S %Z"))

    statuses = [("KITE", _status(feed)), ("SYSTEM", _status(health)), ("RISK", _status(risk)), ("UPSTOX", upstox.status.upper())]
    st.caption("   ·   ".join(f"{_pill(s)} {n} {s}" for n, s in statuses))

    st.divider()
    state_rows = market_state.get("indices") or {}
    cols = st.columns(3)
    for col, symbol in zip(cols, ("NIFTY", "BANKNIFTY", "SENSEX")):
        with col:
            _render_market_card(symbol, series.get(symbol) or [], state_rows.get(symbol) or {})

    st.subheader("Pipeline Pulse")
    pulse = pipeline_pulse(feed_status=_status(feed), risk_status=_status(risk), market_state=market_state, metrics=metrics)
    pulse_cols = st.columns(len(pulse))
    for col, item in zip(pulse_cols, pulse):
        col.metric(item["stage"], item["state"], item["detail"])

    st.subheader("Top Opportunities")
    opportunities = load_top_opportunities(desk_id=desk_id)
    if opportunities:
        st.dataframe(opportunities[:10], use_container_width=True, hide_index=True)
    else:
        st.caption("No authoritative top opportunities in current runtime evidence.")

    left, right = st.columns(2)
    summary = metrics.get("summary") or {}
    with left:
        st.subheader("Candidate Funnel")
        funnel = summary.get("latest_pipeline_funnel") or {}
        funnel_rows = [
            {"stage": "Candidates", "count": summary.get("candidate_pool_latest", 0)},
            {"stage": "Ranked", "count": summary.get("ranked_candidate_count", 0)},
        ]
        for key in ("generated", "rejected", "eligible", "scored", "advisory"):
            if key in funnel:
                funnel_rows.append({"stage": key.title(), "count": funnel.get(key)})
        st.dataframe(funnel_rows, use_container_width=True, hide_index=True)
        rejection = metrics.get("rejection_reason_distribution") or []
        if rejection:
            st.caption("Top rejection reasons")
            st.dataframe(rejection[:8], use_container_width=True, hide_index=True)
    with right:
        st.subheader("Strategy Monitor")
        strategies = load_strategy_monitor(desk_id=desk_id)
        if strategies:
            st.dataframe(strategies[:20], use_container_width=True, hide_index=True)
        else:
            st.caption("No authoritative strategy activity in current runtime streams.")

    left, right = st.columns(2)
    with left:
        st.subheader("Kite / TradeBot Data")
        st.write(f"{_pill(_status(feed))} Feed: {_status(feed)}")
        st.write(f"{_pill(_status(health))} System: {_status(health)}")
        st.caption("Kite remains the operational TradeBot source.")
    with right:
        st.subheader("Upstox Capture")
        st.write(f"{_pill(upstox.status)} Snapshot: {upstox.status.upper()}")
        if upstox.age_sec is not None:
            st.write(f"Snapshot age: {upstox.age_sec:.2f}s")
        st.caption("Observation only. Upstox never substitutes for Kite health.")

    left, right = st.columns(2)
    with left:
        st.subheader("Risk / Safety")
        st.write(f"Risk surface: {_status(risk)}")
        st.write("Broker write authority: OFF")
        st.write("Order authority: OFF")
        st.write("Approval: MANUAL / governed runtime")
    with right:
        st.subheader("Session Analytics")
        st.metric("Candidates", int(summary.get("candidate_pool_latest") or 0))
        st.metric("Ranked", int(summary.get("ranked_candidate_count") or 0))
        denom = int(summary.get("advisory_conversion_denominator") or 0)
        if denom:
            st.metric("Advisory conversion", f"{100 * float(summary.get('advisory_to_execution_conversion_rate') or 0):.1f}%", help=str(summary.get("advisory_conversion_method") or ""))
        else:
            st.caption("No authoritative advisory-conversion population yet.")

    with st.expander("Upstox Option Chain", expanded=False):
        _render_upstox_chain(upstox)

    with st.expander("Engineering Diagnostics", expanded=False):
        st.caption("Legacy engineering surfaces are intentionally demoted from the operator view.")
        st.json({"metric_notes": metrics.get("notes") or [], "metric_sources": metrics.get("source_status") or {}, "market_state_source": market_state.get("_path")})


if __name__ == "__main__":
    main()
