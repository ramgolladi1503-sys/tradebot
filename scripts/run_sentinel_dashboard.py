"""Sentinel Live Advisory Telemetry Dashboard.

Read-only real-time Streamlit dashboard for Sentinel sidecar engine.
Preserves trading safety invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""
from __future__ import annotations

import json
import os
import glob
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(
    page_title="Sentinel Live Advisor Telemetry",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .metric-container {
        background-color: #12161F;
        border: 1px solid #232B3B;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .option-card-live {
        background-color: #0D2818;
        border: 2px solid #2E7D32;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 16px;
    }
    .option-price-badge {
        display: inline-block;
        background-color: #1B5E20;
        color: #FFFFFF;
        font-size: 20px;
        font-weight: bold;
        padding: 6px 14px;
        border-radius: 6px;
        margin: 4px 6px 4px 0px;
    }
    .sl-badge {
        display: inline-block;
        background-color: #B71C1C;
        color: #FFFFFF;
        font-size: 16px;
        font-weight: bold;
        padding: 6px 12px;
        border-radius: 6px;
        margin: 4px 6px 4px 0px;
    }
    .tp-badge {
        display: inline-block;
        background-color: #004D40;
        color: #80CBC4;
        font-size: 16px;
        font-weight: bold;
        padding: 6px 12px;
        border-radius: 6px;
        margin: 4px 6px 4px 0px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🛰️ Sentinel Live Feed Advisory Terminal")
st.caption("Sidecar Telemetry • Real-Time Option Contract Quotes (LTP/Bid/Ask/SL/TP) • Dynamic Regime Gating")

# Sidebar
st.sidebar.title("Config & Status")
auto_refresh = st.sidebar.checkbox("Auto-Refresh Feed", value=True)
refresh_rate = st.sidebar.slider("Refresh Interval (seconds)", min_value=1, max_value=10, value=2)

if st.sidebar.button("🔄 Refresh Now", use_container_width=True):
    st.rerun()

WORKTREE = Path("/private/tmp/tradebot-pr968-b1d10ff-repair")
today_str = datetime.now().strftime("%Y%m%d")
audit_log_path = WORKTREE / f"runtime/audit/sentinel_execution_paths_{today_str}.jsonl"
wal_path = WORKTREE / "runtime/sentinel_apm_wal.json"

# Helper to read latest option quotes from live capture parquet
def get_live_option_quotes() -> dict:
    today_dash = datetime.now().strftime("%Y-%m-%d")
    for base in [Path("/Volumes/TradeBot/live market capture"), Path("/Volumes/TradeBotData/live market capture")]:
        chunks_dir = base / today_dash / "chunks"
        if chunks_dir.exists():
            chunk_files = sorted(chunks_dir.glob("*.parquet"))
            if chunk_files:
                try:
                    df = pd.read_parquet(chunk_files[-1])
                    res = {}
                    for sym in df["symbol"].dropna().unique():
                        sub = df[df["symbol"] == sym]
                        if not sub.empty:
                            r = sub.iloc[-1]
                            res[sym] = {
                                "ltp": float(r["ltp"]) if pd.notna(r.get("ltp")) else None,
                                "bid": float(r["bid"]) if pd.notna(r.get("bid")) else None,
                                "ask": float(r["ask"]) if pd.notna(r.get("ask")) else None,
                                "token": str(r.get("token", "")),
                                "ts": float(r.get("ts", 0)),
                            }
                    return res
                except Exception:
                    pass
    return {}

live_option_book = get_live_option_quotes()

# Display active option prices in sidebar
if live_option_book:
    st.sidebar.markdown("### ⚡ Live Option Stream")
    for sym, q in sorted(live_option_book.items()):
        if "NIFTY" in sym and any(s in sym for s in ["22500", "22550", "22600", "22450"]):
            st.sidebar.markdown(f"**{sym}**")
            st.sidebar.text(f"LTP: ₹{q['ltp']} | Bid: ₹{q['bid']} | Ask: ₹{q['ask']}")

# Load APM WAL state
wal_state = "STANDBY"
wal_payload = None
wal_last_trade = None
wal_history = []
if wal_path.exists():
    try:
        with open(wal_path, "r") as wf:
            wal_data = json.load(wf)
            wal_state = wal_data.get("state", "STANDBY")
            wal_payload = wal_data.get("payload")
            wal_last_trade = wal_data.get("last_completed_trade")
            wal_history = wal_data.get("trade_history", [])
    except Exception:
        pass

# Fallback: Extract all executed trades today across running task logs if WAL was rotated
def get_all_executed_trades_today() -> list:
    trades_dict = {}
    import glob, re
    # Only inspect task logs from today (matching current conversation tasks)
    today_logs = [
        "/Users/madhuram/.gemini/antigravity/brain/162de38c-8263-4254-8b50-0c5fa8538833/.system_generated/tasks/task-12038.log",
        "/Users/madhuram/.gemini/antigravity/brain/162de38c-8263-4254-8b50-0c5fa8538833/.system_generated/tasks/task-12231.log",
        "/Users/madhuram/.gemini/antigravity/brain/162de38c-8263-4254-8b50-0c5fa8538833/.system_generated/tasks/task-12296.log"
    ]
    for p in today_logs:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as lf:
                for l in lf:
                    if "NEW POSITION OPENED" in l:
                        m = re.search(r"NEW POSITION OPENED\] (\w+) \| (.*?) @ Spot ([\d\.]+) \|.*?Option LTP: ₹([\d\.]+)", l)
                        if m:
                            pid = m.group(1)
                            # Format Date and Time from TRADE_HHMM_DIR
                            tm_match = re.search(r"TRADE_(\d{2})(\d{2})_", pid)
                            time_str = f"2026-10-12 {tm_match.group(1)}:{tm_match.group(2)}:00" if tm_match else "2026-10-12"
                            trades_dict[pid] = {
                                "trade_time": time_str,
                                "position_id": pid,
                                "strike_contract": m.group(2).strip(),
                                "entry_price": float(m.group(3)),
                                "opt_entry_ltp": float(m.group(4)),
                                "exit_reason": "IN_FLIGHT",
                                "exit_price": None,
                                "pnl_pts": None,
                                "opt_exit_ltp": None,
                                "opt_pnl_pts": None,
                            }
                    elif "POSITION EXITED" in l and trades_dict:
                        m = re.search(r"Reason: (\w+) \| Exit Spot: ([\d\.]+) \| Spot PnL: [^\d\+\-]+([\+\-]?[\d\.]+) pts \| Option PnL: ([\+\-]?[\d\.]+) pts", l)
                        if m:
                            last_pid = list(trades_dict.keys())[-1]
                            trades_dict[last_pid].update({
                                "exit_reason": m.group(1),
                                "exit_price": float(m.group(2)),
                                "pnl_pts": float(m.group(3)),
                                "opt_pnl_pts": float(m.group(4)),
                                "opt_exit_ltp": round(trades_dict[last_pid]["opt_entry_ltp"] + float(m.group(4)), 2)
                            })
        except Exception:
            continue
    # Merge with wal_history if available
    res = list(trades_dict.values())
    for item in wal_history:
        if isinstance(item, dict) and item.get("position_id"):
            pid = item["position_id"]
            if pid not in [x.get("position_id") for x in res]:
                tm_match = re.search(r"TRADE_(\d{2})(\d{2})_", pid)
                time_str = f"2026-10-12 {tm_match.group(1)}:{tm_match.group(2)}:00" if tm_match else "2026-10-12"
                item_copy = dict(item)
                item_copy["trade_time"] = item_copy.get("entry_time", time_str)
                res.append(item_copy)

    # Sort strictly descending by trade_time (newest trade at the top)
    res.sort(key=lambda x: str(x.get("trade_time", "")), reverse=True)
    return res

# Read Audit Log rows
rows = []
if audit_log_path.exists():
    try:
        with open(audit_log_path, "r", encoding="utf-8") as af:
            for line in af:
                if line.strip():
                    rows.append(json.loads(line.strip()))
    except Exception:
        pass

df_rows = pd.DataFrame(rows) if rows else pd.DataFrame()

# Top KPI Banner
col1, col2, col3, col4, col5 = st.columns(5)
latest_row = rows[-1] if rows else {}
spot_px = latest_row.get("spot_nifty")
atr_val = latest_row.get("atr_1m")
ker_val = latest_row.get("ewma_ker", 0.5)
last_bar_time = latest_row.get("timestamp", "Awaiting stream...")

with col1:
    st.metric("NIFTY Spot", f"₹{spot_px:,.2f}" if spot_px else "Loading...")
with col2:
    st.metric("1m Realized ATR", f"{atr_val:.1f} pts" if atr_val else "Loading...")
with col3:
    st.metric("EWMA-KER (Efficiency)", f"{ker_val:.3f}" if ker_val else "Loading...")
with col4:
    gear_label = "GEAR 2 (Trend)" if ker_val >= 0.35 else "GEAR 1 (Range)"
    st.metric("Regime Gear", gear_label)
with col5:
    st.metric("APM State", wal_state)

st.caption(f"Last Evaluated Bar: **{last_bar_time}** | Total Feed Bars: **{len(rows)}**")

st.markdown("---")

# Main Content Layout
col_left, col_right = st.columns([2, 1])

with col_left:
    # 🎯 REAL-TIME OPTION STRIKE CONTRACT DISPLAY (Spotlight)
    st.subheader("🎯 Active Option Strike Contract Entry & Risk Profile")

    # Determine current setup candidate and find the initial signal bar timestamp
    active_contract_symbol = None
    direction_tag = "PE"
    setup_title = "NIFTY 22550 PE [ITM Breakdown]"
    signal_bar_timestamp = None

    if not df_rows.empty and "advisory" in df_rows.columns:
        buy_rows = df_rows[df_rows["advisory"].str.contains("BUY", na=False)]
        if not buy_rows.empty:
            first_buy = buy_rows.iloc[0]
            latest_buy = buy_rows.iloc[-1]
            adv_text = str(latest_buy.get("advisory", ""))
            # Use timestamp from the first buy bar that triggered the active setup
            signal_bar_timestamp = str(first_buy.get("timestamp", ""))
            if "22450 PE" in adv_text:
                active_contract_symbol = "NIFTY 22450 PE 13 OCT 26"
                direction_tag = "PE"
                setup_title = "NIFTY 22450 PE (ITM Breakdown Setup)"
            elif "22550 PE" in adv_text:
                active_contract_symbol = "NIFTY 22550 PE 13 OCT 26"
                direction_tag = "PE"
                setup_title = "NIFTY 22550 PE (ITM Breakdown Setup)"
            elif "22500 CE" in adv_text:
                active_contract_symbol = "NIFTY 22500 CE 13 OCT 26"
                direction_tag = "CE"
                setup_title = "NIFTY 22500 CE (Bullish Rejection Setup)"
            elif "22500 PE" in adv_text:
                active_contract_symbol = "NIFTY 22500 PE 13 OCT 26"
                direction_tag = "PE"
                setup_title = "NIFTY 22500 PE (ITM Setup)"

    if not active_contract_symbol:
        active_contract_symbol = "NIFTY 22550 PE 13 OCT 26"

    # Current streaming market quote
    live_q = live_option_book.get(active_contract_symbol)
    curr_ltp = live_q.get("ltp") if live_q else None
    curr_bid = live_q.get("bid", curr_ltp) if live_q else None
    curr_ask = live_q.get("ask", curr_ltp) if live_q else None

    # Locked Entry Quote: look up quote at the signal bar timestamp
    locked_entry_q = None
    if signal_bar_timestamp:
        try:
            # Parse ISO timestamp to epoch
            sig_epoch = datetime.fromisoformat(signal_bar_timestamp).timestamp()
            today_dash = datetime.now().strftime("%Y-%m-%d")
            for base in [Path("/Volumes/TradeBot/live market capture"), Path("/Volumes/TradeBotData/live market capture")]:
                chunks_dir = base / today_dash / "chunks"
                if chunks_dir.exists():
                    all_chunks = sorted(chunks_dir.glob("*.parquet"))
                    for c_path in reversed(all_chunks):
                        try:
                            c_df = pd.read_parquet(c_path)
                            c_sub = c_df[(c_df["symbol"] == active_contract_symbol) & (c_df["ts"] <= sig_epoch)]
                            if not c_sub.empty:
                                r_match = c_sub.iloc[-1]
                                locked_entry_q = {
                                    "ltp": float(r_match["ltp"]),
                                    "bid": float(r_match["bid"]),
                                    "ask": float(r_match["ask"]),
                                    "ts": float(r_match["ts"]),
                                }
                                break
                        except Exception:
                            continue
                if locked_entry_q:
                    break
        except Exception:
            pass

    # Only display the Active Option Spotlight Card when APM is actively IN_FLIGHT or has an open payload
    # When a trade is won, lost, or liquidated, it is gone from the top spotlight card.
    is_actively_in_flight = (wal_state in {"IN_FLIGHT", "TRAIL_LOCK", "EXIT_PENDING"} and wal_payload is not None)

    if is_actively_in_flight and wal_payload:
        active_contract_symbol = str(wal_payload.get("opt_symbol", "NIFTY 22450 PE 13 OCT 26"))
        live_q = live_option_book.get(active_contract_symbol)
        curr_ltp = live_q.get("ltp") if live_q else wal_payload.get("opt_current_ltp")
        curr_bid = live_q.get("bid", curr_ltp) if live_q else curr_ltp
        curr_ask = live_q.get("ask", curr_ltp) if live_q else curr_ltp

        entry_ltp = float(wal_payload.get("opt_entry_ltp", 0.0))
        opt_sl = float(wal_payload.get("opt_initial_sl", round(entry_ltp * 0.80, 1))) if wal_payload.get("opt_initial_sl") else round(entry_ltp * 0.80, 1)
        opt_tp_scalp = round(entry_ltp + 15.0, 1)
        opt_tp_runner = round(entry_ltp + 30.0, 1)

        pnl_pts = (curr_ltp - entry_ltp) if (curr_ltp is not None and entry_ltp > 0) else 0.0
        pnl_color = "#81C784" if pnl_pts >= 0 else "#E57373"
        pnl_sign = "+" if pnl_pts >= 0 else ""

        live_ltp_display = f"₹{curr_ltp:.2f} ({pnl_sign}{pnl_pts:.2f} pts)" if curr_ltp is not None else "Awaiting tick..."
        bid_display = f"₹{curr_bid:.2f}" if curr_bid is not None else "N/A"
        ask_display = f"₹{curr_ask:.2f}" if curr_ask is not None else "N/A"

        st.markdown(f"""
        <div class="option-card-live">
            <div style="font-size:18px; font-weight:bold; color:#A5D6A7; margin-bottom:8px;">
                🚀 ACTIVE IN-FLIGHT POSITION: {active_contract_symbol}
            </div>
            <div style="margin-bottom: 12px; display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap;">
                <span class="option-price-badge">🔒 Locked Entry: ₹{entry_ltp:.2f}</span>
                <span style="font-size:16px; font-weight:bold; color:{pnl_color};">
                    Live LTP: {live_ltp_display}
                </span>
                <span style="font-size:13px; color:#CFD8DC;">Bid: {bid_display} | Ask: {ask_display}</span>
            </div>
            <div>
                <span class="sl-badge">🛑 Stop Loss: ₹{opt_sl:.1f}</span>
                <span class="tp-badge">🎯 Target 1 (+15 pts): ₹{opt_tp_scalp:.1f}</span>
                <span class="tp-badge">🚀 Target 2 (+30 pts): ₹{opt_tp_runner:.1f}</span>
            </div>
            <div style="font-size:12px; color:#90A4AE; margin-top:10px;">
                * In-flight trade actively monitored by Sentinel APM. Spot reference: ₹{spot_px:,.2f}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("ℹ️ **No Active In-Flight Trade.** Sentinel APM is standing by for the next qualified displacement breakout.")

    # 📊 DEDICATED RECORD OF ALL EXECUTED TRADES (Separate Columns)
    st.subheader("📋 Executed Trades Record & Performance Log")
    all_executed = get_all_executed_trades_today()
    if all_executed:
        df_trades = pd.DataFrame(all_executed)
        # Sort reverse chronological (newest first)
        df_trades_rev = df_trades.iloc[::-1].reset_index(drop=True)

        st.dataframe(
            df_trades,
            use_container_width=True,
            column_config={
                "trade_time": st.column_config.TextColumn("Date & Time (IST)", width="medium"),
                "position_id": st.column_config.TextColumn("Trade ID", width="small"),
                "strike_contract": st.column_config.TextColumn("Contract", width="medium"),
                "entry_price": st.column_config.NumberColumn("Spot Entry", format="₹%.2f"),
                "exit_price": st.column_config.NumberColumn("Spot Exit", format="₹%.2f"),
                "pnl_pts": st.column_config.NumberColumn("Spot PnL (pts)", format="%+.1f"),
                "opt_entry_ltp": st.column_config.NumberColumn("Option Entry LTP", format="₹%.2f"),
                "opt_exit_ltp": st.column_config.NumberColumn("Option Exit LTP", format="₹%.2f"),
                "opt_pnl_pts": st.column_config.NumberColumn("Option PnL (pts)", format="%+.2f"),
                "exit_reason": st.column_config.TextColumn("Exit Reason / Result", width="medium"),
            }
        )
    else:
        st.caption("No completed trades recorded yet today.")

    st.subheader("📈 Live Market Track & Opening Range Bounds")
    if not df_rows.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_rows["timestamp"],
            y=df_rows["spot_nifty"],
            mode="lines+markers",
            name="Spot Close",
            line=dict(color="#29B6F6", width=2)
        ))
        fig.add_hline(y=22651.10, line_dash="dash", line_color="#81C784", annotation_text="OR High 22651.10")
        fig.add_hline(y=22512.00, line_dash="dash", line_color="#E57373", annotation_text="OR Low 22512.00")
        fig.update_layout(
            template="plotly_dark",
            height=280,
            margin=dict(l=20, r=20, t=25, b=20),
            xaxis_title="Time",
            yaxis_title="Index Level",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("📝 Live Advisory & Audit Trail (Reverse Chronological)")
    if not df_rows.empty:
        display_cols = ["timestamp", "spot_nifty", "atr_1m", "ewma_ker", "advisory", "risk_flag", "candidate_status"]
        valid_cols = [c for c in display_cols if c in df_rows.columns]
        reversed_df = df_rows[valid_cols].iloc[::-1].reset_index(drop=True)
        st.dataframe(
            reversed_df,
            use_container_width=True,
            height=300,
            column_config={
                "advisory": st.column_config.TextColumn("Advisory Signal", width="large"),
                "risk_flag": st.column_config.TextColumn("Risk Gate Flag", width="medium"),
                "candidate_status": st.column_config.TextColumn("Candidate Status", width="medium"),
                "spot_nifty": st.column_config.NumberColumn("Spot Price", format="₹%.2f"),
                "atr_1m": st.column_config.NumberColumn("1m ATR", format="%.2f"),
                "ewma_ker": st.column_config.NumberColumn("EWMA-KER", format="%.3f"),
                "timestamp": st.column_config.TextColumn("Bar Time", width="small"),
            }
        )

with col_right:
    st.subheader("🛡️ Active Position Manager (APM)")
    st.markdown(f"**State**: `{wal_state}`")
    if wal_payload:
        opt_entry_display = f"₹{wal_payload.get('opt_entry_ltp'):.2f}" if wal_payload.get('opt_entry_ltp') is not None else "N/A"
        opt_sl_display = f"₹{wal_payload.get('opt_initial_sl'):.2f}" if wal_payload.get('opt_initial_sl') is not None else "Dynamic Spot-SL"
        entry_spot_display = f"₹{wal_payload.get('entry_price'):.2f}" if wal_payload.get('entry_price') is not None else "N/A"
        current_spot_sl_display = f"₹{wal_payload.get('current_sl'):.2f}" if wal_payload.get('current_sl') is not None else "N/A"
        target_spot_display = f"₹{wal_payload.get('target_price'):.2f}" if wal_payload.get('target_price') is not None else "N/A"

        st.markdown(f"""
        - **Position ID**: `{wal_payload.get('position_id')}`
        - **Contract**: `{wal_payload.get('strike_contract')}`
        - **Direction**: `{wal_payload.get('direction')}`
        - **Option Entry**: `{opt_entry_display}`
        - **Option SL**: `{opt_sl_display}`
        - **Entry Spot**: `{entry_spot_display}`
        - **Current Spot SL**: `{current_spot_sl_display}` (Trail-Locked)
        - **Target Spot**: `{target_spot_display}`
        """)
    else:
        st.caption("No open paper position in-flight. APM is standing by.")

    st.markdown("---")
    st.subheader("🛑 Gate Veto Precedence")
    st.markdown("""
    1. **Lunch Dead Zone** (11:00 – 13:30 in Gear 1)
    2. **Trend Purity** (No counter-fades in Gear 2)
    3. **Energy Gate (SPVD)** (Remaining ATR >= Required)
    4. **Displacement Gate** (>= 1.0 ATR progress from prior exit)
    5. **Macro ATR Extension** (Exhaustion cap > 300 pts)
    6. **Spread Expansion** (Bid-ask spread <= 4.0%)
    7. **Quote Uniqueness** (Single unique contract/token match)
    """)

if auto_refresh:
    time.sleep(refresh_rate)
    st.rerun()
