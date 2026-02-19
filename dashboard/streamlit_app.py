import json
import os
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import altair as alt
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import math

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dashboard.ui as ui
from dashboard.ui import (
    apply_global_style,
    app_shell,
    end_shell,
    section_header,
    empty_state,
    error_state,
    warn_state,
    success_state,
    loading_state,
    confirm_action,
    notify,
    render_notifications,
)

from core.trade_store import fetch_recent_trades, fetch_recent_outcomes, fetch_pnl_series, fetch_execution_stats, fetch_depth_snapshots, fetch_depth_imbalance
from core.scorecard import compute_scorecard
from core.gpt_advisor import get_trade_advice, save_advice, get_day_summary
from core.market_data import fetch_live_market_data
from core.day_type_history import load_day_type_events
from core.time_utils import is_today_local, age_minutes_local, now_local, parse_ts_local
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

st.set_page_config(page_title="Axiom Quant Console", layout="wide")

LOG_PATH = Path("data/trade_log.json")
STRAT_PATH = Path("logs/strategy_perf.json")
apply_global_style()

# Load trade log
if not LOG_PATH.exists():
    st.error("No trade_log.json found.")
    st.stop()

rows = []
with open(LOG_PATH, "r") as f:
    for line in f:
        if not line.strip():
            continue
        rows.append(json.loads(line))

df = pd.DataFrame(rows)
updates_path = Path("data/trade_updates.json")
if updates_path.exists():
    try:
        updates = []
        with open(updates_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                updates.append(json.loads(line))
        upd_df = pd.DataFrame(updates)
        if not upd_df.empty and "trade_id" in upd_df.columns:
            upd_df["timestamp"] = pd.to_datetime(upd_df["timestamp"])
            latest = upd_df.sort_values("timestamp").groupby("trade_id").tail(1)
            merge_cols = [c for c in latest.columns if c not in ("type", "timestamp")]
            df = df.merge(latest[merge_cols], on="trade_id", how="left", suffixes=("", "_upd"))
            for col in ["exit_price", "exit_time", "actual", "r_multiple", "r_label", "fill_price", "latency_ms", "slippage"]:
                if f"{col}_upd" in df.columns:
                    df[col] = df[col].fillna(df[f"{col}_upd"])
                    df.drop(columns=[f"{col}_upd"], inplace=True)
    except Exception as e:
        st.warning(f"Unable to merge trade updates: {e}")

if df.empty or "timestamp" not in df.columns:
    st.warning("No trades found yet. Run the bot to generate trade logs.")
    st.stop()

df["timestamp"] = pd.to_datetime(df["timestamp"])
df["date"] = df["timestamp"].dt.date
df["pnl"] = (df["exit_price"].fillna(df["entry"]) - df["entry"]) * df["qty"]
df.loc[df["side"] == "SELL", "pnl"] *= -1
dfm = df.copy()

def _load_prefs():
    prefs_path = Path("logs/ui_prefs.json")
    if prefs_path.exists():
        try:
            return json.loads(prefs_path.read_text())
        except Exception:
            return {}
    return {}

def _save_prefs(prefs):
    try:
        Path("logs").mkdir(exist_ok=True)
        Path("logs/ui_prefs.json").write_text(json.dumps(prefs, indent=2))
    except Exception:
        pass


def _update_env_var(key: str, value: str):
    try:
        path = Path(".env")
        lines = path.read_text().splitlines() if path.exists() else []
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")
        path.write_text("\n".join(lines) + "\n")
    except Exception:
        pass

def _wf_lock_status():
    try:
        from config import config as cfg
        enabled = getattr(cfg, "STRATEGY_WF_LOCK_ENABLE", False)
        allowed = None
        total = None
        path = Path("logs/walk_forward_strategy_summary.csv")
        if path.exists():
            if path.stat().st_size == 0:
                return enabled, None, None
            try:
                df = pd.read_csv(path)
            except Exception:
                return enabled, None, None
            if not df.empty:
                total = len(df)
                if "passed" in df.columns:
                    allowed = len(df[df["passed"] == True])
                else:
                    allowed = total
        return enabled, allowed, total
    except Exception:
        return False, None, None

prefs = _load_prefs()

def _set_query_tab(tab_name: str):
    try:
        if hasattr(st, "query_params"):
            st.query_params["tab"] = tab_name
        else:
            st.experimental_set_query_params(tab=tab_name)
    except Exception:
        pass

# Theme preference removed (fixed theme)

# Navigation
nav_items = ["Home", "Execution", "Reconciliation", "Risk & Governance", "Data & SLA", "ML/RL", "Market Depth", "Gemini"]
query_tab = None
try:
    qp = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
    if isinstance(qp, dict):
        qv = qp.get("tab")
        if isinstance(qv, list):
            qv = qv[0] if qv else None
        query_tab = qv
except Exception:
    query_tab = None

default_tab = None
if query_tab == "GPT":
    query_tab = "Gemini"
if query_tab in nav_items:
    default_tab = query_tab
elif prefs.get("last_tab") in nav_items or prefs.get("last_tab") == "GPT":
    default_tab = "Gemini" if prefs.get("last_tab") == "GPT" else prefs.get("last_tab")
else:
    default_tab = "Home"

if "nav_choice" not in st.session_state:
    st.session_state["nav_choice"] = default_tab

def _on_nav_change():
    prefs["last_tab"] = st.session_state["nav_choice"]
    _save_prefs(prefs)
    _set_query_tab(st.session_state["nav_choice"])

nav = app_shell("Axiom Quant Console", nav_items, st.session_state["nav_choice"], on_change=_on_nav_change)
render_notifications()
try:
    if st.session_state.get("nav_choice") == "Gemini":
        provider = os.getenv("GPT_PROVIDER", "openai").lower()
        if provider == "gemini":
            if os.getenv("GEMINI_API_KEY"):
                st.sidebar.caption("Gemini API: OK")
            else:
                st.sidebar.warning("Gemini API: missing GEMINI_API_KEY")
        else:
            if os.getenv("OPENAI_API_KEY"):
                st.sidebar.caption("OpenAI API: OK")
            else:
                st.sidebar.warning("OpenAI API: missing OPENAI_API_KEY")
except Exception:
    pass

# Market snapshot refresh controls (only on Home)

def _safe_metric(val, fmt="{:.2f}"):
    try:
        if val is None or (isinstance(val, float) and (pd.isna(val))):
            return "N/A"
        return fmt.format(val)
    except Exception:
        return "N/A"

def _is_market_hours():
    try:
        tz = ZoneInfo("Asia/Kolkata")
        now = datetime.now(tz).time()
        # NSE cash hours 09:15–15:30 IST
        start = datetime.now(tz).replace(hour=9, minute=15, second=0, microsecond=0).time()
        end = datetime.now(tz).replace(hour=15, minute=30, second=0, microsecond=0).time()
        return start <= now <= end
    except Exception:
        # fallback to local time
        now = datetime.now().time()
        return now.hour >= 9 and now.hour < 16

def _should_show_quote_errors(readiness_state: str) -> bool:
    # Show quote errors only during market-open states, or if user explicitly tested.
    if st.session_state.get("force_show_quote_errors", False):
        shown_ts = float(st.session_state.get("force_show_quote_errors_ts", 0.0) or 0.0)
        ttl_sec = 300.0
        if shown_ts <= 0:
            return True
        if (time.time() - shown_ts) <= ttl_sec:
            return True
        st.session_state["force_show_quote_errors"] = False
        st.session_state["force_show_quote_errors_ts"] = 0.0
    return readiness_state in ("READY", "DEGRADED", "BLOCKED", "BOOTING")

def _localize_ts(df_in, col="timestamp"):
    df_out = df_in.copy()
    if col not in df_out.columns:
        return df_out
    ts = pd.to_datetime(df_out[col], errors="coerce")
    try:
        tz = datetime.now().astimezone().tzinfo
        if ts.dt.tz is None:
            ts = ts.dt.tz_localize(tz)
        else:
            ts = ts.dt.tz_convert(tz)
    except Exception:
        pass
    df_out[f"{col}_local"] = ts
    return df_out

def _ml_label_count():
    path = Path("data/trade_log.json")
    if not path.exists():
        return 0
    count = 0
    try:
        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("actual") is not None:
                    count += 1
    except Exception:
        return 0
    return count

def _render_confidence_reliability():
    try:
        from config import config as cfg
        needed = getattr(cfg, "ML_MIN_TRAIN_TRADES", 200)
    except Exception:
        needed = 200
    labeled = _ml_label_count()
    ratio = min(1.0, labeled / max(1, needed))
    status = "HIGH" if labeled >= needed else "LOW"
    color = "#23c55e" if labeled >= needed else "#f59e0b"
    st.markdown(
        f"""<div style='display:flex;align-items:center;gap:10px;'>
        <div style='font-size:0.95rem;color:#a3b3c5;'>Confidence Reliability</div>
        <div style='padding:4px 10px;border-radius:999px;background:{color};color:#0b0f14;font-weight:700;font-size:0.85rem;'>{status}</div>
        <div style='color:#a3b3c5;font-size:0.85rem;'>{labeled}/{needed} labeled</div>
        </div>""",
        unsafe_allow_html=True,
    )
    st.progress(ratio)

def _render_market_snapshot():
    try:
        from core.kite_client import kite_client
        from config import config as cfg
        from core.market_data import fetch_live_market_data
    except Exception as e:
        st.error(f"Market data error: {e}")
        return
    cols = st.columns(3)
    symbols = {
        "NIFTY 50": ("NIFTY", cfg.PREMARKET_INDICES_LTP.get("NIFTY", "NSE:NIFTY 50")),
        "BANKNIFTY": ("BANKNIFTY", cfg.PREMARKET_INDICES_LTP.get("BANKNIFTY", "NSE:BANKNIFTY")),
        "SENSEX": ("SENSEX", "BSE:SENSEX"),
    }
    try:
        q = kite_client.quote([v[1] for v in symbols.values()])
    except Exception as e:
        q = {}
        st.error(f"Market data error: {e}")

    # Regime banner + day type map (once)
    day_map = {}
    try:
        md = fetch_live_market_data()
        reg_map = {m.get("symbol"): m.get("regime_day") or m.get("regime") for m in md if m.get("instrument") == "OPT"}
        if reg_map:
            st.write("Detected Regime: " + ", ".join([f"{k}: {v}" for k, v in reg_map.items()]))
        day_map = {m.get("symbol"): (m.get("day_type"), m.get("day_confidence"), m.get("day_conf_history", [])) for m in md if m.get("instrument") == "OPT"}
        if day_map:
            try:
                conf_min = float(getattr(cfg, "DAYTYPE_CONF_SWITCH_MIN", 0.6))
                low = [k for k, v in day_map.items() if (v[1] is not None and v[1] < conf_min)]
                if low:
                    st.warning(f"Day-type confidence below threshold for: {', '.join(low)}")
            except Exception:
                pass
    except Exception:
        day_map = {}

    # Feed freshness badge (per-instrument SLA) via canonical SLA module
    try:
        from config import config as cfg
        from core.freshness_sla import get_freshness_status
        freshness = get_freshness_status(force=False)
        ltp_age = (freshness.get("ltp") or {}).get("age_sec")
        depth_age = (freshness.get("depth") or {}).get("age_sec")
        max_ltp = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))
        max_depth = float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 2.0))
        market_open = bool(freshness.get("market_open", True))
        stale = (ltp_age is None) or (isinstance(ltp_age, (int, float)) and ltp_age > max_ltp)
        if not market_open:
            st.info(f"Market closed: LTP age {ltp_age}s, depth age {depth_age}s")
        elif stale:
            st.error(f"Feeds stale: LTP age {ltp_age}s (max {max_ltp}s)")
        elif isinstance(depth_age, (int, float)) and depth_age > max_depth:
            st.warning(f"Depth feed lag {depth_age}s (max {max_depth}s)")
        else:
            st.success("Feeds healthy")
    except Exception:
        pass

    # Per-symbol tick health is intentionally suppressed to avoid non-canonical SLA logic.

    # Restart tick feed button
    try:
        import subprocess
        if st.button("Restart Tick Feed", key="restart_tick_feed"):
            log_path = Path("logs/tick_feed_restart.log")
            log_path.parent.mkdir(exist_ok=True)
            with log_path.open("a") as f:
                subprocess.Popen([sys.executable, "scripts/start_depth_ws.py"], stdout=f, stderr=f, start_new_session=True)
            st.success("Tick feed restart triggered (background).")
    except Exception as e:
        st.warning(f"Tick feed restart failed: {e}")

    # ORB confirmation panel
    try:
        section_header("ORB Confirmation")
        if day_map:
            orb_cols = st.columns(len(day_map))
            for i, sym in enumerate(["NIFTY", "BANKNIFTY", "SENSEX"]):
                if sym not in day_map:
                    continue
                md_sym = next((m for m in md if m.get("symbol") == sym), {})
                orb_bias = md_sym.get("orb_bias", "NEUTRAL")
                orb_min = md_sym.get("orb_lock_min", 15)
                mins = md_sym.get("minutes_since_open", 0)
                orb_cols[i].markdown(f"**{sym}**")
                orb_cols[i].write(f"ORB Bias: {orb_bias}")
                orb_cols[i].caption(f"Lock at {orb_min} min | Now {mins} min")
    except Exception:
        pass

    # Risk overlay panel
    try:
        section_header("Risk Overlay")
        if day_map:
            risk_cols = st.columns(len(day_map))
            for i, sym in enumerate(["NIFTY", "BANKNIFTY", "SENSEX"]):
                if sym not in day_map:
                    continue
                dtype, conf, _ = day_map[sym]
                mult = getattr(cfg, "DAYTYPE_RISK_MULT", {}).get(dtype, 1.0)
                risk_cols[i].markdown(f"**{sym}**")
                risk_cols[i].write(f"Day Type: {dtype}")
                risk_cols[i].write(f"Risk Multiplier: {mult:.2f}x")
    except Exception:
        pass

    for i, (label, (sym_key, sym)) in enumerate(symbols.items()):
        price = None
        change = None
        pct = None
        if q and sym in q:
            price = q[sym].get("last_price")
            try:
                prev_close = q[sym].get("ohlc", {}).get("close")
                if isinstance(prev_close, (int, float)) and isinstance(price, (int, float)):
                    change = price - prev_close
                    pct = (change / prev_close) * 100 if prev_close else None
            except Exception:
                pass
        delta = None
        if isinstance(change, (int, float)) and isinstance(pct, (int, float)):
            delta = f"{change:+.2f} ({pct:+.2f}%)"
        with cols[i]:
            st.markdown("<div class='market-card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='market-card-title'>{label}</div>", unsafe_allow_html=True)
            st.metric(label, f"{price:.2f}" if isinstance(price, (int, float)) else "N/A", delta)
            if sym_key in day_map:
                dtype, conf, hist = day_map[sym_key]
                st.markdown(f"<div class='market-card-sub'>Day Type: {sym_key}: {dtype} (conf {conf:.2f})</div>", unsafe_allow_html=True)
                st.caption("Day‑Type Confidence (per symbol)")
                if not hist:
                    hist = _get_daytype_history(sym_key)
                if not hist and conf is not None:
                    hist = [conf]
                if hist:
                    st.line_chart(hist)
            st.markdown("</div>", unsafe_allow_html=True)

if hasattr(st, "fragment"):
    @st.fragment(run_every=5)
    def _market_snapshot_fragment():
        _render_market_snapshot()
else:
    def _market_snapshot_fragment():
        _render_market_snapshot()

def _compute_strategy_stats_from_log(df_in):
    if df_in.empty or "strategy" not in df_in.columns:
        return pd.DataFrame()
    tmp = df_in.copy()
    tmp["pnl"] = (tmp["exit_price"].fillna(tmp["entry"]) - tmp["entry"]) * tmp["qty"]
    tmp.loc[tmp["side"] == "SELL", "pnl"] *= -1
    agg = tmp.groupby("strategy").agg(
        trades=("trade_id", "count"),
        pnl=("pnl", "sum"),
        win_rate=("pnl", lambda x: (x > 0).mean())
    ).reset_index()
    return agg

def _infer_strike_from_id(trade_id: str):
    try:
        import re
        if not trade_id:
            return None
        if "ATM" in trade_id:
            return "ATM"
        # Patterns like SYMBOL-CE-25750-... or SYMBOL-PE-60300-...
        m = re.search(r"-(CE|PE)-(\d{3,6})(?:-|$)", trade_id)
        if m:
            return int(m.group(2))
        # Patterns like SYMBOL-25750-CE-...
        m = re.search(r"-(\d{3,6})-(CE|PE)(?:-|$)", trade_id)
        if m:
            return int(m.group(1))
        # FUT/EQ or non-option ids won't have strike; return None
        return None
    except Exception:
        return None

def _infer_type_from_id(trade_id: str):
    try:
        import re
        if not trade_id:
            return None
        m = re.search(r"-(CE|PE)(?:-|$)", trade_id)
        if m:
            return m.group(1)
        m = re.search(r"(CE|PE)$", trade_id)
        if m:
            return m.group(1)
        return None
    except Exception:
        return None

def _infer_type_from_legs(legs):
    try:
        if not legs:
            return None
        has_ce = any("CE" in str(leg) for leg in legs)
        has_pe = any("PE" in str(leg) for leg in legs)
        if has_ce and not has_pe:
            return "CE"
        if has_pe and not has_ce:
            return "PE"
        if has_ce and has_pe:
            return "MIXED"
        return None
    except Exception:
        return None

def _derive_option_type(row, meta_map=None):
    try:
        t = row.get("type")
        if t in (None, "", "None") or (isinstance(t, float) and pd.isna(t)):
            t = _infer_type_from_id(row.get("trade_id"))
        if t in (None, "", "None") or (isinstance(t, float) and pd.isna(t)):
            t = _infer_type_from_legs(row.get("legs"))
        if (t in (None, "", "None") or (isinstance(t, float) and pd.isna(t))) and meta_map:
            tok = row.get("instrument_token")
            if tok is not None:
                meta = meta_map.get(tok, {})
                t = meta.get("type")
        # Try to resolve MIXED to CE/PE or CE/PE when both
        if t == "MIXED":
            strike = row.get("strike")
            if strike in (None, "", "None") or (isinstance(strike, float) and pd.isna(strike)):
                strike = _infer_strike_from_id(row.get("trade_id")) or _infer_strike_from_legs(row.get("legs"))
            legs = row.get("legs") or []
            strike_str = None
            try:
                strike_str = str(int(float(strike)))
            except Exception:
                strike_str = str(strike) if strike is not None else None
            if strike_str:
                has_ce = any("CE" in str(leg) and strike_str in str(leg) for leg in legs)
                has_pe = any("PE" in str(leg) and strike_str in str(leg) for leg in legs)
                if has_ce and not has_pe:
                    t = "CE"
                elif has_pe and not has_ce:
                    t = "PE"
                elif has_ce and has_pe:
                    t = "CE/PE"
            if t == "MIXED":
                t = "CE/PE"
        return t
    except Exception:
        return row.get("type")

def _fill_type_from_derived(df, meta_map=None):
    try:
        if df is None or df.empty:
            return df
        if "type" not in df.columns:
            df["type"] = None
        df["type"] = df.apply(lambda r: _derive_option_type(r, meta_map), axis=1)
        return df
    except Exception:
        return df

def _get_chain_map():
    try:
        cache = st.session_state.get("quote_chain_map")
        ts = st.session_state.get("quote_chain_map_ts", 0)
        if cache and (time.time() - ts) < 5:
            return cache
    except Exception:
        pass
    try:
        md = fetch_live_market_data()
        chain_map = {m.get("symbol"): m.get("option_chain", []) for m in md if m.get("instrument") == "OPT"}
    except Exception:
        chain_map = {}
    try:
        st.session_state["quote_chain_map"] = chain_map
        st.session_state["quote_chain_map_ts"] = time.time()
    except Exception:
        pass
    return chain_map

def _get_token_symbol_map(exchange):
    try:
        cache_key = f"token_symbol_map_{exchange}"
        cache_ts_key = f"{cache_key}_ts"
        cache = st.session_state.get(cache_key)
        ts = st.session_state.get(cache_ts_key, 0)
        if cache and (time.time() - ts) < 3600:
            return cache
        from core.kite_client import kite_client
        m = kite_client.token_symbol_map(exchange)
        st.session_state[cache_key] = m
        st.session_state[cache_ts_key] = time.time()
        return m
    except Exception:
        return {}

def _get_instrument_meta_map(ttl_sec=3600):
    try:
        cache = st.session_state.get("instrument_meta_map")
        ts = st.session_state.get("instrument_meta_map_ts", 0)
        if cache and (time.time() - ts) < ttl_sec:
            return cache
        from core.kite_client import kite_client
        meta = {}
        for exchange in ("NFO", "BFO"):
            data = kite_client.instruments_cached(exchange, ttl_sec=ttl_sec)
            for inst in data or []:
                tok = inst.get("instrument_token")
                if not tok:
                    continue
                meta[tok] = {
                    "tradingsymbol": inst.get("tradingsymbol"),
                    "symbol": inst.get("name"),
                    "strike": inst.get("strike"),
                    "type": inst.get("instrument_type"),
                    "expiry": str(inst.get("expiry")) if inst.get("expiry") else None,
                    "segment": inst.get("segment"),
                }
        st.session_state["instrument_meta_map"] = meta
        st.session_state["instrument_meta_map_ts"] = time.time()
        return meta
    except Exception:
        return {}

def _get_daytype_history(symbol, max_points=60):
    try:
        cache_key = f"daytype_hist_{symbol}"
        cache_ts_key = f"{cache_key}_ts"
        cache = st.session_state.get(cache_key)
        ts = st.session_state.get(cache_ts_key, 0)
        if cache and (time.time() - ts) < 10:
            return cache
    except Exception:
        pass
    hist = []
    try:
        for obj in load_day_type_events(backfill=True, max_rows=5000):
            if obj.get("symbol") != symbol:
                continue
            conf = obj.get("confidence")
            if conf is None:
                continue
            hist.append(conf)
    except Exception:
        hist = []
    if hist:
        hist = [h for h in hist if isinstance(h, (int, float))]
        hist = hist[-max_points:]
    try:
        st.session_state[cache_key] = hist
        st.session_state[cache_ts_key] = time.time()
    except Exception:
        pass
    return hist

def _fill_strike_from_meta(df, meta_map):
    try:
        if df is None or df.empty:
            return df
        if "strike" not in df.columns:
            df["strike"] = None
        if "type" not in df.columns:
            df["type"] = None
        if "expiry" not in df.columns:
            df["expiry"] = None
        for idx, row in df.iterrows():
            strike = row.get("strike")
            if strike not in (None, "", "None") and not (isinstance(strike, float) and pd.isna(strike)):
                continue
            tok = row.get("instrument_token")
            if tok is None:
                continue
            meta = meta_map.get(tok, {})
            if not meta:
                continue
            if strike in (None, "", "None") or (isinstance(strike, float) and pd.isna(strike)):
                df.at[idx, "strike"] = meta.get("strike")
            if not row.get("type"):
                df.at[idx, "type"] = meta.get("type")
            if not row.get("expiry"):
                df.at[idx, "expiry"] = meta.get("expiry")
        return df
    except Exception:
        return df

def _fill_type_from_legs(df):
    try:
        if df is None or df.empty:
            return df
        if "type" not in df.columns:
            df["type"] = None
        if "legs" not in df.columns:
            return df
        for idx, row in df.iterrows():
            t = row.get("type")
            if t not in (None, "", "None") and not (isinstance(t, float) and pd.isna(t)):
                continue
            t_val = _infer_type_from_legs(row.get("legs"))
            if t_val:
                df.at[idx, "type"] = t_val
        return df
    except Exception:
        return df

def _fill_strike_from_legs(df):
    try:
        if df is None or df.empty:
            return df
        if "strike" not in df.columns:
            df["strike"] = None
        if "legs" not in df.columns:
            return df
        for idx, row in df.iterrows():
            strike = row.get("strike")
            if strike not in (None, "", "None") and not (isinstance(strike, float) and pd.isna(strike)):
                continue
            strike_val = _infer_strike_from_legs(row.get("legs") or [])
            if strike_val is None:
                continue
            df.at[idx, "strike"] = strike_val
        return df
    except Exception:
        return df

def _infer_strike_from_legs(legs):
    try:
        import re
        from collections import Counter
        strikes = []
        for leg in legs or []:
            m = re.search(r"(\d{3,6}(?:\.\d+)?)", str(leg))
            if m:
                try:
                    strikes.append(float(m.group(1)))
                except Exception:
                    continue
        if not strikes:
            return None
        strike_val = Counter(strikes).most_common(1)[0][0]
        if isinstance(strike_val, float) and strike_val.is_integer():
            return int(strike_val)
        return strike_val
    except Exception:
        return None

def _get_quote_cache():
    try:
        cache = st.session_state.get("quote_fallback_cache", {})
        ts = st.session_state.get("quote_fallback_cache_ts", 0)
        return cache, ts
    except Exception:
        return {}, 0

def _set_quote_cache(cache):
    try:
        st.session_state["quote_fallback_cache"] = cache
        st.session_state["quote_fallback_cache_ts"] = time.time()
    except Exception:
        pass

def _hydrate_option_quotes(df, chain_map, cache_ttl=8):
    try:
        if df is None or df.empty:
            return df
        if "opt_ltp" not in df.columns:
            df["opt_ltp"] = None
        if "opt_bid" not in df.columns:
            df["opt_bid"] = None
        if "opt_ask" not in df.columns:
            df["opt_ask"] = None
        if "quote_note" not in df.columns:
            df["quote_note"] = None
        cache, cache_ts = _get_quote_cache()
        pending = []
        for idx, row in df.iterrows():
            if pd.notna(row.get("opt_ltp")) and pd.notna(row.get("opt_bid")) and pd.notna(row.get("opt_ask")):
                continue
            # For spreads, compute net quote from legs to avoid confusing single-leg prices
            if row.get("instrument") == "SPREAD" and row.get("legs"):
                try:
                    sym = row.get("symbol")
                    chain = (chain_map.get(sym) or []) if sym else []
                    legs = row.get("legs") or []
                    expiry = row.get("expiry")
                    def _leg_quote(leg):
                        parts = str(leg).strip().split()
                        if len(parts) < 3:
                            return None
                        side = parts[0].upper()
                        opt_type = parts[1].upper()
                        try:
                            strike = float(parts[2])
                        except Exception:
                            return None
                        opt = next((o for o in chain if str(o.get("type")) == opt_type and float(o.get("strike", 0)) == strike), None)
                        if opt:
                            return side, opt
                        # fallback: quote via Kite symbol lookup
                        try:
                            from core.kite_client import kite_client
                            exchange = "BFO" if str(sym).upper() == "SENSEX" else "NFO"
                            qsym = None
                            if expiry:
                                qsym = kite_client.find_option_symbol_with_expiry(sym, strike, opt_type, expiry, exchange=exchange)
                            if not qsym:
                                qsym = kite_client.find_option_symbol(sym, strike, opt_type, exchange=exchange)
                            if qsym:
                                if cache and (time.time() - cache_ts) < cache_ttl and qsym in cache:
                                    q = cache[qsym]
                                    ltp = q.get("ltp")
                                    bid = q.get("bid")
                                    ask = q.get("ask")
                                else:
                                    q = kite_client.quote([qsym]).get(qsym, {})
                                    ltp = q.get("last_price")
                                    depth = q.get("depth") or {}
                                    bid = depth.get("buy", [{}])[0].get("price")
                                    ask = depth.get("sell", [{}])[0].get("price")
                                    cache[qsym] = {"ltp": ltp, "bid": bid, "ask": ask}
                                return side, {"ltp": ltp, "bid": bid, "ask": ask}
                        except Exception:
                            return None
                        return None
                    leg_quotes = []
                    for leg in legs:
                        q = _leg_quote(leg)
                        if q:
                            leg_quotes.append(q)
                    if leg_quotes and len(leg_quotes) == len(legs):
                        net_ltp = 0.0
                        net_bid = 0.0
                        net_ask = 0.0
                        for side, opt in leg_quotes:
                            ltp = float(opt.get("ltp", 0) or 0)
                            bid = float(opt.get("bid", 0) or 0)
                            ask = float(opt.get("ask", 0) or 0)
                            if side == "BUY":
                                net_ltp += ltp
                                net_bid += bid
                                net_ask += ask
                            else:
                                net_ltp -= ltp
                                net_bid -= ask  # conservative
                                net_ask -= bid
                        df.at[idx, "opt_ltp"] = round(net_ltp, 2)
                        df.at[idx, "opt_bid"] = round(net_bid, 2)
                        df.at[idx, "opt_ask"] = round(net_ask, 2)
                        df.at[idx, "quote_note"] = "net_spread"
                        _set_quote_cache(cache)
                        continue
                    else:
                        df.at[idx, "quote_note"] = "missing_leg_quote"
                        continue
                except Exception:
                    pass
            sym = row.get("symbol")
            strike = row.get("strike")
            token = row.get("instrument_token")
            if not sym or strike in (None, "ATM"):
                continue
            opt_type = row.get("type") or _infer_type_from_id(row.get("trade_id"))
            if not opt_type:
                continue
            chain = chain_map.get(sym) or []
            match = None
            if token:
                match = next((c for c in chain if c.get("instrument_token") == token), None)
            if match is None:
                try:
                    strike_val = float(strike)
                except Exception:
                    strike_val = None
                if strike_val is not None:
                    match = next((c for c in chain if c.get("strike") == strike_val and c.get("type") == opt_type), None)
            if not match:
                # fallback: quote by token/strike from instruments
                exchange = "BFO" if str(sym).upper() == "SENSEX" else "NFO"
                quote_symbol = None
                if token:
                    token_map = _get_token_symbol_map(exchange)
                    ts = token_map.get(token) or token_map.get(int(token)) if token_map else None
                    if ts:
                        quote_symbol = f"{exchange}:{ts}"
                        df.at[idx, "quote_note"] = "token_fallback"
                if not quote_symbol and strike is not None:
                    try:
                        from core.kite_client import kite_client
                        quote_symbol = kite_client.find_option_symbol(sym, strike, opt_type, exchange=exchange)
                        if quote_symbol:
                            df.at[idx, "quote_note"] = "symbol_fallback"
                    except Exception:
                        quote_symbol = None
                if quote_symbol:
                    if cache and (time.time() - cache_ts) < cache_ttl and quote_symbol in cache:
                        cached = cache[quote_symbol]
                        df.at[idx, "opt_ltp"] = cached.get("ltp")
                        df.at[idx, "opt_bid"] = cached.get("bid")
                        df.at[idx, "opt_ask"] = cached.get("ask")
                    else:
                        pending.append((idx, quote_symbol))
                else:
                    df.at[idx, "quote_note"] = "strike not in live chain"
                continue
            df.at[idx, "opt_ltp"] = match.get("ltp")
            df.at[idx, "opt_bid"] = match.get("bid")
            df.at[idx, "opt_ask"] = match.get("ask")
        if pending:
            try:
                from core.kite_client import kite_client
                symbols = list({s for _, s in pending})
                quotes = kite_client.quote(symbols)
                for idx, sym in pending:
                    q = quotes.get(sym, {})
                    if not q:
                        df.at[idx, "quote_note"] = df.at[idx, "quote_note"] or "quote_missing"
                        continue
                    ltp = q.get("last_price")
                    depth = q.get("depth") or {}
                    bid = depth.get("buy", [{}])[0].get("price")
                    ask = depth.get("sell", [{}])[0].get("price")
                    df.at[idx, "opt_ltp"] = ltp
                    df.at[idx, "opt_bid"] = bid
                    df.at[idx, "opt_ask"] = ask
                    cache[sym] = {"ltp": ltp, "bid": bid, "ask": ask}
                _set_quote_cache(cache)
            except Exception:
                pass
        return df
    except Exception:
        return df

def _add_entry_mismatch(df, threshold=None):
    try:
        if df is None or df.empty:
            return df
        if threshold is None:
            try:
                from config import config as cfg
                threshold = float(getattr(cfg, "ENTRY_MISMATCH_PCT", 0.25))
            except Exception:
                threshold = 0.25
        if "entry" not in df.columns or "opt_ltp" not in df.columns:
            return df
        def _mismatch_pct(row):
            try:
                e = row.get("entry")
                l = row.get("opt_ltp")
                if e is None or l is None:
                    return None
                e = float(e)
                l = float(l)
                if l <= 0:
                    return None
                return round(abs(l - e) / l * 100.0, 2)
            except Exception:
                return None
        df["entry_mismatch_pct"] = df.apply(_mismatch_pct, axis=1)
        df["entry_mismatch_note"] = df["entry_mismatch_pct"].apply(
            lambda v: "⚠️ mismatch" if (v is not None and v >= threshold * 100) else ""
        )
        return df
    except Exception:
        return df

def _filter_rows_today(rows, ts_key="timestamp"):
    try:
        now = now_local()
        filtered = []
        for r in rows:
            ts = r.get(ts_key)
            if not ts:
                continue
            if is_today_local(ts, now=now):
                filtered.append(r)
        return filtered
    except Exception:
        return rows

def _load_gpt_advice():
    path = Path("logs/gpt_advice.jsonl")
    if not path.exists():
        return {}
    latest = {}
    try:
        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                tid = obj.get("trade_id")
                if tid:
                    latest[tid] = obj.get("advice")
    except Exception:
        return {}
    return latest

def _load_gpt_pins():
    path = Path("logs/gpt_pins.json")
    if not path.exists():
        return set()

def _load_auto_tune():
    try:
        path = Path("logs/auto_tune.json")
        if not path.exists():
            return {}
        return json.loads(path.read_text())
    except Exception:
        return {}

def _push_notification(kind, message):
    try:
        items = st.session_state.get("notifications", [])
        items.append({"ts": datetime.now().isoformat(), "kind": kind, "message": message})
        st.session_state["notifications"] = items[-5:]
    except Exception:
        pass

def _render_notifications():
    try:
        items = st.session_state.get("notifications", [])
        if not items:
            return
        with st.container():
            cols = st.columns([8, 1])
            with cols[0]:
                for n in items:
                    kind = n.get("kind", "info")
                    msg = n.get("message", "")
                    cls = "success" if kind == "success" else "error" if kind == "error" else "warn" if kind == "warn" else "warn"
                    st.markdown(f"<div class='banner {cls}'>{msg}</div>", unsafe_allow_html=True)
            with cols[1]:
                if st.button("Clear", key="clear_notifications"):
                    st.session_state["notifications"] = []
    except Exception:
        pass

def _empty_state(title, body=""):
    st.markdown(f"<div class='empty-state'><strong>{title}</strong><div>{body}</div></div>", unsafe_allow_html=True)

def _render_skeleton(lines=3):
    st.markdown("".join(["<div class='skeleton'></div>" for _ in range(lines)]), unsafe_allow_html=True)

def _render_table(df, key, page_size=20, height=420, empty_title="No data", empty_body=""):
    if df is None or df.empty:
        _empty_state(empty_title, empty_body)
        return
    total = len(df)
    pages = max(1, math.ceil(total / page_size))
    page = 1
    if pages > 1:
        page = st.number_input("Page", min_value=1, max_value=pages, value=1, step=1, key=f"{key}_page")
        st.caption(f"Page {page}/{pages} • {total} rows")
    start = (page - 1) * page_size
    view = df.iloc[start:start + page_size]
    html = view.to_html(index=False, classes="rt-table", escape=True)
    st.markdown(f"<div class='rt-table-wrap' style='max-height:{height}px'>{html}</div>", unsafe_allow_html=True)

def _confirm_action(key, label, confirm_label="Confirm", cancel_label="Cancel", help_text="Are you sure?"):
    if st.button(label, key=f"{key}_btn"):
        st.session_state[f"{key}_confirm"] = True
    if st.session_state.get(f"{key}_confirm"):
        st.markdown(f"<div class='banner warn'>{help_text}</div>", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 1])
        if c1.button(confirm_label, key=f"{key}_confirm_btn"):
            st.session_state[f"{key}_confirm"] = False
            return True
        if c2.button(cancel_label, key=f"{key}_cancel_btn"):
            st.session_state[f"{key}_confirm"] = False
    return False
    try:
        return set(json.loads(path.read_text()))
    except Exception:
        return set()

def _save_gpt_pins(pins):
    path = Path("logs/gpt_pins.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(sorted(list(pins))))

def _render_gpt_panel(trade_row: dict, market_ctx: dict, key_prefix: str):
    tid = trade_row.get("trade_id")
    if not tid:
        return
    advice_cache = st.session_state.get("gpt_advice_cache", {})
    if tid in advice_cache:
        st.json(advice_cache[tid])
    # Per-panel cooldown display
    cooldown = st.session_state.get("gpt_cooldown_sec", 10)
    last = st.session_state.get("gpt_last_call", {})
    now = time.time()
    remaining = max(0, cooldown - (now - last.get(key_prefix, 0)))
    if remaining > 0:
        st.caption(f"Cooldown: {remaining:.0f}s")
        return
    if st.button("Gemini Advice", key=f"{key_prefix}_gpt_{tid}"):
        with st.spinner("Requesting Gemini advice..."):
            advice = get_trade_advice(trade_row, market_ctx)
            advice_cache[tid] = advice
            st.session_state["gpt_advice_cache"] = advice_cache
            meta = {"symbol": trade_row.get("symbol"), "strategy": trade_row.get("strategy"), "tier": trade_row.get("tier")}
            save_advice(tid, advice, meta=meta)
        st.json(advice)
        last[key_prefix] = time.time()
        st.session_state["gpt_last_call"] = last
    # Pin button
    pins = _load_gpt_pins()
    if st.button("Pin Gemini Advice", key=f"{key_prefix}_pin_{tid}"):
        pins.add(tid)
        _save_gpt_pins(pins)
        st.success(f"Pinned {tid}")

if nav == "Home":
    section_header("Ready To Place Trades")
    try:
        readiness = {}
        state = "UNKNOWN"
        can_trade = False
        blockers = []
        warnings = []
        feed = {}
        kite = {}
        breaker_tripped = False
        auth_health = {}
        feed_freshness = {}
        try:
            from core.readiness_gate import run_readiness_check
            from core.auth_health import get_kite_auth_health
            from core.freshness_sla import get_freshness_status
            readiness = run_readiness_check(write_log=False)
            state = readiness.get("state", "UNKNOWN")
            can_trade = bool(readiness.get("can_trade", False))
            blockers = list(readiness.get("blockers") or [])
            warnings = list(readiness.get("warnings") or [])
            checks = readiness.get("checks") or {}
            feed = checks.get("feed_health") or {}
            kite = checks.get("kite_auth") or {}
            breaker_tripped = bool((checks.get("feed_breaker") or {}).get("tripped"))
            auth_health = get_kite_auth_health(force=False)
            feed_freshness = get_freshness_status(force=False)
            if state == "MARKET_CLOSED":
                shown_ts = float(st.session_state.get("force_show_quote_errors_ts", 0.0) or 0.0)
                if shown_ts and (time.time() - shown_ts) > 300.0:
                    st.session_state["force_show_quote_errors"] = False
                    st.session_state["force_show_quote_errors_ts"] = 0.0
        except Exception:
            st.error("Readiness: BLOCKED — readiness check unavailable")
        if breaker_tripped:
            st.error("Feed breaker tripped — manual clear required. Run: scripts/clear_feed_breaker.py --yes-i-mean-it")
        # Live quotes status banner
        try:
            quote_err = None
            err_path = Path("logs/live_quote_errors.jsonl")
            if err_path.exists():
                lines = err_path.read_text().strip().splitlines()
                if lines:
                    import json as _json
                    quote_err = _json.loads(lines[-1])
                    # Ignore stale errors
                    try:
                        from config import config as cfg
                        ts = quote_err.get("timestamp")
                        if ts:
                            err_dt = datetime.fromisoformat(ts)
                            if err_dt.tzinfo is None:
                                err_dt = err_dt.replace(tzinfo=timezone.utc)
                            age = (datetime.now(timezone.utc) - err_dt.astimezone(timezone.utc)).total_seconds()
                            if age > getattr(cfg, "LIVE_QUOTE_ERROR_TTL_SEC", 300):
                                quote_err = None
                    except Exception:
                        pass
            chain_health = {}
            health_path = Path("logs/option_chain_health.json")
            if health_path.exists():
                try:
                    chain_health = json.loads(health_path.read_text())
                except Exception:
                    chain_health = {}
            status = "OK"
            notes = []
            auth_ok = bool(auth_health.get("ok", False))
            auth_reason = auth_health.get("error") or auth_health.get("reason")
            if not auth_ok:
                status = "ERROR"
                notes.append(f"Auth unhealthy: {auth_reason}")
            feed_ok = bool(feed_freshness.get("ok", True))
            if bool(feed_freshness.get("market_open", False)) and not feed_ok:
                status = "ERROR"
                notes.append("Feed stale (market open)")
            if quote_err and status == "OK":
                status = "WARN"
                notes.append("Live quote fetch failed")
            if chain_health:
                bad = [k for k, v in chain_health.items() if isinstance(v, dict) and v.get("status") in ("ERROR", "WARN")]
                if bad:
                    status = "WARN" if status == "OK" else status
                    notes.append(f"Chain health issues: {', '.join(bad)}")
            show_errors = _should_show_quote_errors(state)
            if state == "MARKET_CLOSED" and not show_errors:
                st.info("Market closed — no trading. Live quote errors hidden off-hours.")
            else:
                if status == "OK":
                    st.success("Live Quotes: OK")
                elif status == "WARN":
                    st.warning("Live Quotes: WARN — " + "; ".join(notes))
                else:
                    # Try to show last error detail + reason classification
                    detail = ""
                    reason = ""
                    try:
                        if quote_err and quote_err.get("detail"):
                            detail = str(quote_err.get("detail"))
                        elif quote_err:
                            detail = str(quote_err)
                    except Exception:
                        detail = ""
                    dlow = detail.lower()
                    if "name resolution" in dlow or "failed to resolve" in dlow or "dns" in dlow:
                        reason = "Network/DNS issue"
                    elif "api_key" in dlow or "access_token" in dlow or "invalid" in dlow:
                        reason = "Auth/Token issue"
                    elif "429" in dlow or "rate" in dlow:
                        reason = "Rate limit"
                    if reason:
                        reason = f" ({reason})"
                    st.error("Live Quotes: ERROR — " + "; ".join(notes) + (f" [{reason.strip()}]" if reason else "") + (f" ({detail})" if detail else ""))
        except Exception:
            pass
        try:
            show_errors = _should_show_quote_errors(state)
            clear_disabled = not show_errors
            if state == "MARKET_CLOSED":
                with st.expander("Diagnostics", expanded=False):
                    col_q1, col_q2 = st.columns([1, 3])
                    if col_q1.button("Test Live Quotes", key="test_live_quotes"):
                        st.session_state["force_show_quote_errors"] = True
                        st.session_state["force_show_quote_errors_ts"] = time.time()
                        from core.market_data import get_ltp
                        for sym in ["NIFTY", "BANKNIFTY", "SENSEX"]:
                            get_ltp(sym)
                        if hasattr(st, "toast"):
                            st.toast("Live quote fetch triggered")
                    if col_q2.button("Clear Live Quote Errors", key="clear_live_quote_errors", disabled=clear_disabled):
                        try:
                            Path("logs/live_quote_errors.jsonl").write_text("")
                            st.success("Cleared live quote error log.")
                        except Exception:
                            st.warning("Unable to clear live quote error log.")
                    try:
                        auth_ok = bool(auth_health.get("ok", False))
                        auth_err = auth_health.get("error") or "ok"
                        st.caption(f"Kite auth: {'OK' if auth_ok else 'ERROR'} — {auth_err}")
                    except Exception:
                        pass
                    try:
                        sla_state = str(feed_freshness.get("state") or "UNKNOWN")
                        ltp_age = (feed_freshness.get("ltp") or {}).get("age_sec")
                        depth_age = (feed_freshness.get("depth") or {}).get("age_sec")
                        st.caption(f"SLA (hidden off-hours): state={sla_state} ltp_age={ltp_age} depth_age={depth_age}")
                    except Exception:
                        pass
            else:
                col_q1, col_q2 = st.columns([1, 3])
                if col_q1.button("Test Live Quotes", key="test_live_quotes"):
                    st.session_state["force_show_quote_errors"] = True
                    st.session_state["force_show_quote_errors_ts"] = time.time()
                    from core.market_data import get_ltp
                    for sym in ["NIFTY", "BANKNIFTY", "SENSEX"]:
                        get_ltp(sym)
                    if hasattr(st, "toast"):
                        st.toast("Live quote fetch triggered")
                if col_q2.button("Clear Live Quote Errors", key="clear_live_quote_errors", disabled=clear_disabled):
                    try:
                        Path("logs/live_quote_errors.jsonl").write_text("")
                        st.success("Cleared live quote error log.")
                    except Exception:
                        st.warning("Unable to clear live quote error log.")
        except Exception:
            pass
        try:
            enabled, allowed, total = _wf_lock_status()
            if enabled:
                if allowed is not None and total is not None:
                    st.success(f"WF Lock: ACTIVE — {allowed}/{total} strategies allowed")
                    if allowed == 0:
                        st.warning("WF Lock is active but no strategies passed walk-forward.")
                else:
                    st.success("WF Lock: ACTIVE")
            else:
                st.info("WF Lock: OFF")
        except Exception:
            pass
        # Auto-tune status badge
        try:
            tune = _load_auto_tune()
            if tune.get("enabled"):
                st.success(
                    "Auto‑Tune: ACTIVE — "
                    f"RR≥{tune.get('min_rr')} | "
                    f"Proba≥{tune.get('min_proba')} | "
                    f"Score≥{tune.get('trade_score_min')} "
                    f"(win_rate={tune.get('win_rate')}, avg_pnl={tune.get('avg_pnl')})"
                )
            else:
                st.info("Auto‑Tune: OFF or insufficient trades")
        except Exception:
            pass
        try:
            badge = {
                "READY": "🟩",
                "DEGRADED": "🟨",
                "MARKET_CLOSED": "🟦",
                "BLOCKED": "🟥",
                "BOOTING": "⬜",
            }.get(state, "⬜")
            reason_tokens = blockers if blockers else warnings
            reason_line = " | ".join(reason_tokens[:2]) if reason_tokens else "ok"
            st.markdown(f"**{badge} {state} | {reason_line}**")
            if state == "READY":
                st.success("Readiness: READY — can trade")
            elif state == "DEGRADED":
                st.warning("Readiness: DEGRADED — do NOT auto-trade")
            elif state == "MARKET_CLOSED":
                st.info("Readiness: MARKET_CLOSED — no trading")
            elif state == "BOOTING":
                st.info("Readiness: BOOTING — warming up")
            else:
                st.error("Readiness: BLOCKED — trading disabled")
            if blockers:
                st.error("Blockers: " + ", ".join(blockers))
            if warnings:
                st.warning("Warnings: " + ", ".join(warnings))
        except Exception:
            st.error("Readiness: BLOCKED — readiness check unavailable")
        try:
            market_open = bool(feed_freshness.get("market_open", False))
            ltp = feed_freshness.get("ltp") or {}
            depth = feed_freshness.get("depth") or {}
            ltp_age = ltp.get("age_sec")
            depth_age = depth.get("age_sec")
            ltp_max = ltp.get("max_age_sec")
            depth_max = depth.get("max_age_sec")
            if market_open:
                st.caption(
                    f"SLA: LTP age={ltp_age:.2f}s (max {ltp_max}) | Depth age={depth_age:.2f}s (max {depth_max})"
                )
        except Exception:
            pass
        checklist = []
        checklist.append(("Readiness can_trade", can_trade))
        checklist.append(("Kite auth OK", bool(kite.get("ok"))))
        checklist.append(("Feed OK (market-open gating)", bool(feed.get("ok"))))
        checklist.append(("Review queue active", Path("logs/review_queue.json").exists()))
        checklist.append(("Risk monitor running", Path("logs/risk_monitor.json").exists()))
        checklist.append(("Execution analytics", Path("logs/execution_analytics.json").exists()))
        cols = st.columns(2)
        for i, (label, ok) in enumerate(checklist):
            cols[i % 2].write(("✅ " if ok else "⬜ ") + label)
        _render_confidence_reliability()
    except Exception:
        pass

    section_header("Pre‑Market Day Plan")
    try:
        plan_path = Path("logs/premarket_plan.json")
        if st.button("Generate Pre‑Market Plan", key="premarket_plan_btn"):
            import subprocess, sys
            subprocess.run([sys.executable, "scripts/premarket_plan.py"], check=False)
        if plan_path.exists():
            plan = json.loads(plan_path.read_text())
            st.json(plan)
        else:
            empty_state("No pre‑market plan yet.")
    except Exception:
        pass
    section_header("Market Snapshot")
    try:
        # Refresh only the market snapshot during market hours to avoid dimming the whole app
        if _is_market_hours():
            _market_snapshot_fragment()
        else:
            _render_market_snapshot()

    except Exception as e:
        st.warning(f"Market snapshot error: {e}")

    section_header("Gate Status (Latest)")
    try:
        gate_path = Path(f"logs/desks/{getattr(cfg, 'DESK_ID', 'DEFAULT')}/gate_status.jsonl")
        if gate_path.exists():
            rows = []
            with gate_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()[-40:]
            for line in lines:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
            if rows:
                gate_df = pd.DataFrame(rows)
                cols = [
                    c
                    for c in [
                        "ts_ist",
                        "symbol",
                        "stage",
                        "indicators_ok",
                        "indicators_age_sec",
                        "primary_regime",
                        "regime_prob_max",
                        "regime_entropy",
                        "indicator_reasons",
                        "regime_reasons",
                        "gate_allowed",
                        "gate_family",
                        "gate_reasons",
                    ]
                    if c in gate_df.columns
                ]
                if cols:
                    ui.table(gate_df[cols].sort_values("ts_ist", ascending=False).head(20), use_container_width=True)
                else:
                    ui.table(gate_df.sort_values("ts_ist", ascending=False).head(20), use_container_width=True)
            else:
                empty_state("No gate status records yet.")
        else:
            empty_state("No gate status file yet.")
    except Exception as e:
        st.warning(f"Gate status error: {e}")

    section_header("Main Trades (High Accuracy)")
    section_header("Manual Review Queue")
    try:
        from core.review_queue import approve, remove_from_queue
        q_path = Path("logs/review_queue.json")
        if q_path.exists():
            q_all = json.loads(q_path.read_text())
            q = _filter_rows_today(q_all)
            if q:
                show_quotes = st.checkbox("Show bid/ask/ltp", value=False, key="show_quotes_main")
                chain_map = _get_chain_map() if show_quotes else {}
                q_df = pd.DataFrame(q)
                meta_map = _get_instrument_meta_map()
                if "trade_id" in q_df.columns:
                    inferred = q_df["trade_id"].apply(_infer_strike_from_id)
                    if "strike" in q_df.columns:
                        q_df["strike"] = q_df["strike"].where(q_df["strike"].notna(), inferred)
                    else:
                        q_df["strike"] = inferred
                    inferred_type = q_df["trade_id"].apply(_infer_type_from_id)
                    if "type" in q_df.columns:
                        q_df["type"] = q_df["type"].where(q_df["type"].notna(), inferred_type)
                    else:
                        q_df["type"] = inferred_type
                q_df = _fill_strike_from_legs(q_df)
                q_df = _fill_type_from_legs(q_df)
                q_df = _fill_strike_from_meta(q_df, meta_map)
                q_df = _fill_type_from_derived(q_df, meta_map)
                if "strike" in q_df.columns:
                    q_df["strike"] = q_df["strike"].astype(str)
                # show only single-leg options (OPT)
                if "instrument" in q_df.columns:
                    q_df = q_df[q_df["instrument"] == "OPT"]
                if "strike" in q_df.columns:
                    q_df["strike"] = q_df["strike"].astype(str)
                if show_quotes:
                    q_df = _hydrate_option_quotes(q_df, chain_map)
                    q_df = _add_entry_mismatch(q_df)
                q_display = q_df.drop(columns=["trade_id"], errors="ignore")
                display_cols = [c for c in ["timestamp", "symbol", "instrument_id", "expiry", "strike", "type", "instrument", "side", "entry", "entry_condition", "entry_ref_price", "stop", "target", "trail_stop_last", "trail_updates", "exit_reason", "qty", "qty_lots", "qty_units", "tradable", "tradable_reasons_blocking", "confidence", "strategy", "regime", "tier", "trade_score", "trade_alignment", "max_profit_label", "max_loss_label", "breakeven_low", "breakeven_high", "est_pnl_at_ltp", "legs"] if c in q_df.columns]
                if show_quotes:
                    display_cols += [c for c in ["opt_ltp", "opt_bid", "opt_ask", "quote_ok"] if c in q_df.columns]
                    display_cols += [c for c in ["quote_note"] if c in q_df.columns]
                    display_cols += [c for c in ["entry_mismatch_pct", "entry_mismatch_note"] if c in q_df.columns]
                if display_cols:
                    ui.table(q_display[display_cols], use_container_width=True)
                else:
                    ui.table(q_display, use_container_width=True)
                q_rows = q_df.to_dict("records")
                if st.button("Clear Queue"):
                    q_path.write_text(json.dumps([], indent=2))
                    st.success("Queue cleared.")
                    q = []
                    q_df = pd.DataFrame(q)
                    q_rows = []
                st.subheader("Suggested Trades (Latest)")
                show_cols = [c for c in ["timestamp", "symbol", "instrument_id", "expiry", "strike", "type", "instrument", "side", "entry", "entry_condition", "entry_ref_price", "stop", "target", "trail_stop_last", "trail_updates", "exit_reason", "qty", "qty_lots", "qty_units", "tradable", "tradable_reasons_blocking", "confidence", "strategy", "regime", "tier", "trade_score", "trade_alignment", "max_profit_label", "max_loss_label", "breakeven_low", "breakeven_high", "est_pnl_at_ltp", "legs"] if c in q_df.columns]
                if show_quotes:
                    show_cols += [c for c in ["opt_ltp", "opt_bid", "opt_ask", "quote_ok"] if c in q_df.columns]
                    show_cols += [c for c in ["quote_note"] if c in q_df.columns]
                    show_cols += [c for c in ["entry_mismatch_pct", "entry_mismatch_note"] if c in q_df.columns]
                ui.table(q_df.sort_values("timestamp", ascending=False)[show_cols].head(20), use_container_width=True)
                with st.container():
                    show_pretrade = st.toggle("Advanced: Pre-Trade Validation", value=False, key="adv_pretrade")
                    if show_pretrade:
                        st.subheader("Pre-Trade Validation Report")
                        val_cols = [c for c in ["trade_id", "pretrade_conf_ok", "pretrade_rr", "pretrade_rr_ok", "pretrade_time"] if c in q_df.columns]
                        if val_cols:
                            sort_col = "pretrade_time" if "pretrade_time" in q_df.columns else ("timestamp" if "timestamp" in q_df.columns else None)
                            if sort_col:
                                ui.table(q_df[val_cols].sort_values(sort_col, ascending=False).head(20), use_container_width=True)
                            else:
                                ui.table(q_df[val_cols].head(20), use_container_width=True)
                for i, row in enumerate(q_rows):
                    tid = row.get("trade_id")
                    if not tid:
                        continue
                    if row.get("instrument") != "OPT":
                        continue
                    with st.container():
                        cols = st.columns([2, 1, 1, 1])
                        strike_val = row.get("strike")
                        if strike_val in (None, "", "None"):
                            strike_val = _infer_strike_from_id(tid)
                        if strike_val in (None, "", "None"):
                            strike_val = _infer_strike_from_legs(row.get("legs"))
                        if strike_val in (None, "", "None") and row.get("instrument_token"):
                            meta = meta_map.get(row.get("instrument_token"), {})
                            strike_val = meta.get("strike")
                        type_val = _derive_option_type(row, meta_map)
                        expiry_val = row.get("expiry")
                        if expiry_val in (None, "", "None") and row.get("instrument_token"):
                            meta = meta_map.get(row.get("instrument_token"), {})
                            expiry_val = meta.get("expiry")
                        instrument_id = row.get("instrument_id")
                        if not instrument_id:
                            label = f"{row.get('symbol')} {strike_val} {type_val}".strip()
                            label = f"INVALID (missing contract) | {label}"
                        else:
                            label = f"{row.get('symbol')} {instrument_id}"
                        if expiry_val not in (None, "", "None"):
                            label = f"{label} | {expiry_val}"
                        entry_val = row.get("entry")
                        stop_val = row.get("stop")
                        target_val = row.get("target")
                        price_bits = []
                        if entry_val is not None:
                            price_bits.append(f"E:{entry_val}")
                        if stop_val is not None:
                            price_bits.append(f"S:{stop_val}")
                        if target_val is not None:
                            price_bits.append(f"T:{target_val}")
                        cond = row.get("entry_condition")
                        if cond:
                            price_bits.append(cond.replace("_", " "))
                        if price_bits:
                            label = f"{label}  ({' | '.join(price_bits)})"
                        cols[0].write(label)
                        # Why this trade passed (live summary)
                        detail = row.get("trade_score_detail") or {}
                        if detail:
                            comps = detail.get("components", {})
                            issues = detail.get("issues", [])
                            if comps:
                                top = sorted(comps.items(), key=lambda x: x[1], reverse=True)[:3]
                                cols[0].caption("Why passed: " + ", ".join([f"{k}:{v:.0f}" for k, v in top]))
                            if issues:
                                cols[0].caption("Risks: " + ", ".join(issues))
                        # Thresholds used (auto‑tuned if available)
                        try:
                            tune = _load_auto_tune()
                            if tune.get("enabled"):
                                cols[0].caption(
                                    f"Thresholds: score≥{tune.get('trade_score_min')}, "
                                    f"rr≥{tune.get('min_rr')}, proba≥{tune.get('min_proba')}"
                                )
                        except Exception:
                            pass
                        if cols[1].button("Approve", key=f"approve_{tid}_{i}"):
                            approve(tid)
                            remove_from_queue(tid)
                            st.success(f"Approved {tid}")
                        if cols[2].button("Reject", key=f"reject_{tid}_{i}"):
                            remove_from_queue(tid)
                            st.warning(f"Rejected {tid}")
            else:
                empty_state("No pending trades in review queue for today.")
        else:
            empty_state("No review queue file yet.")
    except Exception as e:
        st.warning(f"Review queue error: {e}")

    section_header("Exploration Trades (Learning Mode)")
    section_header("Quick Trade Suggestions (Preview)")
    try:
        q2_path = Path("logs/quick_review_queue.json")
        if q2_path.exists():
            q2_all = json.loads(q2_path.read_text())
            q2 = _filter_rows_today(q2_all)
            if q2:
                show_quotes_q = st.checkbox("Show bid/ask/ltp", value=False, key="show_quotes_quick")
                chain_map = _get_chain_map() if show_quotes_q else {}
                q2_df = pd.DataFrame(q2)
                meta_map_q2 = _get_instrument_meta_map()
                if "trade_id" in q2_df.columns:
                    inferred = q2_df["trade_id"].apply(_infer_strike_from_id)
                    if "strike" in q2_df.columns:
                        q2_df["strike"] = q2_df["strike"].where(q2_df["strike"].notna(), inferred)
                    else:
                        q2_df["strike"] = inferred
                    inferred_type = q2_df["trade_id"].apply(_infer_type_from_id)
                    if "type" in q2_df.columns:
                        q2_df["type"] = q2_df["type"].where(q2_df["type"].notna(), inferred_type)
                    else:
                        q2_df["type"] = inferred_type
                q2_df = _fill_strike_from_legs(q2_df)
                q2_df = _fill_type_from_legs(q2_df)
                q2_df = _fill_strike_from_meta(q2_df, meta_map_q2)
                q2_df = _fill_type_from_derived(q2_df, meta_map_q2)
                if "strike" in q2_df.columns:
                    q2_df["strike"] = q2_df["strike"].astype(str)
                # Display order for quick suggestions
                if "qty" in q2_df.columns:
                    q2_df = q2_df.rename(columns={"qty": "lot"})
                # show only single-leg options (OPT)
                if "instrument" in q2_df.columns:
                    q2_df = q2_df[q2_df["instrument"] == "OPT"]
                if show_quotes_q:
                    q2_df = _hydrate_option_quotes(q2_df, chain_map)
                    q2_df = _add_entry_mismatch(q2_df)
                q2_display = q2_df.drop(columns=["trade_id"], errors="ignore")
                show_cols = [c for c in ["symbol", "instrument_id", "expiry", "strike", "type", "side", "entry", "entry_condition", "entry_ref_price", "stop", "target", "trail_stop_last", "trail_updates", "exit_reason", "tradable", "tradable_reasons_blocking", "confidence", "lot", "regime", "tier", "timestamp"] if c in q2_df.columns]
                if show_quotes_q:
                    show_cols += [c for c in ["opt_ltp", "opt_bid", "opt_ask", "quote_ok"] if c in q2_df.columns]
                    show_cols += [c for c in ["quote_note"] if c in q2_df.columns]
                    show_cols += [c for c in ["entry_mismatch_pct", "entry_mismatch_note"] if c in q2_df.columns]
                ui.table(q2_display.sort_values("timestamp", ascending=False)[show_cols].head(20), use_container_width=True)
            else:
                empty_state("No quick suggestions yet for today.")
        else:
            empty_state("No quick suggestions yet.")
    except Exception as e:
        st.warning(f"Quick suggestions error: {e}")

    section_header("20-Point Profit Ideas (Advisory)")
    try:
        t20_path = Path("logs/target_points_queue.json")
        if t20_path.exists():
            t20_all = json.loads(t20_path.read_text())
            t20 = _filter_rows_today(t20_all)
            if t20:
                t20_df = pd.DataFrame(t20)
                meta_map_t20 = _get_instrument_meta_map()
                if "trade_id" in t20_df.columns:
                    inferred = t20_df["trade_id"].apply(_infer_strike_from_id)
                    if "strike" in t20_df.columns:
                        t20_df["strike"] = t20_df["strike"].where(t20_df["strike"].notna(), inferred)
                    else:
                        t20_df["strike"] = inferred
                    inferred_type = t20_df["trade_id"].apply(_infer_type_from_id)
                    if "type" in t20_df.columns:
                        t20_df["type"] = t20_df["type"].where(t20_df["type"].notna(), inferred_type)
                    else:
                        t20_df["type"] = inferred_type
                t20_df = _fill_strike_from_legs(t20_df)
                t20_df = _fill_type_from_legs(t20_df)
                t20_df = _fill_strike_from_meta(t20_df, meta_map_t20)
                t20_df = _fill_type_from_derived(t20_df, meta_map_t20)
                if "instrument" in t20_df.columns:
                    t20_df = t20_df[t20_df["instrument"] == "OPT"]
                if {"target", "entry"}.issubset(set(t20_df.columns)):
                    t20_df["target_points"] = (pd.to_numeric(t20_df["target"], errors="coerce") - pd.to_numeric(t20_df["entry"], errors="coerce")).abs().round(2)
                show_cols = [
                    c
                    for c in [
                        "timestamp",
                        "symbol",
                        "instrument_id",
                        "expiry",
                        "strike",
                        "type",
                        "side",
                        "entry",
                        "target",
                        "target_points",
                        "target_points_min",
                        "stop",
                        "confidence",
                        "strategy",
                        "regime",
                        "tier",
                        "category",
                    ]
                    if c in t20_df.columns
                ]
                if show_cols:
                    ui.table(t20_df.sort_values("timestamp", ascending=False)[show_cols].head(20), use_container_width=True)
                else:
                    ui.table(t20_df.sort_values("timestamp", ascending=False).head(20), use_container_width=True)
                st.caption("Advisory queue only. Trades are still blocked unless readiness and approval gates pass.")
            else:
                empty_state("No 20-point ideas yet for today.")
        else:
            empty_state("No 20-point ideas generated yet.")
    except Exception as e:
        st.warning(f"20-point ideas error: {e}")

    section_header("Zero Hero (Cheap Momentum)")
    try:
        zh_path = Path("logs/zero_hero_queue.json")
        if zh_path.exists():
            zh_all = json.loads(zh_path.read_text())
            zh = _filter_rows_today(zh_all)
            if zh:
                show_quotes_zh = st.checkbox("Show bid/ask/ltp", value=False, key="show_quotes_zh")
                chain_map = _get_chain_map() if show_quotes_zh else {}
                zh_df = pd.DataFrame(zh)
                meta_map_zh = _get_instrument_meta_map()
                if "trade_id" in zh_df.columns:
                    inferred = zh_df["trade_id"].apply(_infer_strike_from_id)
                    if "strike" in zh_df.columns:
                        zh_df["strike"] = zh_df["strike"].where(zh_df["strike"].notna(), inferred)
                    else:
                        zh_df["strike"] = inferred
                    inferred_type = zh_df["trade_id"].apply(_infer_type_from_id)
                    if "type" in zh_df.columns:
                        zh_df["type"] = zh_df["type"].where(zh_df["type"].notna(), inferred_type)
                    else:
                        zh_df["type"] = inferred_type
                zh_df = _fill_strike_from_legs(zh_df)
                zh_df = _fill_type_from_legs(zh_df)
                zh_df = _fill_strike_from_meta(zh_df, meta_map_zh)
                zh_df = _fill_type_from_derived(zh_df, meta_map_zh)
                if "strike" in zh_df.columns:
                    zh_df["strike"] = zh_df["strike"].astype(str)
                # show only single-leg options (OPT)
                if "instrument" in zh_df.columns:
                    zh_df = zh_df[zh_df["instrument"] == "OPT"]
                if show_quotes_zh:
                    zh_df = _hydrate_option_quotes(zh_df, chain_map)
                    zh_df = _add_entry_mismatch(zh_df)
                zh_display = zh_df.drop(columns=["trade_id"], errors="ignore")
                show_cols = [c for c in ["timestamp", "symbol", "strike", "type", "expiry", "side", "entry", "entry_condition", "entry_ref_price", "stop", "target", "qty", "confidence", "strategy", "tier"] if c in zh_df.columns]
                if show_quotes_zh:
                    show_cols += [c for c in ["opt_ltp", "opt_bid", "opt_ask", "quote_ok"] if c in zh_df.columns]
                    show_cols += [c for c in ["quote_note"] if c in zh_df.columns]
                    show_cols += [c for c in ["entry_mismatch_pct", "entry_mismatch_note"] if c in zh_df.columns]
                ui.table(zh_display.sort_values("timestamp", ascending=False)[show_cols].head(20), use_container_width=True)
            else:
                empty_state("No Zero Hero trades yet for today.")
        else:
            empty_state("No Zero Hero trades yet.")
    except Exception as e:
        st.warning(f"Zero Hero error: {e}")

    section_header("Scalp Trades (Range / Low Momentum)")
    try:
        sc_path = Path("logs/scalp_queue.json")
        if sc_path.exists():
            sc_all = json.loads(sc_path.read_text())
            sc = _filter_rows_today(sc_all)
            if sc:
                show_quotes_sc = st.checkbox("Show bid/ask/ltp", value=False, key="show_quotes_sc")
                chain_map = _get_chain_map() if show_quotes_sc else {}
                sc_df = pd.DataFrame(sc)
                meta_map_sc = _get_instrument_meta_map()
                if "trade_id" in sc_df.columns:
                    inferred = sc_df["trade_id"].apply(_infer_strike_from_id)
                    if "strike" in sc_df.columns:
                        sc_df["strike"] = sc_df["strike"].where(sc_df["strike"].notna(), inferred)
                    else:
                        sc_df["strike"] = inferred
                    inferred_type = sc_df["trade_id"].apply(_infer_type_from_id)
                    if "type" in sc_df.columns:
                        sc_df["type"] = sc_df["type"].where(sc_df["type"].notna(), inferred_type)
                    else:
                        sc_df["type"] = inferred_type
                sc_df = _fill_strike_from_legs(sc_df)
                sc_df = _fill_type_from_legs(sc_df)
                sc_df = _fill_strike_from_meta(sc_df, meta_map_sc)
                sc_df = _fill_type_from_derived(sc_df, meta_map_sc)
                if "strike" in sc_df.columns:
                    sc_df["strike"] = sc_df["strike"].astype(str)
                # show only single-leg options (OPT)
                if "instrument" in sc_df.columns:
                    sc_df = sc_df[sc_df["instrument"] == "OPT"]
                if show_quotes_sc:
                    sc_df = _hydrate_option_quotes(sc_df, chain_map)
                    sc_df = _add_entry_mismatch(sc_df)
                sc_display = sc_df.drop(columns=["trade_id"], errors="ignore")
                show_cols = [c for c in ["timestamp", "symbol", "strike", "type", "expiry", "side", "entry", "entry_condition", "entry_ref_price", "stop", "target", "qty", "confidence", "strategy", "tier"] if c in sc_df.columns]
                if show_quotes_sc:
                    show_cols += [c for c in ["opt_ltp", "opt_bid", "opt_ask", "quote_ok"] if c in sc_df.columns]
                    show_cols += [c for c in ["quote_note"] if c in sc_df.columns]
                    show_cols += [c for c in ["entry_mismatch_pct", "entry_mismatch_note"] if c in sc_df.columns]
                ui.table(sc_display.sort_values("timestamp", ascending=False)[show_cols].head(20), use_container_width=True)
            else:
                empty_state("No scalp trades yet for today.")
        else:
            empty_state("No scalp trades yet.")
    except Exception as e:
        st.warning(f"Scalp trades error: {e}")

    section_header("Top Candidates Despite Rejection")
    try:
        reject_path = Path("logs/rejected_candidates.jsonl")
        debug_path = Path("logs/debug_candidates.jsonl")
        if reject_path.exists() or debug_path.exists():
            rej_rows = []
            if reject_path.exists():
                with open(reject_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            rej_rows.append(json.loads(line))
                        except Exception:
                            continue
            if debug_path.exists():
                with open(debug_path, "r") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            row = json.loads(line)
                            row["source"] = "debug"
                            rej_rows.append(row)
                        except Exception:
                            continue
            rej_rows = _filter_rows_today(rej_rows)
            if rej_rows:
                rej_df = pd.DataFrame(rej_rows).tail(10)
                if "atr" in rej_df.columns:
                    rej_df["entry"] = rej_df.apply(lambda r: round((r.get("ask") or r.get("ltp") or 0), 2), axis=1)
                    def _opt_risk_row(r):
                        entry = r.get("entry") or 0
                        bid = r.get("bid") or 0
                        ask = r.get("ask") or 0
                        atr = r.get("atr") or 0
                        opt_atr = max(entry * 0.2, max(ask - bid, 0) * 3.0, 1.0)
                        stop = max(entry - opt_atr, entry * 0.2)
                        target = entry + opt_atr * 1.5
                        return round(stop, 2), round(target, 2)
                    st_vals = rej_df.apply(_opt_risk_row, axis=1, result_type="expand")
                    rej_df["stop_loss"] = st_vals[0]
                    rej_df["target"] = st_vals[1]
                cols = [c for c in ["timestamp", "symbol", "strike", "type", "reason", "ltp", "confidence", "min_proba", "source", "quote_ok"] if c in rej_df.columns]
                cols += [c for c in ["entry", "stop_loss", "target"] if c in rej_df.columns]
                ui.table(rej_df[cols], use_container_width=True)
                if "reason" in rej_df.columns and (rej_df["reason"] == "no_quote").any():
                    st.warning("Some candidates skipped due to missing quotes (no_quote).")
            else:
                empty_state("No rejected candidates logged yet for today.")
        else:
            empty_state("No rejected candidates logged yet.")
    except Exception as e:
        st.warning(f"Rejected candidates error: {e}")

    section_header("Signal Path (Latest)")
    try:
        sp_path = Path("logs/signal_path.jsonl")
        if sp_path.exists():
            rows = []
            with sp_path.open() as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
            if rows:
                df_sp = pd.DataFrame(rows).tail(100)
                sym_filter = st.selectbox("Signal Path Symbol", ["All"] + sorted(df_sp["symbol"].dropna().unique().tolist()), key="signal_path_symbol")
                if sym_filter != "All":
                    df_sp = df_sp[df_sp["symbol"] == sym_filter]
                show_cols = [c for c in ["timestamp", "symbol", "kind", "regime", "direction", "score", "reason", "ltp_change_window", "atr", "threshold"] if c in df_sp.columns]
                ui.table(df_sp.sort_values("timestamp", ascending=False)[show_cols].head(50), use_container_width=True)
            else:
                empty_state("No signal path entries yet.")
        else:
            empty_state("No signal path log yet.")
    except Exception as e:
        st.warning(f"Signal path error: {e}")

    section_header("Suggestion Quality (Hits / Time)")
    try:
        eval_path = Path("logs/suggestion_eval.jsonl")
        if eval_path.exists():
            rows = []
            with open(eval_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
            if rows:
                ev = pd.DataFrame(rows)
                ev["timestamp"] = pd.to_datetime(ev["timestamp"], errors="coerce")
                # Hit-rate by strategy
                hit = ev.groupby("strategy")["outcome"].apply(lambda x: (x == "target").mean()).reset_index()
                hit = hit.rename(columns={"outcome": "hit_rate"})
                st.subheader("Hit-Rate by Strategy")
                ui.table(hit.sort_values("hit_rate", ascending=False), use_container_width=True)
                # Avg time-to-target (if entry_time exists in suggestions)
                if "entry_time" in ev.columns:
                    ev["entry_time"] = pd.to_datetime(ev["entry_time"], errors="coerce")
                    ev["time_to_hit_min"] = (ev["timestamp"] - ev["entry_time"]).dt.total_seconds() / 60.0
                    avg_t = ev[ev["outcome"] == "target"].groupby("strategy")["time_to_hit_min"].mean().reset_index()
                    st.subheader("Average Time-to-Target (min)")
                    ui.table(avg_t.sort_values("time_to_hit_min"), use_container_width=True)
                # Best vs worst strategies
                if not hit.empty:
                    best = hit.iloc[0]
                    worst = hit.iloc[-1]
                    st.subheader("Best vs Worst")
                    st.write(f"Best: {best['strategy']} ({best['hit_rate']:.2%})")
                    st.write(f"Worst: {worst['strategy']} ({worst['hit_rate']:.2%})")
            else:
                empty_state("No suggestion evaluations yet.")
        else:
            empty_state("No suggestion evaluation log yet.")
    except Exception as e:
        st.warning(f"Suggestion quality error: {e}")

    section_header("Advanced Controls")
    try:
        # Force regime toggle (testing)
        try:
            from config import config as cfg
            options = ["AUTO", "TREND", "RANGE", "EVENT"]
            current = getattr(cfg, "FORCE_REGIME", "") or "AUTO"
            sel = st.selectbox("Force Regime (Testing)", options, index=options.index(current) if current in options else 0)
            try:
                from dotenv import set_key
                env_path = str(Path(".env").resolve())
                if sel == "AUTO":
                    os.environ["FORCE_REGIME"] = ""
                    set_key(env_path, "FORCE_REGIME", "")
                else:
                    os.environ["FORCE_REGIME"] = sel
                    set_key(env_path, "FORCE_REGIME", sel)
            except Exception:
                if sel == "AUTO":
                    os.environ["FORCE_REGIME"] = ""
                else:
                    os.environ["FORCE_REGIME"] = sel
            st.caption("Restart main.py to apply forced regime.")
        except Exception:
            pass
        # Day-type lock toggle (testing)
        try:
            from config import config as cfg
            lock_enabled = getattr(cfg, "DAYTYPE_LOCK_ENABLE", True)
            lock_choice = st.checkbox("Lock Day Type After 60 min", value=lock_enabled, key="daytype_lock_toggle")
            if st.button("Apply Day-Type Lock", key="apply_daytype_lock"):
                try:
                    from dotenv import set_key
                    env_path = str(Path(".env").resolve())
                    os.environ["DAYTYPE_LOCK_ENABLE"] = "true" if lock_choice else "false"
                    set_key(env_path, "DAYTYPE_LOCK_ENABLE", "true" if lock_choice else "false")
                    st.success("Day-type lock updated. Restart main.py to apply.")
                except Exception as e:
                    st.warning(f"Day-type lock update failed: {e}")
        except Exception:
            pass
        # Temporary unlock button
        if st.button("Temporary Unlock Day-Type (This Session)", key="unlock_daytype"):
            try:
                from core import market_data as md
                if hasattr(md, "_DAYTYPE_LOCK"):
                    md._DAYTYPE_LOCK.clear()
                st.success("Day-type lock cleared for this session.")
            except Exception as e:
                st.warning(f"Unlock failed: {e}")
        if st.button("Re-Apply Day-Type Lock (This Session)", key="relock_daytype"):
            try:
                from core import market_data as md
                # Lock current day-type snapshot
                for m in fetch_live_market_data():
                    sym = m.get("symbol")
                    if not sym:
                        continue
                    md._DAYTYPE_LOCK[sym] = {
                        "day_type": m.get("day_type"),
                        "day_conf": m.get("day_confidence"),
                        "locked_at": m.get("minutes_since_open", 0),
                    }
                st.success("Day-type lock re-applied for this session.")
            except Exception as e:
                st.warning(f"Re-lock failed: {e}")
        # Time bucket controls
        try:
            from config import config as cfg
            open_end = int(getattr(cfg, "DAYTYPE_BUCKET_OPEN_END", 11))
            mid_end = int(getattr(cfg, "DAYTYPE_BUCKET_MID_END", 14))
            st.markdown("**Time Bucket Schedule**")
            open_val = st.slider("Open bucket ends (hour)", 9, 12, open_end, 1, key="bucket_open_end")
            mid_val = st.slider("Mid bucket ends (hour)", 12, 15, max(mid_end, open_val + 1), 1, key="bucket_mid_end")
            if st.button("Apply Time Buckets", key="apply_time_buckets"):
                try:
                    from dotenv import set_key
                    env_path = str(Path(".env").resolve())
                    os.environ["DAYTYPE_BUCKET_OPEN_END"] = str(open_val)
                    os.environ["DAYTYPE_BUCKET_MID_END"] = str(mid_val)
                    set_key(env_path, "DAYTYPE_BUCKET_OPEN_END", str(open_val))
                    set_key(env_path, "DAYTYPE_BUCKET_MID_END", str(mid_val))
                    st.success("Time buckets updated. Restart main.py to apply.")
                except Exception as e:
                    st.warning(f"Time bucket update failed: {e}")
        except Exception:
            pass
        # Day-type confidence threshold
        try:
            from config import config as cfg
            conf_min = float(getattr(cfg, "DAYTYPE_CONF_SWITCH_MIN", 0.6))
            conf_val = st.slider("Day‑type confidence threshold", 0.3, 0.9, conf_min, 0.05, key="daytype_conf_min")
            if st.button("Apply Confidence Threshold", key="apply_conf_threshold"):
                try:
                    from dotenv import set_key
                    env_path = str(Path(".env").resolve())
                    os.environ["DAYTYPE_CONF_SWITCH_MIN"] = str(conf_val)
                    set_key(env_path, "DAYTYPE_CONF_SWITCH_MIN", str(conf_val))
                    st.success("Confidence threshold updated. Restart main.py to apply.")
                except Exception as e:
                    st.warning(f"Confidence threshold update failed: {e}")
        except Exception:
            pass
    except Exception:
        pass

    section_header("What Blocked Trades Today")
    try:
        rej_path = Path("logs/rejected_candidates.jsonl")
        if rej_path.exists():
            rows = []
            with rej_path.open() as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
            if rows:
                df_rej = pd.DataFrame(rows)
                if "timestamp" in df_rej.columns:
                    now = now_local()
                    df_rej["ts_local"] = df_rej["timestamp"].apply(lambda v: parse_ts_local(v))
                    df_rej = df_rej[df_rej["ts_local"].apply(lambda v: v is not None and v.date() == now.date())]
                if not df_rej.empty and "reason" in df_rej.columns:
                    summary = df_rej["reason"].value_counts().head(8).reset_index()
                    summary.columns = ["reason", "count"]
                    ui.table(summary, use_container_width=True)
                    # Per-strategy debug report
                    try:
                        if "strategy" in df_rej.columns:
                            st.markdown("**Blocked by Strategy (Today)**")
                            strat = (
                                df_rej.groupby(["strategy", "reason"])
                                .size()
                                .reset_index(name="count")
                                .sort_values(["strategy", "count"], ascending=[True, False])
                            )
                            ui.table(strat.head(20), use_container_width=True)
                            # Heatmap view (strategy x reason)
                            try:
                                import altair as alt
                                heat = (
                                    strat.pivot_table(index="strategy", columns="reason", values="count", aggfunc="sum", fill_value=0)
                                    .reset_index()
                                    .melt(id_vars="strategy", var_name="reason", value_name="count")
                                )
                                chart = alt.Chart(heat).mark_rect().encode(
                                    x=alt.X("reason:N", sort="-y", title="Reason"),
                                    y=alt.Y("strategy:N", sort="-x", title="Strategy"),
                                    color=alt.Color("count:Q", scale=alt.Scale(scheme="inferno")),
                                    tooltip=["strategy", "reason", "count"]
                                ).properties(height=220)
                                st.markdown("**Blocked Heatmap (Strategy × Reason)**")
                                st.altair_chart(chart, use_container_width=True)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # Separate panel for blocked stats (outside expander)
                    out_path = Path("logs/blocked_outcomes.jsonl")
                    if out_path.exists():
                        out_rows = []
                        with out_path.open() as f:
                            for line in f:
                                if not line.strip():
                                    continue
                                try:
                                    out_rows.append(json.loads(line))
                                except Exception:
                                    continue
                        if out_rows:
                            out_df = pd.DataFrame(out_rows)
                            section_header("Blocked Trade Stats (Paper)")
                            try:
                                    hits = (out_df["outcome"] == "TARGET_HIT").mean() if not out_df.empty else 0
                                    avg_pnl = out_df["pnl"].mean() if not out_df.empty else 0
                                    st.write(f"Hit-rate: {hits:.1%} | Avg PnL: {avg_pnl:.2f}")
                                    by_reason = out_df.groupby("reason").agg(
                                        hit_rate=("outcome", lambda x: (x == "TARGET_HIT").mean()),
                                        avg_pnl=("pnl", "mean"),
                                        count=("pnl", "count")
                                    ).reset_index()
                                    if not by_reason.empty:
                                        st.bar_chart(by_reason.set_index("reason")[["hit_rate", "avg_pnl"]])
                                    # Blocked vs Real comparison
                                    real = pd.DataFrame()
                                    try:
                                        if LOG_PATH.exists():
                                            rows_real = []
                                            with LOG_PATH.open() as f:
                                                for line in f:
                                                    if not line.strip():
                                                        continue
                                                    try:
                                                        rows_real.append(json.loads(line))
                                                    except Exception:
                                                        continue
                                            real = pd.DataFrame(rows_real)
                                    except Exception:
                                        real = pd.DataFrame()
                                    if not real.empty and "actual" in real.columns:
                                        real = real.dropna(subset=["actual"])
                                        if not real.empty:
                                            real["pnl"] = (real["exit_price"].fillna(real["entry"]) - real["entry"]) * real["qty"]
                                            real.loc[real["side"] == "SELL", "pnl"] *= -1
                                            real_hit = (real["actual"] == 1).mean()
                                            real_avg = real["pnl"].mean()
                                            comp = pd.DataFrame({
                                                "group": ["Blocked", "Real"],
                                                "hit_rate": [hits, real_hit],
                                                "avg_pnl": [avg_pnl, real_avg]
                                            })
                                            st.markdown("**Blocked vs Real Performance**")
                                            st.bar_chart(comp.set_index("group")[["hit_rate", "avg_pnl"]])
                            except Exception:
                                pass
                    with st.expander("Blocked trade details", expanded=False):
                        reasons = ["(None)"] + summary["reason"].tolist()
                        sel_reason = st.selectbox("Reason", reasons, index=0, key="blocked_reason")
                        if sel_reason != "(None)":
                            detail_cols = [c for c in ["timestamp", "symbol", "strike", "type", "reason", "ltp", "bid", "ask", "volume", "oi", "iv", "moneyness"] if c in df_rej.columns]
                            ui.table(df_rej[df_rej["reason"] == sel_reason][detail_cols].head(200), use_container_width=True)
                        # Blocked outcomes (paper results)
                        out_path = Path("logs/blocked_outcomes.jsonl")
                        if out_path.exists():
                            out_rows = []
                            with out_path.open() as f:
                                for line in f:
                                    if not line.strip():
                                        continue
                                    try:
                                        out_rows.append(json.loads(line))
                                    except Exception:
                                        continue
                            if out_rows:
                                out_df = pd.DataFrame(out_rows)
                                if sel_reason != "(None)":
                                    out_df = out_df[out_df["reason"] == sel_reason]
                                out_cols = [c for c in ["timestamp", "symbol", "strike", "type", "reason", "entry", "exit", "pnl", "outcome", "mfe", "mae"] if c in out_df.columns]
                                st.subheader("Blocked Trade Outcomes (Paper)")
                                ui.table(out_df.sort_values("timestamp", ascending=False)[out_cols].head(200), use_container_width=True)
                                # Stats chart
                                try:
                                    hits = (out_df["outcome"] == "TARGET_HIT").mean() if not out_df.empty else 0
                                    avg_pnl = out_df["pnl"].mean() if not out_df.empty else 0
                                    st.markdown("**Blocked Trade Stats**")
                                    st.write(f"Hit-rate: {hits:.1%} | Avg PnL: {avg_pnl:.2f}")
                                    by_reason = out_df.groupby("reason").agg(
                                        hit_rate=("outcome", lambda x: (x == "TARGET_HIT").mean()),
                                        avg_pnl=("pnl", "mean"),
                                        count=("pnl", "count")
                                    ).reset_index()
                                    if not by_reason.empty:
                                        st.bar_chart(by_reason.set_index("reason")[["hit_rate", "avg_pnl"]])
                                except Exception:
                                    pass
                        # Relax toggle for one filter at a time
                        try:
                            from config import config as cfg
                            current = getattr(cfg, "RELAX_BLOCK_REASON", "") or ""
                        except Exception:
                            current = ""
                        # Debug trade mode toggle
                        try:
                            dbg_mode = bool(getattr(cfg, "DEBUG_TRADE_MODE", False))
                        except Exception:
                            dbg_mode = False
                        dbg_choice = st.checkbox("Debug trade mode (log top rejected candidates)", value=dbg_mode, key="debug_trade_mode")
                        if st.button("Apply Debug Mode", key="apply_debug_mode"):
                            try:
                                from dotenv import set_key
                                env_path = str(Path(".env").resolve())
                                os.environ["DEBUG_TRADE_MODE"] = "true" if dbg_choice else "false"
                                set_key(env_path, "DEBUG_TRADE_MODE", "true" if dbg_choice else "false")
                                st.success("Debug trade mode updated. Restart main.py to apply.")
                            except Exception as e:
                                st.warning(f"Debug mode update failed: {e}")
                        options = ["(None)"] + summary["reason"].tolist()
                        choice = st.selectbox("Temporarily relax one filter", options, index=options.index(current) if current in options else 0, key="relax_reason")
                        if st.button("Apply Relaxation", key="apply_relax"):
                            try:
                                from dotenv import set_key
                                env_path = str(Path(".env").resolve())
                                if choice == "(None)":
                                    os.environ["RELAX_BLOCK_REASON"] = ""
                                    set_key(env_path, "RELAX_BLOCK_REASON", "")
                                else:
                                    os.environ["RELAX_BLOCK_REASON"] = choice
                                    set_key(env_path, "RELAX_BLOCK_REASON", choice)
                                st.success("Relaxation updated. Restart main.py to apply.")
                            except Exception as e:
                                st.warning(f"Relaxation update failed: {e}")
                        # Blocked outcomes training toggle
                        try:
                            from config import config as cfg
                            bt_enabled = getattr(cfg, "BLOCKED_TRAIN_ENABLE", True)
                        except Exception:
                            bt_enabled = True
                        train_choice = st.checkbox("Use blocked outcomes for ML", value=bt_enabled, key="blocked_train_toggle")
                        if st.button("Apply ML Toggle", key="apply_blocked_ml"):
                            try:
                                from dotenv import set_key
                                env_path = str(Path(".env").resolve())
                                os.environ["BLOCKED_TRAIN_ENABLE"] = "true" if train_choice else "false"
                                set_key(env_path, "BLOCKED_TRAIN_ENABLE", "true" if train_choice else "false")
                                st.success("Blocked ML toggle updated. Restart main.py to apply.")
                            except Exception as e:
                                st.warning(f"Blocked ML toggle update failed: {e}")
                        # Weight slider for blocked outcomes
                        try:
                            from config import config as cfg
                            w_cur = float(getattr(cfg, "BLOCKED_TRAIN_WEIGHT", 0.5))
                        except Exception:
                            w_cur = 0.5
                        w_val = st.slider("Blocked outcome weight", min_value=0.1, max_value=1.0, value=float(w_cur), step=0.05, key="blocked_weight_slider")
                        if st.button("Apply Weight", key="apply_blocked_weight"):
                            try:
                                from dotenv import set_key
                                env_path = str(Path(".env").resolve())
                                os.environ["BLOCKED_TRAIN_WEIGHT"] = str(w_val)
                                set_key(env_path, "BLOCKED_TRAIN_WEIGHT", str(w_val))
                                st.success("Blocked weight updated. Restart main.py to apply.")
                            except Exception as e:
                                st.warning(f"Blocked weight update failed: {e}")
                else:
                    empty_state("No blocked candidates recorded today.")
            else:
                empty_state("No blocked candidates recorded today.")
        else:
            empty_state("No blocked candidates recorded yet.")
    except Exception as e:
        st.warning(f"Blocked summary error: {e}")

    section_header("Day‑Type History")
    try:
        rows = load_day_type_events(backfill=True, max_rows=10000)
        if rows:
            df_dt = pd.DataFrame(rows)
            if "ts_epoch" in df_dt.columns:
                df_dt["ts_epoch"] = pd.to_numeric(df_dt["ts_epoch"], errors="coerce")
            if "ts_ist" in df_dt.columns:
                df_dt["ts_ist"] = pd.to_datetime(df_dt["ts_ist"], errors="coerce")
            if "ts" not in df_dt.columns:
                df_dt["ts"] = df_dt.get("ts_ist")
            else:
                df_dt["ts"] = pd.to_datetime(df_dt["ts"], errors="coerce")
            if "ts_ist" in df_dt.columns:
                df_dt["ts"] = df_dt["ts_ist"]
            # Export CSV
            try:
                csv_path = Path("logs/day_type_events.csv")
                df_dt.sort_values("ts_epoch", ascending=True).to_csv(csv_path, index=False)
            except Exception:
                pass
            if st.button("Export Day‑Type History CSV", key="export_daytype_csv"):
                try:
                    st.success("Exported to logs/day_type_events.csv")
                except Exception:
                    pass
            ui.table(df_dt.sort_values("ts_epoch", ascending=False).head(200), use_container_width=True)
            try:
                if "ts" in df_dt.columns and "confidence" in df_dt.columns:
                    df_plot = df_dt.dropna(subset=["ts", "confidence"])
                    df_plot = df_plot.sort_values("ts")
                    df_plot = df_plot.set_index("ts")
                    st.line_chart(df_plot[["confidence"]])
            except Exception:
                pass
            # Color-coded day-type timeline
            try:
                if "ts" in df_dt.columns and "day_type" in df_dt.columns:
                    timeline = df_dt.dropna(subset=["ts", "day_type"]).copy()
                    timeline = timeline.sort_values("ts")
                    chart = alt.Chart(timeline).mark_point(size=60).encode(
                        x="ts:T",
                        y=alt.Y("symbol:N", sort=None),
                        color=alt.Color("day_type:N"),
                        tooltip=["ts:T", "symbol:N", "day_type:N", "confidence:Q", "event:N"],
                    ).properties(height=200)
                    st.markdown("**Day‑Type Timeline (Color‑coded)**")
                    st.altair_chart(chart, use_container_width=True)
                    # Grouped per symbol (one row per symbol)
                    st.markdown("**Day‑Type Timeline by Symbol**")
                    chart2 = alt.Chart(timeline).mark_point(size=60).encode(
                        x="ts:T",
                        y=alt.Y("symbol:N", sort=None, title=None),
                        color=alt.Color("day_type:N"),
                        tooltip=["ts:T", "symbol:N", "day_type:N", "confidence:Q", "event:N"],
                    ).properties(height=200)
                    st.altair_chart(chart2, use_container_width=True)
            except Exception:
                pass
        else:
            empty_state("No day‑type history yet.")
    except Exception as e:
        st.warning(f"Day‑type history error: {e}")

if nav == "Gemini":
    section_header("Gemini Summary (Day Plan)")
    try:
        st.session_state.setdefault("gpt_cooldown_sec", 10)
        st.session_state["gpt_cooldown_sec"] = st.slider("Gemini Panel Cooldown (sec)", 5, 60, st.session_state["gpt_cooldown_sec"], 5, key="gpt_panel_cd")
        auto = st.checkbox("Auto‑refresh Gemini Summary", value=False, key="gpt_summary_auto")
        cooldown = st.slider("Summary cooldown (sec)", 60, 900, 300, 30, key="gpt_summary_cooldown")
        if hasattr(st, "fragment") and auto:
            @st.fragment(run_every=cooldown)
            def _gpt_summary_fragment():
                with st.spinner("Requesting Gemini summary..."):
                    md = fetch_live_market_data()
                    summary = get_day_summary({"market": md})
                    st.session_state["gpt_summary"] = summary
                    st.json(summary)
            _gpt_summary_fragment()
        else:
            if st.button("Generate Gemini Summary", key="gpt_summary_btn"):
                with st.spinner("Requesting Gemini summary..."):
                    md = fetch_live_market_data()
                    summary = get_day_summary({"market": md})
                    st.session_state["gpt_summary"] = summary
        col_t1, col_t2 = st.columns(2)
        if col_t1.button("Test Gemini Key", key="gemini_test_btn"):
            with st.spinner("Testing Gemini key..."):
                from core.gpt_advisor import test_connection
                st.session_state["gpt_test"] = test_connection()
        if col_t2.button("List Gemini Models", key="gemini_list_btn"):
            with st.spinner("Fetching Gemini models..."):
                try:
                    import importlib
                    import core.gpt_advisor as ga
                    importlib.reload(ga)
                    if hasattr(ga, "list_gemini_models"):
                        st.session_state["gemini_models"] = ga.list_gemini_models()
                    else:
                        st.session_state["gemini_models"] = {"error": "list_gemini_models not available. Restart Streamlit."}
                except Exception as e:
                    st.session_state["gemini_models"] = {"error": str(e)}
        if "gpt_summary" in st.session_state:
            st.json(st.session_state["gpt_summary"])
        if "gpt_test" in st.session_state:
            if isinstance(st.session_state["gpt_test"], dict) and st.session_state["gpt_test"].get("error"):
                st.error(f"Gemini test failed: {st.session_state['gpt_test']['error']}")
            else:
                st.success("Gemini test OK")
        if "gemini_models" in st.session_state:
            models = st.session_state["gemini_models"]
            if isinstance(models, dict) and models.get("error"):
                st.error(f"Gemini models error: {models['error']}")
            else:
                df_models = pd.DataFrame(models.get("models", []))
                ui.table(df_models, use_container_width=True)
                try:
                    names = [m.get("name") for m in models.get("models", []) if m.get("name")]
                    if names:
                        sel = st.selectbox("Select Gemini model", names, key="gemini_model_select")
                        if st.button("Apply Selected Model", key="gemini_apply_model"):
                            clean = sel.split("/", 1)[1] if sel.startswith("models/") else sel
                            _update_env_var("GEMINI_MODEL", clean)
                            os.environ["GEMINI_MODEL"] = clean
                            st.success(f"Applied GEMINI_MODEL={clean}")
                except Exception:
                    pass
    except Exception as e:
        st.warning(f"Gemini summary error: {e}")

    section_header("Gemini Advice History")
    try:
        hist_path = Path("logs/gpt_advice.jsonl")
        if hist_path.exists():
            rows = []
            with hist_path.open() as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
            if rows:
                df_hist = pd.DataFrame(rows)
                df_hist["action"] = df_hist["advice"].apply(lambda a: a.get("action") if isinstance(a, dict) else None)
                df_hist["confidence"] = df_hist["advice"].apply(lambda a: a.get("confidence") if isinstance(a, dict) else None)
                df_hist["symbol"] = df_hist["meta"].apply(lambda m: m.get("symbol") if isinstance(m, dict) else None)
                df_hist["strategy"] = df_hist["meta"].apply(lambda m: m.get("strategy") if isinstance(m, dict) else None)
                if st.button("Clear Gemini History", key="clear_gpt_history"):
                    try:
                        hist_path.write_text("")
                        st.success("Cleared Gemini advice history.")
                    except Exception as e:
                        st.warning(f"Clear failed: {e}")
                sym_filter = st.selectbox("Symbol", ["All"] + sorted([s for s in df_hist["symbol"].dropna().unique()]), key="gpt_hist_sym")
                action_filter = st.selectbox("Action", ["All", "buy_now", "wait", "no_trade"], key="gpt_hist_action")
                if sym_filter != "All":
                    df_hist = df_hist[df_hist["symbol"] == sym_filter]
                if action_filter != "All":
                    df_hist = df_hist[df_hist["action"] == action_filter]
                cols = ["timestamp", "trade_id", "symbol", "action", "confidence"]
                ui.table(df_hist[cols].sort_values("timestamp", ascending=False).head(200), use_container_width=True)
            else:
                empty_state("No GPT advice history yet.")
        else:
            empty_state("No GPT advice history yet.")
    except Exception as e:
        st.warning(f"Gemini advice history error: {e}")

    section_header("Pinned Gemini Advice")
    try:
        pins = _load_gpt_pins()
        if pins:
            hist_path = Path("logs/gpt_advice.jsonl")
            rows = []
            if hist_path.exists():
                with hist_path.open() as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            continue
            if rows:
                df = pd.DataFrame(rows)
                df = df[df["trade_id"].isin(pins)]
                if not df.empty:
                    df["action"] = df["advice"].apply(lambda a: a.get("action") if isinstance(a, dict) else None)
                    df["confidence"] = df["advice"].apply(lambda a: a.get("confidence") if isinstance(a, dict) else None)
                    cols = ["timestamp", "trade_id", "action", "confidence"]
                    ui.table(df[cols].sort_values("timestamp", ascending=False), use_container_width=True)
            if st.button("Clear Pins", key="clear_gpt_pins"):
                _save_gpt_pins(set())
                st.success("Cleared pinned Gemini advice.")
        else:
            empty_state("No pinned Gemini advice yet.")
    except Exception as e:
        st.warning(f"Pinned Gemini error: {e}")

    section_header("Analyze Trades (Gemini)")

    def _infer_type_from_row(row):
        t = row.get("type") or row.get("opt_type")
        if t in ("CE", "PE"):
            return t
        tid = str(row.get("trade_id", "")).upper()
        if "CE" in tid:
            return "CE"
        if "PE" in tid:
            return "PE"
        return None

    def _infer_strike_from_row(row, ltp_map=None):
        strike = row.get("strike")
        try:
            if isinstance(strike, str) and strike.upper() == "ATM":
                strike = None
        except Exception:
            pass
        if strike is None:
            sym = row.get("symbol")
            ltp = (ltp_map or {}).get(sym)
            step = 50
            try:
                from config import config as cfg
                step_map = getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {})
                step = step_map.get(sym, getattr(cfg, "STRIKE_STEP", 50))
            except Exception:
                step = 50
            if ltp:
                try:
                    return round(round(float(ltp) / step) * step, 2)
                except Exception:
                    return None
        return strike

    def _analyze_queue(path, title, key_prefix, ltp_map=None, chain_map=None):
        p = Path(path)
        if not p.exists():
            return
        data = json.loads(p.read_text())
        if not data:
            return
        df = pd.DataFrame(data)
        if "instrument" in df.columns:
            df = df[df["instrument"] == "OPT"]
        st.subheader(title)
        # Stale row handling + mismatch controls
        try:
            from config import config as cfg
            max_age_default = int(getattr(cfg, "QUEUE_ROW_MAX_AGE_MIN", 120))
            mismatch_default = float(getattr(cfg, "ENTRY_MISMATCH_PCT", 0.25))
        except Exception:
            max_age_default = 120
            mismatch_default = 0.25
        col_a, col_b, col_c = st.columns([1, 1, 1])
        with col_a:
            max_age_min = st.slider(
                "Max queue age (minutes)",
                5,
                720,
                max_age_default,
                5,
                key=f"{key_prefix}_max_age_min",
            )
        with col_b:
            mismatch_pct = st.slider(
                "Entry mismatch warn (%)",
                1,
                100,
                int(mismatch_default * 100),
                1,
                key=f"{key_prefix}_mismatch_pct",
            ) / 100.0
        with col_c:
            hide_stale = st.checkbox(
                "Hide stale rows",
                value=True,
                key=f"{key_prefix}_hide_stale",
            )
        # Compute row age + stale flag
        stale_count = 0
        if "timestamp" in df.columns:
            now = now_local()
            df["row_age_min"] = df["timestamp"].apply(lambda v: age_minutes_local(v, now=now))
            df["row_is_stale"] = df["row_age_min"].apply(lambda v: (v is None) or (v > max_age_min))
            stale_count = int(df["row_is_stale"].sum())
            if hide_stale:
                df = df[~df["row_is_stale"]]
        if stale_count > 0:
            st.caption(f"Stale rows auto‑disabled: {stale_count} (>{max_age_min} min)")
        actionable_only = st.checkbox("Only show actionable (non‑ATM)", value=False, key=f"{key_prefix}_nonatm")
        use_live_entry = st.checkbox("Use live entry for analysis", value=True, key=f"{key_prefix}_live_entry")
        # Ensure strike/type are visible
        if "type" not in df.columns or df["type"].isna().all():
            df["type"] = df.apply(lambda r: _infer_type_from_row(r), axis=1)
        df["strike"] = df.apply(lambda r: _infer_strike_from_row(r, ltp_map=ltp_map), axis=1)
        if actionable_only:
            df = df[~df["strike"].isin(["ATM", None])]
        # Live entry lookup from chain
        def _live_entry(r):
            try:
                sym = r.get("symbol")
                strike = r.get("strike")
                opt_type = r.get("type")
                if sym is None or strike is None or opt_type is None:
                    return None, None, None
                chain = (chain_map or {}).get(sym) or []
                for c in chain:
                    if c.get("strike") == strike and c.get("type") == opt_type:
                        ltp = c.get("ltp")
                        bid = c.get("bid")
                        ask = c.get("ask")
                        if ltp:
                            return ltp, bid, ask
                        if bid and ask:
                            return round((bid + ask) / 2, 2), bid, ask
                return None, None, None
            except Exception:
                return None, None, None
        df[["entry_live", "bid_live", "ask_live"]] = df.apply(lambda r: pd.Series(_live_entry(r)), axis=1)
        # Mismatch warning
        def _mismatch(r):
            try:
                e = r.get("entry")
                le = r.get("entry_live")
                if e is None or le is None:
                    return False
                e = float(e)
                le = float(le)
                if le <= 0:
                    return False
                return abs(le - e) / le >= mismatch_pct
            except Exception:
                return False
        def _mismatch_pct(r):
            try:
                e = r.get("entry")
                le = r.get("entry_live")
                if e is None or le is None:
                    return None
                e = float(e)
                le = float(le)
                if le <= 0:
                    return None
                return round(100.0 * abs(le - e) / le, 2)
            except Exception:
                return None
        df["entry_mismatch"] = df.apply(_mismatch, axis=1)
        df["entry_mismatch_pct"] = df.apply(_mismatch_pct, axis=1)
        df["entry_mismatch_note"] = df["entry_mismatch"].apply(lambda v: "⚠️ mismatch" if v else "")
        # Inline label with entry/stop/target
        def _label_row(r):
            sym = r.get("symbol")
            strike = r.get("strike")
            opt_type = r.get("type")
            entry = r.get("entry_live") if (use_live_entry and pd.notna(r.get("entry_live"))) else r.get("entry")
            stop = r.get("stop")
            target = r.get("target")
            return f"{sym} {strike} {opt_type} | E:{entry} SL:{stop} T:{target}"
        df["trade_label"] = df.apply(_label_row, axis=1)
        display_df = df.drop(columns=["trade_id"], errors="ignore")
        ui.table(display_df.head(20), use_container_width=True)
        if st.button(f"Analyze All {title}", key=f"gpt_all_{key_prefix}"):
            results = []
            for _, row in df.head(3).iterrows():
                row_dict = row.to_dict()
                if use_live_entry and row.get("entry_live"):
                    row_dict["entry"] = row.get("entry_live")
                    row_dict["opt_bid"] = row.get("bid_live")
                    row_dict["opt_ask"] = row.get("ask_live")
                advice = get_trade_advice(row_dict, {"market": "live"})
                results.append({
                    "symbol": row.get("symbol"),
                    "strike": row.get("strike"),
                    "type": row.get("type"),
                    "action": advice.get("action") if isinstance(advice, dict) else None,
                    "confidence": advice.get("confidence") if isinstance(advice, dict) else None,
                    "error": advice.get("error") if isinstance(advice, dict) else None,
                })
            ui.table(pd.DataFrame(results), use_container_width=True)
    try:
        # Build LTP map for strike inference
        ltp_map = {}
        chain_map = {}
        try:
            md_list = fetch_live_market_data()
            for m in md_list:
                sym = m.get("symbol")
                if sym and sym not in ltp_map:
                    ltp_map[sym] = m.get("ltp")
                if sym and sym not in chain_map:
                    chain_map[sym] = m.get("option_chain", [])
        except Exception:
            ltp_map = {}
            chain_map = {}
        _analyze_queue("logs/review_queue.json", "Manual Review Queue", "manual_tab", ltp_map=ltp_map, chain_map=chain_map)
        _analyze_queue("logs/quick_review_queue.json", "Quick Trades", "quick_tab", ltp_map=ltp_map, chain_map=chain_map)
        _analyze_queue("logs/zero_hero_queue.json", "Zero Hero", "zero_tab", ltp_map=ltp_map, chain_map=chain_map)
        _analyze_queue("logs/scalp_queue.json", "Scalp Trades", "scalp_tab", ltp_map=ltp_map, chain_map=chain_map)
        # Rejected candidates
        rej_path = Path("logs/rejected_candidates.jsonl")
        if rej_path.exists():
            rows = []
            with rej_path.open() as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
            if rows:
                rej_df = pd.DataFrame(rows)
                # Filter to current LTP window to avoid stale strikes
                try:
                    from config import config as cfg
                    default_win = getattr(cfg, "REJECTED_STRIKE_WINDOW", 2000)
                    win_map = getattr(cfg, "REJECTED_STRIKE_WINDOW_BY_SYMBOL", {})
                    def _in_window(r):
                        sym = r.get("symbol")
                        ltp = ltp_map.get(sym)
                        strike = r.get("strike")
                        try:
                            strike = float(strike)
                        except Exception:
                            return False
                        if not ltp:
                            return True
                        win = win_map.get(sym, default_win)
                        return abs(strike - float(ltp)) <= win
                    rej_df = rej_df[rej_df.apply(_in_window, axis=1)]
                except Exception:
                    pass
                rej_df = rej_df.tail(10)
                st.subheader("Rejected Candidates")
                ui.table(rej_df, use_container_width=True)
                if st.button("Analyze All Rejected", key="gpt_all_rej_tab"):
                    for _, row in rej_df.head(5).iterrows():
                        row_dict = row.to_dict()
                        row_dict["trade_id"] = f"REJ-{row_dict.get('symbol')}-{row_dict.get('strike')}-{row_dict.get('type')}-{int(datetime.now().timestamp())}"
                        _render_gpt_panel(row_dict, {"market": "live"}, "rej_tab")
    except Exception:
        pass

    section_header("Approved Trades")
    try:
        from core.review_queue import APPROVED_PATH
        a_path = APPROVED_PATH
        if a_path.exists():
            approved = json.loads(a_path.read_text())
            if approved:
                ui.table(pd.DataFrame(approved, columns=["trade_id"]), use_container_width=True)
            else:
                empty_state("No approved trades yet.")
        else:
            empty_state("No approved trades file yet.")
    except Exception as e:
        st.warning(f"Approved trades error: {e}")

    section_header("Re-queue Trades")
    try:
        if "q" in locals() and q:
            st.info("Use Reject to remove; approved trades can be re-queued by ID.")
        a_path = Path("logs/approved_trades.json")
        if a_path.exists():
            approved = json.loads(a_path.read_text())
            if approved:
                tid = st.text_input("Trade ID to re-queue")
                if st.button("Re-queue"):
                    data = []
                    if q_path.exists():
                        data = json.loads(q_path.read_text())
                    data.append({"trade_id": tid, "timestamp": str(pd.Timestamp.now())})
                    q_path.write_text(json.dumps(data, indent=2))
                    st.success(f"Re-queued {tid}")
    except Exception as e:
        st.warning(f"Re-queue error: {e}")

    section_header("Trade Scoring (Manual Entry)")
    try:
        from ml.trade_predictor import TradePredictor
        from core.feature_builder import build_trade_features
        from config import config as cfg
        from core.kite_client import kite_client
        from datetime import datetime

        col1, col2, col3, col4 = st.columns(4)
        sym = col1.selectbox("Symbol", ["NIFTY", "BANKNIFTY", "SENSEX"])
        opt_type = col1.radio("Option Type", ["CE", "PE"], horizontal=True, index=0)
        # Expiry selection: auto-updated to next weekly expiry by symbol
        def _next_expiry_for_symbol(symbol):
            from datetime import date, timedelta
            weekday = 1  # Tuesday for NIFTY/BANKNIFTY
            if symbol.upper() == "SENSEX":
                weekday = 3  # Thursday
            today = date.today()
            days_ahead = (weekday - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)
        expiry_default = _next_expiry_for_symbol(sym)
        expiry = col2.date_input("Expiry", value=expiry_default)
        # Auto-fill strikes from live chain
        strike_list = []
        option_chain = []
        md_live = None
        try:
            md_list = fetch_live_market_data()
            md_live = next((m for m in md_list if m.get("symbol") == sym and m.get("instrument") == "OPT"), None)
            if md_live:
                option_chain = md_live.get("option_chain", [])
                strike_list = sorted(list({o.get("strike") for o in option_chain if o.get("type") == opt_type and o.get("strike") is not None}))
        except Exception:
            strike_list = []
        if strike_list:
            strike = col2.selectbox("Strike", strike_list)
        else:
            strike = col2.number_input("Strike", min_value=0, value=0, step=50)
        entry = col3.number_input("Buy Price", min_value=0.0, value=0.0, step=0.5)
        stop = col3.number_input("Stop Loss", min_value=0.0, value=0.0, step=0.5)
        target = col3.number_input("Target", min_value=0.0, value=0.0, step=0.5)
        # Lots input (default 1 lot)
        lots = col4.number_input("Lots", min_value=1, value=1, step=1)
        score_btn = col4.button("Score Trade")

        if score_btn:
            # Try to fetch live option quote for context
            exchange = "BFO" if sym == "SENSEX" else "NFO"
            ltp = None
            bid = None
            ask = None

            opt = None
            if option_chain and strike:
                for o in option_chain:
                    if o.get("strike") == strike and o.get("type") == opt_type and str(o.get("expiry")) == str(expiry):
                        opt = o
                        break
            if opt:
                ltp = opt.get("ltp")
                bid = opt.get("bid")
                ask = opt.get("ask")
            else:
                # Fallback: direct quote by expiry
                try:
                    ts = kite_client.find_option_symbol_with_expiry(sym, strike, opt_type, expiry, exchange=exchange)
                    if ts:
                        q = kite_client.quote([ts]).get(ts, {})
                        ltp = q.get("last_price")
                        depth = q.get("depth") or {}
                        bid = depth.get("buy", [{}])[0].get("price")
                        ask = depth.get("sell", [{}])[0].get("price")
                        opt = {
                            "strike": strike,
                            "type": opt_type,
                            "ltp": ltp,
                            "bid": bid,
                            "ask": ask,
                            "volume": q.get("volume", 0),
                            "oi": q.get("oi", 0),
                        }
                except Exception:
                    opt = None

            if opt is None or not ltp or not bid or not ask:
                st.error("No live quote found for this strike/expiry. Please choose a strike with live quotes.")
                st.stop()
            # Build minimal market_data for features
            md = md_live or {}
            market_data = {
                "symbol": sym,
                "ltp": md.get("ltp", ltp),
                "vwap": md.get("vwap", ltp),
                "atr": md.get("atr", max(1.0, ltp * 0.002)),
                "bid": bid,
                "ask": ask,
                "volume": md.get("volume", 0),
                "vwap_slope": md.get("vwap_slope", 0),
                "rsi_mom": md.get("rsi_mom", 0),
                "vol_z": md.get("vol_z", 0),
                "moneyness": 0,
                "is_call": 1 if opt_type == "CE" else 0,
                "regime": md.get("regime"),
                "day_type": md.get("day_type"),
            }
            opt_row = opt
            feats = pd.DataFrame([build_trade_features(market_data, opt_row)])
            predictor = TradePredictor()
            conf = predictor.predict_confidence(feats)
            min_conf = getattr(cfg, "ML_MIN_PROBA", 0.6)

            # Risk/reward checks
            rr = None
            if entry and stop and target and entry != stop:
                rr = abs(target - entry) / max(abs(entry - stop), 1e-6)
            rr_ok = rr is not None and rr >= 1.2
            stop_ok = stop < entry if opt_type == "CE" else stop > entry if stop else True
            target_ok = target > entry if opt_type == "CE" else target < entry if target else True

            # Multi-factor scoring engine
            from core.trade_scoring import compute_trade_score
            direction = "BUY_CALL" if opt_type == "CE" else "BUY_PUT"
            score_pack = compute_trade_score(md, opt_row, direction=direction, rr=rr, strategy_name="MANUAL")
            score = score_pack.get("score", 0)
            alignment = score_pack.get("alignment", 0)
            issues = score_pack.get("issues", [])
            day_type = score_pack.get("day_type", "")
            regime = score_pack.get("regime", "")

            # Recommended strategy label (trend vs range)
            rec_strategy = "Trend‑Follow" if day_type in ("TREND_DAY", "RANGE_TREND_DAY", "TREND_RANGE_DAY") else "Mean‑Revert" if day_type in ("RANGE_DAY", "RANGE_VOLATILE") else "Cautious"

            opinion = "DON'T BUY"
            if score >= getattr(cfg, "TRADE_SCORE_MIN", 75) and conf >= min_conf and rr_ok and stop_ok and target_ok:
                if entry >= bid and entry <= ask * 1.01:
                    opinion = "BUY NOW"
                elif entry < bid:
                    opinion = "BUY AT THIS PRICE"
                else:
                    opinion = "BUY AT/NEAR ASK"
            elif score >= getattr(cfg, "QUICK_TRADE_SCORE_MIN", 60):
                opinion = "WAIT"

            st.metric("Confidence", f"{conf:.3f}")
            st.metric("Score", f"{score:.0f}/100")
            # Color-coded alignment badge
            align_color = "#22c55e" if alignment >= 75 else "#f59e0b" if alignment >= 60 else "#ef4444"
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:10px;'>"
                f"<div style='font-weight:600;'>Strategy Alignment</div>"
                f"<div style='background:{align_color};color:#0b0f14;padding:4px 10px;border-radius:999px;font-weight:700;'>"
                f"{alignment:.0f}/100</div></div>",
                unsafe_allow_html=True,
            )
            st.metric("Risk/Reward", f"{rr:.2f}" if rr is not None else "N/A")
            if not rr_ok:
                st.warning("Risk/Reward below 1.2")
            if not stop_ok:
                st.warning("Stop loss should be below entry for calls / above for puts.")
            if not target_ok:
                st.warning("Target should be above entry for calls / below for puts.")
            if issues:
                st.caption("Alignment Audit: " + ", ".join(issues))
            st.metric("Recommended Strategy", rec_strategy)
            st.metric("Opinion", opinion)

            # Per-factor breakdown panel
            try:
                comps = score_pack.get("components", {})
                if comps:
                    st.markdown("**Score Breakdown (Factors)**")
                    comp_df = pd.DataFrame([{"factor": k, "score": v} for k, v in comps.items()])
                    ui.table(comp_df.sort_values("score", ascending=False), use_container_width=True)
            except Exception:
                pass

            # Log scored trade
            try:
                log_path = Path("logs/scored_trades.jsonl")
                log_path.parent.mkdir(exist_ok=True)
                lot_size = 65 if sym == "NIFTY" else 20 if sym == "SENSEX" else 25
                qty = int(lots) * lot_size
                payload = {
                    "timestamp": datetime.now().isoformat(),
                    "symbol": sym,
                    "type": opt_type,
                    "strike": strike,
                    "expiry": str(expiry),
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "lots": int(lots),
                    "qty": qty,
                    "confidence": float(conf),
                    "score": float(score),
                    "strategy_alignment": float(alignment),
                    "day_type": day_type,
                    "regime": regime,
                    "risk_reward": float(rr) if rr is not None else None,
                    "opinion": opinion,
                    "recommended_strategy": rec_strategy,
                    "issues": issues,
                    "opt_ltp": ltp,
                    "opt_bid": bid,
                    "opt_ask": ask,
                }
                with open(log_path, "a") as f:
                    f.write(json.dumps(payload) + "\n")
            except Exception:
                pass
    except Exception as e:
        st.warning(f"Trade scoring error: {e}")

    section_header("Scored Trades")
    try:
        scored_path = Path("logs/scored_trades.jsonl")
        if scored_path.exists():
            rows = []
            with open(scored_path, "r") as f:
                for line in f:
                    if line.strip():
                        rows.append(json.loads(line))
            if rows:
                df_sc = pd.DataFrame(rows)
                if "timestamp" in df_sc.columns:
                    df_sc["timestamp"] = pd.to_datetime(df_sc["timestamp"], errors="coerce")
                try:
                    df_sc["date"] = df_sc["timestamp"].dt.date
                    agg = df_sc.groupby("date").agg(
                        avg_score=("score", "mean"),
                        avg_alignment=("strategy_alignment", "mean")
                    ).reset_index()
                    if not agg.empty:
                        st.markdown("**Score History (Daily)**")
                        st.line_chart(agg.set_index("date")[["avg_score", "avg_alignment"]])
                except Exception:
                    pass
                ui.table(df_sc.sort_values("timestamp", ascending=False).head(50), use_container_width=True)
            else:
                empty_state("No scored trades yet.")
        else:
            empty_state("No scored trades yet.")
    except Exception as e:
        st.warning(f"Scored trades error: {e}")

    section_header("Daily Summary")
    daily = df.groupby("date").agg(
        trades=("trade_id", "count"),
        pnl=("pnl", "sum"),
        win_rate=("pnl", lambda x: (x > 0).mean())
    ).reset_index()
    ui.table(daily, use_container_width=True)

    section_header("Equity Curve")
    df_sorted = df.sort_values("timestamp").copy()
    df_sorted["cum_pnl"] = df_sorted["pnl"].cumsum()
    st.line_chart(df_sorted.set_index("timestamp")["cum_pnl"])

    section_header("Strategy Performance")
    if STRAT_PATH.exists():
        with open(STRAT_PATH, "r") as f:
            strat = json.load(f)
        stats = strat.get("stats", {})
        if stats:
            stats_df = pd.DataFrame(stats).T.reset_index().rename(columns={"index": "strategy"})
            ui.table(stats_df, use_container_width=True)
            st.subheader("Strategy Weights (Sharpe/PF)")
            def weight_row(row):
                if pd.notna(row.get("sharpe")):
                    w = float(row["sharpe"]) + 1.0
                else:
                    pf = row.get("profit_factor", 1.0)
                    w = 2.0 if pf == "inf" else float(pf)
                return max(0.5, min(1.5, w))
            stats_df["weight"] = stats_df.apply(weight_row, axis=1)
            st.bar_chart(stats_df.set_index("strategy")["weight"])
    else:
        fallback = _compute_strategy_stats_from_log(df)
        if not fallback.empty:
            st.info("Using trade_log.json for strategy stats (no strategy_perf.json yet).")
            ui.table(fallback, use_container_width=True)
        else:
            empty_state("No strategy performance data yet.")

    section_header("Recent Trades")
    df_local = _localize_ts(df, "timestamp")
    view_today = st.toggle("Today only", value=True, key="recent_today_only")
    if "timestamp_local" in df_local.columns:
        today = datetime.now().astimezone().date()
        if view_today:
            df_view = df_local[df_local["timestamp_local"].dt.date == today]
        else:
            df_view = df_local
        if not df_view.empty:
            ui.table(df_view.tail(50), use_container_width=True)
        else:
            last_ts = df_local["timestamp_local"].dropna().max() if not df_local.empty else None
            if last_ts is not None:
                st.info(f"No trades logged today. Most recent trade: {last_ts}.")
            else:
                empty_state("No trades logged yet.")
            ui.table(df_local.tail(50), use_container_width=True)
    else:
        ui.table(df.tail(50), use_container_width=True)

    section_header("Recent Trades (SQLite)")
    try:
        cols, rows = fetch_recent_trades(100)
        if rows:
            db_df = pd.DataFrame(rows, columns=cols)
            db_df = _localize_ts(db_df, "timestamp")
            ui.table(db_df, use_container_width=True)
        else:
            empty_state("No trades in SQLite. Showing trade_log.json instead.")
            ui.table(df_local.tail(50) if "timestamp_local" in df_local.columns else df.tail(50), use_container_width=True)
    except Exception as e:
        st.warning(f"SQLite trades error: {e}")

    section_header("Recent Outcomes (SQLite)")
    try:
        cols, rows = fetch_recent_outcomes(100)
        if rows:
            ui.table(pd.DataFrame(rows, columns=cols), use_container_width=True)
        else:
            empty_state("No outcomes in SQLite yet.")
    except Exception as e:
        st.warning(f"SQLite outcomes error: {e}")

    section_header("PnL & Drawdown (SQLite)")
    try:
        cols, rows = fetch_pnl_series(500)
        if rows:
            pnl_df = pd.DataFrame(rows, columns=cols)
            pnl_df["exit_price"] = pnl_df["exit_price"].fillna(pnl_df["entry"])
            pnl_df["pnl"] = (pnl_df["exit_price"] - pnl_df["entry"]) * pnl_df["qty"]
            pnl_df.loc[pnl_df["side"] == "SELL", "pnl"] *= -1
            pnl_df["cum_pnl"] = pnl_df["pnl"].cumsum()
            pnl_df["drawdown"] = pnl_df["cum_pnl"] - pnl_df["cum_pnl"].cummax()
            st.line_chart(pnl_df.set_index("timestamp")[["cum_pnl", "drawdown"]])
        else:
            empty_state("No PnL data in SQLite. Showing from trade_log.json.")
            df_sorted = df.sort_values("timestamp").copy()
            df_sorted["cum_pnl"] = df_sorted["pnl"].cumsum()
            df_sorted["drawdown"] = df_sorted["cum_pnl"] - df_sorted["cum_pnl"].cummax()
            st.line_chart(df_sorted.set_index("timestamp")[["cum_pnl", "drawdown"]])
    except Exception as e:
        st.warning(f"SQLite PnL error: {e}")

if nav == "Execution":
    try:
        enabled, allowed, total = _wf_lock_status()
        if enabled:
            if allowed is not None and total is not None:
                st.success(f"WF Lock: ACTIVE — {allowed}/{total} strategies allowed")
                if allowed == 0:
                    st.warning("WF Lock is active but no strategies passed walk-forward.")
            else:
                st.success("WF Lock: ACTIVE")
        else:
            st.info("WF Lock: OFF")
    except Exception:
        pass
    # Auto-tune status badge
    try:
        tune = _load_auto_tune()
        if tune.get("enabled"):
            st.success(
                "Auto‑Tune: ACTIVE — "
                f"RR≥{tune.get('min_rr')} | "
                f"Proba≥{tune.get('min_proba')} | "
                f"Score≥{tune.get('trade_score_min')} "
                f"(win_rate={tune.get('win_rate')}, avg_pnl={tune.get('avg_pnl')})"
            )
        else:
            st.info("Auto‑Tune: OFF or insufficient trades")
    except Exception:
        pass
    st.subheader("Live Fills Status")
    try:
        status = "Disconnected"
        detail = "No recent fills"
        last_fill = None
        try:
            cols, rows = fetch_execution_stats(5)
            if rows:
                df_exec = pd.DataFrame(rows, columns=cols)
                if "timestamp" in df_exec.columns:
                    df_exec["timestamp"] = pd.to_datetime(df_exec["timestamp"], errors="coerce")
                    last_fill = df_exec["timestamp"].max()
            fills_db = Path("data/trades.db")
            if fills_db.exists() and last_fill is not None:
                age_sec = (datetime.now() - last_fill.to_pydatetime()).total_seconds()
                if age_sec < 300:
                    status = "Live"
                    detail = f"Last fill: {last_fill}"
                else:
                    status = "Stale"
                    detail = f"Last fill: {last_fill}"
        except Exception:
            pass
        col_a, col_b = st.columns([1, 3])
        col_a.metric("Status", status)
        col_b.write(detail)
    except Exception as e:
        st.warning(f"Live fills status error: {e}")

    st.subheader("Symbol Epsilon Stability")
    try:
        eps_path = Path("logs/symbol_eps_history.json")
        if eps_path.exists():
            eps_hist = json.loads(eps_path.read_text())
            eps_df = pd.DataFrame(eps_hist)
            eps_df["ts"] = pd.to_datetime(eps_df["ts"], unit="s")
            eps_expanded = eps_df["eps"].apply(pd.Series)
            eps_expanded["ts"] = eps_df["ts"]
            eps_expanded = eps_expanded.set_index("ts")
            st.line_chart(eps_expanded)
    except Exception as e:
        st.warning(f"Unable to load epsilon history: {e}")

    st.subheader("Execution Quality")
    try:
        from core.execution_engine import ExecutionEngine
        ee = ExecutionEngine()
        st.write("Per-instrument slippage bps (approx):", ee.instrument_slippage)
        cols, rows = fetch_recent_trades(200)
        dfq = pd.DataFrame(rows, columns=cols)
        if "fill_price" in dfq.columns:
            fill_ratio = dfq["fill_price"].notna().mean()
            st.metric("Fill Ratio", _safe_metric(fill_ratio))
        if "latency_ms" in dfq.columns and dfq["latency_ms"].notna().any():
            st.metric("Avg Latency (ms)", _safe_metric(dfq["latency_ms"].dropna().mean(), "{:.1f}"))
        if "fill_price" in dfq.columns:
            fill_ratio = dfq["fill_price"].notna().mean()
            lat = dfq["latency_ms"].dropna().mean() if "latency_ms" in dfq.columns else 0
            score = (fill_ratio * 100) - (lat * 0.01)
            st.metric("Execution Quality Score", _safe_metric(score, "{:.1f}"))
        cols2, rows2 = fetch_execution_stats(200)
        if rows2:
            ui.table(pd.DataFrame(rows2, columns=cols2), use_container_width=True)
    except Exception as e:
        st.warning(f"Execution quality error: {e}")

    st.subheader("Execution Analytics Summary")
    try:
        ea_path = Path("logs/execution_analytics.json")
        if ea_path.exists():
            ea = json.loads(ea_path.read_text())
            ui.table(pd.DataFrame([ea]), use_container_width=True)
        else:
            st.info("Run scripts/run_execution_analytics.py to generate analytics.")
    except Exception as e:
        st.warning(f"Execution analytics error: {e}")

    st.subheader("Execution Intent vs Fill Accuracy")
    try:
        intents_path = Path("logs/execution_intents.jsonl")
        fills_path = Path("logs/reconciliation_summary.json")
        if intents_path.exists() and fills_path.exists():
            intents = []
            with open(intents_path, "r") as f:
                for line in f:
                    if line.strip():
                        intents.append(json.loads(line))
            intents_df = pd.DataFrame(intents)
            rec = json.loads(fills_path.read_text())
            if not intents_df.empty:
                intents_df["ts"] = pd.to_datetime(intents_df["ts"], unit="s")
                intents_count = len(intents_df)
                match_rate = rec.get("match_rate", 0)
                confidence = rec.get("avg_confidence", 0)
                intent_accuracy = match_rate * confidence
                st.metric("Intent Count", intents_count)
                st.metric("Intent → Fill Accuracy (proxy)", f"{intent_accuracy:.2f}")
        else:
            st.info("Run live mode to collect intents + reconciliation summary.")
    except Exception as e:
        st.warning(f"Execution intent accuracy error: {e}")

if nav == "Reconciliation":
    st.subheader("Reconciliation Summary")
    try:
        rec_path = Path("logs/reconciliation_summary.json")
        if rec_path.exists():
            rec = json.loads(rec_path.read_text())
            ui.table(pd.DataFrame([rec]), use_container_width=True)
            if "avg_confidence" in rec:
                st.metric("Reconciliation Confidence", f"{rec['avg_confidence']:.2f}")
        else:
            st.info("Run scripts/reconcile_fills.py to generate reconciliation summary.")
    except Exception as e:
        st.warning(f"Reconciliation summary error: {e}")

    st.subheader("Reconciliation Match-Rate Trend")
    try:
        rec_hist = Path("logs/reconciliation_history.json")
        if rec_hist.exists():
            hist = pd.read_json(rec_hist)
            if not hist.empty:
                hist["ts"] = pd.to_datetime(hist["ts"])
                min_d = hist["ts"].min().date()
                max_d = hist["ts"].max().date()
                default_start = prefs.get("recon_start")
                default_end = prefs.get("recon_end")
                if default_start:
                    try:
                        default_start = pd.to_datetime(default_start).date()
                    except Exception:
                        default_start = min_d
                if default_end:
                    try:
                        default_end = pd.to_datetime(default_end).date()
                    except Exception:
                        default_end = max_d
                start_date, end_date = st.date_input(
                    "Filter range",
                    value=(default_start or min_d, default_end or max_d),
                    min_value=min_d,
                    max_value=max_d
                )
                try:
                    prefs["recon_start"] = str(start_date)
                    prefs["recon_end"] = str(end_date)
                    _save_prefs(prefs)
                except Exception:
                    pass
                if start_date and end_date:
                    hist = hist[(hist["ts"].dt.date >= start_date) & (hist["ts"].dt.date <= end_date)]
                hist = hist.sort_values("ts")
                default_window = int(prefs.get("recon_window", 14))
                window = st.slider("Rolling window (days)", min_value=3, max_value=60, value=default_window, step=1)
                prefs["recon_window"] = window
                _save_prefs(prefs)
                hist["match_rate_roll"] = hist["match_rate"].rolling(window, min_periods=1).mean()
                st.line_chart(hist.set_index("ts")["match_rate"])
                st.line_chart(hist.set_index("ts")["match_rate_roll"])
            else:
                empty_state("No reconciliation history yet.")
        else:
            empty_state("No reconciliation history yet.")
    except Exception as e:
        st.warning(f"Reconciliation history error: {e}")

if nav == "Risk & Governance":
    advanced = st.toggle("Advanced", value=False, key="adv_scorecard")
    if advanced:
        section_header("Top‑1% Readiness Scorecard")
        try:
            scorecard = compute_scorecard()
            sc_df = pd.DataFrame(scorecard)
            ui.table(sc_df, use_container_width=True)
            total_items = len(scorecard)
            passed = sum(1 for r in scorecard if r.get("status") == "PASS")
            readiness = passed / total_items if total_items else 0.0
            section_header("Governance Checklist (Quick Readiness)")
            cols = st.columns([1, 2, 2])
            cols[0].metric("Readiness", f"{readiness:.0%}")
            cols[1].progress(readiness)
            cols[2].write("Status: " + ("Ready to scale" if readiness >= 0.8 else "Needs work"))
            for row in scorecard:
                status = row.get("status")
                prefix = "✅" if status == "PASS" else "⬜"
                prog = row.get("progress")
                st.write(f"{prefix} {row['item']} — {prog}" if prog else f"{prefix} {row['item']}")
                if status != "PASS":
                    for rem in row.get("remaining", []):
                        st.write(f"  - {rem}")
        except Exception as e:
            st.error(f"Scorecard error: {e}")

    section_header("Arm Live Trades")
    try:
        arm_path = Path("logs/arm_live.json")
        arm_state = {"armed": False}
        if arm_path.exists():
            arm_state = json.loads(arm_path.read_text())
        confirm = st.checkbox("I understand this enables live order placement", value=False)
        if st.button("Arm Live Trades", disabled=not confirm):
            arm_state = {"armed": True, "timestamp": pd.Timestamp.now().isoformat()}
            arm_path.parent.mkdir(exist_ok=True)
            arm_path.write_text(json.dumps(arm_state, indent=2))
            st.success("Live trading is armed (placement still guarded by config).")
        st.write(f"Current state: {'ARMED' if arm_state.get('armed') else 'NOT ARMED'}")
    except Exception as e:
        st.warning(f"Arm live trades error: {e}")

if nav == "Data & SLA":
    st.subheader("Daily PF / Sharpe")
    try:
        import sqlite3
        from config import config as cfg
        db = Path(cfg.TRADE_DB_PATH)
        if db.exists():
            conn = sqlite3.connect(db)
            daily = pd.read_sql_query("SELECT * FROM daily_stats ORDER BY date ASC", conn)
            conn.close()
            if not daily.empty:
                daily["date"] = pd.to_datetime(daily["date"])
                st.line_chart(daily.set_index("date")[["profit_factor", "sharpe"]])
            else:
                empty_state("No daily stats yet. Showing from trade_log.json.")
                daily = df.groupby("date").agg(
                    pnl=("pnl", "sum"),
                    win_rate=("pnl", lambda x: (x > 0).mean())
                ).reset_index()
                ui.table(daily, use_container_width=True)
        else:
            empty_state("No trades.db yet.")
    except Exception as e:
        st.warning(f"Daily PF/Sharpe error: {e}")

    st.subheader("Daily Rollup Utility")
    try:
        import subprocess
        if st.button("Run Daily Rollup Now"):
            with st.spinner("Running daily rollup..."):
                result = subprocess.run([sys.executable, "scripts/daily_rollup.py"], check=False, capture_output=True, text=True)
                Path("logs/daily_rollup.log").write_text((result.stdout or "") + "\n" + (result.stderr or ""))
            if result.returncode == 0:
                st.success("Daily rollup completed.")
            else:
                st.error("Daily rollup failed. Check logs/daily_rollup.log.")
    except Exception as e:
        st.warning(f"Daily rollup error: {e}")

    st.subheader("Data SLA Status")
    try:
        from core.freshness_sla import get_freshness_status
        sla = get_freshness_status(force=False)
        ui.table(pd.DataFrame([sla]), use_container_width=True)
    except Exception as e:
        st.warning(f"SLA status error: {e}")

    st.subheader("Option Chain Health")
    try:
        health_path = Path("logs/option_chain_health.json")
        if health_path.exists():
            health = json.loads(health_path.read_text())
            if isinstance(health, dict) and health:
                df_h = pd.DataFrame(health.values())
                ui.table(df_h, use_container_width=True)
                warn = df_h[df_h["status"] == "WARN"] if "status" in df_h.columns else pd.DataFrame()
                if not warn.empty:
                    st.warning("Option chain health warnings detected.")
            else:
                empty_state("No option chain health data yet.")
        else:
            st.info("Run live market fetch to generate option chain health.")
    except Exception as e:
        st.warning(f"Option chain health error: {e}")

    st.subheader("Walk-Forward Risk Summary")
    try:
        summary_path = Path("logs/walk_forward_risk_summary.json")
        strat_path = Path("logs/walk_forward_strategy_summary.csv")
        if summary_path.exists():
            summary = json.loads(summary_path.read_text())
            if isinstance(summary, list) and summary:
                ui.table(pd.DataFrame(summary), use_container_width=True)
            else:
                ui.table(pd.DataFrame([summary]), use_container_width=True)
        else:
            st.info("Run walk-forward backtest to generate risk summary.")
        if strat_path.exists():
            if strat_path.stat().st_size == 0:
                df_s = pd.DataFrame()
            else:
                df_s = pd.read_csv(strat_path)
            if not df_s.empty:
                ui.table(df_s, use_container_width=True)
    except Exception as e:
        st.warning(f"Walk-forward summary error: {e}")

    st.subheader("Walk-Forward Strategy Lock")
    try:
        from config import config as cfg
        lock_default = prefs.get("wf_lock", getattr(cfg, "STRATEGY_WF_LOCK_ENABLE", False))
        wf_lock = st.checkbox("Lock strategy switching to WF-pass only", value=lock_default)
        if wf_lock != lock_default:
            prefs["wf_lock"] = wf_lock
            _save_prefs(prefs)
            _update_env_var("STRATEGY_WF_LOCK_ENABLE", str(wf_lock).lower())
        cfg.STRATEGY_WF_LOCK_ENABLE = wf_lock
        drift_default = prefs.get("wf_live_drift", getattr(cfg, "LIVE_WF_DRIFT_DISABLE", True))
        drift = st.checkbox("Auto-disable strategies on live drift (WF thresholds)", value=drift_default)
        if drift != drift_default:
            prefs["wf_live_drift"] = drift
            _save_prefs(prefs)
            _update_env_var("LIVE_WF_DRIFT_DISABLE", str(drift).lower())
        cfg.LIVE_WF_DRIFT_DISABLE = drift
        st.caption("WF lock gates strategy selection; live drift auto-disables strategies that fall below WF thresholds. If no WF summary exists, all strategies remain eligible.")
        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        col_t1.metric("Min trades", getattr(cfg, "WF_MIN_TRADES", 20))
        col_t2.metric("Min PF", getattr(cfg, "WF_MIN_PF", 1.2))
        col_t3.metric("Min win rate", getattr(cfg, "WF_MIN_WIN_RATE", 0.45))
        col_t4.metric("Max drawdown", getattr(cfg, "WF_MAX_DD", -5000.0))
        strat_path = Path("logs/walk_forward_strategy_summary.csv")
        if strat_path.exists():
            if strat_path.stat().st_size == 0:
                df_s = pd.DataFrame()
            else:
                df_s = pd.read_csv(strat_path)
            if not df_s.empty and "strategy" in df_s.columns:
                if "passed" in df_s.columns:
                    allowed = df_s[df_s["passed"] == True]["strategy"].astype(str).tolist()
                    blocked = df_s[df_s["passed"] == False]["strategy"].astype(str).tolist()
                    col_a, col_b = st.columns(2)
                    col_a.write("Allowed strategies")
                    col_a.write(", ".join(allowed) if allowed else "None")
                    col_b.write("Blocked strategies")
                    col_b.write(", ".join(blocked) if blocked else "None")
                    if wf_lock and not allowed:
                        st.warning("WF lock is enabled but no strategies passed. Trades may be fully blocked.")
    except Exception as e:
        st.warning(f"WF lock error: {e}")

    st.subheader("Walk-Forward Backtest Settings")
    try:
        from config import config as cfg
        data_files = sorted([p for p in Path("data").glob("*.csv")])
        file_opts = [str(p) for p in data_files] if data_files else []
        file_path = st.selectbox("Data file", file_opts) if file_opts else None
        train_size = st.slider("Train size", min_value=0.5, max_value=0.9, value=0.6, step=0.05)
        step = st.number_input("Step size", min_value=50, max_value=2000, value=200, step=50)
        min_trades = st.number_input("WF min trades", min_value=5, max_value=500, value=getattr(cfg, "WF_MIN_TRADES", 20), step=5)
        min_pf = st.number_input("WF min PF", min_value=0.5, max_value=10.0, value=float(getattr(cfg, "WF_MIN_PF", 1.2)), step=0.1)
        min_wr = st.slider("WF min win rate", min_value=0.1, max_value=0.9, value=float(getattr(cfg, "WF_MIN_WIN_RATE", 0.45)), step=0.05)
        max_dd = st.number_input("WF max drawdown", min_value=-100000.0, max_value=0.0, value=float(getattr(cfg, "WF_MAX_DD", -5000.0)), step=500.0)
        entry_window = st.number_input("Entry window (bars)", min_value=1, max_value=20, value=getattr(cfg, "BACKTEST_ENTRY_WINDOW", 3))
        horizon = st.number_input("Horizon (bars)", min_value=1, max_value=50, value=getattr(cfg, "BACKTEST_HORIZON", 5))
        slippage_bps = st.number_input("Slippage (bps)", min_value=0.0, max_value=50.0, value=getattr(cfg, "BACKTEST_SLIPPAGE_BPS", 5.0))
        spread_bps = st.number_input("Spread (bps)", min_value=0.0, max_value=50.0, value=getattr(cfg, "BACKTEST_SPREAD_BPS", 5.0))
        fee = st.number_input("Fee per trade", min_value=0.0, max_value=100.0, value=getattr(cfg, "BACKTEST_FEE_PER_TRADE", 0.0))
        synth_chain = st.checkbox("Use synthetic option chain", value=getattr(cfg, "BACKTEST_USE_SYNTH_CHAIN", True))
        if st.button("Run Walk-Forward Backtest"):
            if not file_path:
                st.error("No data file selected.")
            else:
                # Apply overrides for this run
                cfg.WF_MIN_TRADES = int(min_trades)
                cfg.WF_MIN_PF = float(min_pf)
                cfg.WF_MIN_WIN_RATE = float(min_wr)
                cfg.WF_MAX_DD = float(max_dd)
                cfg.BACKTEST_ENTRY_WINDOW = int(entry_window)
                cfg.BACKTEST_HORIZON = int(horizon)
                cfg.BACKTEST_SLIPPAGE_BPS = float(slippage_bps)
                cfg.BACKTEST_SPREAD_BPS = float(spread_bps)
                cfg.BACKTEST_FEE_PER_TRADE = float(fee)
                cfg.BACKTEST_USE_SYNTH_CHAIN = bool(synth_chain)
                from core.run_backtest import run_backtest
                with st.spinner("Running walk-forward backtest..."):
                    run_backtest(file_path, train_size=float(train_size), step=int(step))
                st.success("Backtest complete. Risk summary updated.")
    except Exception as e:
        st.warning(f"Backtest settings error: {e}")

if nav == "ML/RL":
    st.subheader("Model Training Utilities")
    try:
        import subprocess
        import os
        # Status badges
        micro_trained = Path("models/microstructure_model.h5").exists() or Path("logs/micro_feature_importance.csv").exists()
        rl_trained = Path("logs/rl_metrics.json").exists()
        col_s1, col_s2 = st.columns(2)
        col_s1.metric("Micro Model", "Trained" if micro_trained else "Not trained")
        col_s2.metric("RL Model", "Trained" if rl_trained else "Not trained")

        col_a, col_b, col_c = st.columns(3)
        if col_a.button("Train Micro Model"):
            with st.spinner("Training microstructure model..."):
                env = os.environ.copy()
                env["MPLCONFIGDIR"] = "/tmp/mpl"
                result = subprocess.run([sys.executable, "models/train_micro_model.py"], check=False, env=env, capture_output=True, text=True)
                Path("logs/train_micro.log").write_text((result.stdout or "") + "\n" + (result.stderr or ""))
            st.success("Micro model training completed.")
        if "rl_training" not in st.session_state:
            st.session_state["rl_training"] = False
        if col_b.button("Train RL (Validate)", disabled=st.session_state["rl_training"]):
            st.session_state["rl_training"] = True
            result = None
            try:
                with st.spinner("Training RL model..."):
                    result = subprocess.run([sys.executable, "rl/train_validate_rl.py"], check=False, capture_output=True, text=True)
                    Path("logs/train_rl.log").write_text((result.stdout or "") + "\n" + (result.stderr or ""))
            finally:
                st.session_state["rl_training"] = False
            if result and result.returncode == 0:
                st.success("RL training completed.")
            else:
                st.error("RL training failed or did not finish. Check the Training Console for details.")
        if col_c.button("Refresh IV Skew Data"):
            with st.spinner("Refreshing option chain..."):
                result = subprocess.run([sys.executable, "scripts/refresh_option_chain.py"], check=False, capture_output=True, text=True)
                Path("logs/refresh_iv.log").write_text((result.stdout or "") + "\n" + (result.stderr or ""))
            st.success("IV skew refresh completed.")
    except Exception as e:
        st.warning(f"Training utilities error: {e}")

    st.subheader("Training Console")
    try:
        # persist refresh interval
        default_refresh = int(prefs.get("refresh_sec", 3))
        refresh_sec = st.slider("Console refresh (seconds)", min_value=2, max_value=15, value=default_refresh, step=1)
        try:
            prefs["refresh_sec"] = refresh_sec
            _save_prefs(prefs)
        except Exception:
            pass
        interval_ms = refresh_sec * 1000
        if hasattr(st, "autorefresh"):
            st.autorefresh(interval=interval_ms, key="train_log_refresh")
        else:
            try:
                from streamlit_autorefresh import st_autorefresh  # type: ignore
                st_autorefresh(interval=interval_ms, key="train_log_refresh")
            except Exception:
                pass
        log_files = {
            "Micro Train": Path("logs/train_micro.log"),
            "RL Train": Path("logs/train_rl.log"),
            "IV Refresh": Path("logs/refresh_iv.log"),
        }
        choice = st.selectbox("Select log", list(log_files.keys()))
        log_path = log_files[choice]
        if log_path.exists():
            text = log_path.read_text()[-8000:]
            # simple color-coding for errors
            lines = text.splitlines()
            err_lines = [ln for ln in lines if "error" in ln.lower() or "traceback" in ln.lower()]
            if err_lines:
                st.error("Errors found in log (showing last 5):")
                st.code("\n".join(err_lines[-5:]), language="text")
            st.code(text, language="text")
            # auto-scroll hint
            st.caption("Log view shows the latest lines (auto-scroll).")
        else:
            empty_state("No logs yet. Run a training job above.")
    except Exception as e:
        st.warning(f"Training console error: {e}")

    st.subheader("RL Metrics")
    try:
        rl_path = Path("logs/rl_metrics.json")
        if rl_path.exists():
            rld = pd.read_json(rl_path)
            rld["timestamp"] = pd.to_datetime(rld["timestamp"])
            rld = rld.sort_values("timestamp")
            st.line_chart(rld.set_index("timestamp")[["total_reward", "sharpe", "max_drawdown"]])
        else:
            empty_state("No RL metrics yet. Run rl/train_validate_rl.py if RL is enabled.")
    except Exception as e:
        st.warning(f"RL metrics error: {e}")

if nav == "Market Depth":
    st.subheader("Depth Snapshots (SQLite)")
    try:
        cols, rows = fetch_depth_snapshots(100)
        if rows:
            ds = pd.DataFrame(rows, columns=cols)
            meta_map = _get_instrument_meta_map()
            # Parse depth_json for clean summary columns
            try:
                import json as _json
                parsed = []
                for _, r in ds.iterrows():
                    try:
                        payload = _json.loads(r["depth_json"])
                        depth = payload.get("depth", {})
                        imb = payload.get("imbalance")
                        buy = depth.get("buy", [])
                        sell = depth.get("sell", [])
                        best_bid = buy[0].get("price") if buy else None
                        best_ask = sell[0].get("price") if sell else None
                        spread = None
                        if best_bid and best_ask:
                            spread = best_ask - best_bid
                        meta = meta_map.get(r["instrument_token"], {})
                        parsed.append({
                            "timestamp": r["timestamp"],
                            "symbol": meta.get("symbol"),
                            "strike": meta.get("strike"),
                            "type": meta.get("type"),
                            "expiry": meta.get("expiry"),
                            "best_bid": best_bid,
                            "best_ask": best_ask,
                            "spread": spread,
                            "imbalance": imb,
                        })
                    except Exception:
                        continue
                if parsed:
                    clean = pd.DataFrame(parsed)
                    ui.table(clean, use_container_width=True)
                else:
                    ui.table(ds[["timestamp", "instrument_token"]], use_container_width=True)
            except Exception:
                ui.table(ds[["timestamp", "instrument_token"]], use_container_width=True)
        else:
            empty_state("No depth snapshots yet.")
    except Exception as e:
        st.warning(f"Depth snapshot error: {e}")

    st.subheader("Depth Imbalance (by Instrument)")
    try:
        cols, rows = fetch_depth_imbalance(500)
        if rows:
            import json as _json
            from core.kite_client import kite_client
            meta_map = _get_instrument_meta_map()
            imb_rows = []
            for row in rows:
                # depth_snapshots query can return (timestamp, instrument_token, depth_json, timestamp_epoch)
                ts, token, dj = row[0], row[1], row[2]
                try:
                    obj = _json.loads(dj)
                    imb = obj.get("imbalance")
                except Exception:
                    imb = None
                meta = meta_map.get(token, {})
                imb_rows.append({
                    "timestamp": ts,
                    "instrument_token": token,
                    "symbol": meta.get("symbol"),
                    "strike": meta.get("strike"),
                    "type": meta.get("type"),
                    "expiry": meta.get("expiry"),
                    "imbalance": imb
                })
            imb_df = pd.DataFrame(imb_rows).dropna()
            if not imb_df.empty:
                imb_df["timestamp"] = pd.to_datetime(imb_df["timestamp"])
                imb_df["symbol"] = imb_df["symbol"].fillna(imb_df["instrument_token"].astype(str))
                pivot = imb_df.pivot_table(index="timestamp", columns="instrument_token", values="imbalance", aggfunc="mean")
                st.line_chart(pivot)
                imb_df["hour"] = imb_df["timestamp"].dt.hour
                heat = imb_df.pivot_table(index="symbol", columns="hour", values="imbalance", aggfunc="mean")
                ui.table(heat, use_container_width=True)
            else:
                empty_state("No imbalance data yet.")
        else:
            empty_state("No imbalance data yet.")
    except Exception as e:
        st.warning(f"Depth imbalance error: {e}")

# End app shell container
end_shell()
