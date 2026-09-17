"""TradeBot Operator Cockpit (PR #914).
High-Density One-Viewport Trading Operator Terminal.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st
import altair as alt

from config import config as cfg
from dashboard.loaders import load_feed_state, load_health_gate_report, load_risk_state
from dashboard.metrics_runtime import load_runtime_metrics
from dashboard.operator_truth import (
    load_index_series,
    load_market_state,
    load_strategy_monitor,
    load_top_opportunities,
    pipeline_pulse,
    INDEX_SYMBOLS
)
from dashboard.upstox_option_chain_reader import load_upstox_option_chain_snapshot


def _status(obj) -> str:
    return str(getattr(obj, "status", "UNKNOWN") or "UNKNOWN").upper()


def _status_color(status_str: str) -> str:
    s = str(status_str).lower().strip()
    if s in {"ok", "live", "fresh", "healthy", "pass", "safe", "bullish"}:
        return "#26a69a"  # Teal / Green
    if s in {"warn", "warning", "stale", "partial", "sideways", "observed"}:
        return "#ffa726"  # Amber
    if s in {"fail", "blocked", "error", "bearish", "rejected", "incomplete"}:
        return "#ef5350"  # Red
    return "#90a4ae"  # Slate / Gray


def _pill_html(name: str, state: str) -> str:
    s = state.lower().strip()
    if s in {"ok", "live", "fresh", "healthy", "pass", "safe"}:
        cls = "status-pill-ok"
        symbol = "●"
    elif s in {"warn", "warning", "stale", "partial", "observed"}:
        cls = "status-pill-warn"
        symbol = "◌"
    elif s in {"fail", "blocked", "error", "incomplete"}:
        cls = "status-pill-err"
        symbol = "✕"
    else:
        cls = "status-pill-neutral"
        symbol = "○"
    return f"<span class='status-pill {cls}'>{symbol} {name}: {state.upper()}</span>"


def _render_market_panel(symbol: str, series: list[dict], state: dict) -> None:
    zone = str(state.get("zone") or "UNKNOWN").upper()
    levels = state.get("levels") or {}

    if zone == "BULLISH":
        trend = levels.get("bull_trend_price")
        reversal = levels.get("bull_reversal_price")
    elif zone == "BEARISH":
        trend = levels.get("bear_trend_price")
        reversal = levels.get("bear_reversal_price")
    else:
        trend = levels.get("bull_trend_price") or levels.get("bear_trend_price")
        reversal = levels.get("bull_reversal_price") or levels.get("bear_reversal_price")

    last_price_str = "—"
    pct_change_str = ""
    pct_color = "#90a4ae"

    df_chart = pd.DataFrame()
    if series:
        df_chart = pd.DataFrame(series)
        df_chart["time"] = pd.to_datetime(df_chart["ts"], unit="s")
        p_first = float(series[0]["price"])
        p_last = float(series[-1]["price"])
        last_price_str = f"{p_last:,.2f}"
        if p_first > 0:
            pct = ((p_last - p_first) / p_first) * 100.0
            sign = "+" if pct >= 0 else ""
            pct_change_str = f"{sign}{pct:.2f}%"
            pct_color = "#26a69a" if pct >= 0 else "#ef5350"

    zone_color = _status_color(zone)

    # Clean, high-density Header Hierarchy
    html_header = f"""
    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
        <span style="font-size: 1.05rem; font-weight: 800; letter-spacing: 0.05em; color: #eceff1;">{symbol}</span>
        <span style="font-size: 1.15rem; font-weight: 700; font-family: monospace; color: #ffffff;">{last_price_str}</span>
        <span style="font-size: 0.82rem; font-weight: 600; color: {pct_color};">{pct_change_str}</span>
        <span style="font-size: 0.72rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; background: {zone_color}22; color: {zone_color}; border: 1px solid {zone_color}66;">{zone}</span>
    </div>
    """
    st.markdown(html_header, unsafe_allow_html=True)

    # Altair Chart (Local scale, never flattened to 0)
    if not df_chart.empty and len(df_chart) > 1:
        p_min = df_chart["price"].min()
        p_max = df_chart["price"].max()
        p_padding = max(5.0, (p_max - p_min) * 0.15)

        y_scale = alt.Scale(domain=[p_min - p_padding, p_max + p_padding], zero=False)

        base = alt.Chart(df_chart).encode(
            x=alt.X("time:T", axis=alt.Axis(format="%H:%M", title=None, labels=True, ticks=False, domain=False, grid=False, labelFontSize=9, labelColor="#78909c")),
            y=alt.Y("price:Q", axis=alt.Axis(title=None, format=",.1f", orient="right", labelFontSize=9, labelColor="#78909c", grid=True, gridColor="#37474f33"), scale=y_scale)
        ).properties(height=120)

        line = base.mark_line(strokeWidth=1.8, color="#00e5ff" if pct_color == "#26a69a" else "#ff5252")
        chart_layers = [line]

        # Add trend / reversal rule overlays if within sensible range
        rules_data = []
        if trend is not None and (p_min - p_padding * 2 <= trend <= p_max + p_padding * 2):
            rules_data.append({"val": float(trend), "label": "Trend", "color": "#26a69a"})
        if reversal is not None and (p_min - p_padding * 2 <= reversal <= p_max + p_padding * 2):
            rules_data.append({"val": float(reversal), "label": "Reversal", "color": "#ef5350"})

        if rules_data:
            df_rules = pd.DataFrame(rules_data)
            rules = alt.Chart(df_rules).mark_rule(strokeDash=[3, 3], strokeWidth=1.2).encode(
                y="val:Q",
                color=alt.Color("color:N", scale=None)
            )
            chart_layers.append(rules)

        st.altair_chart(alt.layer(*chart_layers), use_container_width=True)
    else:
        st.info("Kite index series unavailable")

    trend_str = f"{trend:,.2f}" if trend is not None else "—"
    rev_str = f"{reversal:,.2f}" if reversal is not None else "—"
    blockers = state.get("blockers") or []
    block_info = f" · <span style='color:#ef5350;'>Blocked: {', '.join(map(str, blockers[:2]))}</span>" if blockers else ""

    st.markdown(
        f"""<div style="font-size: 0.75rem; color: #90a4ae; display: flex; justify-content: space-between; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 3px;">
            <span>Trend: <b style="color:#26a69a;">{trend_str}</b> · Rev: <b style="color:#ef5350;">{rev_str}</b>{block_info}</span>
            <span style="color: #546e7a;">KITE · FRESH</span>
        </div>""",
        unsafe_allow_html=True
    )


def _render_upstox_chain(snapshot) -> None:
    st.caption("SOURCE: UPSTOX · READ ONLY · Independent capture path (Not part of Kite operational pipeline)")
    if snapshot.status != "fresh":
        st.warning(f"Upstox option-chain snapshot: {snapshot.status.upper()}. {snapshot.message}")
        return
    roots = snapshot.payload.get("chains") or {}
    choices = [x for x in ("NIFTY", "BANKNIFTY", "SENSEX") if x in roots]
    root = st.selectbox("Underlying Index", choices) if choices else None
    if not root:
        st.caption("No option-chain rows in current snapshot.")
        return
    chain = roots[root]
    st.caption(f"Expiry: {chain.get('expiry', 'UNKNOWN')} · Snapshot age: {snapshot.age_sec:.2f}s · Source: UPSTOX FULL MODE")
    rows = chain.get("rows") or []
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("No strike rows available.")


def main() -> None:
    st.set_page_config(
        page_title="TradeBot Operator Cockpit",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Scoped Custom CSS for Ultra-Compact One-Viewport UX
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0.6rem !important;
            padding-bottom: 1.0rem !important;
            padding-left: 1.0rem !important;
            padding-right: 1.0rem !important;
            max-width: 100% !important;
        }
        h1, h2, h3, h4 {
            margin-top: 0.15rem !important;
            margin-bottom: 0.15rem !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            font-weight: 700 !important;
        }
        hr {
            margin-top: 0.35rem !important;
            margin-bottom: 0.35rem !important;
            border-color: rgba(255, 255, 255, 0.08) !important;
        }
        .status-pill {
            display: inline-block;
            padding: 2px 9px;
            border-radius: 10px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            margin-left: 4px;
        }
        .status-pill-ok { background: rgba(38, 166, 154, 0.18); color: #26a69a; border: 1px solid rgba(38, 166, 154, 0.4); }
        .status-pill-warn { background: rgba(255, 179, 0, 0.18); color: #ffb300; border: 1px solid rgba(255, 179, 0, 0.4); }
        .status-pill-err { background: rgba(239, 83, 80, 0.18); color: #ef5350; border: 1px solid rgba(239, 83, 80, 0.4); }
        .status-pill-neutral { background: rgba(255, 255, 255, 0.08); color: #90a4ae; border: 1px solid rgba(255, 255, 255, 0.15); }
        .pulse-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 6px;
            padding: 6px 8px;
            text-align: center;
            position: relative;
        }
        .pulse-card::after {
            content: "➔";
            position: absolute;
            right: -10px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 0.65rem;
            color: rgba(255, 255, 255, 0.2);
            z-index: 2;
        }
        .pulse-card-last::after {
            content: "";
        }
        .section-header {
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #b0bec5;
            margin-bottom: 4px;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.35rem !important;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.75rem !important;
            color: #90a4ae !important;
        }
        [data-testid="stDataFrame"] {
            font-size: 0.80rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    feed = load_feed_state(desk_id)
    health = load_health_gate_report(desk_id)
    risk = load_risk_state(desk_id)
    upstox = load_upstox_option_chain_snapshot()
    metrics = load_runtime_metrics(desk_id=desk_id)
    market_state = load_market_state()
    series = load_index_series(desk_id=desk_id)
    summary = metrics.get("summary") or {}

    # 1. HEADER & HEALTH STRIP
    top_col1, top_col2 = st.columns([1, 1])
    with top_col1:
        st.markdown(
            f"""<div style="display: flex; align-items: baseline; gap: 10px;">
                <span style="font-size: 1.25rem; font-weight: 800; letter-spacing: 0.08em; color: #eceff1;">TRADEBOT</span>
                <span style="font-size: 0.80rem; font-weight: 600; color: #78909c;">OPERATOR COCKPIT · DESK: {desk_id}</span>
            </div>""",
            unsafe_allow_html=True
        )
    with top_col2:
        pills_html = f"""<div style="text-align: right; display: flex; justify-content: flex-end; align-items: center;">
            {_pill_html("KITE", _status(feed))}
            {_pill_html("SYSTEM", _status(health))}
            {_pill_html("RISK", _status(risk))}
            {_pill_html("UPSTOX", upstox.status)}
            <span style="margin-left: 10px; font-size: 0.80rem; color: #78909c; font-family: monospace;">{datetime.now().astimezone().strftime("%H:%M:%S %Z")}</span>
        </div>"""
        st.markdown(pills_html, unsafe_allow_html=True)

    if os.getenv("OPERATOR_COCKPIT_OFFLINE_FIXTURE", "").strip().lower() == "true":
        st.markdown(
            """<div style="background: rgba(255, 179, 0, 0.12); border-left: 4px solid #ffb300; padding: 4px 10px; margin: 3px 0; font-size: 0.80rem; color: #ffca28; font-weight: 600;">
                ⚠️ OFFLINE FIXTURE VALIDATION — Synthetic evidence mode · Zero broker connections · Truth surfaces active
            </div>""",
            unsafe_allow_html=True
        )

    st.divider()

    # 2. THREE MARKET PANELS
    state_rows = market_state.get("indices") or {}
    mkt_cols = st.columns(3)
    for col, symbol in zip(mkt_cols, INDEX_SYMBOLS):
        with col:
            _render_market_panel(symbol, series.get(symbol) or [], state_rows.get(symbol) or {})

    st.divider()

    # 3. PIPELINE PULSE (Visual Centerpiece)
    st.markdown("<div class='section-header'>Pipeline Pulse</div>", unsafe_allow_html=True)
    pulse = pipeline_pulse(feed_status=_status(feed), risk_status=_status(risk), market_state=market_state, metrics=metrics)

    cards_html = []
    for i, item in enumerate(pulse):
        stage_name = str(item.get("stage") or "")
        stage_state = str(item.get("state") or "")
        stage_detail = str(item.get("detail") or "")
        s_color = _status_color(stage_state)

        card = (
            f'<div style="flex: 1; min-width: 0; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 6px; padding: 6px 8px; text-align: center;">'
            f'<div style="font-size: 0.68rem; font-weight: 700; color: #90a4ae; letter-spacing: 0.05em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{stage_name}</div>'
            f'<div style="font-size: 0.92rem; font-weight: 800; color: {s_color}; margin: 2px 0;">{stage_state}</div>'
            f'<div style="font-size: 0.68rem; color: #b0bec5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{stage_detail}">{stage_detail}</div>'
            f'</div>'
        )
        cards_html.append(card)
        if i < len(pulse) - 1:
            arrow = '<div style="display: flex; align-items: center; justify-content: center; color: rgba(255, 255, 255, 0.25); font-size: 0.75rem; padding: 0 2px;">➔</div>'
            cards_html.append(arrow)

    pulse_container_html = f"<div style='display: flex; align-items: stretch; justify-content: space-between; gap: 4px; margin: 4px 0 8px 0;'>{''.join(cards_html)}</div>"
    st.markdown(pulse_container_html, unsafe_allow_html=True)

    st.divider()

    # 4. TOP OPPORTUNITIES
    st.markdown("<div class='section-header'>Top Opportunities</div>", unsafe_allow_html=True)
    opportunities = load_top_opportunities(desk_id=desk_id)
    if opportunities:
        st.dataframe(opportunities[:8], use_container_width=True, hide_index=True)
    else:
        st.markdown(
            """<div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 4px; padding: 6px 12px; font-size: 0.80rem; color: #90a4ae;">
                <b style="color: #eceff1;">NO QUALIFYING OPPORTUNITY</b> · Pipeline active · Strategies evaluated · Zero candidates meet current gate thresholds
            </div>""",
            unsafe_allow_html=True
        )

    st.divider()

    # 5. CANDIDATE FUNNEL & STRATEGY MONITOR
    mid_l, mid_r = st.columns([1, 1])
    with mid_l:
        st.markdown("<div class='section-header'>Candidate Funnel</div>", unsafe_allow_html=True)
        funnel = summary.get("latest_pipeline_funnel") or {}
        f_cols = st.columns(4)
        c_pool = summary.get("candidate_pool_latest", 0)
        c_rank = summary.get("ranked_candidate_count", 0)
        c_gen = funnel.get("generated", c_pool)
        c_adv = summary.get("advisory_conversion_denominator", funnel.get("advisory", 0))

        with f_cols[0]: st.metric("Evaluated", c_gen)
        with f_cols[1]: st.metric("Candidates", c_pool)
        with f_cols[2]: st.metric("Ranked", c_rank)
        with f_cols[3]: st.metric("Advisory", c_adv)

        rejection = metrics.get("rejection_reason_distribution") or []
        if rejection:
            st.caption("Rejection Reasons")
            st.dataframe(rejection[:5], use_container_width=True, hide_index=True)

    with mid_r:
        st.markdown("<div class='section-header'>Strategy Monitor</div>", unsafe_allow_html=True)
        strategies = load_strategy_monitor(desk_id=desk_id)
        if strategies:
            st.dataframe(strategies[:12], use_container_width=True, hide_index=True)
        else:
            st.markdown(
                """<div style="font-size: 0.80rem; color: #90a4ae; padding: 8px 0;">
                    No authoritative strategy activity in current runtime streams.
                </div>""",
                unsafe_allow_html=True
            )

    st.divider()

    # 6. OPERATIONAL SOURCES & RISK GOVERNANCE
    bot_l, bot_r = st.columns([1, 1])
    with bot_l:
        st.markdown("<div class='section-header'>Operational Sources & Feed Authority</div>", unsafe_allow_html=True)
        st.markdown(
            f"""<div style="display: flex; gap: 12px; font-size: 0.80rem;">
                <div style="flex: 1; background: rgba(255,255,255,0.02); padding: 6px 10px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.05);">
                    <b>KITE OPERATIONAL FEED</b><br/>
                    Feed: <span style="color: {_status_color(_status(feed))}; font-weight: 700;">{_status(feed)}</span> · System: <span style="color: {_status_color(_status(health))}; font-weight: 700;">{_status(health)}</span><br/>
                    <span style="font-size: 0.72rem; color: #78909c;">Primary trading execution & state source</span>
                </div>
                <div style="flex: 1; background: rgba(255,255,255,0.02); padding: 6px 10px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.05);">
                    <b>UPSTOX CAPTURE (INDEPENDENT)</b><br/>
                    Snapshot: <span style="color: {_status_color(upstox.status)}; font-weight: 700;">{upstox.status.upper()}</span> · Age: {f"{upstox.age_sec:.1f}s" if upstox.age_sec is not None else "—"}<br/>
                    <span style="font-size: 0.72rem; color: #78909c;">Observation only · Never substitutes Kite</span>
                </div>
            </div>""",
            unsafe_allow_html=True
        )

    with bot_r:
        st.markdown("<div class='section-header'>Risk Governance & Execution Safety</div>", unsafe_allow_html=True)
        st.markdown(
            f"""<div style="background: rgba(255,255,255,0.02); padding: 6px 10px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.05); font-size: 0.80rem;">
                Risk Surface: <span style="color: {_status_color(_status(risk))}; font-weight: 700;">{_status(risk)}</span> · Broker Write: <b>OFF</b> · Order Authority: <b>OFF</b> · Mode: <b>MANUAL APPROVAL</b><br/>
                <span style="font-size: 0.72rem; color: #78909c;">All order generation gates locked · Read-only telemetry</span>
            </div>""",
            unsafe_allow_html=True
        )

    # 7. COLLAPSED SECONDARY EXPANDERS
    with st.expander("Upstox Option Chain Snapshot", expanded=False):
        _render_upstox_chain(upstox)

    with st.expander("Engineering Diagnostics & Telemetry Integrity", expanded=False):
        st.markdown("<div class='section-header'>Runtime Source Telemetry Summary</div>", unsafe_allow_html=True)
        sources_dict = metrics.get("source_status") or {}
        diag_rows = []
        for src_name, src_info in sorted(sources_dict.items()):
            if isinstance(src_info, dict):
                diag_rows.append({
                    "Source": src_name,
                    "State": "FOUND" if src_info.get("exists") else "MISSING",
                    "Currentness": "EXPLICIT_CURRENT" if src_info.get("current") else "UNPROVEN",
                    "Count": src_info.get("row_count", "—"),
                    "Path": Path(str(src_info.get("path") or "")).name or "—"
                })
        if diag_rows:
            st.dataframe(diag_rows, use_container_width=True, hide_index=True)
        else:
            st.caption("No registered runtime source streams.")

        st.caption("Raw Metric Notes & Complete Filesystem Paths:")
        st.json({
            "metric_notes": metrics.get("notes") or [],
            "metric_sources": metrics.get("source_status") or {},
            "market_state_source": market_state.get("_path")
        })


if __name__ == "__main__":
    main()
