import json
import os
import logging
import signal
import subprocess
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import altair as alt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import math

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)

import dashboard.ui as ui
from dashboard.components import (
    render_allocation_summary,
    render_candidate_pool_summary,
    render_rejection_reason_breakdown,
    render_score_distribution,
)
from dashboard.loaders import load_depth_vm, load_execution_vm, load_recon_vm
from dashboard.metrics_runtime import load_runtime_metrics
from dashboard.renderers import render_depth_panel, render_execution_panel, render_recon_panel
from dashboard.runtime import run_state_engine_if_due
from dashboard.utils import normalize_trade_df, filter_by_permission, dedupe_by_trade_key
from dashboard.ui.utils.derive_fields import (
    parse_option_side,
    parse_underlying,
    map_strategy_category,
)
from dashboard.ui.utils.cache_utils import (
    REFRESH_MODE_ALWAYS_UI,
    REFRESH_MODE_FEED_ACTIVE,
    REFRESH_MODE_MARKET_OPEN_ONLY,
    file_sig,
    should_trade_autorefresh,
)
from dashboard.ui.utils.strategy_timeline import (
    floor_timestamp_to_bucket,
    compute_strategy_timeline_metrics,
    build_blocker_distribution,
)
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
from core.market_data import (
    fetch_live_market_data,
    get_underlying_candles as market_data_get_underlying_candles,
    get_option_candles_or_snapshots as market_data_get_option_candles_or_snapshots,
)
from core.auth_health import load_auth_runtime_guard
from core.day_type_history import load_day_type_events, day_type_events_dataframe
from core.market_calendar import market_open as canonical_market_open
from core.offhours import is_offhours
from core.time_utils import (
    is_today_local,
    age_minutes_local,
    now_local,
    parse_ts_local,
    get_market_phase_ist,
    parse_hhmm_time,
)
from core.trade_log_paths import resolve_trade_log_path
from core.learning_paths import canonical_suggestion_eval_log_path, canonical_suggestions_log_path, suggestion_eval_log_paths
from core.sim_pnl import DEFAULT_DELTAS, delta_key, simulate_row, compute_row_live_pnl
from core.trailing_display import apply_trailing_display_df
from core.trade_activation import should_activate, activate_trade
from core.trade_state_engine import run_state_engine_once
from core.trailing import init_trailing, update_trailing, check_exit
from core.tf_utils import check_tf_available
from core.feed_debug import get_feed_debug
from core.market_data_monitor import get_feed_health_snapshot
from core.reject_telemetry import get_recent_reject_telemetry
from core.paths import logs_dir, data_root, db_dir
from core.market_snapshot_schema import validate_market_snapshot
from core.market_snapshot_store import (
    DEFAULT_MARKET_SNAPSHOT_PATH,
    get_market_snapshot_status,
    read_market_snapshot,
)
from core.runtime_snapshot_store import ADVISORY_LATEST_PATH, TOP_OPPORTUNITIES_LATEST_PATH, RANKED_PIPELINE_LATEST_PATH
from core.telemetry_streams import iter_recent_events
from core.advisory_schema import AdvisorySchemaError, deserialize_advisory_row, log_advisory_schema_error
from dashboard.readers.advisory_reader import read_advisory_snapshot_rows
from dashboard.readers.snapshot_reader import read_snapshot_payload
from dashboard.ui.table_model import (
    normalize_df as normalize_table_df,
    compute_trade_key as compute_table_trade_key,
    dedupe as dedupe_table_df,
    select_display_df,
    filter_non_active,
)
from config import config as cfg
import time
try:
    from streamlit_autorefresh import st_autorefresh
    ST_AUTORREFRESH_AVAILABLE = True
except Exception:  # pragma: no cover
    ST_AUTORREFRESH_AVAILABLE = False
    def st_autorefresh(*args, **kwargs):
        return 0

try:
    from core.review_queue import (
        APPROVED_PATH as REVIEW_APPROVED_PATH,
        QUEUE_PATH as REVIEW_QUEUE_PATH,
        QUICK_QUEUE_PATH as QUICK_REVIEW_QUEUE_PATH,
        SCALP_QUEUE_PATH,
        TARGET_POINTS_QUEUE_PATH,
        ZERO_HERO_QUEUE_PATH,
        load_queue_rows,
        write_queue_rows,
    )
except Exception:
    REVIEW_QUEUE_PATH = _log_path("review_queue.json")
    QUICK_REVIEW_QUEUE_PATH = _log_path("quick_review_queue.json")
    ZERO_HERO_QUEUE_PATH = _log_path("zero_hero_queue.json")
    SCALP_QUEUE_PATH = _log_path("scalp_queue.json")
    TARGET_POINTS_QUEUE_PATH = _log_path("target_points_queue.json")
    REVIEW_APPROVED_PATH = _log_path("approved_trades.json")
    def _fallback_epoch_ms(value):
        try:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                v = float(value)
                if v <= 0:
                    return None
                if v >= 10_000_000_000:
                    return int(v)
                return int(v * 1000.0)
            text = str(value).strip()
            if not text:
                return None
            try:
                return _fallback_epoch_ms(float(text))
            except Exception:
                pass
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return int(dt.timestamp() * 1000.0)
        except Exception:
            return None

    def load_queue_rows(path: Path):
        try:
            raw = json.loads(Path(path).read_text())
            if not isinstance(raw, list):
                return []
            out = []
            for row in raw:
                if not isinstance(row, dict):
                    continue
                ts_ms = _fallback_epoch_ms(row.get("timestamp_epoch_ms"))
                if ts_ms is None:
                    ts_ms = _fallback_epoch_ms(row.get("timestamp_utc_iso"))
                if ts_ms is None:
                    ts_ms = _fallback_epoch_ms(row.get("timestamp"))
                if ts_ms is None:
                    ts_ms = int(time.time() * 1000.0)
                row = dict(row)
                row["timestamp_epoch_ms"] = int(ts_ms)
                row["timestamp_utc_iso"] = datetime.fromtimestamp(
                    float(ts_ms) / 1000.0, tz=timezone.utc
                ).isoformat()
                out.append(row)
            return out
        except Exception:
            pass
        return []
    def write_queue_rows(path: Path, rows: list[dict]):
        Path(path).write_text(json.dumps([r for r in rows if isinstance(r, dict)], indent=2))


def fmt_conf(conf) -> str:
    try:
        val = float(conf)
    except Exception:
        return "n/a"
    if not math.isfinite(val):
        return "n/a"
    return f"{val:.2f}"

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

st.set_page_config(page_title="Axiom Quant Console", layout="wide")
if "auto_refresh_enabled" not in st.session_state:
    # Safer default: manual browser refresh, operator can opt-in to live reruns.
    st.session_state.auto_refresh_enabled = False
if "state_engine_enabled" not in st.session_state:
    # Run queue lifecycle updates on rerun even when UI autorefresh is disabled.
    st.session_state["state_engine_enabled"] = True
if "trade_refresh_mode" not in st.session_state:
    st.session_state["trade_refresh_mode"] = REFRESH_MODE_MARKET_OPEN_ONLY

LOG_PATH = resolve_trade_log_path()
STRAT_PATH = logs_dir() / "strategy_perf.json"
apply_global_style()

_RERUN_PERF = {"data_load_ms": 0.0, "steps": []}
_DEFAULT_JSONL_TAIL_ROWS = 250
_FULL_JSONL_TAIL_ROWS = 5000
_DASHBOARD_LIVE_MD_CACHE_TTL_SEC = 1.0
_DASHBOARD_HISTORY_ERROR_COOLDOWN_SEC = 30.0


def _dashboard_read_only_mode() -> bool:
    return bool(getattr(cfg, "UI_DASHBOARD_READ_ONLY", True))


def _read_only_market_snapshot_rows() -> list[dict]:
    path = data_root() / "option_chain_latest.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("dashboard_read_only_artifact_error artifact=option_chain_latest error=%s", exc)
        return []
    if not isinstance(payload, dict):
        return []
    rows: list[dict] = []
    for symbol, chain in payload.items():
        if not isinstance(chain, list):
            continue
        rows.append(
            {
                "symbol": str(symbol or "").upper(),
                "instrument": "OPT",
                "option_chain": list(chain),
            }
        )
    return rows


def _normalize_display_ts_for_rows(rows: list[dict]) -> None:
    from core.time_utils import format_ts_ist

    for rec in rows:
        if not isinstance(rec, dict):
            continue
        ts_epoch = rec.get("display_ts_epoch")
        if ts_epoch is None:
            continue
        formatted = format_ts_ist(ts_epoch)
        if formatted:
            rec["display_ts_ist"] = formatted


def _filter_rows_today(rows, ts_key="timestamp"):
    try:
        if not isinstance(rows, (list, tuple)):
            return []
        now = now_local()
        filtered = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            ts = r.get(ts_key)
            if not ts:
                ts = datetime.now(timezone.utc).isoformat()
                r[ts_key] = ts
            if isinstance(ts, (int, float)) or str(ts_key).endswith("_epoch"):
                try:
                    ts = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
                except Exception:
                    continue
            if is_today_local(ts, now=now):
                filtered.append(r)
        return filtered
    except Exception:
        return []


def _log_read_only_block(operation: str, caller: str, detail: str = "") -> None:
    logger.warning(
        "dashboard_read_only_guard_blocked operation=%s caller=%s detail=%s",
        operation,
        caller,
        detail or "read_only_mode",
    )


def _log_dashboard_forbidden_call(function_name: str, caller: str, detail: str = "") -> None:
    logger.warning(
        "[DASHBOARD_FORBIDDEN_CALL] function=%s caller=%s detail=%s",
        function_name,
        caller,
        detail or "read_only_snapshot_path",
    )


def _coerce_status_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def read_market_snapshot_for_dashboard(
    path: str | Path = DEFAULT_MARKET_SNAPSHOT_PATH,
    *,
    stale_after_sec: float | None = None,
) -> dict:
    # Dashboard read-only snapshot path. Missing or stale artifacts must not trigger recompute.
    target = Path(path).expanduser()
    stale_after = float(
        stale_after_sec
        if stale_after_sec is not None
        else getattr(cfg, "DASHBOARD_MARKET_SNAPSHOT_STALE_AFTER_SEC", 15.0)
    )
    status = get_market_snapshot_status(target, stale_after_sec=stale_after)
    state = str(status.get("state") or "invalid")
    age_sec = status.get("age_sec")
    errors = list(status.get("errors") or [])
    if state in {"missing", "invalid"}:
        logger.info(
            "[DASHBOARD_SNAPSHOT_READ] state=%s age_sec=%s symbol_count=0 path=%s errors=%s",
            state,
            age_sec,
            target,
            "|".join(errors),
        )
        return {
            "state": state,
            "age_sec": age_sec,
            "errors": errors,
            "path": str(target),
            "snapshot": {},
        }
    try:
        snapshot = read_market_snapshot(target)
    except Exception as exc:
        logger.info(
            "[DASHBOARD_SNAPSHOT_READ] state=invalid age_sec=%s symbol_count=0 path=%s errors=%s",
            age_sec,
            target,
            str(exc),
        )
        return {
            "state": "invalid",
            "age_sec": age_sec,
            "errors": [str(exc)],
            "path": str(target),
            "snapshot": {},
        }
    valid, validation_errors = validate_market_snapshot(snapshot)
    if not valid:
        logger.info(
            "[DASHBOARD_SNAPSHOT_READ] state=invalid age_sec=%s symbol_count=0 path=%s errors=%s",
            age_sec,
            target,
            "|".join(validation_errors),
        )
        return {
            "state": "invalid",
            "age_sec": age_sec,
            "errors": list(validation_errors),
            "path": str(target),
            "snapshot": {},
        }
    symbol_count = len(dict(snapshot.get("symbols") or {}))
    logger.info(
        "[DASHBOARD_SNAPSHOT_READ] state=%s age_sec=%s symbol_count=%d path=%s",
        state,
        age_sec,
        symbol_count,
        target,
    )
    return {
        "state": state,
        "age_sec": age_sec,
        "errors": errors,
        "path": str(target),
        "snapshot": snapshot,
    }


def get_market_snapshot_view_model(
    path: str | Path = DEFAULT_MARKET_SNAPSHOT_PATH,
    *,
    stale_after_sec: float | None = None,
) -> dict:
    payload = read_market_snapshot_for_dashboard(path, stale_after_sec=stale_after_sec)
    snapshot = dict(payload.get("snapshot") or {})
    market_open = _coerce_status_bool(snapshot.get("market_open"))
    market_mode = "OFFHOURS" if not market_open else "LIVE"
    return {
        "state": str(payload.get("state") or "invalid"),
        "age_sec": payload.get("age_sec"),
        "errors": list(payload.get("errors") or []),
        "path": payload.get("path"),
        "market_open": market_open,
        "market_mode": market_mode,
        "generated_at": snapshot.get("generated_at"),
        "warnings": list(snapshot.get("warnings") or []),
        "symbols": dict(snapshot.get("symbols") or {}),
        "producer_meta": dict(snapshot.get("producer_meta") or {}),
    }


def _perf_timed_load(label: str, fn, *args, **kwargs):
    started = time.perf_counter()
    out = fn(*args, **kwargs)
    elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
    _RERUN_PERF["data_load_ms"] = float(_RERUN_PERF.get("data_load_ms", 0.0) + elapsed_ms)
    steps = list(_RERUN_PERF.get("steps") or [])
    if len(steps) < 12:
        steps.append((str(label), float(round(elapsed_ms, 2))))
    _RERUN_PERF["steps"] = steps
    try:
        logger.info("dashboard_data_load label=%s dt_ms=%.2f", label, elapsed_ms)
    except Exception:
        pass
    return out


def _perf_timed_render(label: str, fn, *args, **kwargs):
    started = time.perf_counter()
    out = fn(*args, **kwargs)
    elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
    try:
        logger.info("dashboard_render label=%s dt_ms=%.2f", label, elapsed_ms)
    except Exception:
        pass
    return out


def _log_path(*parts: str) -> Path:
    return logs_dir().joinpath(*parts)


def _trade_db_sig() -> tuple[bool, int, int]:
    db_path = Path(str(getattr(cfg, "TRADE_DB_PATH", "") or ""))
    return file_sig(db_path)


@st.cache_data(ttl=5, show_spinner=False)
def _fetch_recent_trades_cached(limit: int, _db_sig: tuple[bool, int, int]):
    _ = _db_sig
    return fetch_recent_trades(int(limit))


@st.cache_data(ttl=5, show_spinner=False)
def _fetch_recent_outcomes_cached(limit: int, _db_sig: tuple[bool, int, int]):
    _ = _db_sig
    return fetch_recent_outcomes(int(limit))


@st.cache_data(ttl=5, show_spinner=False)
def _fetch_execution_stats_cached(limit: int, _db_sig: tuple[bool, int, int]):
    _ = _db_sig
    return fetch_execution_stats(int(limit))


@st.cache_data(ttl=5, show_spinner=False)
def _load_jsonl_tail_cached(path_str: str, sig: tuple[bool, int, int], max_lines: int) -> list[dict]:
    _ = sig
    path = Path(path_str)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    rows: list[dict] = []
    for line in lines[-max(1, int(max_lines)):]:
        text = str(line or "").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


@st.cache_data(ttl=5, show_spinner=False)
def _iter_recent_events_cached(
    path_str: str,
    sig: tuple[bool, int, int],
    now_bucket: int,
    max_age_sec: float,
    event_types: tuple[str, ...],
    max_lines: int,
) -> list[dict]:
    _ = sig
    now_epoch = float(max(0, int(now_bucket))) * 5.0
    return iter_recent_events(
        Path(path_str),
        now_epoch=now_epoch,
        max_age_sec=float(max_age_sec),
        event_types=set(event_types),
        max_lines=int(max_lines),
    )


@st.cache_data(ttl=1)
def _load_runtime_health_cached(path_str: str, sig: tuple) -> dict:
    _ = sig
    try:
        payload = json.loads(Path(path_str).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_runtime_health_latest() -> dict:
    path = _log_path("runtime_health_latest.json")
    payload = _load_runtime_health_cached(str(path), file_sig(path))
    if not isinstance(payload, dict):
        return {}
    out = dict(payload)
    ts_value = out.get("snapshot_ts_epoch", out.get("ts_epoch"))
    snapshot_age = None
    try:
        if ts_value is not None:
            snapshot_age = max(0.0, float(time.time()) - float(ts_value))
    except Exception:
        snapshot_age = None
    out["snapshot_path"] = str(path)
    out["snapshot_age_sec"] = snapshot_age
    return out


def _bridge_feed_state_from_runtime_health(
    feed_state_machine: dict,
    feed_debug: dict,
    runtime_health: dict,
) -> tuple[dict, dict]:
    out_sm = dict(feed_state_machine or {})
    out_fd = dict(feed_debug or {})
    rh = runtime_health if isinstance(runtime_health, dict) else {}
    rh_feed = rh.get("feed") if isinstance(rh.get("feed"), dict) else {}
    ws_connected = rh_feed.get("ws_connected")

    now_epoch = float(time.time())
    ts_epoch = rh.get("ts_epoch")
    try:
        ts_epoch = float(ts_epoch)
    except Exception:
        ts_epoch = None
    max_age_sec = float(getattr(cfg, "UI_RUNTIME_HEALTH_MAX_AGE_SEC", 120.0))
    snapshot_age_sec = None
    try:
        if ts_epoch is not None:
            snapshot_age_sec = max(0.0, now_epoch - float(ts_epoch))
    except Exception:
        snapshot_age_sec = None
    if ts_epoch is None or (snapshot_age_sec is not None and snapshot_age_sec > max_age_sec):
        return out_sm, out_fd

    local_state = str(out_sm.get("state") or "").upper()
    local_reason = str(out_sm.get("reason") or "").lower()
    local_ws = out_fd.get("ws_connected")
    market_open = bool(rh.get("market_open", False))
    last_tick_age = rh_feed.get("last_tick_age_sec")
    ltp_age = rh_feed.get("ltp_age_sec")
    depth_age = rh_feed.get("depth_age_sec")
    subscriptions_count = rh_feed.get("subscriptions_count")
    intended_tokens_count = rh_feed.get("intended_tokens_count")
    runtime_last_error = rh_feed.get("last_error")
    allow_stale_quotes = bool(rh_feed.get("allow_stale_quotes", False))
    sla_state = str(rh_feed.get("sla_state") or "").strip().upper()
    if not sla_state:
        sla_state = "LIVE" if (market_open and not allow_stale_quotes) else "PLANNING"
    ltp_required_raw = rh_feed.get("ltp_required")
    if isinstance(ltp_required_raw, bool):
        ltp_required = ltp_required_raw
    else:
        ltp_required = bool(sla_state == "LIVE" and market_open and (not allow_stale_quotes))
    depth_required_raw = rh_feed.get("depth_required")
    depth_required = bool(depth_required_raw) if isinstance(depth_required_raw, bool) else False
    ltp_max_age_sec = rh_feed.get("ltp_max_age_sec")
    depth_max_age_sec = rh_feed.get("depth_max_age_sec")
    sla_status = str(rh_feed.get("sla_status") or "").strip().upper()
    sla_reasons = list(rh_feed.get("reasons") or [])
    stale_tick_threshold = float(
        max(
            float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)),
            float(getattr(cfg, "FEED_HEALTH_OPTION_OK_AGE_SEC", 2.5)),
        )
    )
    try:
        ltp_max_age_sec_f = float(ltp_max_age_sec)
    except Exception:
        ltp_max_age_sec_f = stale_tick_threshold
    try:
        depth_max_age_sec_f = float(depth_max_age_sec)
    except Exception:
        depth_max_age_sec_f = float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 6.0))
    strict_live_freshness = bool(sla_state == "LIVE" and market_open and (not allow_stale_quotes))

    observed_ltp_age = None
    if isinstance(last_tick_age, (int, float)):
        observed_ltp_age = float(last_tick_age)
    elif isinstance(ltp_age, (int, float)):
        observed_ltp_age = float(ltp_age)
    observed_depth_age = float(depth_age) if isinstance(depth_age, (int, float)) else None

    # SLA/source policy failures are authoritative and should surface even when ws telemetry is unavailable.
    has_sla_fail = bool(sla_status in {"FAIL", "STALE", "DOWN"} and sla_reasons)
    policy_age_fail = False
    policy_age_reason = ""
    if bool(ltp_required) and observed_ltp_age is not None and observed_ltp_age > ltp_max_age_sec_f:
        policy_age_fail = True
        policy_age_reason = "runtime_health_sla_ltp_stale"
    if bool(depth_required) and observed_depth_age is not None and observed_depth_age > depth_max_age_sec_f:
        policy_age_fail = True
        if not policy_age_reason:
            policy_age_reason = "runtime_health_sla_depth_stale"
    strict_live_stale = bool(
        strict_live_freshness
        and observed_ltp_age is not None
        and observed_ltp_age > stale_tick_threshold
    )

    should_override = bool(
        local_state in ("", "DOWN", "UNKNOWN")
        or "no_ws" in local_reason
        or local_ws in (None, False)
    )
    if not should_override:
        return out_sm, out_fd

    if has_sla_fail:
        out_sm["state"] = "DEGRADED"
        out_sm["reason"] = f"runtime_health_sla_fail:{sla_reasons[0]}"
    elif strict_live_stale:
        out_sm["state"] = "DEGRADED"
        out_sm["reason"] = "runtime_health_ws_connected_but_stale_ticks"
    elif policy_age_fail:
        out_sm["state"] = "DEGRADED"
        out_sm["reason"] = policy_age_reason
    elif ws_connected is True:
        out_sm["state"] = "OK"
        out_sm["reason"] = "runtime_health_ws_connected"
    elif ws_connected is False:
        if strict_live_freshness and market_open:
            out_sm["state"] = "DOWN"
            out_sm["reason"] = "runtime_health_ws_disconnected"
        else:
            out_sm["state"] = "UNKNOWN"
            out_sm["reason"] = "runtime_health_ws_disconnected_nonlive"
    else:
        out_sm["state"] = "UNKNOWN"
        out_sm["reason"] = "runtime_health_ws_unknown"

    out_sm["ws_msg_age_sec"] = observed_ltp_age
    if ws_connected in (True, False):
        out_fd["ws_connected"] = bool(ws_connected)
        out_fd["ws_connected_source"] = "runtime_health_bridge"
    if subscriptions_count is not None:
        out_fd["subscribed_tokens_count"] = subscriptions_count
    if intended_tokens_count is not None:
        out_fd["intended_tokens_count"] = intended_tokens_count
    if runtime_last_error not in (None, "", "None"):
        out_fd["feed_runtime_last_error"] = runtime_last_error
    if observed_ltp_age is not None:
        out_fd["last_tick_age_sec"] = observed_ltp_age
    return out_sm, out_fd


def _refresh_trade_state():
    if _dashboard_read_only_mode():
        logger.info("dashboard_read_only_skip operation=state_engine")
        return False
    try:
        desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
        return run_state_engine_if_due(
            session_state=st.session_state,
            desk_id=desk_id,
            run_once=run_state_engine_once,
            refresh_sec=float(getattr(cfg, "UI_STATE_ENGINE_REFRESH_SEC", 5.0)),
            now_fn=time.time,
        )
    except Exception as exc:
        logger.warning("trade_state_engine_failed: %s", exc)
        return False


_refresh_trade_state()

SPEED_TRADER_COLS = [
    "timestamp",
    "trade_status",
    "first_seen",
    "last_seen",
    "update_count",
    "symbol",
    "instrument_id",
    "expiry_date",
    "tradingsymbol",
    "strike",
    "option_type",
    "side",
    "direction",
    "permission",
    "entry",
    "signal_price",
    "current_ltp",
    "suggested_entry",
    "price_age_sec",
    "entry_status",
    "target",
    "stop",
    "status",
    "activation_price",
    "activated_ts",
    "pnl_points",
    "pnl_cash",
    "confidence",
]

EXECUTABLE_PRICING_COLS = [
    "ltp",
    "bid",
    "ask",
    "mark_price",
    "quote_age_sec",
    "spread_pct",
]

EXPLORER_COLUMN_PRESETS = {
    "Minimal": [
        "timestamp",
        "symbol",
        "underlying",
        "option_side",
        "strategy_family",
        "permission_bucket",
        "final_action",
        "final_blocker",
        "global_conf",
        "entry_status",
        "feed_state",
    ],
    "Strategy": [
        "timestamp",
        "symbol",
        "strategy_family",
        "strategy_category",
        "permission_bucket",
        "global_conf",
        "signal_score",
        "regime_conf",
        "orb_bias",
        "orb_factor",
        "reg_penalty",
    ],
    "Execution": [
        "timestamp",
        "symbol",
        "option_side",
        "permission_bucket",
        "permission_reason",
        "entry_status",
        "entry_block_reason",
        "final_action",
        "final_blocker",
    ],
    "Strategy+Execution": [
        "timestamp",
        "symbol",
        "underlying",
        "option_side",
        "strategy_family",
        "strategy_category",
        "permission_bucket",
        "permission_reason",
        "final_action",
        "final_blocker",
        "entry_status",
        "entry_block_reason",
        "global_conf",
        "signal_score",
        "regime_conf",
        "orb_bias",
        "orb_factor",
        "reg_penalty",
        "feed_state",
        "quote_age_sec",
        "spread_pct",
    ],
    "Feed/Quality": [
        "timestamp",
        "symbol",
        "feed_state",
        "quote_age_sec",
        "spread_pct",
        "ltp",
        "bid",
        "ask",
        "mark_price",
        "permission_bucket",
        "final_blocker",
    ],
    "Debug": [
        "timestamp",
        "run_id",
        "trade_key",
        "source_bucket",
        "symbol",
        "tradingsymbol",
        "underlying",
        "option_side",
        "strategy_family",
        "strategy_category",
        "permission_bucket",
        "permission_reason",
        "entry_status",
        "entry_block_reason",
        "final_action",
        "final_blocker",
        "global_conf",
        "signal_score",
        "regime_conf",
        "orb_bias",
        "orb_factor",
        "reg_penalty",
        "feed_state",
        "quote_age_sec",
        "spread_pct",
    ],
}


def _desk_log_path(filename: str) -> Path:
    desk_log_dir = str(getattr(cfg, "DESK_LOG_DIR", "") or "").strip()
    if desk_log_dir:
        return Path(desk_log_dir) / filename
    desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT")
    return logs_dir() / f"desks/{desk_id}/{filename}"


@st.cache_data(ttl=1.0, show_spinner=False)
def _load_trade_log_rows_cached(path_str: str, sig: tuple[bool, int, int], max_rows: int | None = None) -> list[dict]:
    _ = sig
    try:
        resolved = Path(path_str)
        if not resolved.exists():
            return []
        raw = resolved.read_text(encoding="utf-8").strip()
    except Exception:
        return []
    if not raw:
        return []

    # Support both JSONL (canonical) and legacy JSON array formats.
    if raw.startswith("["):
        try:
            payload = json.loads(raw)
            if isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, dict)]
                if max_rows is not None and int(max_rows) > 0:
                    return rows[-max(1, int(max_rows)) :]
                return rows
        except Exception:
            return []
        return []

    rows: list[dict] = []
    lines = raw.splitlines()
    if max_rows is not None and int(max_rows) > 0:
        lines = lines[-max(1, int(max_rows)) :]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _load_trade_log_rows(path: Path, *, max_rows: int | None = None) -> list[dict]:
    resolved = resolve_trade_log_path(path)
    return _load_trade_log_rows_cached(str(resolved), file_sig(resolved), max_rows)


def _load_json_payload_uncached(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _load_snapshot_payload_uncached(path: Path) -> dict:
    payload = read_snapshot_payload(path)
    inner = payload.get("payload")
    return inner if isinstance(inner, dict) else {}


def _load_jsonl_tail_uncached(path: Path, max_rows: int) -> list[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    rows: list[dict] = []
    for line in lines[-max(1, int(max_rows)) :]:
        text = str(line or "").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _load_live_suggestions_status() -> dict:
    return _perf_timed_load(
        "suggestions_status_json",
        _load_json_payload_uncached,
        logs_dir() / "suggestions_status.json",
    )


def _dashboard_feed_display_summary(snapshot: dict) -> tuple[str, str, object, object]:
    runtime_health = snapshot.get("runtime_health") or {}
    runtime_feed = runtime_health.get("feed") if isinstance(runtime_health.get("feed"), dict) else {}
    runtime_state = str(runtime_feed.get("runtime_state") or "").strip().upper()
    ws_connected = runtime_feed.get("ws_connected")
    subscribed_count = runtime_feed.get("subscribed_option_tokens_count")
    if subscribed_count is None:
        subscribed_count = runtime_feed.get("subscribed_tokens_count")
    try:
        subscribed_count_int = int(subscribed_count) if subscribed_count is not None else None
    except Exception:
        subscribed_count_int = None

    if runtime_state == "RUNNING" and bool(ws_connected) and (
        subscribed_count_int is None or subscribed_count_int > 0
    ):
        ltp_age = runtime_feed.get("last_tick_age_sec", runtime_feed.get("last_ws_tick_age_sec"))
        depth_age = runtime_feed.get("last_depth_age_sec")
        return "OK", "runtime_running", ltp_age, depth_age

    if runtime_state in {"SUBSCRIBE_FAILED", "AUTH_BLOCKED", "IMPORT_MISSING", "DOWN"}:
        ltp_age = runtime_feed.get("last_tick_age_sec", runtime_feed.get("last_ws_tick_age_sec"))
        depth_age = runtime_feed.get("last_depth_age_sec")
        reason = str(runtime_feed.get("last_error") or runtime_state.lower()).strip() or runtime_state.lower()
        return "DOWN", reason, ltp_age, depth_age

    feed = snapshot.get("feed_freshness") or {}
    feed_debug = snapshot.get("feed_debug") or {}
    return _feed_status_summary(feed, feed_debug)


def _load_freshness_latest() -> dict:
    payload = _perf_timed_load(
        "freshness_latest_json",
        _load_json_payload_uncached,
        logs_dir() / "freshness_latest.json",
    )
    if not isinstance(payload, dict):
        return {}
    try:
        updated_at = str(payload.get("updated_at") or "").strip()
        if updated_at:
            dt_text = updated_at[:-1] + "+00:00" if updated_at.endswith("Z") else updated_at
            updated_dt = datetime.fromisoformat(dt_text)
            if updated_dt.year < 2023:
                logger.warning("dashboard_freshness_payload_invalid reason=updated_at_before_2023 updated_at=%s", updated_at)
                return {}
    except Exception:
        logger.warning("dashboard_freshness_payload_invalid reason=updated_at_parse_error updated_at=%s", payload.get("updated_at"))
        return {}
    decisions = payload.get("decisions")
    if isinstance(decisions, dict):
        for symbol, symbol_payload in decisions.items():
            if not isinstance(symbol_payload, dict):
                continue
            for decision_type, decision_payload in symbol_payload.items():
                if not isinstance(decision_payload, dict):
                    continue
                try:
                    now_epoch = decision_payload.get("now_epoch")
                    if now_epoch is not None and float(now_epoch) < 1577836800.0:
                        logger.warning(
                            "dashboard_freshness_payload_invalid reason=decision_now_epoch_before_2020 symbol=%s decision_type=%s now_epoch=%s",
                            symbol,
                            decision_type,
                            now_epoch,
                        )
                        return {}
                except Exception:
                    logger.warning(
                        "dashboard_freshness_payload_invalid reason=decision_now_epoch_parse_error symbol=%s decision_type=%s now_epoch=%s",
                        symbol,
                        decision_type,
                        decision_payload.get("now_epoch"),
                    )
                    return {}
    return payload


def _add_upstox_links(df):
    # Upstox deep links are intentionally disabled in runtime UI.
    return df


def _render_trade_explorer_sidebar_filters(explorer_df: pd.DataFrame):
    if explorer_df is None or explorer_df.empty:
        return {}
    if "trade_date" not in explorer_df.columns:
        explorer_df = _derive_trade_explorer_fields(explorer_df)
        if explorer_df.empty:
            return {}
    with st.sidebar:
        st.markdown("### Trade Explorer Filters")
        trade_dates = explorer_df.get("trade_date", pd.Series(dtype="object"))
        date_options = sorted([d for d in trade_dates.dropna().astype(str).unique().tolist() if d and d != "UNKNOWN"])
        selected_dates = []
        if len(date_options) > 1:
            selected_dates = st.multiselect(
                "Date",
                options=date_options,
                default=date_options,
                key="explorer_filter_dates",
            )

        run_options = sorted([r for r in explorer_df["run_id"].dropna().astype(str).unique().tolist() if r and r != "UNKNOWN"])
        selected_run_ids = []
        if run_options:
            selected_run_ids = st.multiselect(
                "Run ID",
                options=run_options,
                default=run_options,
                key="explorer_filter_run_ids",
            )

        def _all_multiselect(label: str, column: str, key: str):
            options = sorted([v for v in explorer_df[column].dropna().astype(str).unique().tolist() if v])
            if not options:
                return []
            selected = st.multiselect(label, options=options, default=options, key=key)
            if len(selected) == len(options):
                return []
            return selected

        underlyings = _all_multiselect("Underlying", "underlying", "explorer_filter_underlying")
        option_sides = _all_multiselect("CE/PE", "option_side", "explorer_filter_option_side")
        strategy_categories = _all_multiselect("Strategy Category", "strategy_category", "explorer_filter_strategy_category")
        strategy_families = _all_multiselect("Strategy Family", "strategy_family", "explorer_filter_strategy_family")
        permission_buckets = _all_multiselect("Permission Bucket", "permission_bucket", "explorer_filter_permission_bucket")
        final_blockers = _all_multiselect("Final Blocker", "final_blocker", "explorer_filter_final_blocker")
        feed_states = _all_multiselect("Feed State", "feed_state", "explorer_filter_feed_state")
        symbol_query = st.text_input("Symbol Search", value="", key="explorer_filter_symbol_search")

        global_range = _numeric_slider_config(explorer_df, "global_conf")
        spread_range = _numeric_slider_config(explorer_df, "spread_pct")
        quote_age_range = _numeric_slider_config(explorer_df, "quote_age_sec")

        selected_global = None
        if global_range is not None:
            selected_global = st.slider(
                "global_conf range",
                min_value=float(global_range[0]),
                max_value=float(global_range[1]),
                value=(float(global_range[0]), float(global_range[1])),
                step=0.01,
                key="explorer_filter_global_conf",
            )
        selected_spread = None
        if spread_range is not None:
            selected_spread = st.slider(
                "spread_pct range",
                min_value=float(spread_range[0]),
                max_value=float(spread_range[1]),
                value=(float(spread_range[0]), float(spread_range[1])),
                step=0.0005,
                key="explorer_filter_spread_pct",
            )
        selected_quote_age = None
        if quote_age_range is not None:
            selected_quote_age = st.slider(
                "quote_age_sec range",
                min_value=float(quote_age_range[0]),
                max_value=float(quote_age_range[1]),
                value=(float(quote_age_range[0]), float(quote_age_range[1])),
                step=0.1,
                key="explorer_filter_quote_age_sec",
            )

        preset = st.selectbox(
            "Column Preset",
            options=list(EXPLORER_COLUMN_PRESETS.keys()),
            index=0,
            key="explorer_col_preset",
        )
        preset_cols = [c for c in EXPLORER_COLUMN_PRESETS[preset] if c in explorer_df.columns]
        if st.session_state.get("explorer_col_preset_prev") != preset:
            st.session_state["explorer_selected_cols"] = preset_cols
            st.session_state["explorer_col_preset_prev"] = preset
        selected_cols = st.multiselect(
            "Columns",
            options=list(explorer_df.columns),
            key="explorer_selected_cols",
        )
        show_charts = st.checkbox("Show summary charts", value=True, key="explorer_show_charts")

    return {
        "dates": selected_dates if selected_dates and len(selected_dates) < len(date_options) else [],
        "run_ids": selected_run_ids if selected_run_ids and len(selected_run_ids) < len(run_options) else [],
        "underlyings": underlyings,
        "option_sides": option_sides,
        "strategy_categories": strategy_categories,
        "strategy_families": strategy_families,
        "permission_buckets": permission_buckets,
        "final_blockers": final_blockers,
        "feed_states": feed_states,
        "symbol_query": symbol_query,
        "global_conf_range": selected_global,
        "spread_pct_range": selected_spread,
        "quote_age_sec_range": selected_quote_age,
        "selected_cols": selected_cols,
        "show_charts": show_charts,
    }


def _load_live_suggestions_df(limit: int = 100) -> pd.DataFrame:
    advisory_snapshot = _perf_timed_load(
        "advisory_latest_snapshot_json",
        read_advisory_snapshot_rows,
        ADVISORY_LATEST_PATH,
        limit=max(1, int(limit)),
    )
    snapshot_state = str(advisory_snapshot.get("state") or "")
    snapshot_rows = list(advisory_snapshot.get("rows") or []) if isinstance(advisory_snapshot, dict) else []
    if snapshot_rows:
        rows = snapshot_rows
    elif snapshot_state == "invalid":
        logger.warning(
            "dashboard_live_advisory_snapshot_invalid path=%s errors=%s",
            advisory_snapshot.get("path"),
            "|".join(list(advisory_snapshot.get("errors") or [])),
        )
        return pd.DataFrame()
    else:
        logger.warning(
            "dashboard_live_advisory_snapshot_missing path=%s",
            ADVISORY_LATEST_PATH,
        )
        return pd.DataFrame()
    if bool(getattr(cfg, "UI_LIVE_ROW_REQUIRE_TODAY", True)):
        filtered_rows = _filter_rows_today(rows, ts_key="display_ts_epoch")
        has_display_ts = any(
            isinstance(r, dict) and r.get("display_ts_epoch") not in (None, "", "None") for r in rows
        )
        if not filtered_rows and not has_display_ts:
            filtered_rows = _filter_rows_today(rows, ts_key="timestamp")
        if filtered_rows:
            rows = filtered_rows
        elif has_display_ts:
            return pd.DataFrame()
    if not rows:
        return pd.DataFrame()

    validated_rows: list[dict] = []
    for row in rows:
        try:
            validated_rows.append(deserialize_advisory_row(row, allow_legacy=False))
        except AdvisorySchemaError as exc:
            log_advisory_schema_error("dashboard.live_suggestions", row, exc)
            logger.warning("dashboard_live_advisory_schema_error trade_id=%s error=%s", row.get("trade_id") if isinstance(row, dict) else None, exc)
    if not validated_rows:
        return pd.DataFrame()
    _normalize_display_ts_for_rows(validated_rows)
    df_live = _perf_timed_load("suggestions_dataframe_build", pd.DataFrame, validated_rows)
    if df_live.empty:
        return df_live
    if bool(getattr(cfg, "CANDIDATE_ROW_KIND_CANONICAL_ONLY", True)):
        if "row_kind" in df_live.columns:
            row_kind = df_live["row_kind"].fillna("").astype(str).str.lower().str.strip()
            df_live = df_live[row_kind.eq("canonical_suggestion")].copy()
        if "non_canonical_levels" in df_live.columns:
            non_canonical = df_live["non_canonical_levels"].fillna(False).astype(bool)
            df_live = df_live[~non_canonical].copy()
        if not df_live.empty:
            required_cols = ["entry", "target"]
            if "stop_loss" in df_live.columns:
                required_cols.append("stop_loss")
            elif "stop" in df_live.columns:
                required_cols.append("stop")
            for required_col in required_cols:
                if required_col in df_live.columns:
                    df_live = df_live[df_live[required_col].notna()].copy()
            if "stop_loss" in df_live.columns and "stop" not in df_live.columns:
                df_live["stop"] = df_live["stop_loss"]
    if df_live.empty:
        return df_live
    if "trade_key" not in df_live.columns:
        df_live["trade_key"] = None
    if "advisory_id" in df_live.columns:
        missing_trade_key = df_live["trade_key"].isna() | df_live["trade_key"].astype(str).str.strip().eq("")
        df_live.loc[missing_trade_key, "trade_key"] = df_live.loc[missing_trade_key, "advisory_id"]
    if "trade_id" in df_live.columns:
        missing_trade_key = df_live["trade_key"].isna() | df_live["trade_key"].astype(str).str.strip().eq("")
        df_live.loc[missing_trade_key, "trade_key"] = df_live.loc[missing_trade_key, "trade_id"]
    df_live = _add_upstox_links(df_live)
    df_live = _prepare_trade_display_df(df_live)
    return df_live


def _load_top_opportunities_frames(limit: int = 25) -> dict[str, pd.DataFrame]:
    snapshot = _perf_timed_load(
        "top_opportunities_snapshot_json",
        read_snapshot_payload,
        RANKED_PIPELINE_LATEST_PATH,
    )
    if not isinstance(snapshot, dict) or str(snapshot.get("state") or "") != "ok":
        try:
            import streamlit as st

            st.error("canonical ranked pipeline missing")
        except Exception:
            logger.warning("dashboard_canonical_ranked_pipeline_missing")
        return {"top_executable": pd.DataFrame(), "top_advisory": pd.DataFrame()}
    payload = snapshot.get("payload") if isinstance(snapshot, dict) else {}
    if not isinstance(payload, dict):
        return {"top_executable": pd.DataFrame(), "top_advisory": pd.DataFrame()}

    def _build_df(rows_key: str) -> pd.DataFrame:
        rows = payload.get(rows_key)
        if not isinstance(rows, list) or not rows:
            return pd.DataFrame()
        validated_rows: list[dict] = []
        for row in list(rows)[: max(1, int(limit))]:
            try:
                validated_rows.append(row)
            except AdvisorySchemaError as exc:
                log_advisory_schema_error(f"dashboard.{rows_key}", row, exc)
                logger.warning(
                    "dashboard_top_opportunities_schema_error list=%s trade_id=%s error=%s",
                    rows_key,
                    row.get("trade_id") if isinstance(row, dict) else None,
                    exc,
                )
        if not validated_rows:
            return pd.DataFrame()
        if bool(getattr(cfg, "UI_LIVE_ROW_REQUIRE_TODAY", True)):
            filtered_rows = _filter_rows_today(validated_rows, ts_key="display_ts_epoch")
            has_display_ts = any(
                isinstance(r, dict) and r.get("display_ts_epoch") not in (None, "", "None")
                for r in validated_rows
            )
            if not filtered_rows and not has_display_ts:
                filtered_rows = _filter_rows_today(validated_rows, ts_key="timestamp")
            if filtered_rows:
                validated_rows = filtered_rows
            elif has_display_ts:
                return pd.DataFrame()
        _normalize_display_ts_for_rows(validated_rows)
        df = _perf_timed_load(f"{rows_key}_dataframe_build", pd.DataFrame, validated_rows)
        if df.empty:
            return df
        df = _add_upstox_links(df)
        return _prepare_trade_display_df(df)

    return {
        "top_executable": _build_df("top_executable_opportunities"),
        "top_advisory": _build_df("top_advisory_opportunities"),
    }


def _is_dashboard_auth_fetch_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    markers = (
        "tokenexception",
        "access_token",
        "api_key",
        "incorrect api key",
        "invalid session",
        "session expired",
        "hist_error",
        "forbidden",
        "unauthorized",
    )
    return any(marker in text for marker in markers)


def _dashboard_history_cooldown_keys(name: str) -> tuple[str, str]:
    key = str(name or "history").strip().lower().replace(" ", "_")
    return (
        f"dashboard_history_cooldown_until_{key}",
        f"dashboard_history_cooldown_reason_{key}",
    )


def _history_fetch_suppressed(name: str) -> bool:
    cooldown_key, reason_key = _dashboard_history_cooldown_keys(name)
    now_ts = float(time.time())
    try:
        cooldown_until = float(st.session_state.get(cooldown_key) or 0.0)
    except Exception:
        cooldown_until = 0.0
    if cooldown_until <= now_ts:
        return False
    try:
        reason = str(st.session_state.get(reason_key) or "")
    except Exception:
        reason = ""
    logger.info(
        "dashboard_history_fetch_suppressed name=%s cooldown_remaining_sec=%.2f reason=%s",
        name,
        max(0.0, cooldown_until - now_ts),
        reason or "cooldown",
    )
    return True


def _record_history_fetch_failure(name: str, exc: Exception) -> None:
    if not _is_dashboard_auth_fetch_error(exc):
        return
    cooldown_key, reason_key = _dashboard_history_cooldown_keys(name)
    now_ts = float(time.time())
    try:
        st.session_state[cooldown_key] = now_ts + _DASHBOARD_HISTORY_ERROR_COOLDOWN_SEC
        st.session_state[reason_key] = str(exc)
    except Exception:
        pass


def _fetch_day_type_events_dashboard(*, caller: str, max_rows: int) -> list[dict]:
    cache_key = f"dashboard_day_type_events_cache_{int(max_rows)}"
    cache_ts_key = f"{cache_key}_ts"
    now_ts = float(time.time())
    try:
        cached = list(st.session_state.get(cache_key) or [])
    except Exception:
        cached = []
    try:
        cache_ts = float(st.session_state.get(cache_ts_key) or 0.0)
    except Exception:
        cache_ts = 0.0
    if cached and (now_ts - cache_ts) <= 10.0:
        logger.info(
            "dashboard_data_load label=day_type_events_cache_hit caller=%s dt_ms=0.00 rows=%d",
            caller,
            len(cached),
        )
        return cached
    if _history_fetch_suppressed("day_type_events"):
        return cached
    started = time.perf_counter()
    try:
        rows = list(load_day_type_events(backfill=False, max_rows=int(max_rows)) or [])
        elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        logger.info(
            "dashboard_history_fetch_attempt name=day_type_events caller=%s result=ok dt_ms=%.2f rows=%d",
            caller,
            elapsed_ms,
            len(rows),
        )
        try:
            st.session_state[cache_key] = rows
            st.session_state[cache_ts_key] = now_ts
        except Exception:
            pass
        return rows
    except Exception as exc:
        elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        logger.warning(
            "dashboard_history_fetch_attempt name=day_type_events caller=%s result=error dt_ms=%.2f error=%s",
            caller,
            elapsed_ms,
            exc,
        )
        _record_history_fetch_failure("day_type_events", exc)
        return cached


def _fetch_live_market_data_dashboard(
    caller: str,
    *,
    allow_stale_cache: bool = True,
    allow_broker_fetch: bool = False,
) -> list[dict]:
    if str(caller or "").strip() == "market_snapshot":
        _log_dashboard_forbidden_call("fetch_live_market_data", caller, "use_market_snapshot_artifact")
        return []
    now_ts = float(time.time())
    cache_key = "dashboard_live_market_data_cache"
    cache_ts_key = "dashboard_live_market_data_cache_ts"
    cooldown_key = "dashboard_live_market_data_error_cooldown_until"
    cooldown_reason_key = "dashboard_live_market_data_error_reason"
    try:
        cached = list(st.session_state.get(cache_key) or [])
    except Exception:
        cached = []
    try:
        cache_ts = float(st.session_state.get(cache_ts_key) or 0.0)
    except Exception:
        cache_ts = 0.0
    try:
        cooldown_until = float(st.session_state.get(cooldown_key) or 0.0)
    except Exception:
        cooldown_until = 0.0
    cooldown_reason = ""
    try:
        cooldown_reason = str(st.session_state.get(cooldown_reason_key) or "")
    except Exception:
        cooldown_reason = ""

    if cached and (now_ts - cache_ts) <= _DASHBOARD_LIVE_MD_CACHE_TTL_SEC:
        logger.info(
            "dashboard_market_data_cache_hit caller=%s age_sec=%.2f rows=%d",
            caller,
            max(0.0, now_ts - cache_ts),
            len(cached),
        )
        return cached
    artifact_rows = _read_only_market_snapshot_rows()
    if artifact_rows:
        logger.info(
            "dashboard_market_data_artifact_hit caller=%s rows=%d",
            caller,
            len(artifact_rows),
        )
        try:
            st.session_state[cache_key] = artifact_rows
            st.session_state[cache_ts_key] = now_ts
        except Exception:
            pass
        return artifact_rows
    if _dashboard_read_only_mode() or not allow_broker_fetch:
        _log_read_only_block("live_market_data_fetch", caller, "artifact_missing")
        logger.warning("dashboard_market_data_artifact_missing caller=%s", caller)
        return []
    if cooldown_until > now_ts:
        logger.info(
            "dashboard_history_fetch_suppressed caller=%s cooldown_remaining_sec=%.2f reason=%s",
            caller,
            max(0.0, cooldown_until - now_ts),
            cooldown_reason or "cooldown",
        )
        return cached if allow_stale_cache else []

    started = time.perf_counter()
    try:
        rows = list(fetch_live_market_data(allow_history_seed=False) or [])
        elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        logger.info(
            "dashboard_history_fetch_attempt caller=%s result=ok dt_ms=%.2f rows=%d",
            caller,
            elapsed_ms,
            len(rows),
        )
        try:
            st.session_state[cache_key] = rows
            st.session_state[cache_ts_key] = now_ts
            st.session_state[cooldown_key] = 0.0
            st.session_state[cooldown_reason_key] = ""
        except Exception:
            pass
        return rows
    except Exception as exc:
        elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        logger.warning(
            "dashboard_history_fetch_attempt caller=%s result=error dt_ms=%.2f error=%s",
            caller,
            elapsed_ms,
            exc,
        )
        if _is_dashboard_auth_fetch_error(exc):
            try:
                st.session_state[cooldown_key] = now_ts + _DASHBOARD_HISTORY_ERROR_COOLDOWN_SEC
                st.session_state[cooldown_reason_key] = str(exc)
            except Exception:
                pass
        return cached if allow_stale_cache else []


def _should_enable_local_trade_refresh(show_active_view: bool, show_advisory_view: bool) -> bool:
    return bool(
        hasattr(st, "fragment")
        and bool(st.session_state.get("auto_refresh_enabled", False))
        and (bool(show_active_view) or bool(show_advisory_view))
    )


def _load_approved_trades(path: Path):
    if not path.exists():
        return [], []
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return [], []
    rows = []
    if isinstance(raw, dict) and isinstance(raw.get("approvals"), dict):
        for trade_id, payload in raw.get("approvals", {}).items():
            if not trade_id:
                continue
            rec = {"trade_id": str(trade_id)}
            if isinstance(payload, dict):
                rec.update(
                    {
                        "approved_epoch": payload.get("approved_epoch"),
                        "expires_epoch": payload.get("expires_epoch"),
                        "payload_hash": payload.get("payload_hash"),
                        "legacy": bool(payload.get("legacy", False)),
                        "status": payload.get("status"),
                    }
                )
            rows.append(rec)
    elif isinstance(raw, list):
        for trade_id in raw:
            rows.append({"trade_id": str(trade_id), "legacy": True})
    now_epoch = time.time()
    active = []
    for rec in rows:
        exp = rec.get("expires_epoch")
        try:
            exp_val = float(exp) if exp is not None else None
        except Exception:
            exp_val = None
        if exp_val is None or exp_val > now_epoch:
            active.append(rec)
    return rows, active


def _safe_sort_by_last_seen(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    work = df.copy()

    def _coerce_epoch(series: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().any():
            numeric = numeric.where(numeric <= 1e12, numeric / 1000.0)
        text = series.astype(str)
        text = text.where(text.str.strip().ne(""), None)
        parsed = pd.to_datetime(text, errors="coerce", utc=True)
        parsed_epoch = pd.Series([float("nan")] * len(series), index=series.index, dtype="float64")
        mask = parsed.notna()
        if mask.any():
            parsed_epoch.loc[mask] = parsed.loc[mask].astype("int64") / 1_000_000_000.0
        return numeric.where(numeric.notna(), parsed_epoch)

    display_epoch = None
    if "display_ts_epoch" in work.columns:
        display_epoch = _coerce_epoch(work["display_ts_epoch"])

    decision_epoch = None
    for field in (
        "decision_ts_epoch",
        "decision_ts_utc",
        "decision_ts_ist",
        "ts_epoch",
        "ts_utc",
        "ts_ist",
        "timestamp_epoch_ms",
        "timestamp_utc_iso",
        "timestamp",
        "created_ts_epoch",
        "created_at",
    ):
        if field in work.columns:
            candidate = _coerce_epoch(work[field])
            decision_epoch = candidate if decision_epoch is None else decision_epoch.where(decision_epoch.notna(), candidate)

    snapshot_epoch = None
    for field in (
        "snapshot_ts_epoch",
        "snapshot_ts_utc",
        "snapshot_ts_ist",
    ):
        if field in work.columns:
            candidate = _coerce_epoch(work[field])
            snapshot_epoch = candidate if snapshot_epoch is None else snapshot_epoch.where(snapshot_epoch.notna(), candidate)

    if display_epoch is None:
        if decision_epoch is not None:
            display_epoch = decision_epoch
        elif snapshot_epoch is not None:
            display_epoch = snapshot_epoch
    else:
        if decision_epoch is not None:
            display_epoch = display_epoch.where(display_epoch.notna(), decision_epoch)
        elif snapshot_epoch is not None:
            display_epoch = display_epoch.where(display_epoch.notna(), snapshot_epoch)

    if display_epoch is None:
        display_epoch = pd.Series(float("nan"), index=work.index, dtype="float64")
    work["display_ts_epoch"] = display_epoch
    if "last_seen_ts" in work.columns:
        work["last_seen_ts"] = pd.to_datetime(work["last_seen_ts"], errors="coerce", utc=True)
        work["last_seen_ts"] = work["last_seen_ts"].fillna(pd.Timestamp.now(tz="UTC"))
    else:
        work["last_seen_ts"] = pd.to_datetime(display_epoch, errors="coerce", unit="s", utc=True)
        work["last_seen_ts"] = work["last_seen_ts"].fillna(pd.Timestamp.now(tz="UTC"))
    return work.sort_values("display_ts_epoch", ascending=False, kind="mergesort")


def _prepare_trade_display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    work = _safe_sort_by_last_seen(df.copy())
    # Do not re-normalize display frames here; table-model normalization can inject
    # canonical columns with null placeholders and pollute visible tables.
    if "trade_key" in work.columns:
        work = work.drop_duplicates(subset=["trade_key"], keep="first")
    return work


def _is_entry_executable_status(value) -> bool:
    status = str(value or "").strip().upper()
    return status in {"OK", "LIVE_OK", "VALID", "NONE", "", "PRICE_MISMATCH", "REST_FALLBACK"}


def _is_canonical_advisory_df(df: pd.DataFrame | None) -> bool:
    if df is None or df.empty:
        return False
    canonical_cols = {
        "hard_blockers",
        "soft_penalties",
        "warnings",
        "confidence_final",
        "advisory_visible",
        "execution_status",
        "entry_source",
    }
    return any(col in df.columns for col in canonical_cols)


def _enforce_executable_entry_display(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if _is_canonical_advisory_df(df):
        return df
    if "entry_status" not in df.columns or "entry" not in df.columns:
        return df
    out = df.copy()
    status = out["entry_status"].astype(str).str.strip().str.upper()
    executable_mask = status.apply(_is_entry_executable_status)
    out.loc[~executable_mask, "entry"] = None
    return out


def _select_visible_advisory_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    if "advisory_visible" in out.columns:
        visible = out["advisory_visible"].fillna(True).astype(bool)
        out = out[visible].copy()
    if out.empty:
        return out
    return _prepare_trade_display_df(out)


def _build_reject_reason_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "primary_blocker" not in df.columns:
        return pd.DataFrame(columns=["primary_blocker", "count"])
    return (
        df["primary_blocker"]
        .astype(str)
        .str.strip()
        .replace({"": "UNSPECIFIED", "None": "UNSPECIFIED"})
        .value_counts()
        .rename_axis("primary_blocker")
        .reset_index(name="count")
    )


def _select_executable_suggestion_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = _prepare_trade_display_df(df.copy())
    if out.empty:
        return out

    status = out.get("status", pd.Series(index=out.index, dtype=object)).fillna("").astype(str).str.upper().str.strip()
    readiness = out.get("readiness", pd.Series(index=out.index, dtype=object)).fillna("").astype(str).str.upper().str.strip()
    execution_status = out.get("execution_status", pd.Series(index=out.index, dtype=object)).fillna("").astype(str).str.lower().str.strip()
    entry_status = out.get("entry_status", pd.Series(index=out.index, dtype=object)).fillna("").astype(str).str.lower().str.strip()
    entry_source = out.get("entry_source", pd.Series(index=out.index, dtype=object)).fillna("").astype(str).str.lower().str.strip()
    execution_entry_status = out.get("execution_entry_status", pd.Series(index=out.index, dtype=object)).fillna("").astype(str).str.lower().str.strip()
    execution_entry_source = out.get("execution_entry_source", pd.Series(index=out.index, dtype=object)).fillna("").astype(str).str.lower().str.strip()

    entry_value = pd.to_numeric(out.get("entry"), errors="coerce")
    execution_entry = pd.to_numeric(out.get("execution_entry"), errors="coerce")

    blocked_status = status.isin({"INVALID", "BLOCKED", "BLOCKED_CONTRACT", "BLOCKED_APPROVAL"})
    blocked_readiness = readiness.isin({"BLOCKED", "QUEUE_ONLY", "ADVISORY_ONLY"})
    blocked_execution_status = execution_status.isin({"blocked", "queue_only", "advisory_only"})
    invalid_entry_status = entry_status.isin({"", "missing", "non_executable"})
    invalid_entry_source = entry_source.isin({"last", "mark", "mid"})
    valid_execution_source = execution_entry_source.isin({"ask", "bid", "retained_prior_ask", "retained_prior_bid"})
    valid_execution_status = execution_entry_status.eq("executable")
    has_no_hard_blockers = out.get("hard_blockers", pd.Series(index=out.index, dtype=object)).apply(
        lambda value: len(value) == 0 if isinstance(value, (list, tuple, set)) else str(value or "").strip() == ""
    )

    executable_mask = (
        status.eq("READY")
        & readiness.eq("READY")
        & execution_status.eq("executable")
        & entry_value.notna()
        & execution_entry.notna()
        & valid_execution_status
        & valid_execution_source
        & (~invalid_entry_status)
        & (~invalid_entry_source)
        & (~blocked_status)
        & (~blocked_readiness)
        & (~blocked_execution_status)
        & has_no_hard_blockers
    )
    return out[executable_mask].copy()


def _select_advisory_table_source(
    *,
    show_exec_only: bool,
    top_frames: dict[str, pd.DataFrame],
    suggested_live_df: pd.DataFrame,
) -> tuple[pd.DataFrame, str]:
    if show_exec_only:
        primary = top_frames.get("top_executable", pd.DataFrame())
        if primary is not None and not primary.empty:
            return primary, "top_executable_snapshot"
        return _select_executable_suggestion_rows(suggested_live_df), "advisory_fallback_executable"
    primary = top_frames.get("top_advisory", pd.DataFrame())
    if primary is not None and not primary.empty:
        return primary, "top_advisory_snapshot"
    return _select_visible_advisory_rows(suggested_live_df), "advisory_fallback_visible"


def _simulation_display_cols(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty:
        return []
    ordered = [
        "sim_reason",
        "lot_size",
        "lot_size_source",
        "lot_fallback_used",
    ]
    ordered.extend(sorted([c for c in df.columns if str(c).startswith("sim_pnl_")]))
    return [c for c in ordered if c in df.columns]


def _queue_sources() -> list[tuple[str, Path]]:
    return [
        # Source: manual review queue file
        ("review_queue", REVIEW_QUEUE_PATH),
        # Source: quick suggestion queue file
        ("suggested_quick", QUICK_REVIEW_QUEUE_PATH),
        # Source: 20-point advisory queue file
        ("advisory_20", TARGET_POINTS_QUEUE_PATH),
        # Source: zero-to-hero advisory queue file
        ("advisory_zh", ZERO_HERO_QUEUE_PATH),
        # Source: scalp queue file
        ("suggested_scalp", SCALP_QUEUE_PATH),
    ]


def _trade_universe_sources_sig() -> tuple[tuple[str, tuple[bool, int, int]], ...]:
    sigs: list[tuple[str, tuple[bool, int, int]]] = []
    for source, path in _queue_sources():
        p = Path(path)
        sigs.append((source, file_sig(p)))
    return tuple(sigs)


def _exit_intel_state_sig() -> tuple[bool, int, int]:
    return file_sig(logs_dir() / "exit_intel_state.jsonl")


@st.cache_data(ttl=1, show_spinner=False)
def _load_exit_intel_state_df_cached(_sig: tuple[bool, int, int]) -> pd.DataFrame:
    path = logs_dir() / "exit_intel_state.jsonl"
    if not path.exists():
        return pd.DataFrame()
    rows: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = str(line).strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "trade_id" not in df.columns:
        return pd.DataFrame()
    if "ts_epoch" in df.columns:
        df["ts_epoch"] = pd.to_numeric(df["ts_epoch"], errors="coerce")
        df = df.sort_values("ts_epoch", ascending=False)
    return df.drop_duplicates(subset=["trade_id"], keep="first")


def _load_exit_intel_state_df() -> pd.DataFrame:
    return _load_exit_intel_state_df_cached(_exit_intel_state_sig())


def _merge_exit_intel_state(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    state_df = _load_exit_intel_state_df()
    if state_df is None or state_df.empty:
        return df
    merge_cols = [
        c
        for c in [
            "trade_id",
            "best_price_seen",
            "best_price_ts",
            "current_sl",
            "current_tp",
            "exit_intel_phase",
            "exit_intel_action",
            "stall_counter",
            "last_action_ts",
            "reason_codes",
            "remaining_qty_units",
        ]
        if c in state_df.columns
    ]
    if not merge_cols:
        return df
    right = state_df[merge_cols].drop_duplicates(subset=["trade_id"], keep="first")
    out = df.copy()
    if "trade_id" in out.columns:
        return out.merge(right, on="trade_id", how="left", suffixes=("", "_exit"))
    if "identity" in out.columns:
        right_identity = right.rename(columns={"trade_id": "identity"})
        return out.merge(right_identity, on="identity", how="left", suffixes=("", "_exit"))
    return out


def _concat_frames_safely(frames: list[pd.DataFrame]) -> pd.DataFrame:
    valid: list[pd.DataFrame] = []
    for frame in frames:
        if frame is None or frame.empty:
            continue
        # Skip fully-empty/NA entries that trigger pandas concat future warnings.
        if frame.dropna(how="all").empty:
            continue
        valid.append(frame)
    if not valid:
        return pd.DataFrame()
    return pd.concat(valid, axis=0, ignore_index=True)


@st.cache_data(ttl=1, show_spinner=False)
def _load_trade_universe_df_cached(_sources_sig: tuple[tuple[str, tuple[bool, int, int]], ...]) -> pd.DataFrame:
    frames = []
    meta_map = _get_instrument_meta_map()
    for source, path in _queue_sources():
        try:
            p = Path(path)
            if not p.exists():
                continue
            rows = load_queue_rows(p)
            if not rows:
                continue
            tmp = pd.DataFrame(rows)
            if tmp.empty:
                continue
            tmp["source_bucket"] = source
            tmp = normalize_trade_df(tmp, meta_map)
            if tmp is not None and not tmp.empty:
                frames.append(tmp)
        except Exception as exc:
            logger.warning("trade_universe_load_failed source=%s path=%s err=%s", source, path, exc)
    if not frames:
        return pd.DataFrame()
    merged = _concat_frames_safely(frames)
    if merged.empty:
        return merged
    merged = normalize_table_df(merged)
    merged = compute_table_trade_key(merged)
    merged = dedupe_table_df(merged)
    return _safe_sort_by_last_seen(merged)


def _load_trade_universe_df() -> pd.DataFrame:
    return _load_trade_universe_df_cached(_trade_universe_sources_sig())


def _series_first_non_null(df: pd.DataFrame, columns: list[str], default=None) -> pd.Series:
    available = [col for col in columns if col in df.columns]
    if not available:
        return pd.Series([default] * len(df), index=df.index, dtype="object")
    series = df[available].bfill(axis=1).iloc[:, 0]
    if default is not None:
        series = series.where(series.notna(), default)
    return series


def _extract_trace_field(df: pd.DataFrame, key: str) -> pd.Series:
    if "decision_trace" not in df.columns:
        return pd.Series([None] * len(df), index=df.index, dtype="object")
    return df["decision_trace"].apply(
        lambda v: v.get(key) if isinstance(v, dict) else None
    )


def _derive_permission_bucket(df: pd.DataFrame) -> pd.Series:
    permission = _series_first_non_null(df, ["permission"], default="").astype(str).str.upper().str.strip()
    final_action = _series_first_non_null(df, ["final_action"], default="").astype(str).str.upper().str.strip()
    entry_status = _series_first_non_null(df, ["entry_status"], default="").astype(str).str.upper().str.strip()
    global_conf = pd.to_numeric(
        _series_first_non_null(df, ["global_conf", "global_confidence", "confidence"]),
        errors="coerce",
    )
    high_threshold = float(getattr(cfg, "HIGH_EXECUTE_MIN_CONF", 0.65))

    bucket = pd.Series("ADVISORY", index=df.index, dtype="object")
    queue_mask = permission.str.startswith("QUEUE")
    exec_mask = permission.isin(["EXECUTE", "HIGH_EXECUTE"]) | final_action.eq("EXECUTE")
    high_mask = exec_mask & (
        global_conf >= high_threshold
    ) & (~entry_status.isin(["STALE_OPTION_LTP", "STALE_PRICE", "INVALID_LTP", "NO_TOKEN", "MISSING_OPTION_TOKEN"]))

    bucket.loc[queue_mask] = "QUEUE"
    bucket.loc[exec_mask] = "EXECUTE"
    bucket.loc[high_mask] = "HIGH_EXECUTE"
    return bucket


def _derive_final_blocker(df: pd.DataFrame) -> pd.Series:
    blocker = _series_first_non_null(
        df,
        [
            "final_blocker",
            "entry_block_reason",
            "permission_reason",
            "hard_reject_reason",
            "reject_reason",
        ],
    )
    blocker = blocker.fillna("NONE").astype(str).str.strip()
    blocker = blocker.where(blocker.ne(""), "NONE")
    return blocker


def _derive_feed_state(df: pd.DataFrame) -> pd.Series:
    base = _series_first_non_null(df, ["feed_state"])
    from_snapshot = pd.Series([None] * len(df), index=df.index, dtype="object")
    if "feed_health_snapshot" in df.columns:
        from_snapshot = df["feed_health_snapshot"].apply(
            lambda v: v.get("state") if isinstance(v, dict) else None
        )
    out = base.where(base.notna(), from_snapshot)
    out = out.fillna("UNKNOWN").astype(str).str.upper()
    return out.where(out.ne(""), "UNKNOWN")


def _derive_trade_explorer_fields(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    symbol = _series_first_non_null(work, ["symbol"], default="").astype(str)
    tradingsymbol = _series_first_non_null(work, ["tradingsymbol"], default="").astype(str)
    strategy_hint = _series_first_non_null(
        work,
        ["strategy_family", "strategy_id", "strategy", "generator", "source_bucket"],
        default="UNKNOWN",
    )
    option_type = _series_first_non_null(work, ["option_type", "type"], default="")
    option_type_norm = option_type.astype(str).str.upper()
    option_type_norm = option_type_norm.replace({"CALL": "CE", "PUT": "PE"})
    option_side = option_type_norm.where(option_type_norm.isin(["CE", "PE"]), "UNKNOWN")
    option_side = option_side.where(
        option_side.isin(["CE", "PE"]),
        tradingsymbol.map(parse_option_side),
    )
    option_side = option_side.where(
        option_side.isin(["CE", "PE"]),
        symbol.map(parse_option_side),
    )
    option_side = option_side.fillna("UNKNOWN").astype(str).str.upper()
    option_side = option_side.where(option_side.isin(["CE", "PE"]), "UNKNOWN")

    underlying = symbol.map(parse_underlying)
    underlying = underlying.where(
        underlying.ne("UNKNOWN"),
        tradingsymbol.map(parse_underlying),
    ).fillna("UNKNOWN")

    strategy_family = strategy_hint.fillna("UNKNOWN").astype(str).str.strip().str.upper()
    strategy_family = strategy_family.where(strategy_family.ne(""), "UNKNOWN")
    strategy_category = strategy_family.map(map_strategy_category).fillna("UNKNOWN")

    global_conf = pd.to_numeric(
        _series_first_non_null(work, ["global_conf", "global_confidence", "confidence"]),
        errors="coerce",
    )
    spread_pct = pd.to_numeric(_series_first_non_null(work, ["spread_pct"]), errors="coerce")
    quote_age_sec = pd.to_numeric(_series_first_non_null(work, ["quote_age_sec", "price_age_sec"]), errors="coerce")
    signal_score = pd.to_numeric(
        _series_first_non_null(work, ["signal_score"], default=None).where(
            _series_first_non_null(work, ["signal_score"]).notna(),
            _extract_trace_field(work, "signal_score"),
        ),
        errors="coerce",
    )
    regime_conf = pd.to_numeric(
        _series_first_non_null(work, ["regime_conf"], default=None).where(
            _series_first_non_null(work, ["regime_conf"]).notna(),
            _extract_trace_field(work, "regime_conf"),
        ),
        errors="coerce",
    )
    orb_bias = _series_first_non_null(work, ["orb_bias"]).where(
        _series_first_non_null(work, ["orb_bias"]).notna(),
        _extract_trace_field(work, "orb_bias"),
    )
    orb_factor = pd.to_numeric(
        _series_first_non_null(work, ["orb_factor"]).where(
            _series_first_non_null(work, ["orb_factor"]).notna(),
            _extract_trace_field(work, "orb_factor"),
        ),
        errors="coerce",
    )
    reg_penalty = pd.to_numeric(
        _series_first_non_null(work, ["reg_penalty"]).where(
            _series_first_non_null(work, ["reg_penalty"]).notna(),
            _extract_trace_field(work, "reg_penalty"),
        ),
        errors="coerce",
    )

    final_action = _series_first_non_null(work, ["final_action"])
    final_action = final_action.fillna("").astype(str).str.upper().str.strip()

    entry_block_reason = _series_first_non_null(work, ["entry_block_reason"])
    permission_reason = _series_first_non_null(work, ["permission_reason"])
    entry_status = _series_first_non_null(work, ["entry_status"])
    permission = _series_first_non_null(work, ["permission"])

    ts_source = _series_first_non_null(
        work,
        ["last_seen_ts", "timestamp_utc_iso", "timestamp", "ts_ist", "ts_utc", "first_seen"],
        default=None,
    )
    ts_series = pd.to_datetime(ts_source, errors="coerce", utc=True)
    if "timestamp_epoch_ms" in work.columns:
        ts_epoch_ms = pd.to_numeric(work["timestamp_epoch_ms"], errors="coerce")
        ts_from_ms = pd.to_datetime(ts_epoch_ms / 1000.0, unit="s", errors="coerce", utc=True)
        ts_series = ts_series.where(ts_series.notna(), ts_from_ms)
    trade_date = ts_series.dt.tz_convert("Asia/Kolkata").dt.date.astype(str)
    trade_date = trade_date.where(trade_date.ne("NaT"), "UNKNOWN")

    run_id = _series_first_non_null(work, ["run_id"], default="UNKNOWN").astype(str)
    run_id = run_id.where(run_id.str.strip().ne(""), "UNKNOWN")

    work["underlying"] = underlying
    work["option_side"] = option_side
    work["strategy_family"] = strategy_family
    work["strategy_category"] = strategy_category
    work["global_conf"] = global_conf
    work["spread_pct"] = spread_pct
    work["quote_age_sec"] = quote_age_sec
    work["signal_score"] = signal_score
    work["regime_conf"] = regime_conf
    work["orb_bias"] = orb_bias
    work["orb_factor"] = orb_factor
    work["reg_penalty"] = reg_penalty
    work["permission"] = permission
    work["permission_reason"] = permission_reason
    work["entry_status"] = entry_status
    work["entry_block_reason"] = entry_block_reason
    work["final_action"] = final_action
    work["permission_bucket"] = _derive_permission_bucket(work)
    work["final_blocker"] = _derive_final_blocker(work)
    work["feed_state"] = _derive_feed_state(work)
    work["trade_date"] = trade_date
    work["run_id"] = run_id
    work["ts_sort"] = ts_series
    return work


def _apply_trade_explorer_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if filters.get("dates"):
        out = out[out["trade_date"].isin(filters["dates"])]
    if filters.get("run_ids"):
        out = out[out["run_id"].isin(filters["run_ids"])]
    for col, key in (
        ("underlying", "underlyings"),
        ("option_side", "option_sides"),
        ("strategy_category", "strategy_categories"),
        ("strategy_family", "strategy_families"),
        ("permission_bucket", "permission_buckets"),
        ("final_blocker", "final_blockers"),
        ("feed_state", "feed_states"),
    ):
        vals = filters.get(key) or []
        if vals:
            out = out[out[col].isin(vals)]
    text_query = str(filters.get("symbol_query") or "").strip().upper()
    if text_query:
        sym = out.get("symbol", pd.Series([""] * len(out), index=out.index)).fillna("").astype(str).str.upper()
        ts = out.get("tradingsymbol", pd.Series([""] * len(out), index=out.index)).fillna("").astype(str).str.upper()
        out = out[sym.str.contains(text_query, regex=False) | ts.str.contains(text_query, regex=False)]

    for col, range_key in (
        ("global_conf", "global_conf_range"),
        ("spread_pct", "spread_pct_range"),
        ("quote_age_sec", "quote_age_sec_range"),
    ):
        rng = filters.get(range_key)
        if not rng:
            continue
        series = pd.to_numeric(out.get(col), errors="coerce")
        out = out[(series >= float(rng[0])) & (series <= float(rng[1]))]
    return out


def _numeric_slider_config(df: pd.DataFrame, column: str) -> tuple[float, float] | None:
    if column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    if values.empty:
        return None
    lo = float(values.min())
    hi = float(values.max())
    if lo > hi:
        return None
    return (lo, hi)


def _render_trade_explorer_panel(
    trade_universe_df: pd.DataFrame,
    trade_explorer_filters: dict | None = None,
):
    section_header("Trade Explorer")
    if trade_universe_df is None or trade_universe_df.empty:
        empty_state("No rows available for explorer.")
        return
    explorer_df = _derive_trade_explorer_fields(trade_universe_df)
    if explorer_df.empty:
        empty_state("No rows available for explorer.")
        return
    filters = dict(trade_explorer_filters or {})
    filtered = _apply_trade_explorer_filters(explorer_df, filters)
    filtered = filtered.sort_values("ts_sort", ascending=False, na_position="last")

    high_mask = filtered["permission_bucket"].astype(str).eq("HIGH_EXECUTE")
    final_action = filtered["final_action"].fillna("").astype(str).str.upper()
    total_rows = int(len(filtered))
    high_count = int(high_mask.sum())
    executed_count = int(final_action.eq("EXECUTE").sum())
    demoted_count = int((high_mask & (~final_action.eq("EXECUTE"))).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Rows", total_rows)
    c2.metric("HIGH_EXECUTE", high_count)
    c3.metric("Executed", executed_count)
    c4.metric("Demoted", demoted_count)

    if filtered.empty:
        empty_state("No rows match current explorer filters.")
        return

    default_cols = [
        "timestamp",
        "tradingsymbol",
        "symbol",
        "underlying",
        "expiry_date",
        "strike",
        "option_type",
        "option_side",
        "entry",
        "execution_entry",
        "stop",
        "stop_loss",
        "target",
        "best_bid",
        "best_ask",
        "current_ltp",
        "quote_age_sec",
        "strategy_family",
        "permission_bucket",
        "final_action",
        "final_blocker",
        "entry_status",
        "execution_entry_status",
        "global_conf",
        "rank_score",
        "confidence",
        "feed_state",
    ]
    alias_pairs = {
        "tradingsymbol": ["trading_symbol", "instrument_name", "contract"],
        "expiry_date": ["expiry"],
        "option_type": ["opt_type", "right"],
        "entry": ["entry_price", "execution_entry"],
        "stop": ["stop_loss", "sl"],
        "target": ["take_profit", "tp"],
    }
    for canonical, aliases in alias_pairs.items():
        if canonical not in filtered.columns:
            for alias in aliases:
                if alias in filtered.columns:
                    filtered[canonical] = filtered[alias]
                    break
    display_cols = [col for col in default_cols if col in filtered.columns]
    if not display_cols:
        display_cols = list(filtered.columns[:25])
    display_df = filtered[display_cols].head(500).copy()
    st.caption(f"Filtered rows: {len(filtered)} (showing top {len(display_df)} by latest timestamp)")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if bool(filters.get("show_charts", True)):
        try:
            import matplotlib.pyplot as plt

            fam = filtered["strategy_family"].fillna("UNKNOWN").astype(str).value_counts().head(12)
            blocker = filtered["final_blocker"].fillna("NONE").astype(str).value_counts().head(12)
            cc1, cc2 = st.columns(2)
            with cc1:
                fig1, ax1 = plt.subplots(figsize=(6, 3))
                fam.sort_values(ascending=False).plot(kind="bar", ax=ax1)
                ax1.set_title("Count by Strategy Family")
                ax1.set_xlabel("strategy_family")
                ax1.set_ylabel("count")
                plt.xticks(rotation=45, ha="right")
                st.pyplot(fig1, clear_figure=True)
            with cc2:
                fig2, ax2 = plt.subplots(figsize=(6, 3))
                blocker.sort_values(ascending=False).plot(kind="bar", ax=ax2)
                ax2.set_title("Count by Final Blocker")
                ax2.set_xlabel("final_blocker")
                ax2.set_ylabel("count")
                plt.xticks(rotation=45, ha="right")
                st.pyplot(fig2, clear_figure=True)
        except Exception as exc:
            logger.warning("trade_explorer_charts_failed: %s", exc)


def _timeline_window_bounds(
    window_mode: str,
    last_n_min: int,
    custom_start_local: datetime | None,
    custom_end_local: datetime | None,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    now_local = pd.Timestamp.now(tz="Asia/Kolkata")
    mode = str(window_mode or "Today").strip()
    if mode == "Today":
        start_local = now_local.normalize()
        end_local = now_local
    elif mode == "Last N minutes":
        minutes = max(1, int(last_n_min or 60))
        start_local = now_local - pd.Timedelta(minutes=minutes)
        end_local = now_local
    else:
        if custom_start_local is None or custom_end_local is None:
            return None, None
        start_local = pd.Timestamp(custom_start_local)
        end_local = pd.Timestamp(custom_end_local)
        if start_local.tzinfo is None:
            start_local = start_local.tz_localize("Asia/Kolkata")
        else:
            start_local = start_local.tz_convert("Asia/Kolkata")
        if end_local.tzinfo is None:
            end_local = end_local.tz_localize("Asia/Kolkata")
        else:
            end_local = end_local.tz_convert("Asia/Kolkata")
    start_utc = start_local.tz_convert("UTC")
    end_utc = end_local.tz_convert("UTC")
    if end_utc < start_utc:
        start_utc, end_utc = end_utc, start_utc
    return start_utc, end_utc


def _filter_df_time_window(
    df: pd.DataFrame,
    start_utc: pd.Timestamp | None,
    end_utc: pd.Timestamp | None,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if "ts_sort" not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    ts = pd.to_datetime(out["ts_sort"], utc=True, errors="coerce")
    mask = ts.notna()
    if start_utc is not None:
        mask = mask & (ts >= start_utc)
    if end_utc is not None:
        mask = mask & (ts <= end_utc)
    out = out[mask].copy()
    out["ts_sort"] = ts[mask]
    return out


@st.cache_data(ttl=20, show_spinner=False)
def _compute_strategy_timeline_cached(
    timeline_df: pd.DataFrame,
    bucket_size: str,
    start_epoch_ms: int | None,
    end_epoch_ms: int | None,
) -> pd.DataFrame:
    if timeline_df is None or timeline_df.empty:
        return pd.DataFrame()
    work = timeline_df.copy()
    if "ts_sort" not in work.columns:
        return pd.DataFrame()
    work["ts_sort"] = pd.to_datetime(work["ts_sort"], utc=True, errors="coerce")
    work = work[work["ts_sort"].notna()].copy()
    if work.empty:
        return pd.DataFrame()
    if start_epoch_ms is not None:
        start = pd.Timestamp(float(start_epoch_ms) / 1000.0, unit="s", tz="UTC")
        work = work[work["ts_sort"] >= start]
    if end_epoch_ms is not None:
        end = pd.Timestamp(float(end_epoch_ms) / 1000.0, unit="s", tz="UTC")
        work = work[work["ts_sort"] <= end]
    if work.empty:
        return pd.DataFrame()
    out = compute_strategy_timeline_metrics(work, bucket_size=bucket_size, ts_col="ts_sort")
    if out is None or out.empty:
        return pd.DataFrame()
    out["time_bucket_local"] = pd.to_datetime(out["time_bucket"], utc=True, errors="coerce").dt.tz_convert("Asia/Kolkata")
    out["time_bucket_label"] = out["time_bucket_local"].dt.strftime("%Y-%m-%d %H:%M")
    return out


def _render_strategy_timeline_tab():
    section_header("Strategy Timeline")
    base_df = _derive_trade_explorer_fields(_load_trade_universe_df())
    if base_df is None or base_df.empty:
        empty_state("No strategy timeline data available.")
        return

    controls_a, controls_b, controls_c, controls_d = st.columns(4)
    bucket_size = controls_a.selectbox("Bucket Size", ["1m", "5m", "15m"], index=1, key="timeline_bucket_size")
    window_mode = controls_b.selectbox(
        "Time Window",
        ["Today", "Last N minutes", "Custom start-end"],
        index=0,
        key="timeline_window_mode",
    )
    metric = controls_c.selectbox(
        "Metric",
        ["candidates", "high_execute", "executed", "demoted_rate", "execution_rate"],
        index=0,
        key="timeline_metric_selector",
    )
    if window_mode == "Last N minutes":
        last_n = int(controls_d.number_input("Last N minutes", min_value=1, max_value=1440, value=120, step=5, key="timeline_last_n"))
        start_utc, end_utc = _timeline_window_bounds(window_mode, last_n, None, None)
    elif window_mode == "Custom start-end":
        now_local = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
        start_col, end_col = st.columns(2)
        start_date = start_col.date_input("Start date", value=now_local.date(), key="timeline_custom_start_date")
        start_time = start_col.time_input("Start time", value=now_local.time().replace(second=0, microsecond=0), key="timeline_custom_start_time")
        end_date = end_col.date_input("End date", value=now_local.date(), key="timeline_custom_end_date")
        end_time = end_col.time_input("End time", value=now_local.time().replace(second=0, microsecond=0), key="timeline_custom_end_time")
        start_local = datetime.combine(start_date, start_time).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        end_local = datetime.combine(end_date, end_time).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        start_utc, end_utc = _timeline_window_bounds(window_mode, 0, start_local, end_local)
    else:
        start_utc, end_utc = _timeline_window_bounds(window_mode, 0, None, None)

    start_ms = int(start_utc.timestamp() * 1000.0) if start_utc is not None else None
    end_ms = int(end_utc.timestamp() * 1000.0) if end_utc is not None else None
    timeline_source = base_df[
        [
            c
            for c in [
                "ts_sort",
                "strategy_family",
                "permission_bucket",
                "final_action",
                "final_blocker",
                "outcome",
                "symbol",
                "trade_key",
                "entry_status",
                "permission_reason",
                "entry_block_reason",
                "global_conf",
                "signal_score",
                "regime_conf",
                "orb_bias",
                "orb_factor",
                "reg_penalty",
                "feed_state",
                "quote_age_sec",
                "spread_pct",
                "underlying",
                "option_side",
                "run_id",
                "source_bucket",
            ]
            if c in base_df.columns
        ]
    ].copy()
    agg_df = _compute_strategy_timeline_cached(timeline_source, bucket_size, start_ms, end_ms)
    if agg_df is None or agg_df.empty:
        empty_state("No timeline rows in selected window.")
        return

    scoreboard_cols = [
        col
        for col in [
            "time_bucket_label",
            "strategy_family",
            "candidates",
            "high_execute",
            "executed",
            "demoted",
            "demoted_rate",
            "execution_rate",
            "top_blocker",
            "missed_winners",
        ]
        if col in agg_df.columns
    ]
    st.caption("Aggregated scoreboard by time bucket and strategy family.")
    st.dataframe(
        agg_df[scoreboard_cols].sort_values(["time_bucket_label", "strategy_family"], ascending=[True, True]),
        use_container_width=True,
        hide_index=True,
    )

    pivot = agg_df.pivot_table(
        index="time_bucket_label",
        columns="strategy_family",
        values=metric,
        aggfunc="sum",
        fill_value=0.0,
    ).sort_index()
    st.markdown("**Pivot (time bucket x strategy family)**")
    st.dataframe(pivot, use_container_width=True)

    bucket_view = agg_df[["time_bucket", "time_bucket_label"]].drop_duplicates().sort_values("time_bucket", ascending=True)
    bucket_labels = bucket_view["time_bucket_label"].tolist()
    if not bucket_labels:
        empty_state("No timeline buckets available.")
        return
    selected_bucket_label = st.selectbox(
        "Bar Chart Bucket",
        options=bucket_labels,
        index=len(bucket_labels) - 1,
        key="timeline_selected_bucket",
    )
    selected_bucket_ts = bucket_view.loc[
        bucket_view["time_bucket_label"] == selected_bucket_label, "time_bucket"
    ].iloc[0]
    bucket_slice = agg_df[agg_df["time_bucket"] == selected_bucket_ts].copy()
    bar_series = bucket_slice.set_index("strategy_family")["candidates"].sort_values(ascending=False)
    st.markdown("**Counts by strategy family (selected bucket)**")
    st.bar_chart(bar_series)

    st.markdown("**Drill-down**")
    strategy_options = sorted(bucket_slice["strategy_family"].dropna().astype(str).unique().tolist())
    selected_strategy = st.selectbox(
        "Strategy Family",
        options=strategy_options,
        key="timeline_selected_strategy_family",
    )
    window_df = _filter_df_time_window(base_df, start_utc, end_utc)
    window_df = window_df.copy()
    window_df["_time_bucket"] = window_df["ts_sort"].apply(lambda v: floor_timestamp_to_bucket(v, bucket_size))
    drill_df = window_df[
        (window_df["_time_bucket"] == selected_bucket_ts)
        & (window_df["strategy_family"].astype(str) == str(selected_strategy))
    ].copy()
    drill_df = drill_df.sort_values("ts_sort", ascending=False)
    preset_cols = [c for c in EXPLORER_COLUMN_PRESETS["Strategy+Execution"] if c in drill_df.columns]
    st.caption(f"Drill-down rows: {len(drill_df)} (showing top {min(len(drill_df), 500)})")
    if drill_df.empty:
        empty_state("No rows for selected bucket + strategy family.")
    else:
        st.dataframe(drill_df[preset_cols].head(500), use_container_width=True, hide_index=True)
        blocker_dist = build_blocker_distribution(drill_df, blocker_col="final_blocker")
        st.markdown("**Blocker distribution (drill-down subset)**")
        st.dataframe(blocker_dist, use_container_width=True, hide_index=True)


def filter_trades_for_panel(trades, panel_name: str) -> pd.DataFrame:
    """
    Strict, unit-testable panel filter contract.
    - active: status == ACTIVE
    - suggested: status in {PLANNING, PROPOSED}
    - review: status == QUEUED_REVIEW
    """
    panel = str(panel_name or "").strip().lower()
    allowed = {
        "active": {"ACTIVE"},
        "suggested": {"PLANNING", "PROPOSED", "ADVISORY_ONLY", "READY"},
        "review": {"QUEUED_REVIEW", "BLOCKED_APPROVAL", "BLOCKED_CONTRACT"},
    }.get(panel)
    if allowed is None:
        raise ValueError(f"unsupported panel_name={panel_name!r}")

    if trades is None:
        return pd.DataFrame()
    if isinstance(trades, pd.DataFrame):
        df = trades.copy()
    else:
        rows = list(trades or [])
        df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "status" not in df.columns:
        df["status"] = "PLANNING"
    status = df["status"].astype(str).str.upper().str.strip()
    return df[status.isin(allowed)].copy()


def _partition_trade_universe(df_all: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if df_all is None or df_all.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty
    active = filter_trades_for_panel(df_all, "active")
    review = filter_trades_for_panel(df_all, "review")
    planning = filter_trades_for_panel(df_all, "suggested")

    review_source = review.get("source_bucket", pd.Series([""] * len(review), index=review.index)).astype(str)
    review = review[review_source == "review_queue"].copy()

    planning_source = planning.get("source_bucket", pd.Series([""] * len(planning), index=planning.index)).astype(str)
    advisory = planning[planning_source.str.startswith("advisory_")].copy()
    suggested = planning[planning_source.str.startswith("suggested_")].copy()
    if suggested.empty:
        suggested = planning[~planning_source.str.startswith("advisory_")].copy()
    return (
        _safe_sort_by_last_seen(active),
        _safe_sort_by_last_seen(review),
        _safe_sort_by_last_seen(suggested),
        _safe_sort_by_last_seen(advisory),
    )


def _with_active_runtime_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in ("mark_price", "bid", "ask", "ltp", "pnl_unrealized"):
        if col not in out.columns:
            out[col] = None
    if "opt_bid" in out.columns:
        out["bid"] = out["bid"].where(out["bid"].notna(), out["opt_bid"])
    if "opt_ask" in out.columns:
        out["ask"] = out["ask"].where(out["ask"].notna(), out["opt_ask"])
    if "live_ltp" in out.columns:
        out["ltp"] = out["ltp"].where(out["ltp"].notna(), out["live_ltp"])
    if "opt_ltp" in out.columns:
        out["ltp"] = out["ltp"].where(out["ltp"].notna(), out["opt_ltp"])
    if "current_ltp" in out.columns:
        out["ltp"] = out["ltp"].where(out["ltp"].notna(), out["current_ltp"])
    mid = (pd.to_numeric(out.get("bid"), errors="coerce") + pd.to_numeric(out.get("ask"), errors="coerce")) / 2.0
    out["mark_price"] = out["mark_price"].where(pd.to_numeric(out["mark_price"], errors="coerce").notna(), mid)
    out["mark_price"] = out["mark_price"].where(pd.to_numeric(out["mark_price"], errors="coerce").notna(), out["ltp"])
    if "pnl_cash" in out.columns:
        out["pnl_unrealized"] = out["pnl_unrealized"].where(
            pd.to_numeric(out["pnl_unrealized"], errors="coerce").notna(),
            out["pnl_cash"],
        )
    if "pnl_1lot" in out.columns:
        out["pnl_unrealized"] = out["pnl_unrealized"].where(
            pd.to_numeric(out["pnl_unrealized"], errors="coerce").notna(),
            out["pnl_1lot"],
        )
    return out


def _is_nullish(value) -> bool:
    try:
        return value is None or bool(pd.isna(value))
    except Exception:
        return value is None


def _first_non_null(*values):
    for value in values:
        if not _is_nullish(value):
            return value
    return None


def _extract_quote_from_trade_row(trade_row: dict | pd.Series | None) -> dict | None:
    row = dict(trade_row or {})
    quote = {
        "ltp": _first_non_null(row.get("opt_ltp"), row.get("ltp"), row.get("live_ltp"), row.get("current_ltp")),
        "bid": _first_non_null(row.get("opt_bid"), row.get("bid")),
        "ask": _first_non_null(row.get("opt_ask"), row.get("ask")),
        "mark_price": _first_non_null(row.get("mark_price")),
        "quote_age_sec": _first_non_null(row.get("quote_age_sec")),
        "spread_pct": _first_non_null(row.get("spread_pct")),
    }
    has_quote = any(not _is_nullish(quote.get(col)) for col in ("ltp", "bid", "ask", "mark_price", "quote_age_sec"))
    return quote if has_quote else None


def build_display_row(trade, quote):
    row = dict(trade or {})
    quote_data = dict(quote or {})
    out = dict(row)
    out["ltp"] = _first_non_null(quote_data.get("ltp"))
    out["bid"] = _first_non_null(quote_data.get("bid"))
    out["ask"] = _first_non_null(quote_data.get("ask"))
    out["mark_price"] = _first_non_null(quote_data.get("mark_price"))
    out["quote_age_sec"] = _first_non_null(quote_data.get("quote_age_sec"))
    spread_pct = _safe_float(_first_non_null(quote_data.get("spread_pct")))
    if _is_nullish(out["mark_price"]):
        out["mark_price"], _ = _derive_mark_price(
            out.get("ltp"),
            out.get("bid"),
            out.get("ask"),
            out.get("quote_age_sec"),
        )
    if spread_pct is None:
        bid_val = _safe_float(out.get("bid"))
        ask_val = _safe_float(out.get("ask"))
        base_val = _safe_float(out.get("mark_price"))
        if base_val in (None, 0.0):
            base_val = _safe_float(out.get("ltp"))
        if bid_val is not None and ask_val is not None and base_val not in (None, 0.0):
            spread_pct = (ask_val - bid_val) / base_val
    out["spread_pct"] = spread_pct
    for col in EXECUTABLE_PRICING_COLS:
        if col not in out:
            out[col] = None
    return out


def _apply_executable_pricing(df: pd.DataFrame, chain_map: dict | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    work = df.copy()
    try:
        priced = _hydrate_option_quotes(work.copy(), chain_map if chain_map is not None else _get_chain_map())
        if priced is not None and not priced.empty:
            work = priced
    except Exception as exc:
        logger.warning("pricing_adapter_hydrate_failed: %s", exc)
    for col in EXECUTABLE_PRICING_COLS:
        if col not in work.columns:
            work[col] = None
    for idx, trade in work.iterrows():
        enriched = build_display_row(trade.to_dict(), _extract_quote_from_trade_row(trade))
        for col in EXECUTABLE_PRICING_COLS:
            work.at[idx, col] = enriched.get(col)
    return work


def _inject_executable_pricing_cols(display_cols: list[str]) -> list[str]:
    if not display_cols:
        return []
    ordered = [c for c in display_cols if c not in EXECUTABLE_PRICING_COLS]
    if "stop" in ordered:
        insert_at = ordered.index("stop") + 1
    elif "confidence" in ordered:
        insert_at = ordered.index("confidence")
    else:
        insert_at = len(ordered)
    for col in EXECUTABLE_PRICING_COLS:
        ordered.insert(insert_at, col)
        insert_at += 1
    deduped = []
    for col in ordered:
        if col not in deduped:
            deduped.append(col)
    return deduped


def _normalize_option_type(value) -> str:
    text = str(value or "").strip().upper()
    if text in {"CE", "CALL", "C"}:
        return "CE"
    if text in {"PE", "PUT", "P"}:
        return "PE"
    return text


def _format_trade_strike(value) -> str:
    strike = _safe_float(value)
    if strike is None:
        return ""
    if float(strike).is_integer():
        return str(int(strike))
    return f"{strike:g}"


def _coerce_epoch_ms(value) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, pd.Timestamp):
            ts = value
            if ts.tzinfo is None:
                ts = ts.tz_localize(timezone.utc)
            else:
                ts = ts.tz_convert(timezone.utc)
            return int(ts.timestamp() * 1000.0)
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return int(dt.timestamp() * 1000.0)
        if isinstance(value, (int, float)):
            val = float(value)
            if val <= 0:
                return None
            if val >= 10_000_000_000:
                return int(val)
            return int(val * 1000.0)
        text = str(value).strip()
        if not text:
            return None
        try:
            return _coerce_epoch_ms(float(text))
        except Exception:
            pass
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        ts = pd.to_datetime(text, errors="coerce", utc=True)
        if pd.isna(ts):
            return None
        return int(ts.timestamp() * 1000.0)
    except Exception:
        return None


def _infer_underlying_symbol(trade) -> str | None:
    row = dict(trade or {})
    haystack = " ".join(
        [
            str(row.get("symbol") or ""),
            str(row.get("tradingsymbol") or ""),
            str(row.get("instrument_id") or ""),
            str(row.get("trade_id") or ""),
        ]
    ).upper()
    if "BANKNIFTY" in haystack or "NIFTY BANK" in haystack:
        return "BANKNIFTY"
    if "SENSEX" in haystack:
        return "SENSEX"
    if "NIFTY" in haystack:
        return "NIFTY"
    return None


def _stable_trade_key(trade) -> str:
    row = dict(trade or {})
    symbol = str(_infer_underlying_symbol(row) or row.get("symbol") or "").upper().strip()
    expiry = str(row.get("expiry_date") or row.get("expiry") or "").strip()
    strike = _format_trade_strike(row.get("strike"))
    opt_type = _normalize_option_type(row.get("opt_type") or row.get("type"))
    side = str(row.get("side") or "").upper().strip()
    return "|".join([symbol, expiry, strike, opt_type, side])


MICRO_TRAIN_STATUS_RUNNING = "RUNNING"
MICRO_TRAIN_STATUS_FAILED = "FAILED"
MICRO_TRAIN_STATUS_SUCCESS = "SUCCESS"


def _micro_training_paths() -> dict[str, Path]:
    model_path_raw = str(getattr(cfg, "MICRO_MODEL_PATH", "models/microstructure_model.h5") or "").strip()
    model_path = Path(model_path_raw) if model_path_raw else Path("models/microstructure_model.h5")
    return {
        "log": _log_path("train_micro.log"),
        "pid": _log_path("train_micro.pid"),
        "lock": _log_path("train_micro.lock"),
        "status": _log_path("train_micro.status.json"),
        "model_artifact": model_path,
        "feature_importance": _log_path("micro_feature_importance.csv"),
    }


def _legacy_micro_training_paths() -> dict[str, Path]:
    legacy_logs = ROOT / "logs"
    return {
        "log": legacy_logs / "train_micro.log",
        "status": legacy_logs / "train_micro.status.json",
    }


def _read_pid(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        pid = int(raw)
        return pid if pid > 0 else None
    except Exception:
        return None


def _is_pid_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    # Reap completed child processes to avoid zombie PIDs being treated as "running".
    if hasattr(os, "waitpid"):
        try:
            waited_pid, _ = os.waitpid(pid, os.WNOHANG)
            if int(waited_pid or 0) == int(pid):
                return False
        except ChildProcessError:
            # Not a child of this process (or already reaped); fall back to kill(0).
            pass
        except Exception:
            pass
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload or {}), indent=2, sort_keys=True), encoding="utf-8")


def _append_log_line(path: Path, line: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(str(line).rstrip() + "\n")
    except Exception:
        pass


def _compute_decision_debug_metrics(
    trade_universe_df: pd.DataFrame,
    advisory_df: pd.DataFrame,
    decision_gate: dict | None,
) -> dict:
    gate = dict(decision_gate or {})
    rows = gate.get("rows") if isinstance(gate.get("rows"), dict) else {}
    allowed_symbols = gate.get("allowed_symbols") if isinstance(gate.get("allowed_symbols"), list) else []

    candidates_generated = int(len(trade_universe_df.index)) if isinstance(trade_universe_df, pd.DataFrame) else 0
    advisory_rows = int(len(advisory_df.index)) if isinstance(advisory_df, pd.DataFrame) else 0

    try:
        decisions_generated = int(gate.get("evaluations_last_window") or 0)
    except Exception:
        decisions_generated = 0
    if decisions_generated <= 0 and rows:
        decisions_generated = int(len(rows))

    try:
        decisions_passed = int(gate.get("decisions_last_window") or 0)
    except Exception:
        decisions_passed = 0
    if decisions_passed <= 0:
        if allowed_symbols:
            decisions_passed = int(len(allowed_symbols))
        elif rows:
            decisions_passed = int(sum(1 for row in rows.values() if bool((row or {}).get("gate_allowed"))))

    window_60s = 60.0
    window_15m = 900.0
    now_epoch = float(time.time())
    # Use 5-second buckets to keep cache hit-rate high while preserving near-live behavior.
    now_bucket = int(now_epoch // 5)
    decisions_path = _desk_log_path("decisions.jsonl")
    candidates_path = _desk_log_path("candidates.jsonl")
    decision_events_60s = _iter_recent_events_cached(
        str(decisions_path),
        file_sig(decisions_path),
        now_bucket,
        window_60s,
        ("decision_evaluated", "decision_allowed", "decision_blocked"),
        _FULL_JSONL_TAIL_ROWS,
    )
    decision_events_15m = _iter_recent_events_cached(
        str(decisions_path),
        file_sig(decisions_path),
        now_bucket,
        window_15m,
        ("decision_blocked",),
        _FULL_JSONL_TAIL_ROWS,
    )
    candidate_events_60s = _iter_recent_events_cached(
        str(candidates_path),
        file_sig(candidates_path),
        now_bucket,
        window_60s,
        ("candidate_seen",),
        _FULL_JSONL_TAIL_ROWS,
    )

    eval_per_min = int(sum(1 for row in decision_events_60s if str(row.get("event_type") or "") == "decision_evaluated"))
    allowed_per_min = int(sum(1 for row in decision_events_60s if str(row.get("event_type") or "") == "decision_allowed"))
    candidates_per_min = int(len(candidate_events_60s))

    blocker_counts: dict[str, int] = {}
    for row in decision_events_15m:
        blockers = row.get("blockers")
        if not isinstance(blockers, list):
            blockers = []
        for reason in blockers:
            text = str(reason or "").strip()
            if not text:
                continue
            blocker_counts[text] = int(blocker_counts.get(text, 0)) + 1
    top_blockers_15m = sorted(blocker_counts.items(), key=lambda item: (-item[1], item[0]))[:5]

    return {
        "candidates_generated": max(0, candidates_generated),
        "decisions_generated": max(0, decisions_generated),
        "decisions_passed": max(0, decisions_passed),
        "advisory_rows": max(0, advisory_rows),
        "candidates_per_min": max(0, candidates_per_min),
        "evaluations_per_min": max(0, eval_per_min),
        "allowed_per_min": max(0, allowed_per_min),
        "top_blockers_15m": top_blockers_15m,
    }


def _should_emit_decision_debug_log(last_emit_ts: float, now_ts: float, interval_sec: float = 30.0) -> bool:
    try:
        now_val = float(now_ts)
    except Exception:
        return False
    try:
        last_val = float(last_emit_ts)
    except Exception:
        last_val = 0.0
    try:
        interval_val = max(1.0, float(interval_sec))
    except Exception:
        interval_val = 30.0
    if last_val <= 0.0:
        return True
    return (now_val - last_val) >= interval_val


def _log_decision_debug_metrics(metrics: dict, *, interval_sec: float = 30.0) -> None:
    now_ts = time.time()
    last_ts = float(st.session_state.get("decision_debug_metrics_last_log_ts", 0.0) or 0.0)
    if not _should_emit_decision_debug_log(last_ts, now_ts, interval_sec=interval_sec):
        return
    payload = {
        "ts_epoch": float(now_ts),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "event": "DASHBOARD_DECISION_DEBUG_METRICS",
        "desk_id": str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT"),
        "candidates_generated": int(metrics.get("candidates_generated") or 0),
        "decisions_generated": int(metrics.get("decisions_generated") or 0),
        "decisions_passed": int(metrics.get("decisions_passed") or 0),
        "advisory_rows": int(metrics.get("advisory_rows") or 0),
    }
    _append_log_line(
        _desk_log_path("decision_debug_metrics.jsonl"),
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
    )
    st.session_state["decision_debug_metrics_last_log_ts"] = float(now_ts)


def _resolve_micro_train_backend(value: str | None) -> str:
    backend = str(value or getattr(cfg, "MICRO_MODEL_TRAIN_BACKEND", "auto") or "auto").strip().lower()
    if backend not in {"auto", "tensorflow", "sklearn"}:
        return "auto"
    return backend


def _micro_model_artifact_exists(paths: dict[str, Path] | None = None) -> bool:
    work = dict(paths or _micro_training_paths())
    model_path = Path(work["model_artifact"])
    candidates = [model_path, Path(work["feature_importance"])]
    if model_path.suffix.lower() in {".h5", ".keras"}:
        candidates.append(model_path.with_suffix(".pkl"))
    return any(path.exists() for path in candidates)


def _micro_model_badge_state(
    paths: dict[str, Path] | None = None,
    state: dict | None = None,
) -> tuple[str, bool]:
    work = dict(paths or _micro_training_paths())
    micro_state = dict(state or _compute_micro_training_status(work))
    status = str(micro_state.get("status") or "").upper()
    artifact_exists = _micro_model_artifact_exists(work)
    readiness = _micro_model_readiness(paths=work, state=micro_state)
    stale_artifact = bool(artifact_exists and (status == MICRO_TRAIN_STATUS_FAILED or not readiness.get("ready")))

    if status == MICRO_TRAIN_STATUS_RUNNING:
        return "Training", stale_artifact
    if bool(readiness.get("ready")):
        return "Trained", stale_artifact
    if stale_artifact:
        return "Not trained", True
    return "Not trained", False


def _cleanup_micro_train_runtime_files(paths: dict[str, Path] | None = None) -> None:
    work = dict(paths or _micro_training_paths())
    for key in ("pid", "lock"):
        try:
            Path(work[key]).unlink(missing_ok=True)
        except Exception:
            pass


def _is_micro_training_running(paths: dict[str, Path] | None = None) -> tuple[bool, int | None]:
    work = dict(paths or _micro_training_paths())
    pid = _read_pid(Path(work["pid"]))
    if pid is None:
        return False, None
    if _is_pid_alive(pid):
        return True, pid
    _cleanup_micro_train_runtime_files(work)
    return False, None


def _tail_log_lines(path: Path, limit: int = 50) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    count = max(1, int(limit))
    return lines[-count:]


def _last_training_report(log_path: Path) -> dict:
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return {}
    for line in reversed(lines):
        text = str(line or "").strip()
        if not text.startswith("{"):
            continue
        try:
            obj = json.loads(text)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return {}


def _normalize_class_labels(raw_labels) -> list[int]:
    if not isinstance(raw_labels, (list, tuple, set)):
        return []
    labels: set[int] = set()
    for value in raw_labels:
        try:
            labels.add(int(value))
        except Exception:
            continue
    return sorted(labels)


def _micro_model_readiness(
    paths: dict[str, Path] | None = None,
    state: dict | None = None,
) -> dict:
    # Fail-closed readiness: status + artifact + training evidence + class variance.
    work = dict(paths or _micro_training_paths())
    micro_state = dict(state or _compute_micro_training_status(work))
    status = str(micro_state.get("status") or "").upper()
    artifact_exists = _micro_model_artifact_exists(work)
    report = _last_training_report(Path(work["log"]))
    report_status = str(
        report.get("status")
        or micro_state.get("last_report_status")
        or ""
    ).upper()
    class_labels = _normalize_class_labels(
        report.get("class_labels")
        if isinstance(report, dict)
        else micro_state.get("class_labels")
    )
    if not class_labels:
        class_labels = _normalize_class_labels(micro_state.get("class_labels"))
    class_variance_ok = len(class_labels) >= 2

    reason_code = None
    if status == MICRO_TRAIN_STATUS_RUNNING:
        reason_code = "TRAINING_RUNNING"
    elif status != MICRO_TRAIN_STATUS_SUCCESS:
        reason_code = "STATUS_NOT_SUCCESS"
    elif not artifact_exists:
        reason_code = "ARTIFACT_MISSING"
    elif not report:
        reason_code = "TRAIN_REPORT_MISSING"
    elif report_status not in {"TRAINED", "DRY_RUN_OK"}:
        reason_code = "TRAIN_REPORT_STATUS_INVALID"
    elif not class_variance_ok:
        reason_code = "CLASS_VARIANCE_NOT_PROVEN"

    return {
        "ready": reason_code is None,
        "reason_code": reason_code,
        "status": status,
        "artifact_exists": bool(artifact_exists),
        "report_status": report_status or None,
        "class_labels": class_labels,
        "class_variance_ok": bool(class_variance_ok),
    }


def _compute_micro_training_status(paths: dict[str, Path] | None = None) -> dict:
    work = dict(paths or _micro_training_paths())
    status_path = Path(work["status"])
    log_path = Path(work["log"])
    running, pid = _is_micro_training_running(work)
    status_payload = _read_json(status_path)
    status = str(status_payload.get("status") or "").upper()

    if running:
        if status != MICRO_TRAIN_STATUS_RUNNING:
            status_payload = {
                "status": MICRO_TRAIN_STATUS_RUNNING,
                "pid": int(pid),
                "started_epoch": float(status_payload.get("started_epoch") or time.time()),
                "log_path": str(log_path),
                "model_artifact_path": str(work["model_artifact"]),
            }
            _write_json(status_path, status_payload)
    else:
        if status == MICRO_TRAIN_STATUS_RUNNING:
            report = _last_training_report(log_path)
            report_status = str(report.get("status") or "").upper()
            final_status = MICRO_TRAIN_STATUS_SUCCESS if report_status in {"TRAINED", "DRY_RUN_OK"} else MICRO_TRAIN_STATUS_FAILED
            status_payload = {
                **status_payload,
                "status": final_status,
                "finished_epoch": float(time.time()),
                "pid": None,
                "last_report_status": report_status or None,
                "last_report_reason": report.get("reason"),
                "class_labels": report.get("class_labels"),
                "target_positive_rate": report.get("target_positive_rate"),
                "backend_used": report.get("backend_used"),
                "log_path": str(log_path),
                "model_artifact_path": str(work["model_artifact"]),
            }
            _write_json(status_path, status_payload)
        elif status not in {MICRO_TRAIN_STATUS_SUCCESS, MICRO_TRAIN_STATUS_FAILED}:
            status_payload = {
                "status": MICRO_TRAIN_STATUS_SUCCESS if _micro_model_artifact_exists(work) else MICRO_TRAIN_STATUS_FAILED,
                "pid": None,
                "log_path": str(log_path),
                "model_artifact_path": str(work["model_artifact"]),
            }
            _write_json(status_path, status_payload)

    status_payload = _read_json(status_path)
    status_payload["running"] = bool(running)
    status_payload["pid"] = int(pid) if running and pid else None
    status_payload["log_path"] = str(log_path)
    status_payload["model_artifact_path"] = str(work["model_artifact"])
    status_payload["feature_importance_path"] = str(work["feature_importance"])
    legacy = _legacy_micro_training_paths()
    legacy_status_payload = _read_json(Path(legacy["status"]))
    if legacy_status_payload:
        canonical_status = str(status_payload.get("status") or "").upper()
        legacy_status = str(legacy_status_payload.get("status") or "").upper()
        status_payload["legacy_status_path"] = str(legacy["status"])
        status_payload["legacy_status"] = legacy_status or None
        status_payload["legacy_status_conflict"] = bool(
            canonical_status and legacy_status and canonical_status != legacy_status
        )
    readiness = _micro_model_readiness(paths=work, state=status_payload)
    status_payload["ready"] = bool(readiness.get("ready"))
    status_payload["ready_reason_code"] = readiness.get("reason_code")
    status_payload["class_labels"] = readiness.get("class_labels", status_payload.get("class_labels"))
    status_payload["class_variance_ok"] = bool(readiness.get("class_variance_ok"))
    status_payload["log_tail"] = _tail_log_lines(log_path, limit=50)
    if str(status_payload.get("status") or "").upper() not in {
        MICRO_TRAIN_STATUS_RUNNING,
        MICRO_TRAIN_STATUS_FAILED,
        MICRO_TRAIN_STATUS_SUCCESS,
    }:
        status_payload["status"] = MICRO_TRAIN_STATUS_FAILED
    return status_payload


def start_micro_training_subprocess(
    *,
    backend_override: str | None = None,
    paths: dict[str, Path] | None = None,
    popen_fn=None,
    root_dir: Path | None = None,
) -> tuple[bool, str]:
    work = dict(paths or _micro_training_paths())
    runner = popen_fn or subprocess.Popen
    running, pid = _is_micro_training_running(work)
    if running:
        return False, f"Micro model training already running (pid={pid})."

    backend = _resolve_micro_train_backend(backend_override)
    command = [sys.executable, "-m", "models.train_micro_model"]
    if backend != "auto":
        command.extend(["--backend", backend])

    for key in ("log", "pid", "lock", "status", "model_artifact", "feature_importance"):
        Path(work[key]).parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    env.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["PYTHONPATH"] = (
        str(ROOT)
        if not env.get("PYTHONPATH")
        else str(ROOT) + os.pathsep + str(env.get("PYTHONPATH"))
    )
    log_path = Path(work["log"])
    _append_log_line(log_path, f"[{datetime.now(timezone.utc).isoformat()}] START {' '.join(command)}")

    log_handle = None
    try:
        log_handle = log_path.open("a", encoding="utf-8")
        proc = runner(
            command,
            cwd=str(root_dir or ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
        proc_pid = int(getattr(proc, "pid", 0) or 0)
        if proc_pid <= 0:
            raise RuntimeError("missing training process pid")
        Path(work["pid"]).write_text(str(proc_pid), encoding="utf-8")
        _write_json(
            Path(work["lock"]),
            {
                "pid": proc_pid,
                "started_epoch": float(time.time()),
                "command": command,
                "cwd": str(root_dir or ROOT),
            },
        )
        _write_json(
            Path(work["status"]),
            {
                "status": MICRO_TRAIN_STATUS_RUNNING,
                "pid": proc_pid,
                "started_epoch": float(time.time()),
                "log_path": str(log_path),
                "model_artifact_path": str(work["model_artifact"]),
                "feature_importance_path": str(work["feature_importance"]),
                "backend": backend,
            },
        )
        return True, f"Micro model training started (pid={proc_pid}, backend={backend})."
    except Exception as exc:
        _write_json(
            Path(work["status"]),
            {
                "status": MICRO_TRAIN_STATUS_FAILED,
                "pid": None,
                "finished_epoch": float(time.time()),
                "error": f"{type(exc).__name__}: {exc}",
                "log_path": str(log_path),
                "model_artifact_path": str(work["model_artifact"]),
            },
        )
        return False, f"Unable to start micro model training. Check {log_path}."
    finally:
        try:
            if log_handle is not None:
                log_handle.close()
        except Exception:
            pass


def cancel_micro_training(paths: dict[str, Path] | None = None) -> tuple[bool, str]:
    work = dict(paths or _micro_training_paths())
    running, pid = _is_micro_training_running(work)
    if not running or pid is None:
        return False, "No micro model training process is running."

    cancelled = False
    try:
        if hasattr(os, "killpg"):
            os.killpg(pid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
        cancelled = True
    except ProcessLookupError:
        cancelled = True
    except Exception:
        cancelled = False

    if cancelled:
        # Avoid UI-thread sleeps; issue immediate hard-stop escalation if process remains alive.
        if _is_pid_alive(pid):
            try:
                if hasattr(os, "killpg"):
                    os.killpg(pid, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGKILL)
            except Exception:
                pass

    _cleanup_micro_train_runtime_files(work)
    _append_log_line(Path(work["log"]), f"[{datetime.now(timezone.utc).isoformat()}] CANCEL pid={pid}")
    _write_json(
        Path(work["status"]),
        {
            "status": MICRO_TRAIN_STATUS_FAILED,
            "pid": None,
            "finished_epoch": float(time.time()),
            "cancelled": True,
            "log_path": str(work["log"]),
            "model_artifact_path": str(work["model_artifact"]),
        },
    )
    if not cancelled:
        return False, f"Unable to cancel training process pid={pid}. See {work['log']}."
    return True, f"Cancelled micro model training (pid={pid})."


@st.cache_data(ttl=20, show_spinner=False)
def get_underlying_candles(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    columns = ["time_ms", "open", "high", "low", "close", "volume"]
    empty = pd.DataFrame(columns=columns)
    if _history_fetch_suppressed("underlying_candles"):
        return empty
    try:
        start = _coerce_epoch_ms(start_ms)
        end = _coerce_epoch_ms(end_ms)
        if start is None or end is None:
            return empty
        out = market_data_get_underlying_candles(
            symbol=str(symbol or ""),
            interval=str(interval or "minute"),
            start_ms=int(start),
            end_ms=int(end),
        )
        if out is None or out.empty:
            return empty
        for col in columns:
            if col not in out.columns:
                out[col] = None
        return out[columns]
    except Exception as exc:
        logger.warning("chart_view_get_candles_failed symbol=%s err=%s", symbol, exc)
        _record_history_fetch_failure("underlying_candles", exc)
        return empty


@st.cache_data(ttl=20, show_spinner=False)
def _get_option_candles_or_snapshots_cached(
    trade_payload_json: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> pd.DataFrame:
    columns = ["time_ms", "ltp", "bid", "ask", "mark_price", "quote_age_sec", "spread_pct", "source"]
    empty = pd.DataFrame(columns=columns)
    if _history_fetch_suppressed("option_candles"):
        return empty
    try:
        trade = json.loads(trade_payload_json or "{}")
        out = market_data_get_option_candles_or_snapshots(
            trade=trade,
            interval=str(interval or "minute"),
            start_ms=int(start_ms),
            end_ms=int(end_ms),
        )
        if out is None or out.empty:
            return empty
        for col in columns:
            if col not in out.columns:
                out[col] = None
        return out[columns]
    except Exception as exc:
        logger.warning("chart_view_get_option_series_failed err=%s", exc)
        _record_history_fetch_failure("option_candles", exc)
        return empty


def get_option_candles_or_snapshots(trade, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    columns = ["time_ms", "ltp", "bid", "ask", "mark_price", "quote_age_sec", "spread_pct", "source"]
    empty = pd.DataFrame(columns=columns)
    try:
        start = _coerce_epoch_ms(start_ms)
        end = _coerce_epoch_ms(end_ms)
        if start is None or end is None:
            return empty
        trade_payload = dict(trade or {})
        trade_payload_json = json.dumps(trade_payload, sort_keys=True, default=str)
        return _get_option_candles_or_snapshots_cached(
            trade_payload_json=trade_payload_json,
            interval=str(interval or "minute"),
            start_ms=int(start),
            end_ms=int(end),
        )
    except Exception:
        return empty


# Backward-compatible alias used by phase-1 chart view.
def get_candles(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    return get_underlying_candles(symbol=symbol, interval=interval, start_ms=start_ms, end_ms=end_ms)


def _interval_ms(interval: str) -> int:
    mapping = {
        "minute": 60_000,
        "1minute": 60_000,
        "3minute": 180_000,
        "5minute": 300_000,
        "10minute": 600_000,
        "15minute": 900_000,
        "30minute": 1_800_000,
        "60minute": 3_600_000,
        "day": 86_400_000,
    }
    key = str(interval or "5minute").strip().lower()
    return mapping.get(key, 300_000)


def _auto_interval_for_range(interval: str, start_ms: int, end_ms: int, max_points: int = 1500) -> str:
    choices = ["minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"]
    requested = str(interval or "5minute").strip().lower()
    range_ms = max(0, int(end_ms) - int(start_ms))
    if range_ms <= 0:
        return requested
    if requested in choices:
        start_idx = choices.index(requested)
    else:
        start_idx = 0
    for cand in choices[start_idx:]:
        est = range_ms / max(1, _interval_ms(cand))
        if est <= float(max_points):
            return cand
    return choices[-1]


def _downsample_points(df: pd.DataFrame, max_points: int = 1500) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    limit = max(1, int(max_points))
    if len(df) <= limit:
        return df
    stride = max(1, int(math.ceil(len(df) / float(limit))))
    out = df.iloc[::stride].copy()
    if out.empty:
        return df.tail(limit).copy()
    if "time_ms" in df.columns:
        out = out.sort_values("time_ms")
    return out


def _collect_chart_marker_rows(trades_df: pd.DataFrame, underlying: str, max_markers: int = 50) -> list[dict]:
    if trades_df is None or trades_df.empty:
        return []
    symbol = str(underlying or "").upper().strip()
    if not symbol:
        return []
    limit = max(0, int(max_markers or 0))
    if limit == 0:
        return []
    records = []
    for _, row_obj in trades_df.iterrows():
        row = row_obj.to_dict()
        row_underlying = _infer_underlying_symbol(row)
        if row_underlying != symbol:
            continue
        status = str(row.get("status") or "").upper().strip()
        reject_reason = str(row.get("reject_reason") or "").strip()
        has_reject_reason = reject_reason not in {"", "None", "none", "nan", "NaN"}
        is_rejected = status in {"PLANNING", "PROPOSED"} or has_reject_reason
        is_active = status == "ACTIVE"
        if not (is_rejected or is_active):
            continue
        ts_ms = _coerce_epoch_ms(
            row.get("timestamp_epoch_ms")
            or row.get("timestamp_utc_iso")
            or row.get("timestamp")
            or row.get("last_seen_ts")
        )
        entry_val = _safe_float(row.get("entry"))
        if ts_ms is None or entry_val is None:
            continue
        row["timestamp_epoch_ms"] = int(ts_ms)
        row["entry"] = float(entry_val)
        row["marker_kind"] = "active" if is_active else "rejected"
        row["reject_reason"] = reject_reason if has_reject_reason else None
        row["chart_trade_key"] = str(row.get("chart_trade_key") or _stable_trade_key(row))
        records.append(row)
    records.sort(key=lambda r: int(r.get("timestamp_epoch_ms") or 0), reverse=True)
    return records[:limit]


def build_option_series(df_or_snapshots, mode: str) -> pd.DataFrame:
    columns = [
        "time_ms",
        "opt_price",
        "ltp",
        "bid",
        "ask",
        "mark_price",
        "mid_price",
        "quote_age_sec",
        "spread_pct",
        "source",
    ]
    empty = pd.DataFrame(columns=columns)
    if df_or_snapshots is None:
        return empty
    if isinstance(df_or_snapshots, pd.DataFrame):
        work = df_or_snapshots.copy()
    else:
        work = pd.DataFrame(list(df_or_snapshots or []))
    if work.empty:
        return empty

    def _row_num(row, keys):
        for key in keys:
            val = _safe_float(row.get(key))
            if val is not None:
                return float(val)
        return None

    def _row_ts_ms(row):
        for key in ("time_ms", "timestamp_epoch_ms", "timestamp_epoch", "ts_epoch", "timestamp_iso", "timestamp", "ts"):
            ts = _coerce_epoch_ms(row.get(key))
            if ts is not None:
                return int(ts)
        return None

    work["time_ms"] = work.apply(_row_ts_ms, axis=1)
    work = work.dropna(subset=["time_ms"]).copy()
    if work.empty:
        return empty
    work["time_ms"] = pd.to_numeric(work["time_ms"], errors="coerce")
    work = work.dropna(subset=["time_ms"]).copy()
    work["time_ms"] = work["time_ms"].astype("int64")

    work["ltp"] = work.apply(lambda r: _row_num(r, ("ltp", "last_price", "close", "opt_ltp", "current_ltp")), axis=1)
    work["bid"] = work.apply(lambda r: _row_num(r, ("bid", "best_bid", "opt_bid")), axis=1)
    work["ask"] = work.apply(lambda r: _row_num(r, ("ask", "best_ask", "opt_ask")), axis=1)
    work["quote_age_sec"] = work.apply(lambda r: _row_num(r, ("quote_age_sec", "price_age_sec")), axis=1)
    work["spread_pct"] = work.apply(lambda r: _row_num(r, ("spread_pct",)), axis=1)
    work["source"] = work.apply(lambda r: str(r.get("source") or "option_snapshot"), axis=1)

    work["mid_price"] = (pd.to_numeric(work["bid"], errors="coerce") + pd.to_numeric(work["ask"], errors="coerce")) / 2.0
    work["mark_price"] = work.apply(lambda r: _row_num(r, ("mark_price", "mark")), axis=1)
    work["mark_price"] = pd.to_numeric(work["mark_price"], errors="coerce")
    work["mark_price"] = work["mark_price"].where(work["mark_price"].notna(), work["mid_price"])
    work["mark_price"] = work["mark_price"].where(work["mark_price"].notna(), pd.to_numeric(work["ltp"], errors="coerce"))

    base = pd.to_numeric(work["mark_price"], errors="coerce")
    base = base.where(base > 0, pd.to_numeric(work["ltp"], errors="coerce"))
    spread_calc = (pd.to_numeric(work["ask"], errors="coerce") - pd.to_numeric(work["bid"], errors="coerce")) / base
    work["spread_pct"] = pd.to_numeric(work["spread_pct"], errors="coerce")
    work["spread_pct"] = work["spread_pct"].where(work["spread_pct"].notna(), spread_calc)

    mode_norm = str(mode or "mark").strip().lower()
    if mode_norm == "mid":
        work["opt_price"] = pd.to_numeric(work["mid_price"], errors="coerce")
    elif mode_norm == "ltp":
        work["opt_price"] = pd.to_numeric(work["ltp"], errors="coerce")
    else:
        work["opt_price"] = pd.to_numeric(work["mark_price"], errors="coerce")

    work = work.sort_values("time_ms").drop_duplicates(subset=["time_ms"], keep="last")
    work = _downsample_points(work, max_points=1500)
    for col in columns:
        if col not in work.columns:
            work[col] = None
    return work[columns]


def detect_stale_points(option_df: pd.DataFrame, thresholds: dict | None = None) -> tuple[pd.Series, list[str]]:
    if option_df is None or option_df.empty:
        return pd.Series(dtype=bool), []
    cfg_map = dict(thresholds or {})
    max_quote_age = _safe_float(cfg_map.get("quote_age_sec_max"), default=float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0)))
    outside_pct = _safe_float(cfg_map.get("ltp_outside_band_pct"), default=float(getattr(cfg, "OPTION_LAST_OUTSIDE_BAND_PCT", 0.01)))
    max_spread_pct = _safe_float(cfg_map.get("spread_pct_max"), default=float(getattr(cfg, "MAX_SPREAD_PCT", 0.03)))
    max_quote_age = float(max_quote_age if max_quote_age is not None else 8.0)
    outside_pct = float(outside_pct if outside_pct is not None else 0.01)
    max_spread_pct = float(max_spread_pct if max_spread_pct is not None else 0.03)

    stale_mask: list[bool] = []
    stale_reasons: list[str] = []
    for _, row in option_df.iterrows():
        reasons = []
        quote_age = _safe_float(row.get("quote_age_sec"))
        if quote_age is not None and quote_age > max_quote_age:
            reasons.append(f"quote_age_sec>{max_quote_age:.2f}")
        bid = _safe_float(row.get("bid"))
        ask = _safe_float(row.get("ask"))
        ltp = _safe_float(row.get("ltp"))
        if ltp is not None and bid is not None and ask is not None:
            lo = min(bid, ask) * max(0.0, 1.0 - outside_pct)
            hi = max(bid, ask) * (1.0 + outside_pct)
            if ltp < lo or ltp > hi:
                reasons.append("ltp_outside_bid_ask_band")
        spread_pct = _safe_float(row.get("spread_pct"))
        if spread_pct is None and bid is not None and ask is not None:
            base = _safe_float(row.get("mark_price"))
            if base in (None, 0.0):
                base = ltp
            if base not in (None, 0.0):
                spread_pct = (ask - bid) / base
        if spread_pct is not None and spread_pct > max_spread_pct:
            reasons.append(f"spread_pct>{max_spread_pct:.4f}")
        stale_mask.append(bool(reasons))
        stale_reasons.append("; ".join(reasons))
    return pd.Series(stale_mask, index=option_df.index), stale_reasons


def build_dual_axis_figure(
    underlying_df: pd.DataFrame,
    option_df: pd.DataFrame,
    trade,
    markers_df,
    option_mode: str = "mark",
    show_quote_diagnostics: bool = True,
    stale_thresholds: dict | None = None,
) -> go.Figure:
    row = dict(trade or {})
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    required = {"time_ms", "open", "high", "low", "close", "volume"}

    if isinstance(underlying_df, pd.DataFrame) and (not underlying_df.empty) and required.issubset(set(underlying_df.columns)):
        base = underlying_df.copy()
        base["time_ms"] = pd.to_numeric(base["time_ms"], errors="coerce")
        base = base.dropna(subset=["time_ms"]).sort_values("time_ms")
        if not base.empty:
            base["time_dt"] = pd.to_datetime(base["time_ms"], unit="ms", utc=True).dt.tz_convert("Asia/Kolkata")
            fig.add_trace(
                go.Candlestick(
                    x=base["time_dt"],
                    open=base["open"],
                    high=base["high"],
                    low=base["low"],
                    close=base["close"],
                    name="Underlying",
                ),
                secondary_y=False,
            )
    if not fig.data:
        fig.add_annotation(
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            text="No underlying candle data available.",
        )
        fig.update_layout(
            title="Trade Chart",
            xaxis_title="Time",
            yaxis_title="Underlying",
            yaxis2_title="Option",
            margin=dict(l=40, r=360, t=60, b=40),
        )
        return fig

    option_work = option_df.copy() if isinstance(option_df, pd.DataFrame) else pd.DataFrame()
    if option_work is not None and not option_work.empty:
        option_work["time_ms"] = pd.to_numeric(option_work.get("time_ms"), errors="coerce")
        option_work = option_work.dropna(subset=["time_ms"]).sort_values("time_ms").copy()
        if not option_work.empty:
            option_work = _downsample_points(option_work, max_points=1500)
            option_work["time_dt"] = pd.to_datetime(option_work["time_ms"], unit="ms", utc=True).dt.tz_convert("Asia/Kolkata")
            option_work["opt_price"] = pd.to_numeric(option_work.get("opt_price"), errors="coerce")
            plot_opt = option_work.dropna(subset=["opt_price"])
            if not plot_opt.empty:
                fig.add_trace(
                    go.Scatter(
                        x=plot_opt["time_dt"],
                        y=plot_opt["opt_price"],
                        mode="lines",
                        line=dict(color="#1d4ed8", width=2),
                        name=f"Option {str(option_mode).upper()}",
                    ),
                    secondary_y=True,
                )

    x_vals = []
    try:
        first_trace = fig.data[0]
        x_vals = list(first_trace.x) if hasattr(first_trace, "x") else []
    except Exception:
        x_vals = []
    x0 = x_vals[0] if x_vals else datetime.now(ZoneInfo("Asia/Kolkata"))
    x1 = x_vals[-1] if x_vals else datetime.now(ZoneInfo("Asia/Kolkata"))

    for field, color, name in [("entry", "#3b82f6", "Entry"), ("stop", "#ef4444", "Stop"), ("target", "#22c55e", "Target")]:
        val = _safe_float(row.get(field))
        if val is None:
            continue
        fig.add_shape(
            type="line",
            x0=x0,
            x1=x1,
            y0=float(val),
            y1=float(val),
            xref="x",
            yref="y2",
            line=dict(color=color, width=1.6, dash="dot"),
        )
        fig.add_annotation(
            x=1.0,
            y=float(val),
            xref="paper",
            yref="y2",
            text=f"{name}: {val:.2f}",
            showarrow=False,
            xanchor="left",
            font=dict(size=10, color=color),
        )

    activation_ts = _coerce_epoch_ms(
        row.get("activated_ts")
        or row.get("activation_ts")
        or row.get("timestamp_epoch_ms")
        or row.get("timestamp_utc_iso")
        or row.get("timestamp")
    )
    activation_px = _safe_float(row.get("activation_price"))
    if activation_px is None:
        activation_px = _safe_float(row.get("entry"))
    if activation_ts is not None and activation_px is not None:
        activation_dt = datetime.fromtimestamp(float(activation_ts) / 1000.0, tz=timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))
        fig.add_trace(
            go.Scatter(
                x=[activation_dt],
                y=[float(activation_px)],
                mode="markers",
                marker=dict(size=10, color="#2563eb", symbol="diamond"),
                name="Activation",
            ),
            secondary_y=True,
        )

    marker_rows = markers_df if isinstance(markers_df, list) else list(getattr(markers_df, "to_dict", lambda *_: [])("records") if markers_df is not None else [])
    if marker_rows:
        rej_x, rej_y, rej_text = [], [], []
        act_x, act_y, act_text = [], [], []
        for marker in marker_rows:
            m = dict(marker or {})
            ts_ms = _coerce_epoch_ms(m.get("timestamp_epoch_ms"))
            price = _safe_float(m.get("entry"))
            if ts_ms is None or price is None:
                continue
            dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))
            text = (
                f"trade_key: {m.get('chart_trade_key') or _stable_trade_key(m)}<br>"
                f"reject_reason: {m.get('reject_reason') or 'None'}<br>"
                f"quote_age_sec: {m.get('quote_age_sec')}<br>"
                f"spread_pct: {m.get('spread_pct')}"
            )
            if str(m.get("marker_kind") or "").lower() == "active":
                act_x.append(dt)
                act_y.append(float(price))
                act_text.append(text)
            else:
                rej_x.append(dt)
                rej_y.append(float(price))
                rej_text.append(text)
        if rej_x:
            fig.add_trace(
                go.Scatter(
                    x=rej_x,
                    y=rej_y,
                    mode="markers",
                    name="Rejected/Advisory",
                    text=rej_text,
                    hovertemplate="%{text}<extra></extra>",
                    marker=dict(size=6, color="rgba(107,114,128,0.6)", symbol="circle"),
                ),
                secondary_y=True,
            )
        if act_x:
            fig.add_trace(
                go.Scatter(
                    x=act_x,
                    y=act_y,
                    mode="markers",
                    name="Active Trades",
                    text=act_text,
                    hovertemplate="%{text}<extra></extra>",
                    marker=dict(size=8, color="#1d4ed8", symbol="diamond"),
                ),
                secondary_y=True,
            )

    if option_work is not None and not option_work.empty and "opt_price" in option_work.columns:
        stale_mask, stale_reasons = detect_stale_points(option_work, thresholds=stale_thresholds)
        option_work = option_work.copy()
        option_work["stale"] = stale_mask
        option_work["stale_reason"] = stale_reasons
        stale_points = option_work[option_work["stale"] & option_work["opt_price"].notna()]
        if not stale_points.empty:
            fig.add_trace(
                go.Scatter(
                    x=stale_points["time_dt"],
                    y=stale_points["opt_price"],
                    mode="markers",
                    name="Stale/Illiquid",
                    text=stale_points["stale_reason"].apply(lambda r: f"STALE/ILLQ: {r}" if r else "STALE/ILLQ").tolist(),
                    hovertemplate="%{text}<extra></extra>",
                    marker=dict(size=7, color="#dc2626", symbol="x"),
                ),
                secondary_y=True,
            )

    latest = {}
    if option_work is not None and not option_work.empty:
        try:
            latest = option_work.sort_values("time_ms").iloc[-1].to_dict()
        except Exception:
            latest = {}
    trade_key = str(row.get("chart_trade_key") or _stable_trade_key(row))
    diagnostics = [
        f"trade_key: {trade_key}",
        f"status: {row.get('status')}",
        f"side: {row.get('side')}",
        f"confidence: {row.get('confidence')}",
        f"option_mode: {str(option_mode).lower()}",
    ]
    if show_quote_diagnostics:
        diagnostics.extend(
            [
                f"ltp: {_first_non_null(latest.get('ltp'), row.get('ltp'))}",
                f"bid: {_first_non_null(latest.get('bid'), row.get('bid'))}",
                f"ask: {_first_non_null(latest.get('ask'), row.get('ask'))}",
                f"mark: {_first_non_null(latest.get('mark_price'), row.get('mark_price'))}",
                f"spread_pct: {_first_non_null(latest.get('spread_pct'), row.get('spread_pct'))}",
                f"quote_age_sec: {_first_non_null(latest.get('quote_age_sec'), row.get('quote_age_sec'))}",
            ]
        )
    fig.add_annotation(
        x=1.01,
        y=1.0,
        xref="paper",
        yref="paper",
        align="left",
        showarrow=False,
        bordercolor="#6b7280",
        borderwidth=1,
        bgcolor="rgba(17,24,39,0.04)",
        font=dict(size=11),
        text="<br>".join(diagnostics),
    )
    if str(option_mode or "").lower() == "ltp":
        fig.add_annotation(
            x=0.01,
            y=0.98,
            xref="paper",
            yref="paper",
            showarrow=False,
            text="LTP may be stale",
            font=dict(size=11, color="#dc2626"),
            bgcolor="rgba(254,226,226,0.7)",
        )

    title_symbol = _infer_underlying_symbol(row) or str(row.get("symbol") or "UNDERLYING")
    fig.update_layout(
        title=f"{title_symbol} vs Option ({str(option_mode).upper()})",
        xaxis_title="Time (IST)",
        margin=dict(l=40, r=360, t=60, b=40),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_yaxes(title_text=f"{title_symbol} (Underlying)", secondary_y=False)
    fig.update_yaxes(title_text="Option Price", secondary_y=True)
    return fig


def build_chart(trade, candles_df, marker_rows: list[dict] | None = None) -> go.Figure:
    row = dict(trade or {})
    fig = go.Figure()
    required = {"time_ms", "open", "high", "low", "close", "volume"}
    has_candles = isinstance(candles_df, pd.DataFrame) and (not candles_df.empty) and required.issubset(set(candles_df.columns))
    if has_candles:
        work = candles_df.copy()
        work["time_ms"] = pd.to_numeric(work["time_ms"], errors="coerce")
        work = work.dropna(subset=["time_ms"]).sort_values("time_ms")
        if not work.empty:
            work["time_dt"] = pd.to_datetime(work["time_ms"], unit="ms", utc=True).dt.tz_convert("Asia/Kolkata")
            fig.add_trace(
                go.Candlestick(
                    x=work["time_dt"],
                    open=work["open"],
                    high=work["high"],
                    low=work["low"],
                    close=work["close"],
                    name="Candles",
                )
            )
    if not fig.data:
        fig.add_annotation(
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            text="No candle data available for the selected trade.",
        )
        fig.update_layout(
            title="Trade Chart",
            xaxis_title="Time",
            yaxis_title="Price",
            xaxis_rangeslider_visible=False,
            margin=dict(l=40, r=320, t=60, b=40),
        )
        return fig

    overlays = [
        ("entry", "Entry", "#3b82f6"),
        ("stop", "Stop", "#ef4444"),
        ("target", "Target", "#22c55e"),
    ]
    for field, label, color in overlays:
        val = _safe_float(row.get(field))
        if val is None:
            continue
        fig.add_hline(
            y=float(val),
            line_dash="dot",
            line_color=color,
            annotation_text=f"{label}: {val:.2f}",
            annotation_position="left",
        )

    ts_ms = _coerce_epoch_ms(
        row.get("timestamp_epoch_ms")
        or row.get("timestamp_utc_iso")
        or row.get("timestamp")
        or row.get("last_seen_ts")
    )
    if ts_ms is not None:
        marker_y = _safe_float(row.get("entry"))
        if marker_y is None and has_candles and isinstance(candles_df, pd.DataFrame) and (not candles_df.empty):
            try:
                marker_y = _safe_float(candles_df.sort_values("time_ms")["close"].iloc[-1])
            except Exception:
                marker_y = None
        if marker_y is not None:
            marker_x = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))
            fig.add_trace(
                go.Scatter(
                    x=[marker_x],
                    y=[float(marker_y)],
                    mode="markers",
                    marker=dict(size=11, color="#f59e0b", symbol="diamond"),
                    name="Trade timestamp",
                )
            )

    marker_rows = list(marker_rows or [])
    if marker_rows:
        rejected_x, rejected_y, rejected_text = [], [], []
        active_x, active_y, active_text = [], [], []
        for marker in marker_rows:
            marker_kind = str(marker.get("marker_kind") or "").strip().lower()
            ts_ms = _coerce_epoch_ms(marker.get("timestamp_epoch_ms"))
            entry_val = _safe_float(marker.get("entry"))
            if ts_ms is None or entry_val is None:
                continue
            ts_dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))
            trade_key = str(marker.get("chart_trade_key") or _stable_trade_key(marker))
            reject_reason = marker.get("reject_reason")
            quote_age = _safe_float(marker.get("quote_age_sec"))
            spread_pct = _safe_float(marker.get("spread_pct"))
            hover_text = (
                f"trade_key: {trade_key}<br>"
                f"reject_reason: {reject_reason if reject_reason not in (None, '') else 'None'}<br>"
                f"quote_age_sec: {quote_age if quote_age is not None else 'None'}<br>"
                f"spread_pct: {spread_pct if spread_pct is not None else 'None'}"
            )
            if marker_kind == "active":
                active_x.append(ts_dt)
                active_y.append(float(entry_val))
                active_text.append(hover_text)
            else:
                rejected_x.append(ts_dt)
                rejected_y.append(float(entry_val))
                rejected_text.append(hover_text)
        if rejected_x:
            fig.add_trace(
                go.Scatter(
                    x=rejected_x,
                    y=rejected_y,
                    mode="markers",
                    name="Rejected/Advisory",
                    text=rejected_text,
                    hovertemplate="%{text}<extra></extra>",
                    marker=dict(size=6, color="rgba(107,114,128,0.55)", symbol="circle"),
                )
            )
        if active_x:
            fig.add_trace(
                go.Scatter(
                    x=active_x,
                    y=active_y,
                    mode="markers",
                    name="Active Trades",
                    text=active_text,
                    hovertemplate="%{text}<extra></extra>",
                    marker=dict(size=8, color="#2563eb", symbol="diamond"),
                )
            )

    annotation_fields = [
        ("status", row.get("status")),
        ("side", row.get("side")),
        ("confidence", _safe_float(row.get("confidence"))),
        ("reject_reason", row.get("reject_reason")),
        ("pricing_mode", row.get("pricing_mode")),
        ("quote_age_sec", _safe_float(row.get("quote_age_sec"))),
        ("spread_pct", _safe_float(row.get("spread_pct"))),
        ("ltp", _safe_float(row.get("ltp"))),
        ("bid", _safe_float(row.get("bid"))),
        ("ask", _safe_float(row.get("ask"))),
        ("mark_price", _safe_float(row.get("mark_price"))),
    ]
    lines = []
    for key, value in annotation_fields:
        if value is None or value == "":
            continue
        if isinstance(value, float):
            lines.append(f"{key}: {value:.4f}")
        else:
            lines.append(f"{key}: {value}")
    if not lines:
        lines = ["No trade metadata available."]
    fig.add_annotation(
        x=1.01,
        y=1.0,
        xref="paper",
        yref="paper",
        align="left",
        showarrow=False,
        bordercolor="#6b7280",
        borderwidth=1,
        bgcolor="rgba(17,24,39,0.04)",
        font=dict(size=11),
        text="<br>".join(lines),
    )
    title_symbol = _infer_underlying_symbol(row) or str(row.get("symbol") or "UNDERLYING")
    fig.update_layout(
        title=f"{title_symbol} Candlestick Chart",
        xaxis_title="Time (IST)",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        margin=dict(l=40, r=320, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def _render_chart_view_panel(trade_universe_df: pd.DataFrame):
    chart_view_enabled = st.checkbox("Chart view", value=False, key="chart_view_toggle")
    if not chart_view_enabled:
        return
    section_header("Chart View")
    try:
        source_df = _prepare_trade_display_df(trade_universe_df)
        if source_df is None or source_df.empty:
            st.info("Chart view: no trades available.")
            return
        chart_df = _apply_executable_pricing(source_df)
        chart_df["chart_trade_key"] = chart_df.apply(lambda r: _stable_trade_key(r.to_dict()), axis=1)
        chart_df = chart_df[chart_df["chart_trade_key"].astype(str).str.strip().ne("")]
        if chart_df.empty:
            st.info("Chart view: no trades with a valid key.")
            return
        chart_df = _safe_sort_by_last_seen(chart_df).drop_duplicates(subset=["chart_trade_key"], keep="first")
        options = chart_df["chart_trade_key"].tolist()
        selected_key = st.selectbox("Select trade_key", options=options, key="chart_trade_key_select")
        selected_row = chart_df.loc[chart_df["chart_trade_key"] == selected_key].head(1)
        if selected_row.empty:
            st.info("Chart view: selected trade not found.")
            return
        trade = selected_row.iloc[0].to_dict()

        load_chart_history = st.checkbox("Load chart history", value=False, key="chart_load_history")
        show_option_line = st.checkbox("Show option line", value=False, key="chart_show_option_line")
        option_mode = st.selectbox("Option line mode", ["mark", "mid", "ltp"], index=0, key="chart_option_line_mode")
        show_quote_diagnostics = st.checkbox("Show quote diagnostics", value=True, key="chart_show_quote_diagnostics")

        underlying = _infer_underlying_symbol(trade)
        if not underlying:
            st.info("Chart view: unable to infer underlying symbol from selected trade.")
            return
        chart_interval = str(getattr(cfg, "DASHBOARD_CHART_INTERVAL", "5minute") or "5minute")
        lookback_hours = int(getattr(cfg, "DASHBOARD_CHART_LOOKBACK_HOURS", 6) or 6)
        forward_hours = int(getattr(cfg, "DASHBOARD_CHART_FORWARD_HOURS", 1) or 1)
        now_ms = int(time.time() * 1000.0)
        trade_ts_ms = _coerce_epoch_ms(
            trade.get("timestamp_epoch_ms")
            or trade.get("timestamp_utc_iso")
            or trade.get("timestamp")
            or trade.get("last_seen_ts")
        ) or now_ms
        start_ms = max(0, trade_ts_ms - (lookback_hours * 60 * 60 * 1000))
        end_ms = max(now_ms, trade_ts_ms + (forward_hours * 60 * 60 * 1000))
        chart_interval = _auto_interval_for_range(chart_interval, start_ms, end_ms, max_points=1500)

        if not load_chart_history:
            st.info("Chart history is disabled until requested. Enable 'Load chart history' to fetch underlying and option history.")
            return

        candles_df = get_underlying_candles(underlying, chart_interval, start_ms, end_ms)
        if candles_df is None or candles_df.empty:
            st.info(f"Chart view: candle data unavailable for {underlying}.")
            return

        option_df = pd.DataFrame(
            columns=[
                "time_ms",
                "opt_price",
                "ltp",
                "bid",
                "ask",
                "mark_price",
                "mid_price",
                "quote_age_sec",
                "spread_pct",
                "source",
            ]
        )
        if show_option_line:
            option_raw = get_option_candles_or_snapshots(trade, chart_interval, start_ms, end_ms)
            if option_raw is None or option_raw.empty:
                st.warning("No option series data.")
            else:
                source_vals = {str(v).lower() for v in option_raw.get("source", pd.Series(dtype="object")).dropna().astype(str).tolist()}
                if source_vals and source_vals.issubset({"option_snapshot"}):
                    st.warning("Option history unavailable; using sparse snapshots.")
                option_df = build_option_series(option_raw, option_mode)
                if option_df is None or option_df.empty:
                    st.warning("No option series data.")

        marker_rows = _collect_chart_marker_rows(chart_df, underlying=underlying, max_markers=50)
        stale_thresholds = {
            "quote_age_sec_max": float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0)),
            "ltp_outside_band_pct": float(getattr(cfg, "OPTION_LAST_OUTSIDE_BAND_PCT", 0.01)),
            "spread_pct_max": float(getattr(cfg, "MAX_SPREAD_PCT", 0.03)),
        }
        fig = build_dual_axis_figure(
            underlying_df=candles_df,
            option_df=option_df if show_option_line else pd.DataFrame(),
            trade=trade,
            markers_df=marker_rows,
            option_mode=option_mode,
            show_quote_diagnostics=show_quote_diagnostics,
            stale_thresholds=stale_thresholds,
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        logger.exception("chart_view_panel_failed: %s", exc)
        st.info("Chart view is temporarily unavailable. Tables continue to render.")


updates_candidates = [
    logs_dir() / "trade_updates.jsonl",
    data_root() / "trade_updates.json",
]
updates_path = next((p for p in updates_candidates if p.exists()), updates_candidates[0])
if updates_path.exists():
    try:
        updates = []
        with updates_path.open("r", encoding="utf-8") as f:
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

def _ensure_trade_df_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    df_out = df_in.copy()
    datetime_cols = ("timestamp", "ts")
    numeric_cols = (
        "entry",
        "exit_price",
        "qty",
        "target",
        "stop_loss",
        "target_points",
        "strike",
        "instrument_token",
        "opt_bid",
        "opt_ask",
        "opt_ltp",
        "confidence",
        "weight",
        "entry_mismatch_pct",
        "row_age_min",
        "cum_pnl",
        "drawdown",
        "eps",
    )
    text_cols = (
        "trade_id",
        "symbol",
        "side",
        "instrument",
        "expiry",
        "reason",
        "type",
        "action",
        "advice",
        "outcome",
        "system_state",
        "quote_note",
        "entry_mismatch_note",
        "trade_label",
        "hour",
        "row_is_stale",
        "passed",
    )

    for col in datetime_cols:
        if col not in df_out.columns:
            df_out[col] = pd.Series(dtype="datetime64[ns]")
    for col in numeric_cols:
        if col not in df_out.columns:
            df_out[col] = pd.Series(dtype="float64")
    for col in text_cols:
        if col not in df_out.columns:
            df_out[col] = pd.Series(dtype="object")
    return df_out


# Keep dashboard importable even before nav-specific trade logs are loaded.
rows: list[dict] = []
df = _ensure_trade_df_schema(pd.DataFrame())

def _load_prefs():
    prefs_path = _log_path("ui_prefs.json")
    if prefs_path.exists():
        try:
            return json.loads(prefs_path.read_text())
        except Exception:
            return {}
    return {}

def _save_prefs(prefs):
    try:
        logs_dir().mkdir(exist_ok=True)
        _log_path("ui_prefs.json").write_text(json.dumps(prefs, indent=2))
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
        path = _log_path("walk_forward_strategy_summary.csv")
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
UI_MODE_OPTIONS = ["Trader", "Ops/Research"]


def _normalize_ui_mode(raw) -> str:
    value = str(raw or "Trader").strip().lower()
    if value in {"ops", "ops/research", "ops_research", "research", "ops-research"}:
        return "Ops/Research"
    return "Trader"

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
nav_items = [
    "Home",
    "Strategy Timeline",
    "Execution",
    "Reconciliation",
    "Risk & Governance",
    "Data & SLA",
    "ML/RL",
    "Market Depth",
    "Gemini",
]
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
if str(nav or "") == "Home":
    rows = []
    df = _ensure_trade_df_schema(pd.DataFrame())
    logger.info("dashboard_data_load label=trade_log_rows_skipped_home dt_ms=0.00")
else:
    trade_log_tail_rows = _DEFAULT_JSONL_TAIL_ROWS if str(nav or "") == "Home" else _FULL_JSONL_TAIL_ROWS
    rows = _perf_timed_load("trade_log_rows", _load_trade_log_rows, LOG_PATH, max_rows=trade_log_tail_rows)
    df = _perf_timed_load("trade_log_dataframe", pd.DataFrame, rows)
    df = _ensure_trade_df_schema(df)
if df.empty:
    live_suggestions_status = _load_live_suggestions_status()
    live_suggestions_df = _load_live_suggestions_df(limit=100)
    visible_suggestion_count = int(
        live_suggestions_status.get("visible_suggestion_count")
        or len(live_suggestions_df)
        or 0
    )
    visible_executable_count = int(live_suggestions_status.get("visible_executable_count") or 0)
    if (
        visible_suggestion_count > 0
        or visible_executable_count > 0
        or bool(live_suggestions_status.get("feed_ok"))
        or bool(live_suggestions_status.get("ws_connected"))
    ):
        st.info(
            "No closed trades logged yet. Live suggestion snapshots are available "
            f"({visible_suggestion_count} visible, {visible_executable_count} executable)."
        )
    else:
        st.info("No trades logged yet. Dashboard is active in empty-history mode.")
    try:
        auth_guard = load_auth_runtime_guard()
        if bool((auth_guard or {}).get("degrade_to_planning")):
            st.warning(
                "OFFHOURS MODE (degraded): pre-open auth is unhealthy; "
                "planning views remain available while execution is gated."
            )
    except Exception:
        pass
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df["date"] = df["timestamp"].dt.date
entry = pd.to_numeric(df["entry"], errors="coerce")
exit_px = pd.to_numeric(df["exit_price"], errors="coerce")
qty = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)
df["pnl"] = (exit_px.fillna(entry) - entry) * qty
df.loc[df["side"].astype(str).str.upper() == "SELL", "pnl"] *= -1
dfm = df.copy()
default_ui_mode = _normalize_ui_mode(prefs.get("ui_mode", "Trader"))
if "ui_mode_choice" not in st.session_state:
    st.session_state["ui_mode_choice"] = default_ui_mode


def _on_ui_mode_change():
    prefs["ui_mode"] = _normalize_ui_mode(st.session_state.get("ui_mode_choice", "Trader"))
    _save_prefs(prefs)

st.caption("Dashboard Mode")
st.radio(
    "Dashboard Mode",
    UI_MODE_OPTIONS,
    key="ui_mode_choice",
    on_change=_on_ui_mode_change,
    help="Trader mode hides research/admin widgets on Home.",
    horizontal=True,
    label_visibility="collapsed",
)


def _is_ops_research_mode() -> bool:
    return _normalize_ui_mode(st.session_state.get("ui_mode_choice", "Trader")) == "Ops/Research"


def _is_trader_mode() -> bool:
    return not _is_ops_research_mode()


class _SkipSection(Exception):
    pass


render_notifications()
try:
    if st.session_state.get("nav_choice") == "Gemini":
        provider = os.getenv("GPT_PROVIDER", "openai").lower()
        if provider == "gemini":
            if os.getenv("GEMINI_API_KEY"):
                st.caption("Gemini API: OK")
            else:
                st.caption("Gemini API: missing GEMINI_API_KEY")
        else:
            if os.getenv("OPENAI_API_KEY"):
                st.caption("OpenAI API: OK")
            else:
                st.caption("OpenAI API: missing OPENAI_API_KEY")
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

def _safe_float(val, default=None):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except Exception:
        return default

def _should_plot_series(values):
    try:
        if values is None:
            return False
        if isinstance(values, (list, tuple)):
            clean = [v for v in values if v is not None and not (isinstance(v, float) and pd.isna(v))]
        else:
            clean = [v for v in list(values) if v is not None and not (isinstance(v, float) and pd.isna(v))]
        if len(clean) < 2:
            return False
        return len(set(clean)) > 1
    except Exception:
        return False


def _compute_readiness_snapshot():
    snapshot = {
        "state": "UNKNOWN",
        "can_trade": False,
        "blockers": [],
        "warnings": [],
        "readiness": {},
        "checks": {},
        "feed_freshness": {},
        "feed_state_machine": {},
        "feed_debug": {},
        "decision_gate": {},
        "decision_rows": {},
        "decision_blockers_by_symbol": {},
        "latest_decision_row": {},
        "auth_health": {},
        "kite": {},
        "error": None,
    }
    try:
        from core.readiness_gate import run_readiness_check
        readiness = run_readiness_check(write_log=False)
        state = readiness.get("state", "UNKNOWN")
        can_trade = bool(readiness.get("can_trade", False))
        blockers = list(readiness.get("blockers") or [])
        warnings = list(readiness.get("warnings") or [])
        checks = readiness.get("checks") or {}
        decision_gate = checks.get("decision_gate") or {}
        decision_rows = decision_gate.get("rows") or {}
        decision_blockers_by_symbol = decision_gate.get("blockers_by_symbol") or {}
        latest_decision_row = {}
        if isinstance(decision_rows, dict) and decision_rows:
            try:
                latest_decision_row = max(
                    decision_rows.values(),
                    key=lambda row: float((row or {}).get("ts_epoch") or 0.0),
                )
            except Exception:
                latest_decision_row = {}
        if "ok" in decision_gate:
            can_trade = bool(decision_gate.get("ok"))
        try:
            from core.auth_health import get_kite_auth_health
            auth_health = get_kite_auth_health(force=False)
        except Exception:
            auth_health = {}
        try:
            from core.freshness_sla import get_freshness_status
            feed_freshness = get_freshness_status(force=True)
        except Exception:
            feed_freshness = {}
        try:
            feed_state_machine = get_feed_health_snapshot()
        except Exception:
            feed_state_machine = {}
        try:
            feed_debug = get_feed_debug()
        except Exception:
            feed_debug = {}
        runtime_health = _load_runtime_health_latest()
        feed_state_machine, feed_debug = _bridge_feed_state_from_runtime_health(
            feed_state_machine,
            feed_debug,
            runtime_health,
        )
        snapshot.update(
            {
                "state": state,
                "can_trade": can_trade,
                "blockers": blockers,
                "warnings": warnings,
                "readiness": readiness,
                "checks": checks,
                "feed_freshness": feed_freshness,
                "feed_state_machine": feed_state_machine,
                "feed_debug": feed_debug,
                "decision_gate": decision_gate,
                "decision_rows": decision_rows,
                "decision_blockers_by_symbol": decision_blockers_by_symbol,
                "latest_decision_row": latest_decision_row,
                "auth_health": auth_health,
                "kite": checks.get("kite_auth") or {},
                "runtime_health": runtime_health,
            }
        )
    except Exception as e:
        snapshot["error"] = str(e)
    return snapshot


def _get_readiness_snapshot() -> dict:
    """
    Reuse readiness snapshot for a short window to avoid repeated heavy checks
    on quick reruns caused by UI interactions.
    """
    try:
        ttl_sec = max(1.0, float(getattr(cfg, "UI_READINESS_CACHE_SEC", 2.0)))
    except Exception:
        ttl_sec = 2.0
    now_epoch = float(time.time())
    cached = st.session_state.get("_readiness_snapshot_cache")
    if isinstance(cached, dict):
        cached_ts = float(cached.get("ts_epoch") or 0.0)
        payload = cached.get("payload")
        if cached_ts > 0.0 and (now_epoch - cached_ts) < ttl_sec and isinstance(payload, dict):
            return payload
    payload = _compute_readiness_snapshot()
    st.session_state["_readiness_snapshot_cache"] = {
        "ts_epoch": now_epoch,
        "payload": payload,
    }
    return payload


def _market_phase_ist() -> str:
    try:
        return get_market_phase_ist(
            now=now_local(),
            premarket_start=parse_hhmm_time(getattr(cfg, "PREMARKET_START_IST", "09:00"), default=parse_hhmm_time("09:00")),
            open_time=parse_hhmm_time(getattr(cfg, "MARKET_OPEN_IST", "09:15")),
            close_time=parse_hhmm_time(getattr(cfg, "MARKET_CLOSE_IST", "15:30")),
            segment=str(getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")),
        )
    except Exception:
        return "CLOSED"


def _feed_status_summary(feed: dict, feed_debug: dict):
    ltp_age = (feed.get("ltp") or {}).get("age_sec")
    ltp_max = (feed.get("ltp") or {}).get("max_age_sec")
    depth_age = (feed.get("depth") or {}).get("age_sec")
    market_open = bool(feed.get("market_open", False))
    allow_stale = bool(feed.get("allow_stale_quotes", False))
    sla_state = str(feed.get("state") or "UNKNOWN").upper()
    reasons = list(feed.get("reasons") or [])

    if sla_state == "MARKET_CLOSED" or not market_open:
        phase = _market_phase_ist()
        if phase == "PREMARKET":
            return "IDLE", "premarket", ltp_age, depth_age
        return "IDLE", "market closed", ltp_age, depth_age
    if allow_stale or sla_state in ("OFFHOURS", "PLANNING", "IDLE"):
        reason = reasons[0] if reasons else ("planning mode" if allow_stale else "idle")
        return "IDLE", reason, ltp_age, depth_age
    if market_open and ltp_age is None:
        return "IDLE", "no_ticks_yet", ltp_age, depth_age
    if sla_state == "STALE":
        if ltp_age is None:
            return "IDLE", "no_ticks_yet", ltp_age, depth_age
        if ltp_max is not None and ltp_age <= ltp_max:
            return "DEGRADED", "ltp_delayed", ltp_age, depth_age
        return "STALE", (reasons[0] if reasons else "stale"), ltp_age, depth_age
    if sla_state == "DEGRADED":
        return "DEGRADED", (reasons[0] if reasons else "degraded"), ltp_age, depth_age
    if sla_state == "OK":
        return "OK", "healthy", ltp_age, depth_age
    return "IDLE", (reasons[0] if reasons else "unknown"), ltp_age, depth_age


def _compute_trade_refresh_gate(snapshot: dict) -> tuple[bool, str, str]:
    feed_sm = snapshot.get("feed_state_machine") or {}
    feed_state_sm = str(feed_sm.get("state") or "").upper()
    if feed_state_sm in {"OK", "DEGRADED", "DOWN"}:
        feed_state = feed_state_sm
    else:
        feed_state, _reason, _ltp_age, _depth_age = _dashboard_feed_display_summary(snapshot)
    try:
        market_open = bool(canonical_market_open())
    except Exception:
        feed = snapshot.get("feed_freshness") or {}
        market_open = bool(feed.get("market_open", False))
    feed = snapshot.get("feed_freshness") or {}
    state = str(feed.get("state") or "").upper()
    market_status = "OPEN" if market_open and state != "MARKET_CLOSED" else "CLOSED"
    feed_status = "ACTIVE" if feed_state in ("OK", "DEGRADED") else "INACTIVE"
    should_refresh = should_trade_autorefresh(
        auto_refresh_enabled=bool(st.session_state.get("auto_refresh_enabled", False)),
        refresh_mode=str(st.session_state.get("trade_refresh_mode") or REFRESH_MODE_MARKET_OPEN_ONLY),
        feed_status=feed_status,
        market_status=market_status,
    )
    return should_refresh, feed_status, market_status


def _render_status_row(snapshot: dict):
    try:
        state = str(snapshot.get("state") or "UNKNOWN")
        phase = _market_phase_ist()
        if state == "MARKET_CLOSED" and phase == "PREMARKET":
            state = "PREMARKET"
        can_trade = snapshot.get("can_trade")
        feed_sm = snapshot.get("feed_state_machine") or {}
        feed_debug = snapshot.get("feed_debug") or {}
        auth_health = snapshot.get("auth_health") or {}
        feed_state_sm = str(feed_sm.get("state") or "").upper()
        feed_reason_sm = str(feed_sm.get("reason") or "").strip()
        if feed_state_sm in {"OK", "DEGRADED", "DOWN"}:
            feed_state = feed_state_sm
            feed_reason = feed_reason_sm or "state_machine"
            ltp_age = feed_sm.get("ws_msg_age_sec")
            depth_age = None
        else:
            feed_state, feed_reason, ltp_age, depth_age = _dashboard_feed_display_summary(snapshot)
        if phase == "PREMARKET" and feed_state == "DOWN" and "no_ws" in str(feed_reason).lower():
            feed_state = "IDLE"
            feed_reason = "premarket"
        sla_text = "LTP N/A | Depth N/A"
        if isinstance(ltp_age, (int, float)) or isinstance(depth_age, (int, float)):
            ltp_txt = f"{ltp_age:.1f}s" if isinstance(ltp_age, (int, float)) else "N/A"
            depth_txt = f"{depth_age:.1f}s" if isinstance(depth_age, (int, float)) else "N/A"
            sla_text = f"LTP {ltp_txt} | Depth {depth_txt}"
        auth_ok = bool(auth_health.get("ok", False))
        risk_ok = _log_path("risk_monitor.json").exists()
        review_ok = REVIEW_QUEUE_PATH.exists()
        exec_ok = (logs_dir() / "execution_analytics.json").exists()
        cols = st.columns(7)
        cols[0].caption(("✅" if can_trade else "❌") + f" Readiness: {state}")
        feed_icon = {"OK": "✅", "DEGRADED": "🟠", "DOWN": "❌", "STALE": "❌", "IDLE": "🟡"}.get(feed_state, "⬜")
        ws_src = str(feed_debug.get("ws_connected_source") or "unknown")
        ws_val = feed_debug.get("ws_connected")
        subs_count = feed_debug.get("subscribed_tokens_count")
        intended_count = feed_debug.get("intended_tokens_count")
        last_error = feed_debug.get("feed_runtime_last_error")
        ws_diag = f" | ws={ws_val} ({ws_src}) | subs={subs_count}/{intended_count}"
        if last_error:
            ws_diag += f" | err={str(last_error)[:60]}"
        cols[1].caption(f"{feed_icon} Feed: {feed_state} ({feed_reason}){ws_diag}")
        cols[2].caption(("✅" if auth_ok else "❌") + " Kite auth")
        cols[3].caption(("✅" if risk_ok else "⬜") + " Risk monitor")
        cols[4].caption(("✅" if review_ok else "⬜") + " Review queue")
        cols[5].caption(("✅" if exec_ok else "⬜") + " Exec analytics")
        cols[6].caption("🕒 " + sla_text)
    except Exception:
        pass


def _feed_banner_text(feed_state: str, feed_reason: str, strict_live: bool) -> str | None:
    state = str(feed_state or "").upper()
    reason = str(feed_reason or "n/a")
    if state == "DEGRADED":
        msg = "LIVE entries blocked; advisory only." if strict_live else "Monitoring mode; advisory/training flow continues."
        return f"Feed DEGRADED: {reason}. {msg}"
    if state == "DOWN":
        msg = "LIVE entries blocked and reconnect requested." if strict_live else "Reconnect requested; live gating not enforced in this mode."
        return f"Feed DOWN: {reason}. {msg}"
    return None


def _render_feed_health_banner(snapshot: dict):
    try:
        feed_sm = snapshot.get("feed_state_machine") or {}
        feed_state = str(feed_sm.get("state") or "").upper()
        feed_reason = str(feed_sm.get("reason") or "n/a")
        feed_debug = snapshot.get("feed_debug") or {}
        feed_freshness = snapshot.get("feed_freshness") or {}
        runtime_health = snapshot.get("runtime_health") or {}
        runtime_feed = runtime_health.get("feed") if isinstance(runtime_health.get("feed"), dict) else {}
        runtime_state = str(
            runtime_feed.get("runtime_state")
            or feed_debug.get("feed_runtime_state")
            or ""
        ).strip().upper()
        runtime_error = str(
            runtime_feed.get("last_error")
            or feed_debug.get("feed_runtime_last_error")
            or ""
        ).strip()
        allow_stale_quotes = bool(runtime_feed.get("allow_stale_quotes", feed_freshness.get("allow_stale_quotes", False)))
        ltp_required_raw = runtime_feed.get("ltp_required")
        if isinstance(ltp_required_raw, bool):
            ltp_required = ltp_required_raw
        else:
            ltp_required = bool(feed_freshness.get("market_open", False) and (not allow_stale_quotes))
        mode = str(runtime_health.get("mode") or getattr(cfg, "EXECUTION_MODE", "PAPER") or "PAPER").upper()
        strict_live = bool(mode == "LIVE" and ltp_required and (not allow_stale_quotes))
        phase = _market_phase_ist()
        if phase == "PREMARKET" and feed_state == "DOWN" and "no_ws" in feed_reason.lower():
            st.markdown(
                "<div class='banner warn'>Pre-market session (09:00-09:15 IST): waiting for live WS ticks. "
                "Trade suggestions/execution gates activate from 09:15 IST.</div>",
                unsafe_allow_html=True,
            )
            return
        banner_text = _feed_banner_text(feed_state, feed_reason, strict_live=strict_live)
        if banner_text:
            css_class = "warn" if feed_state == "DEGRADED" else "error"
            st.markdown(f"<div class='banner {css_class}'>{banner_text}</div>", unsafe_allow_html=True)
        if runtime_state in {"IMPORT_MISSING", "AUTH_BLOCKED", "SUBSCRIBE_FAILED"}:
            st.error(
                f"WebSocket runtime state={runtime_state}. "
                f"last_error={runtime_error or 'unknown'}"
            )
        try:
            ws_connected = feed_debug.get("ws_connected")
            intended = feed_debug.get("intended_tokens_count")
            subscribed = feed_debug.get("subscribed_tokens_count")
            subscribed_by_symbol = feed_debug.get("subscribed_tokens_count_by_symbol") or {}
            missing_option_tokens = feed_debug.get("missing_option_tokens_count")
            ltp_age = feed_debug.get("last_tick_age_sec")
            depth_age = feed_debug.get("last_depth_age_sec")
            last_error = feed_debug.get("feed_runtime_last_error")
            st.caption(
                "Feed runtime: "
                f"ws_connected={ws_connected} "
                f"tokens={subscribed}/{intended} "
                f"missing_option_tokens={missing_option_tokens} "
                f"last_tick_age={ltp_age} "
                f"last_depth_age={depth_age} "
                f"last_error={last_error or 'none'}"
            )
            if subscribed_by_symbol:
                st.caption(f"Token coverage by symbol: {subscribed_by_symbol}")
        except Exception:
            pass
    except Exception:
        pass

readiness_snapshot = _perf_timed_load("readiness_snapshot", _get_readiness_snapshot)
st.session_state["readiness_snapshot"] = readiness_snapshot
_render_status_row(readiness_snapshot)
_render_feed_health_banner(readiness_snapshot)
with st.expander("Feed Debug", expanded=False):
    try:
        rh_payload = readiness_snapshot.get("runtime_health") or {}
        rh_path = str(rh_payload.get("snapshot_path") or _log_path("runtime_health_latest.json"))
        rh_age = rh_payload.get("snapshot_age_sec")
        feed_debug_payload = readiness_snapshot.get("feed_debug") or {}
        freshness_payload = _load_freshness_latest()
        st.json(
            {
                "state_machine": readiness_snapshot.get("feed_state_machine") or {},
                "legacy_debug": feed_debug_payload,
                "cross_process_feed": {
                    "ws_connected": feed_debug_payload.get("ws_connected"),
                    "ws_connected_source": feed_debug_payload.get("ws_connected_source"),
                    "subscribed_tokens_count": feed_debug_payload.get("subscribed_tokens_count"),
                    "subscribed_tokens_count_by_symbol": feed_debug_payload.get("subscribed_tokens_count_by_symbol"),
                    "missing_option_tokens_count": feed_debug_payload.get("missing_option_tokens_count"),
                    "missing_option_tokens_count_by_symbol": feed_debug_payload.get("missing_option_tokens_count_by_symbol"),
                    "distinct_tokens_recent": feed_debug_payload.get("distinct_tokens_recent"),
                    "feed_runtime_db_age_sec": feed_debug_payload.get("feed_runtime_db_age_sec"),
                },
                "runtime_health_snapshot": {
                    "path": rh_path,
                    "snapshot_age_sec": rh_age,
                    "snapshot_ts_epoch": rh_payload.get("snapshot_ts_epoch", rh_payload.get("ts_epoch")),
                },
                "freshness_latest": freshness_payload,
            }
        )
    except Exception:
        st.caption("Feed debug unavailable.")

def _is_market_hours():
    return _market_phase_ist() == "OPEN"

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
    if is_offhours({"state": readiness_state}):
        return False
    return readiness_state in ("READY", "DEGRADED", "BLOCKED", "BOOTING")


def _truncate_live_quote_errors_log() -> bool:
    """Best-effort truncate for live quote error log."""
    try:
        log_path = _log_path("live_quote_errors.jsonl")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8"):
            pass
        return True
    except Exception:
        return False

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
    path = resolve_trade_log_path(LOG_PATH)
    rows = _load_trade_log_rows(path)
    count = 0
    for obj in rows:
        if obj.get("actual") is not None:
            count += 1
    return count


def _suggestion_reliability_snapshot() -> dict:
    try:
        from config import config as cfg  # local import to avoid import-order side effects

        latest_path = Path(
            str(
                getattr(
                    cfg,
                    "SUGGESTION_RELIABILITY_LATEST_PATH",
                    str(_log_path("suggestion_reliability_latest.json")),
                )
            )
        )
    except Exception:
        latest_path = _log_path("suggestion_reliability_latest.json")

    payload = _read_json(latest_path)
    status = str(payload.get("status") or "UNKNOWN").upper()
    try:
        allowed = int(payload.get("allowed_count") or 0)
    except Exception:
        allowed = 0
    try:
        candidates = int(payload.get("candidate_count") or 0)
    except Exception:
        candidates = 0
    try:
        min_allowed = int(payload.get("min_allowed") or 20)
    except Exception:
        min_allowed = 20
    return {
        "path": str(latest_path),
        "exists": bool(latest_path.exists()),
        "status": status,
        "allowed_count": allowed,
        "candidate_count": candidates,
        "min_allowed": max(1, min_allowed),
        "mode": str(payload.get("mode") or ""),
        "window_sec": payload.get("window_sec"),
        "reason_codes": list(payload.get("reason_codes") or []),
    }


def _render_confidence_reliability():
    try:
        from config import config as cfg
        needed = getattr(cfg, "ML_MIN_TRAIN_TRADES", 200)
    except Exception:
        needed = 200
    labeled = _ml_label_count()
    label_ratio = min(1.0, labeled / max(1, needed))
    label_status = "READY" if labeled >= needed else "LOW_SAMPLE"
    label_color = "#23c55e" if labeled >= needed else "#f59e0b"

    reliability = _suggestion_reliability_snapshot()
    allowed = int(reliability.get("allowed_count") or 0)
    candidates = int(reliability.get("candidate_count") or 0)
    min_allowed = int(reliability.get("min_allowed") or 20)
    sample_ratio = min(1.0, allowed / max(1, min_allowed))
    sample_status = "READY" if allowed >= min_allowed else "LOW_SAMPLE"
    sample_color = "#23c55e" if allowed >= min_allowed else "#f59e0b"
    rel_status = str(reliability.get("status") or "UNKNOWN")

    left, right = st.columns(2)
    with left:
        st.markdown(
            f"""<div style='display:flex;align-items:center;gap:10px;'>
            <div style='font-size:0.95rem;color:#a3b3c5;'>ML Label Coverage</div>
            <div style='padding:4px 10px;border-radius:999px;background:{label_color};color:#0b0f14;font-weight:700;font-size:0.85rem;'>{label_status}</div>
            <div style='color:#a3b3c5;font-size:0.85rem;'>{labeled}/{needed} labeled</div>
            </div>""",
            unsafe_allow_html=True,
        )
        st.progress(label_ratio)
    with right:
        st.markdown(
            f"""<div style='display:flex;align-items:center;gap:10px;'>
            <div style='font-size:0.95rem;color:#a3b3c5;'>Suggestion Reliability Sample</div>
            <div style='padding:4px 10px;border-radius:999px;background:{sample_color};color:#0b0f14;font-weight:700;font-size:0.85rem;'>{sample_status}</div>
            <div style='color:#a3b3c5;font-size:0.85rem;'>{allowed}/{min_allowed} allowed ({candidates} candidates)</div>
            </div>""",
            unsafe_allow_html=True,
        )
        st.progress(sample_ratio)
        st.caption(f"Latest status: {rel_status}")
        reasons = list(reliability.get("reason_codes") or [])
        if reasons:
            st.caption(f"Reason: {', '.join(str(x) for x in reasons)}")

def _render_market_snapshot():
    try:
        from config import config as cfg
    except Exception as e:
        st.error(f"Market data error: {e}")
        return
    snapshot_vm = _perf_timed_load("market_snapshot_artifact", get_market_snapshot_view_model)
    snapshot_state = str(snapshot_vm.get("state") or "invalid")
    snapshot_age = snapshot_vm.get("age_sec")
    snapshot_warnings = list(snapshot_vm.get("warnings") or [])
    symbols_payload = dict(snapshot_vm.get("symbols") or {})
    market_mode = str(snapshot_vm.get("market_mode") or "UNKNOWN")
    market_open = bool(snapshot_vm.get("market_open"))
    cols = st.columns(3)
    symbols = {
        "NIFTY 50": ("NIFTY", cfg.PREMARKET_INDICES_LTP.get("NIFTY", "NSE:NIFTY 50")),
        "BANKNIFTY": ("BANKNIFTY", cfg.PREMARKET_INDICES_LTP.get("BANKNIFTY", "NSE:BANKNIFTY")),
        "SENSEX": ("SENSEX", "BSE:SENSEX"),
    }
    reg_map = {
        symbol: {
            "regime": ((payload.get("regime") or {}).get("trend")) or "UNKNOWN",
            "confidence": ((payload.get("regime") or {}).get("confidence")),
            "volatility_state": ((payload.get("regime") or {}).get("volatility_state")),
        }
        for symbol, payload in symbols_payload.items()
        if isinstance(payload, dict)
    }
    if reg_map:
        lines = []
        for sym, info in reg_map.items():
            conf_txt = "n/a"
            try:
                if info.get("confidence") is not None:
                    conf_txt = f"{float(info.get('confidence')):.2f}"
            except Exception:
                conf_txt = "n/a"
            lines.append(f"{sym}: {info.get('regime')} (conf={conf_txt})")
        st.caption("Model regime: " + " | ".join(lines))

    if snapshot_state == "missing":
        st.warning("Market snapshot artifact missing. Dashboard is read-only and will not recompute it.")
    elif snapshot_state == "invalid":
        st.error(
            "Market snapshot artifact invalid. Dashboard is read-only and will not repair it."
        )
    elif snapshot_state == "stale":
        age_txt = f"{float(snapshot_age):.1f}s" if isinstance(snapshot_age, (int, float)) else "n/a"
        st.warning(f"Market snapshot is stale ({age_txt}). Showing last completed engine snapshot.")
    else:
        age_txt = f"{float(snapshot_age):.1f}s" if isinstance(snapshot_age, (int, float)) else "n/a"
        st.caption(f"Snapshot: {snapshot_state} | Mode {market_mode} | Open {market_open} | Age {age_txt}")
    if snapshot_warnings:
        st.caption("Snapshot warnings: " + " | ".join(str(item) for item in snapshot_warnings[:6]))

    # Feed freshness badge (canonical SLA snapshot)
    try:
        snap = st.session_state.get("readiness_snapshot") or {}
        feed_state, feed_reason, ltp_age, depth_age = _dashboard_feed_display_summary(snap)
        ltp_txt = f"{ltp_age:.1f}s" if isinstance(ltp_age, (int, float)) else "N/A"
        depth_txt = f"{depth_age:.1f}s" if isinstance(depth_age, (int, float)) else "N/A"
        st.caption(f"Feed: {feed_state} ({feed_reason}) | LTP age {ltp_txt} | Depth age {depth_txt}")
    except Exception:
        pass

    if not symbols_payload:
        st.caption("Market snapshot data unavailable from prebuilt artifacts.")

    for i, (label, (sym_key, sym)) in enumerate(symbols.items()):
        del sym
        symbol_payload = symbols_payload.get(sym_key) if isinstance(symbols_payload.get(sym_key), dict) else {}
        ohlc = symbol_payload.get("ohlc") if isinstance(symbol_payload.get("ohlc"), dict) else {}
        regime = symbol_payload.get("regime") if isinstance(symbol_payload.get("regime"), dict) else {}
        feed_health = symbol_payload.get("feed_health") if isinstance(symbol_payload.get("feed_health"), dict) else {}
        option_chain_summary = (
            symbol_payload.get("option_chain_summary")
            if isinstance(symbol_payload.get("option_chain_summary"), dict)
            else {}
        )
        price = None
        change = None
        pct = None
        try:
            price = symbol_payload.get("ltp", symbol_payload.get("spot"))
            prev_close = ohlc.get("close")
            if isinstance(prev_close, (int, float)) and isinstance(price, (int, float)):
                change = float(price) - float(prev_close)
                pct = (change / float(prev_close)) * 100.0 if float(prev_close) else None
        except Exception:
            price = None
        delta = None
        if isinstance(change, (int, float)) and isinstance(pct, (int, float)):
            delta = f"{change:+.2f} ({pct:+.2f}%)"
        with cols[i]:
            st.markdown("<div class='market-card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='market-card-title'>{label}</div>", unsafe_allow_html=True)
            st.metric(label, f"{price:.2f}" if isinstance(price, (int, float)) else "N/A", delta)
            if regime.get("trend"):
                st.markdown(
                    f"<div class='market-card-sub'>Model regime: {regime.get('trend')}</div>",
                    unsafe_allow_html=True,
                )
            if regime.get("volatility_state"):
                st.markdown(
                    (
                        "<div class='market-card-sub'>Volatility state: "
                        f"{regime.get('volatility_state')} (conf {fmt_conf(regime.get('confidence'))})"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
            if option_chain_summary.get("chain_quality"):
                st.caption(f"Chain quality: {option_chain_summary.get('chain_quality')}")
            if option_chain_summary.get("atm_strike") is not None:
                st.caption(f"ATM strike: {option_chain_summary.get('atm_strike')}")
            if feed_health.get("status"):
                uq_age = feed_health.get("underlying_quote_age_sec")
                oq_age = feed_health.get("option_quote_age_sec")
                uq_txt = f"{float(uq_age):.1f}s" if isinstance(uq_age, (int, float)) else "n/a"
                oq_txt = f"{float(oq_age):.1f}s" if isinstance(oq_age, (int, float)) else "n/a"
                st.caption(
                    f"Feed: {feed_health.get('status')} | Underlying {uq_txt} | Option {oq_txt}"
                )
            st.markdown("</div>", unsafe_allow_html=True)

if hasattr(st, "fragment"):
    @st.fragment(run_every=5)
    def _market_snapshot_fragment():
        _perf_timed_render("market_snapshot_fragment", _render_market_snapshot)
else:
    def _market_snapshot_fragment():
        _perf_timed_render("market_snapshot_fragment", _render_market_snapshot)

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
        md = _fetch_live_market_data_dashboard("chain_map", allow_stale_cache=True)
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
                    "lot_size": inst.get("lot_size"),
                }
        st.session_state["instrument_meta_map"] = meta
        st.session_state["instrument_meta_map_ts"] = time.time()
        return meta
    except Exception:
        return {}

def _coerce_date_only(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.fromisoformat(text).date()
    except Exception:
        return None

def _with_expiry_dte(df, meta_map=None):
    if "expiry_date" not in df.columns:
        df["expiry_date"] = None
    if "expiry" in df.columns:
        df["expiry_date"] = df["expiry_date"].where(df["expiry_date"].notna(), df["expiry"])
    if meta_map and "instrument_token" in df.columns:
        def _fill(row):
            if row.get("expiry_date"):
                return row.get("expiry_date")
            tok = row.get("instrument_token")
            meta = meta_map.get(tok) if tok is not None else None
            return meta.get("expiry") if isinstance(meta, dict) else None
        df["expiry_date"] = df.apply(_fill, axis=1)
    df["dte"] = df["expiry_date"].apply(lambda v: (_coerce_date_only(v) - datetime.now().date()).days if _coerce_date_only(v) else None)
    return df

def _ensure_activation_fields(df):
    if df is None or df.empty:
        return df
    if "status" not in df.columns:
        df["status"] = "PLANNING"
    else:
        df["status"] = df["status"].fillna("PLANNING")
    if "entry_condition" not in df.columns:
        df["entry_condition"] = "BREAKOUT"
    else:
        df["entry_condition"] = df["entry_condition"].fillna("BREAKOUT")
    for col in (
        "activated_ts",
        "fill_price",
        "ltp_at_activation",
        "activation_price",
        "activation_reason",
        "invalidation_reason",
        "activation_feed_state",
        "activation_quote_age_sec",
        "activation_spread_pct",
        "activation_gate_reason",
        "activation_ui_flag",
        "activation_advisory",
        "activation_manual_override_used",
    ):
        if col not in df.columns:
            df[col] = None
    return df


def _contract_resolved(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("instrument") or "").upper() != "OPT":
        return True
    if row.get("tradable") is False:
        return False
    reasons = row.get("tradable_reasons_blocking") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    elif not isinstance(reasons, (list, tuple, set)):
        reasons = []
    if "unresolved_contract" in reasons:
        return False
    if not row.get("instrument_token") and not row.get("instrument_id"):
        return False
    if not (row.get("expiry_date") or row.get("expiry")):
        return False
    return True


def _mask_unresolved_prices(df, fields=None):
    if df is None or df.empty:
        return df
    if fields is None:
        fields = ["entry", "stop", "target", "target_points", "target_premium", "stop_premium"]

    def _mask(row):
        try:
            row_dict = row.to_dict()
        except Exception:
            row_dict = row
        if not _contract_resolved(row_dict):
            for field in fields:
                if field in row:
                    row[field] = None
        return row

    try:
        return df.apply(_mask, axis=1)
    except Exception:
        return df


def _resolve_opt_ltp(row: dict):
    ltp = row.get("current_ltp")
    if ltp is None:
        ltp = row.get("opt_ltp")
    if ltp is None:
        ltp = row.get("mark_price")
    if ltp is None:
        ltp = row.get("suggested_entry")
    if ltp is None:
        bid = row.get("opt_bid")
        ask = row.get("opt_ask")
        try:
            if bid is not None and ask is not None:
                ltp = (float(bid) + float(ask)) / 2.0
        except Exception:
            ltp = None
    return _safe_float(ltp)


def _derive_target_from_entry_stop(entry_val: float, stop_val: float, side: str, rr: float) -> float | None:
    try:
        entry_f = float(entry_val)
        stop_f = float(stop_val)
        rr_f = float(rr)
    except Exception:
        return None
    risk = abs(entry_f - stop_f)
    if risk <= 0:
        return None
    side_val = str(side or "").upper()
    if side_val == "SELL":
        target = entry_f - (risk * rr_f)
    else:
        target = entry_f + (risk * rr_f)
    if target <= 0:
        return None
    return round(float(target), 2)


def _ensure_targets(df, rr_default: float) -> tuple[pd.DataFrame, dict[str, float]]:
    if df is None or df.empty:
        return df, {}
    if "target" not in df.columns:
        df["target"] = None
    if "target_derived" not in df.columns:
        df["target_derived"] = False
    if "target_rr" not in df.columns:
        df["target_rr"] = None
    derived_targets: dict[str, float] = {}
    for idx, row in df.iterrows():
        if row.get("target") not in (None, "", "None"):
            continue
        entry_val = _safe_float(row.get("entry"))
        stop_val = _safe_float(row.get("stop"))
        side_val = row.get("side")
        if entry_val is None or stop_val is None:
            continue
        target_val = _derive_target_from_entry_stop(entry_val, stop_val, side_val, rr_default)
        if target_val is None:
            continue
        df.at[idx, "target"] = target_val
        df.at[idx, "target_derived"] = True
        df.at[idx, "target_rr"] = rr_default
        trade_id = row.get("trade_id")
        if trade_id:
            derived_targets[str(trade_id)] = float(target_val)
    return df, derived_targets


def _persist_queue_targets(path: Path, q_all: list[dict], derived_targets: dict[str, float], rr_default: float) -> bool:
    if not derived_targets or not q_all:
        return False
    updated = False
    for entry in q_all:
        tid = entry.get("trade_id")
        if not tid or str(tid) not in derived_targets:
            continue
        if entry.get("target") not in (None, "", "None"):
            continue
        entry["target"] = float(derived_targets[str(tid)])
        entry["target_derived"] = True
        entry["target_rr"] = rr_default
        updated = True
    if updated:
        try:
            path.write_text(json.dumps(q_all, indent=2))
        except Exception:
            return False
    return updated


def _add_live_pnl_columns(df, meta_map=None):
    if df is None or df.empty:
        return df
    for col in ("live_ltp", "pnl_1qty", "pnl_1lot", "pnl_reason", "pnl_status_reason", "pnl_points", "pnl_cash"):
        if col not in df.columns:
            df[col] = None
    for idx, row in df.iterrows():
        row_dict = row.to_dict()
        if not _contract_resolved(row_dict):
            df.at[idx, "live_ltp"] = "N/A"
            df.at[idx, "pnl_1qty"] = "N/A"
            df.at[idx, "pnl_1lot"] = "N/A"
            df.at[idx, "pnl_reason"] = "unresolved_contract"
            df.at[idx, "pnl_status_reason"] = "unresolved_contract"
            continue
        ltp = row_dict.get("live_ltp")
        if ltp is None:
            ltp = _resolve_opt_ltp(row_dict)
        if ltp is None and row_dict.get("current_ltp") is not None:
            ltp = row_dict.get("current_ltp")
        df.at[idx, "live_ltp"] = ltp
        status = str(row_dict.get("status") or "PLANNING").upper()
        if status != "ACTIVE":
            df.at[idx, "pnl_1qty"] = "—"
            df.at[idx, "pnl_1lot"] = "—"
            df.at[idx, "pnl_reason"] = "inactive"
            df.at[idx, "pnl_status_reason"] = "inactive"
            df.at[idx, "pnl_points"] = "—"
            df.at[idx, "pnl_cash"] = "—"
            continue
        row_dict["live_ltp"] = ltp
        pnl = compute_row_live_pnl(row_dict, meta_map=meta_map)
        df.at[idx, "pnl_reason"] = pnl.get("pnl_reason")
        reason_map = {
            "missing_ltp": "no_ltp",
            "missing_fill_price": "no_fill_price",
            "invalid_side": "invalid_side",
            "inactive": "inactive",
        }
        pnl_reason = pnl.get("pnl_reason")
        df.at[idx, "pnl_status_reason"] = reason_map.get(pnl_reason, pnl_reason)
        if pnl.get("pnl_1qty") is None:
            df.at[idx, "pnl_1qty"] = "—"
        else:
            df.at[idx, "pnl_1qty"] = pnl.get("pnl_1qty")
        if pnl.get("pnl_1lot") is None:
            df.at[idx, "pnl_1lot"] = "—"
        else:
            df.at[idx, "pnl_1lot"] = pnl.get("pnl_1lot")
        try:
            fill = float(row_dict.get("activation_price") or row_dict.get("fill_price"))
            ltp_val = float(ltp) if ltp is not None else None
        except Exception:
            fill = None
            ltp_val = None
        side_val = str(row_dict.get("side") or "").upper()
        if fill is None or ltp_val is None or side_val not in ("BUY", "SELL"):
            df.at[idx, "pnl_points"] = "—"
            df.at[idx, "pnl_cash"] = "—"
        else:
            pnl_points = (ltp_val - fill) if side_val == "BUY" else (fill - ltp_val)
            df.at[idx, "pnl_points"] = round(float(pnl_points), 2)
            lot_size = pnl.get("lot_size")
            if lot_size:
                df.at[idx, "pnl_cash"] = round(float(pnl_points) * float(lot_size), 2)
            else:
                df.at[idx, "pnl_cash"] = "—"
    return df


def _select_speed_trader_cols(df: pd.DataFrame, extra_cols: list[str] | None = None) -> list[str]:
    cols = [c for c in SPEED_TRADER_COLS if c in df.columns]
    if extra_cols:
        for col in extra_cols:
            if col in df.columns and col not in cols:
                cols.append(col)
    return cols


def _cap_unknown_regime_advisory(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if "regime" not in df.columns:
        return df
    max_per_symbol = int(getattr(cfg, "PERMISSION_UNKNOWN_REGIME_MAX_PER_SYMBOL", 2))
    max_total = int(getattr(cfg, "PERMISSION_UNKNOWN_REGIME_MAX_TOTAL", 6))
    if max_per_symbol <= 0 or max_total <= 0:
        return df.head(0)
    regime_series = df["regime"].fillna("").astype(str).str.upper()
    regime_conf = pd.to_numeric(df.get("regime_confidence"), errors="coerce").fillna(
        pd.to_numeric(df.get("day_confidence"), errors="coerce").fillna(0.0)
    )
    mask = (regime_series == "UNKNOWN") & (regime_conf < 0.35)
    if not mask.any():
        return df
    subset = df[mask].copy()
    if "permission" in subset.columns:
        subset = subset[subset["permission"].fillna("").astype(str).str.upper() == "ADVISORY_ONLY"]
    if "global_confidence" in subset.columns:
        subset = subset.sort_values("global_confidence", ascending=False)
    if "symbol" in subset.columns:
        subset = subset.groupby("symbol", as_index=False).head(max_per_symbol)
    subset = subset.head(max_total)
    other = df[~mask]
    if other.empty:
        return subset
    merged = _concat_frames_safely([other, subset])
    if merged.empty:
        return merged
    if "timestamp" in merged.columns:
        return merged.sort_values("timestamp", ascending=False)
    return merged


def _render_upstox_table(table_df: pd.DataFrame, display_cols: list[str], key_prefix: str):
    if table_df is None or table_df.empty:
        return
    cols = [c for c in display_cols if c in table_df.columns]
    display = table_df[cols].copy()
    for col in display.columns:
        is_date = pd.api.types.is_datetime64_any_dtype(display[col])
        if not is_date and isinstance(col, str) and any(x in col.lower() for x in ("_ts", "ts_", "timestamp", "time", "_utc")):
            is_date = True
            
        if is_date:
            dt_col = pd.to_datetime(display[col], errors="coerce")
            try:
                if dt_col.dt.tz is None:
                    dt_col = dt_col.dt.tz_localize("UTC")
                display[col] = dt_col.dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d %H:%M:%S IST")
            except Exception:
                display[col] = dt_col.dt.strftime("%Y-%m-%d %H:%M:%S")
        display[col] = display[col].apply(_table_display_cell)
    use_container_width = bool(getattr(cfg, "UI_TABLE_USE_CONTAINER_WIDTH", False))
    st.dataframe(
        display,
        use_container_width=use_container_width,
        hide_index=True,
        height=min(650, 42 * (len(display) + 1)),
    )


_DISPLAY_NULL_MARKERS = {"", "NONE", "NAN", "NAT", "NULL", "N/A", "NA"}


def _table_display_cell(value):
    try:
        if value is None:
            return "—"
        if isinstance(value, float) and math.isnan(value):
            return "—"
    except Exception:
        pass
    text = str(value).strip()
    if text.upper() in _DISPLAY_NULL_MARKERS:
        return "—"
    return value


def _zero_to_hero_display_columns(df):
    return _select_speed_trader_cols(
        df,
        [
            "premium",
            "pnl_1lot",
            "pnl_status_reason",
            "ui_warning",
            "note",
        ],
    )

def _ensure_trailing_fields(df):
    if df is None or df.empty:
        return df
    for col in (
        "original_stop",
        "trail_enabled",
        "trail_offset",
        "trail_rule",
        "trail_start",
        "mfe_price",
        "trail_stop",
        "current_stop",
        "last_update_ts",
        "exit_signal",
        "exit_reason",
        "exit_price",
        "exit_ts",
        "pnl_estimate_1lot",
        "profit_locked",
    ):
        if col not in df.columns:
            df[col] = None
    return df


def _calc_trail_offset(row, min_offset, risk_mult):
    try:
        min_off = float(min_offset)
    except Exception:
        min_off = 5.0
    try:
        mult = float(risk_mult)
    except Exception:
        mult = 0.5
    entry = _safe_float(row.get("fill_price") or row.get("entry"))
    stop = _safe_float(row.get("original_stop") or row.get("stop"))
    if entry is None or stop is None:
        return max(min_off, 5.0)
    risk = abs(entry - stop)
    return max(min_off, risk * mult)


def _activate_planning_rows(df, auto_activate=False):
    if df is None or df.empty:
        return df, False, []
    df = _ensure_activation_fields(df)
    if not auto_activate:
        return df, False, []
    updated = False
    activated_rows = []
    now_ts = datetime.now(timezone.utc).isoformat()
    max_quote_age = float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0))
    max_spread_pct = float(getattr(cfg, "MAX_SPREAD_PCT", 0.03))
    for idx, row in df.iterrows():
        status = str(row.get("status") or "PLANNING").upper()
        if status != "PLANNING":
            continue
        if not row.get("instrument_token"):
            continue
        ltp = row.get("current_ltp")
        if ltp is None:
            ltp = row.get("opt_ltp")
        mark_price = row.get("mark_price")
        if ltp is None:
            ltp = mark_price
        if ltp is None:
            bid = row.get("opt_bid")
            ask = row.get("opt_ask")
            try:
                if bid is not None and ask is not None:
                    ltp = (float(bid) + float(ask)) / 2.0
            except Exception:
                ltp = None
        if ltp is None:
            continue
        try:
            age_sec = _safe_float(row.get("price_age_sec"))
            if age_sec is None:
                age_sec = _safe_float(row.get("quote_age_sec"))
            # When quote hydration supplies current bid/ask/ltp without explicit age,
            # treat it as current for this render pass.
            if age_sec is None:
                age_sec = 0.0
            if age_sec > max_quote_age:
                continue
        except Exception:
            continue
        spread_pct = None
        try:
            bid_val = _safe_float(row.get("opt_bid"))
            ask_val = _safe_float(row.get("opt_ask"))
            base_val = _safe_float(mark_price) or _safe_float(ltp)
            if (
                bid_val is not None
                and ask_val is not None
                and base_val is not None
                and base_val > 0
            ):
                spread_pct = (ask_val - bid_val) / base_val
                if spread_pct > max_spread_pct:
                    continue
        except Exception:
            pass
        if _safe_float(mark_price) in (None, 0.0) and _safe_float(ltp) in (None, 0.0):
            continue
        advisory_only = str(row.get("permission") or "").strip().upper() == "ADVISORY_ONLY"
        can_activate, signal = should_activate(
            row.get("side"),
            row.get("entry_condition"),
            row.get("entry"),
            ltp,
            execution_mode=str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").upper(),
            advisory=bool(advisory_only),
            quote_age_sec=age_sec,
            spread_pct=spread_pct,
            return_signal=True,
        )
        df.at[idx, "activation_feed_state"] = signal.get("feed_state")
        df.at[idx, "activation_quote_age_sec"] = signal.get("quote_age_sec")
        df.at[idx, "activation_spread_pct"] = signal.get("spread_pct")
        df.at[idx, "activation_gate_reason"] = signal.get("reason")
        df.at[idx, "activation_ui_flag"] = signal.get("ui_flag")
        df.at[idx, "activation_advisory"] = bool(signal.get("advisory"))
        df.at[idx, "activation_manual_override_used"] = bool(signal.get("manual_override_used"))
        if not can_activate:
            df.at[idx, "activation_reason"] = signal.get("reason")
            continue
        if can_activate:
            updated_row = activate_trade(row.to_dict(), ltp, ts=now_ts, activation_signal=signal)
            df.at[idx, "status"] = updated_row.get("status")
            df.at[idx, "activated_ts"] = updated_row.get("activated_ts")
            df.at[idx, "fill_price"] = updated_row.get("fill_price")
            df.at[idx, "ltp_at_activation"] = updated_row.get("ltp_at_activation")
            df.at[idx, "activation_feed_state"] = updated_row.get("activation_feed_state")
            df.at[idx, "activation_quote_age_sec"] = updated_row.get("activation_quote_age_sec")
            df.at[idx, "activation_spread_pct"] = updated_row.get("activation_spread_pct")
            df.at[idx, "activation_gate_reason"] = updated_row.get("activation_gate_reason")
            df.at[idx, "activation_ui_flag"] = updated_row.get("activation_ui_flag")
            df.at[idx, "activation_advisory"] = updated_row.get("activation_advisory")
            df.at[idx, "activation_manual_override_used"] = updated_row.get("activation_manual_override_used")
            df.at[idx, "activation_reason"] = "ENTRY_TRIGGERED"
            updated = True
            activated_rows.append(updated_row)
    return df, updated, activated_rows


def _persist_queue_activation(path: Path, rows: list[dict], df: pd.DataFrame):
    if not rows:
        return False
    updated = False
    for row in rows:
        if not row.get("status"):
            row["status"] = "PLANNING"
            updated = True
        if not row.get("entry_condition"):
            row["entry_condition"] = "BREAKOUT"
            updated = True
    if df is None or df.empty or "trade_id" not in df.columns:
        if updated:
            path.write_text(json.dumps(rows, indent=2))
        return updated
    df_map = {str(r.get("trade_id")): r for r in df.to_dict("records") if r.get("trade_id")}
    for row in rows:
        tid = row.get("trade_id")
        if not tid:
            continue
        rec = df_map.get(str(tid))
        if not rec:
            continue
        for field in (
            "status",
            "entry_condition",
            "activated_ts",
            "activation_price",
            "fill_price",
            "ltp_at_activation",
            "activation_feed_state",
            "activation_quote_age_sec",
            "activation_spread_pct",
            "activation_gate_reason",
            "activation_ui_flag",
            "activation_advisory",
            "activation_manual_override_used",
            "activation_reason",
            "current_ltp",
            "current_ltp_ts",
            "price_age_sec",
            "original_stop",
            "trail_enabled",
            "trail_offset",
            "mfe_price",
            "trail_stop",
            "last_update_ts",
            "exit_signal",
            "exit_reason",
            "exit_price",
            "exit_ts",
            "pnl_estimate_1lot",
            "pnl_points",
            "pnl_cash",
        ):
            if rec.get(field) is None:
                continue
            if row.get(field) != rec.get(field):
                row[field] = rec.get(field)
                updated = True
    if updated:
        path.write_text(json.dumps(rows, indent=2))
    return updated


def _log_activation_events(rows: list[dict], queue_name: str):
    if not rows:
        return
    try:
        path = _log_path("activation_events.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            for row in rows:
                payload = {
                    "timestamp": row.get("activated_ts") or datetime.now(timezone.utc).isoformat(),
                    "trade_id": row.get("trade_id"),
                    "symbol": row.get("symbol"),
                    "side": row.get("side"),
                    "entry": row.get("entry"),
                    "fill_price": row.get("fill_price"),
                    "ltp_at_activation": row.get("ltp_at_activation"),
                    "queue": queue_name,
                }
                f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _log_trailing_events(rows: list[dict], queue_name: str):
    if not rows:
        return
    try:
        path = _log_path("trailing_events.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            for row in rows:
                f.write(json.dumps({**row, "queue": queue_name}) + "\n")
    except Exception:
        pass


def _apply_trailing(df, queue_name, path, rows, trail_enabled, min_offset, risk_mult, is_live_mode):
    if df is None or df.empty:
        return df, False
    df = _ensure_trailing_fields(df)
    if not trail_enabled:
        return df, False
    updated = False
    events = []
    now_ts = datetime.now(timezone.utc).isoformat()
    for idx, row in df.iterrows():
        status = str(row.get("status") or "PLANNING").upper()
        if status != "ACTIVE":
            continue
        if not row.get("instrument_token"):
            continue
        ltp = row.get("opt_ltp")
        if ltp is None:
            bid = row.get("opt_bid")
            ask = row.get("opt_ask")
            try:
                if bid is not None and ask is not None:
                    ltp = (float(bid) + float(ask)) / 2.0
            except Exception:
                ltp = None
        if ltp is None:
            continue
        trade = row.to_dict()
        if trade.get("original_stop") is None and trade.get("stop") is not None:
            trade["original_stop"] = _safe_float(trade.get("stop"))
        trade["trail_enabled"] = bool(trade.get("trail_enabled", True))
        if trade.get("trail_offset") is None:
            trade["trail_offset"] = _calc_trail_offset(trade, min_offset, risk_mult)
        before_stop = trade.get("stop")
        before_mfe = trade.get("mfe_price")
        before_trail = trade.get("trail_stop")
        trade = init_trailing(trade)
        trade = update_trailing(trade, ltp)
        should_exit, reason = check_exit(trade, ltp)
        if should_exit:
            trade["exit_signal"] = True
            trade["exit_reason"] = reason or "TRAIL_STOP"
            trade["exit_price"] = _safe_float(ltp)
            trade["exit_ts"] = now_ts
            if not is_live_mode:
                trade["status"] = "RESOLVED"
        try:
            lot = trade.get("lot_size")
            if lot is None:
                from core.sim_pnl import resolve_lot_size
                lot, _src, _fb = resolve_lot_size(trade)
            if lot:
                fill = _safe_float(trade.get("fill_price"))
                ltp_val = _safe_float(ltp)
                side = str(trade.get("side") or "").upper()
                if fill is not None and ltp_val is not None:
                    pnl = (ltp_val - fill) * float(lot)
                    if side == "SELL":
                        pnl = (fill - ltp_val) * float(lot)
                    trade["pnl_estimate_1lot"] = round(pnl, 2)
        except Exception:
            pass
        for field in (
            "original_stop",
            "trail_enabled",
            "trail_offset",
            "mfe_price",
            "trail_stop",
            "stop",
            "last_update_ts",
            "exit_signal",
            "exit_reason",
            "exit_price",
            "exit_ts",
            "status",
            "pnl_estimate_1lot",
        ):
            if field in trade:
                df.at[idx, field] = trade.get(field)
        changed = (
            trade.get("stop") != before_stop
            or trade.get("mfe_price") != before_mfe
            or trade.get("trail_stop") != before_trail
            or bool(trade.get("exit_signal"))
        )
        if changed:
            events.append(
                {
                    "timestamp": now_ts,
                    "trade_id": trade.get("trade_id"),
                    "symbol": trade.get("symbol"),
                    "side": trade.get("side"),
                    "status": trade.get("status"),
                    "mfe_price": trade.get("mfe_price"),
                    "trail_stop": trade.get("trail_stop"),
                    "stop": trade.get("stop"),
                    "exit_signal": trade.get("exit_signal"),
                    "exit_reason": trade.get("exit_reason"),
                }
            )
            updated = True
    if updated:
        _persist_queue_activation(path, rows, df)
        _log_trailing_events(events, queue_name)
    return df, updated

def _get_daytype_history(symbol, max_points=60):
    started = time.perf_counter()
    try:
        cache_key = f"daytype_hist_{symbol}"
        cache_ts_key = f"{cache_key}_ts"
        cache = st.session_state.get(cache_key)
        ts = st.session_state.get(cache_ts_key, 0)
        if cache and (time.time() - ts) < 60:
            logger.info(
                "dashboard_data_load label=daytype_history_cache_hit symbol=%s dt_ms=0.00 points=%d",
                symbol,
                len(list(cache or [])),
            )
            return cache
    except Exception:
        pass
    hist = []
    try:
        rows = _perf_timed_load(
            "daytype_history_rows",
            _fetch_day_type_events_dashboard,
            caller=f"daytype_history:{symbol}",
            max_rows=5000,
        )
        for obj in rows:
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
    elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
    logger.info(
        "dashboard_data_load label=daytype_history_build symbol=%s dt_ms=%.2f points=%d",
        symbol,
        elapsed_ms,
        len(hist),
    )
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


def _derive_mark_price(last_price, bid, ask, quote_age_sec=None):
    last_val = _safe_float(last_price)
    bid_val = _safe_float(bid)
    ask_val = _safe_float(ask)
    mid_val = None
    if bid_val is not None and ask_val is not None:
        mid_val = (bid_val + ask_val) / 2.0
    outside_tol = float(getattr(cfg, "OPTION_LAST_OUTSIDE_BAND_PCT", 0.01))
    outside_band = False
    if last_val is not None and bid_val is not None and ask_val is not None:
        lo = min(bid_val, ask_val) * max(0.0, 1.0 - outside_tol)
        hi = max(bid_val, ask_val) * (1.0 + outside_tol)
        outside_band = bool(last_val < lo or last_val > hi)
    stale = False
    try:
        stale = quote_age_sec is None or float(quote_age_sec) > float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8))
    except Exception:
        stale = quote_age_sec is None
    if mid_val is not None and (outside_band or stale or last_val is None):
        return mid_val, "mid"
    if last_val is not None:
        return last_val, "last"
    if ask_val is not None:
        return ask_val, "ask"
    if bid_val is not None:
        return bid_val, "bid"
    if mid_val is not None:
        return mid_val, "mid"
    return None, "none"


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
        if "mark_price" not in df.columns:
            df["mark_price"] = None
        if "price_source" not in df.columns:
            df["price_source"] = None
        if "quote_age_sec" not in df.columns:
            df["quote_age_sec"] = None
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
                df.at[idx, "quote_note"] = "strike not in cached chain"
                continue
            df.at[idx, "opt_ltp"] = match.get("ltp")
            bid = match.get("best_bid", match.get("bid"))
            ask = match.get("best_ask", match.get("ask"))
            quote_age_sec = match.get("quote_age_sec")
            mark_price = match.get("mark_price")
            if mark_price in (None, "", 0):
                mark_price, source = _derive_mark_price(match.get("last_price", match.get("ltp")), bid, ask, quote_age_sec)
            else:
                source = match.get("price_source") or "mark"
            df.at[idx, "opt_ltp"] = mark_price if mark_price is not None else match.get("ltp")
            df.at[idx, "opt_bid"] = bid
            df.at[idx, "opt_ask"] = ask
            df.at[idx, "mark_price"] = mark_price
            df.at[idx, "price_source"] = source
            df.at[idx, "quote_age_sec"] = quote_age_sec
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

def _load_gpt_advice():
    path = _log_path("gpt_advice.jsonl")
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
    path = _log_path("gpt_pins.json")
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text())
        if isinstance(payload, list):
            return set(str(x) for x in payload)
    except Exception:
        return set()
    return set()

def _load_auto_tune():
    try:
        path = _log_path("auto_tune.json")
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


def _record_tab_render_duration(tab_name: str, start_ts: float) -> float:
    try:
        elapsed_ms = max(0.0, (time.perf_counter() - float(start_ts)) * 1000.0)
    except Exception:
        elapsed_ms = 0.0
    timings = dict(st.session_state.get("tab_render_durations_ms") or {})
    timings[str(tab_name or "UNKNOWN")] = float(round(elapsed_ms, 2))
    st.session_state["tab_render_durations_ms"] = timings
    st.session_state["tab_last_rendered"] = str(tab_name or "UNKNOWN")
    st.session_state["tab_last_rendered_ts_epoch"] = float(time.time())
    try:
        logger.info("dashboard_tab_render tab=%s dt_ms=%.2f", tab_name, elapsed_ms)
    except Exception:
        pass
    return elapsed_ms


def _render_tab_timing_footer(active_tab: str) -> None:
    timings = dict(st.session_state.get("tab_render_durations_ms") or {})
    active_ms = timings.get(str(active_tab), None)
    heavy_tabs = {"Risk & Governance", "Data & SLA", "ML/RL", "Market Depth"}
    heavy_executed = str(active_tab) in heavy_tabs
    parts = []
    for name in [
        "Home",
        "Strategy Timeline",
        "Execution",
        "Reconciliation",
        "Risk & Governance",
        "Data & SLA",
        "ML/RL",
        "Market Depth",
        "Gemini",
    ]:
        if name in timings:
            parts.append(f"{name}={timings[name]:.1f}ms")
    compact = " | ".join(parts) if parts else "no tab timings yet"
    active_text = f"{active_ms:.1f}ms" if isinstance(active_ms, (int, float)) else "n/a"
    st.caption(
        "Tab render debug: "
        f"active={active_tab} ({active_text}) "
        f"heavy_tabs_executed={heavy_executed} "
        f"| {compact}"
    )


def _render_rerun_perf_footer(active_tab: str) -> None:
    timings = dict(st.session_state.get("tab_render_durations_ms") or {})
    render_ms = _safe_float(timings.get(str(active_tab)))
    data_load_ms = _safe_float(st.session_state.get("rerun_data_load_ms"), 0.0) or 0.0
    steps = list(st.session_state.get("rerun_data_load_steps") or [])
    st.caption(
        "Performance report: "
        f"render_time_ms={render_ms:.1f} "
        f"data_load_ms={float(data_load_ms):.1f}"
    )
    if steps:
        compact_steps = " | ".join([f"{name}:{ms:.1f}ms" for name, ms in steps[:8]])
        st.caption(f"Data load breakdown: {compact_steps}")

def _save_gpt_pins(pins):
    path = _log_path("gpt_pins.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(list(pins))))

def _render_gpt_panel(trade_row: dict, market_ctx: dict, key_prefix: str):
    tid = trade_row.get("trade_id")
    if not tid:
        return
    provider = str(os.getenv("GPT_PROVIDER", "openai") or "openai").strip().lower()
    provider_label = "Gemini" if provider == "gemini" else "OpenAI"
    model_name = (
        str(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
        if provider == "gemini"
        else str(os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    )
    st.caption(f"Provider: {provider_label} | model: {model_name}")
    advice_cache = st.session_state.get("gpt_advice_cache", {})
    if tid in advice_cache:
        cached = advice_cache[tid]
        if isinstance(cached, dict) and str(cached.get("error") or "").strip():
            st.error(f"{provider_label} advice error: {cached.get('error')}")
        st.json(cached)
    # Per-panel cooldown display
    cooldown = st.session_state.get("gpt_cooldown_sec", 10)
    last = st.session_state.get("gpt_last_call", {})
    now = time.time()
    remaining = max(0, cooldown - (now - last.get(key_prefix, 0)))
    if remaining > 0:
        st.caption(f"Cooldown: {remaining:.0f}s")
        return
    button_label = "AI Advice (Gemini)" if provider == "gemini" else "AI Advice (OpenAI)"
    if st.button(button_label, key=f"{key_prefix}_gpt_{tid}"):
        with st.spinner(f"Requesting {provider_label} advice..."):
            advice = get_trade_advice(trade_row, market_ctx)
            advice_cache[tid] = advice
            st.session_state["gpt_advice_cache"] = advice_cache
            meta = {"symbol": trade_row.get("symbol"), "strategy": trade_row.get("strategy"), "tier": trade_row.get("tier")}
            save_advice(tid, advice, meta=meta)
        if isinstance(advice, dict) and str(advice.get("error") or "").strip():
            st.error(f"{provider_label} advice error: {advice.get('error')}")
        st.json(advice)
        last[key_prefix] = time.time()
        st.session_state["gpt_last_call"] = last
    # Pin button
    pins = _load_gpt_pins()
    if st.button("Pin Gemini Advice", key=f"{key_prefix}_pin_{tid}"):
        pins.add(tid)
        _save_gpt_pins(pins)
        st.success(f"Pinned {tid}")

_active_tab_render_start = time.perf_counter()

if nav == "Home":
    section_header("Ready To Place Trades")
    snapshot = st.session_state.get("readiness_snapshot") or _compute_readiness_snapshot()
    readiness = snapshot.get("readiness") or {}
    state = snapshot.get("state", "UNKNOWN")
    can_trade = bool(snapshot.get("can_trade", False))
    blockers = list(snapshot.get("blockers") or [])
    warnings = list(snapshot.get("warnings") or [])
    checks = snapshot.get("checks") or {}
    kite = snapshot.get("kite") or {}
    breaker_tripped = bool((checks.get("feed_breaker") or {}).get("tripped"))
    decision_gate = snapshot.get("decision_gate") or {}
    decision_rows = snapshot.get("decision_rows") or {}
    decision_blockers_by_symbol = snapshot.get("decision_blockers_by_symbol") or {}
    latest_decision_row = snapshot.get("latest_decision_row") or {}
    auth_health = snapshot.get("auth_health") or {}
    feed_freshness = snapshot.get("feed_freshness") or {}
    view_options = ["Active Trades", "Review Queue", "Advisory", "Feed / Debug", "Scorecards"]
    if st.session_state.get("home_view_selector") not in view_options:
        st.session_state["home_view_selector"] = "Advisory"
    with st.sidebar:
        st.checkbox("Live update trades", value=False, key="auto_refresh_enabled")
        st.radio(
            "Refresh mode",
            [
                REFRESH_MODE_MARKET_OPEN_ONLY,
                REFRESH_MODE_ALWAYS_UI,
                REFRESH_MODE_FEED_ACTIVE,
            ],
            index=[
                REFRESH_MODE_MARKET_OPEN_ONLY,
                REFRESH_MODE_ALWAYS_UI,
                REFRESH_MODE_FEED_ACTIVE,
            ].index(str(st.session_state.get("trade_refresh_mode") or REFRESH_MODE_MARKET_OPEN_ONLY)),
            key="trade_refresh_mode",
        )
        home_view = st.selectbox(
            "View",
            view_options,
            index=view_options.index(str(st.session_state.get("home_view_selector") or "Advisory")),
            key="home_view_selector",
        )
        refresh_interval_sec = max(2.0, float(getattr(cfg, "UI_REFRESH_SEC", 2.0)))
        st.session_state["refresh_interval_sec"] = refresh_interval_sec

    show_active_view = home_view == "Active Trades"
    show_review_view = home_view == "Review Queue"
    show_advisory_view = home_view == "Advisory"
    show_feed_debug_view = home_view == "Feed / Debug"
    show_scorecards_view = home_view == "Scorecards"

    if state == "MARKET_CLOSED":
        shown_ts = float(st.session_state.get("force_show_quote_errors_ts", 0.0) or 0.0)
        if shown_ts and (time.time() - shown_ts) > 300.0:
            st.session_state["force_show_quote_errors"] = False
            st.session_state["force_show_quote_errors_ts"] = 0.0
    with st.expander("Readiness Details", expanded=False):
        if snapshot.get("error"):
            st.caption(f"Readiness check unavailable: {snapshot.get('error')}")
        if breaker_tripped:
            st.caption("❌ Feed breaker tripped — manual clear required. Run: scripts/clear_feed_breaker.py --yes-i-mean-it")
        # Live quotes status banner
        try:
            quote_err = None
            quote_err_file_missing = False
            err_path = _log_path("live_quote_errors.jsonl")
            if err_path.exists():
                lines = err_path.read_text().strip().splitlines()
                if lines:
                    import json as _json
                    quote_err = _json.loads(lines[-1])
                    # Ignore stale errors
                    try:
                        from config import config as cfg
                        ttl_sec = float(getattr(cfg, "LIVE_QUOTE_ERROR_TTL_SEC", 300))
                        ts_epoch = quote_err.get("ts_epoch")
                        if isinstance(ts_epoch, (int, float)):
                            age = time.time() - float(ts_epoch)
                            if age > ttl_sec:
                                quote_err = None
                        else:
                            ts = quote_err.get("ts_ist") or quote_err.get("timestamp")
                            if ts:
                                err_dt = datetime.fromisoformat(ts)
                                if err_dt.tzinfo is None:
                                    err_dt = err_dt.replace(tzinfo=timezone.utc)
                                age = (datetime.now(timezone.utc) - err_dt.astimezone(timezone.utc)).total_seconds()
                                if age > ttl_sec:
                                    quote_err = None
                    except Exception:
                        pass
            else:
                quote_err_file_missing = True
            chain_health = {}
            health_path = _log_path("option_chain_health.json")
            if health_path.exists():
                try:
                    chain_health = json.loads(health_path.read_text())
                except Exception:
                    chain_health = {}
            offhours_mode = is_offhours(
                {
                    "state": state,
                    "market_open": feed_freshness.get("market_open"),
                    "offhours_mode": feed_freshness.get("offhours_mode"),
                }
            )
            status = "OK"
            notes = []
            auth_ok = bool(auth_health.get("ok", False))
            auth_reason = auth_health.get("error") or auth_health.get("reason")
            if (not offhours_mode) and (not auth_ok):
                status = "ERROR"
                notes.append(f"Auth unhealthy: {auth_reason}")
            feed_ok = bool(feed_freshness.get("ok", True))
            if (not offhours_mode) and bool(feed_freshness.get("market_open", False)) and not feed_ok:
                status = "ERROR"
                notes.append("Feed stale (market open)")
            if quote_err and status == "OK" and (not offhours_mode):
                status = "WARN"
                quote_event = (
                    quote_err.get("event_code")
                    or quote_err.get("error")
                    or quote_err.get("event")
                    or "live_quote_error"
                )
                notes.append(f"Live quote fetch failed ({quote_event})")
            if chain_health and (not offhours_mode):
                bad = [k for k, v in chain_health.items() if isinstance(v, dict) and v.get("status") in ("ERROR", "WARN")]
                if bad:
                    status = "WARN" if status == "OK" else status
                    notes.append(f"Chain health issues: {', '.join(bad)}")
            show_errors = _should_show_quote_errors(state)
            if offhours_mode:
                st.caption("OFFHOURS MODE — live quote and bid/ask errors are suppressed while market is closed.")
                try:
                    ltp_age = (feed_freshness.get("ltp") or {}).get("age_sec")
                    depth_age = (feed_freshness.get("depth") or {}).get("age_sec")
                    ltp_max = (feed_freshness.get("ltp") or {}).get("max_age_sec")
                    depth_max = (feed_freshness.get("depth") or {}).get("max_age_sec")
                    st.caption(
                        f"OFFHOURS SLA: LTP age={ltp_age}s (max {ltp_max}) | "
                        f"Depth age={depth_age}s (max {depth_max})"
                    )
                except Exception:
                    pass
            elif state == "MARKET_CLOSED" and not show_errors:
                st.caption("Market closed — no trading. Live quote errors hidden off-hours.")
            else:
                if status == "OK":
                    st.caption("Live Quotes: OK")
                elif status == "WARN":
                    st.caption("Live Quotes: WARN — " + "; ".join(notes))
                else:
                    # Try to show last error detail + reason classification
                    detail = ""
                    reason = ""
                    try:
                        if quote_err and isinstance(quote_err.get("details"), dict) and quote_err["details"].get("detail"):
                            detail = str(quote_err["details"].get("detail"))
                        elif quote_err and quote_err.get("detail"):
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
                    st.caption("Live Quotes: ERROR — " + "; ".join(notes) + (f" [{reason.strip()}]" if reason else "") + (f" ({detail})" if detail else ""))
                if quote_err_file_missing:
                    st.caption("No live quote errors yet")
        except Exception:
            pass
        if _is_ops_research_mode():
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
                                if _truncate_live_quote_errors_log():
                                    st.caption("Cleared live quote error log.")
                                else:
                                    st.caption("Unable to clear live quote error log.")
                            except Exception:
                                st.caption("Unable to clear live quote error log.")
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
                            if _truncate_live_quote_errors_log():
                                st.caption("Cleared live quote error log.")
                            else:
                                st.caption("Unable to clear live quote error log.")
                        except Exception:
                            st.caption("Unable to clear live quote error log.")
            except Exception:
                pass
        try:
            enabled, allowed, total = _wf_lock_status()
            if enabled:
                if allowed is not None and total is not None:
                    st.caption(f"WF Lock: ACTIVE — {allowed}/{total} strategies allowed")
                    if allowed == 0:
                        st.caption("WF Lock is active but no strategies passed walk-forward.")
                else:
                    st.caption("WF Lock: ACTIVE")
            else:
                st.caption("WF Lock: OFF")
        except Exception:
            pass
        # Auto-tune status badge
        try:
            tune = _load_auto_tune()
            if tune.get("enabled"):
                st.caption(
                    "Auto‑Tune: ACTIVE — "
                    f"RR≥{tune.get('min_rr')} | "
                    f"Proba≥{tune.get('min_proba')} | "
                    f"Score≥{tune.get('trade_score_min')} "
                    f"(win_rate={tune.get('win_rate')}, avg_pnl={tune.get('avg_pnl')})"
                )
            else:
                st.caption("Auto‑Tune: OFF or insufficient trades")
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
            if blockers:
                st.caption("Blockers: " + ", ".join(blockers))
            if warnings:
                st.caption("Warnings: " + ", ".join(warnings))
            if isinstance(decision_blockers_by_symbol, dict) and decision_blockers_by_symbol:
                rows = []
                for sym, sym_blockers in sorted(decision_blockers_by_symbol.items()):
                    vals = [str(x) for x in (sym_blockers or []) if str(x).strip()]
                    rows.append(
                        {
                            "symbol": sym,
                            "decision_allowed": len(vals) == 0,
                            "decision_blockers": ", ".join(vals) if vals else "[]",
                        }
                    )
                if rows:
                    st.caption("Decision Blockers By Symbol")
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            explain_rows = []
            for node in (latest_decision_row.get("decision_explain") or []):
                if not isinstance(node, dict):
                    continue
                reasons = node.get("reasons") or []
                explain_rows.append(
                    {
                        "node": node.get("node"),
                        "ok": bool(node.get("ok")),
                        "reasons": ", ".join([str(x) for x in reasons if str(x).strip()]) if reasons else "",
                    }
                )
            if explain_rows:
                st.caption("Decision DAG Explain (Latest)")
                st.dataframe(pd.DataFrame(explain_rows), use_container_width=True, hide_index=True)
        except Exception:
            st.caption("Readiness: BLOCKED — readiness check unavailable")
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
        _render_confidence_reliability()

    if not show_feed_debug_view:
        with st.expander("Market Snapshot", expanded=False):
            try:
                if _is_market_hours():
                    _market_snapshot_fragment()
                else:
                    _render_market_snapshot()
            except Exception as e:
                st.caption(f"Market snapshot error: {e}")

    if show_feed_debug_view:
        with st.expander("Pre‑Market Day Plan", expanded=False):
            try:
                plan_path = _log_path("premarket_plan.json")
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
        with st.expander("Market Snapshot", expanded=False):
            try:
                # Refresh only the market snapshot during market hours to avoid dimming the whole app
                if _is_market_hours():
                    _market_snapshot_fragment()
                else:
                    _render_market_snapshot()

            except Exception as e:
                st.caption(f"Market snapshot error: {e}")

        with st.expander("Gate Status (Latest)", expanded=False):
            try:
                gate_path = _desk_log_path("gate_status.jsonl")
                if gate_path.exists():
                    load_full = st.checkbox("Load full gate history", value=False, key="gate_status_full_history")
                    max_rows = _FULL_JSONL_TAIL_ROWS if load_full else _DEFAULT_JSONL_TAIL_ROWS
                    rows = _perf_timed_load(
                        "gate_status_jsonl_tail",
                        _load_jsonl_tail_cached,
                        str(gate_path),
                        file_sig(gate_path),
                        max_rows,
                    )
                    if rows:
                        gate_df = pd.DataFrame(rows)
                        for _json_col in ("gate_reasons", "decision_blockers", "decision_explain", "feed_health_snapshot", "node_call_counts"):
                            if _json_col in gate_df.columns:
                                gate_df[_json_col] = gate_df[_json_col].apply(
                                    lambda v: json.dumps(v, ensure_ascii=True) if isinstance(v, (dict, list)) else v
                                )
                        if "system_state" in gate_df.columns:
                            warmup_df = gate_df[gate_df["system_state"].fillna("READY").astype(str).str.upper() == "WARMUP"]
                            if not warmup_df.empty:
                                st.caption("System State: WARMUP — strategy evaluation blocked until warmup contract is met.")
                                warmup_latest = (
                                    warmup_df.sort_values("ts_ist", ascending=False)
                                    .groupby("symbol", as_index=False)
                                    .first()
                                )
                                for col in ("warmup_bars_by_timeframe", "warmup_min_bars_by_timeframe", "warmup_reasons"):
                                    if col in warmup_latest.columns:
                                        warmup_latest[col] = warmup_latest[col].apply(
                                            lambda v: json.dumps(v, ensure_ascii=True) if isinstance(v, (dict, list)) else v
                                        )
                                warmup_cols = [
                                    c
                                    for c in [
                                        "ts_ist",
                                        "symbol",
                                        "system_state",
                                        "warmup_bars_by_timeframe",
                                        "warmup_min_bars_by_timeframe",
                                        "indicator_last_update_epoch",
                                        "warmup_reasons",
                                    ]
                                    if c in warmup_latest.columns
                                ]
                                if warmup_cols:
                                    ui.table(warmup_latest[warmup_cols], use_container_width=True)
                        cols = [
                            c
                            for c in [
                                "ts_ist",
                                "symbol",
                                "stage",
                                "system_state",
                                "indicators_ok",
                                "indicators_age_sec",
                                "ohlc_bars_count",
                                "warmup_min_bars",
                                "primary_regime",
                                "regime_prob_max",
                                "regime_entropy",
                                "indicator_reasons",
                                "warmup_reasons",
                                "regime_reasons",
                                "decision_stage",
                                "decision_blockers",
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
                st.caption(f"Gate status error: {e}")

    try:
        should_refresh, feed_status, market_status = _compute_trade_refresh_gate(readiness_snapshot)
        st.session_state["ui_should_refresh"] = bool(should_refresh)
        st.session_state["ui_feed_status"] = str(feed_status)
        st.session_state["ui_market_status"] = str(market_status)
        st.session_state["ui_local_trade_refresh_enabled"] = _should_enable_local_trade_refresh(
            show_active_view=show_active_view,
            show_advisory_view=show_advisory_view,
        )
        if bool(st.session_state.get("auto_refresh_enabled", False)) and not should_refresh:
            if bool(st.session_state.get("ui_local_trade_refresh_enabled", False)):
                st.caption(
                    "Execution-sensitive refresh is gated, but the live trade table still updates from runtime files."
                )
            else:
                st.caption(
                    f"Live refresh gated ({st.session_state.get('trade_refresh_mode')}) | feed={feed_status} market={market_status}"
                )
    except Exception as exc:
        logger.exception("trades_autorefresh_failed: %s", exc)
        st.session_state["ui_should_refresh"] = False
        st.session_state["ui_feed_status"] = "INACTIVE"
        st.session_state["ui_market_status"] = "UNKNOWN"
        st.session_state["ui_local_trade_refresh_enabled"] = False
        st.warning("Live update encountered a data issue; refresh loop will retry automatically.")

    needs_trade_universe = show_active_view
    if needs_trade_universe:
        trade_universe_df = _perf_timed_load("trade_universe_df", _load_trade_universe_df)
        df_active_all, df_review_all, df_suggested_all, df_advisory_all = _perf_timed_load(
            "trade_universe_partition",
            _partition_trade_universe,
            trade_universe_df,
        )
        if _is_ops_research_mode():
            st.caption(
                "Trade partitions "
                f"(deduped={len(trade_universe_df)}, active={len(df_active_all)}, "
                f"planning={len(df_suggested_all) + len(df_advisory_all)}, review={len(df_review_all)})"
            )
    else:
        trade_universe_df = pd.DataFrame()
        df_active_all = pd.DataFrame()
        df_review_all = pd.DataFrame()
        df_suggested_all = pd.DataFrame()
        df_advisory_all = pd.DataFrame()

    if show_feed_debug_view:
        decision_debug_metrics = _perf_timed_load(
            "decision_debug_metrics",
            _compute_decision_debug_metrics,
            trade_universe_df,
            df_advisory_all,
            decision_gate,
        )
    else:
        decision_debug_metrics = {
            "candidates_per_min": 0,
            "evaluations_per_min": 0,
            "allowed_per_min": 0,
            "candidates_generated": 0,
            "decisions_generated": 0,
            "decisions_passed": 0,
            "advisory_rows": 0,
            "top_blockers_15m": [],
        }
    with st.expander("Decision Pipeline Debug", expanded=False):
        rate1, rate2, rate3 = st.columns(3)
        rate1.metric("candidates/min", f"{int(decision_debug_metrics.get('candidates_per_min') or 0)}")
        rate2.metric("evaluations/min", f"{int(decision_debug_metrics.get('evaluations_per_min') or 0)}")
        rate3.metric("allowed/min", f"{int(decision_debug_metrics.get('allowed_per_min') or 0)}")
        total1, total2, total3, total4 = st.columns(4)
        total1.metric("candidates_generated", f"{int(decision_debug_metrics['candidates_generated'])}")
        total2.metric("decisions_generated", f"{int(decision_debug_metrics['decisions_generated'])}")
        total3.metric("decisions_passed", f"{int(decision_debug_metrics['decisions_passed'])}")
        total4.metric("advisory_rows", f"{int(decision_debug_metrics['advisory_rows'])}")
        top_blockers_15m = list(decision_debug_metrics.get("top_blockers_15m") or [])
        if top_blockers_15m:
            st.caption("Top blockers (last 15m)")
            blocker_df = pd.DataFrame(
                [{"blocker": str(reason), "count": int(count)} for reason, count in top_blockers_15m]
            )
            st.dataframe(blocker_df, use_container_width=True, hide_index=True)
        st.caption("Metrics log every 30s to desk logs: decision_debug_metrics.jsonl")
    _log_decision_debug_metrics(decision_debug_metrics, interval_sec=30.0)

    def _render_home_trade_fragment(label: str, fn) -> None:
        use_local_fragment = bool(st.session_state.get("ui_local_trade_refresh_enabled", False)) and hasattr(st, "fragment")
        refresh_every = max(2.0, float(st.session_state.get("refresh_interval_sec") or getattr(cfg, "UI_REFRESH_SEC", 2.0)))
        if use_local_fragment:
            @st.fragment(run_every=refresh_every)
            def _fragment():
                _perf_timed_render(label, fn)
            _fragment()
            return
        _perf_timed_render(label, fn)

    if show_active_view:
        explorer_filters = _render_trade_explorer_sidebar_filters(trade_universe_df)

        def _render_active_trades_section():
            _render_trade_explorer_panel(trade_universe_df, explorer_filters)
            section_header("Active Trades")
            try:
                active_df = _prepare_trade_display_df(df_active_all)
                active_df = _with_active_runtime_metrics(active_df)
                active_df = _merge_exit_intel_state(active_df)
                active_display = select_display_df(active_df, "active")
                active_display = _prepare_trade_display_df(active_display)
                if not active_display.empty and "trade_key" in active_display.columns and "trade_key" in active_df.columns:
                    active_extras = [
                        c
                        for c in ["trade_key", "mark_price", "bid", "ask", "ltp", "pnl_unrealized"]
                        if c in active_df.columns
                    ]
                    active_extras += [
                        c
                        for c in [
                            "exit_intel_phase",
                            "exit_intel_action",
                            "reason_codes",
                            "best_price_seen",
                            "current_sl",
                            "current_tp",
                            "stall_counter",
                            "last_action_ts",
                        ]
                        if c in active_df.columns and c not in active_extras
                    ]
                    if len(active_extras) > 1:
                        active_display = active_display.merge(
                            active_df[active_extras].drop_duplicates(subset=["trade_key"], keep="last"),
                            on="trade_key",
                            how="left",
                        )
                active_display = _apply_executable_pricing(active_display)
                active_cols = [
                    c
                    for c in [
                        "last_seen_ts",
                        "identity",
                        "status",
                        "side",
                        "entry",
                        "stop",
                        "target",
                        "pnl_unrealized",
                        "live_ltp",
                        "pnl_points",
                        "pnl_cash",
                        "qty",
                        "confidence",
                        "exit_intel_phase",
                        "exit_intel_action",
                        "reason_codes",
                        "best_price_seen",
                        "current_sl",
                        "current_tp",
                        "stall_counter",
                    ]
                    if c in active_display.columns
                ]
                active_cols = [c for c in _inject_executable_pricing_cols(active_cols) if c in active_display.columns]
                if not active_display.empty:
                    _render_upstox_table(active_display, active_cols, "active_trades")
                else:
                    empty_state("No active trades right now.")
            except Exception as exc:
                logger.exception("active_trades_render_failed: %s", exc)
                st.info("No active trades right now.")
            _render_chart_view_panel(trade_universe_df)

        _render_home_trade_fragment("home_active_trades", _render_active_trades_section)

    if show_review_view:
        section_header("Review Queue (Latest)")
    try:
        if not show_review_view:
            raise _SkipSection()
        from core.review_queue import approve, remove_from_queue
        q_path = REVIEW_QUEUE_PATH
        if q_path.exists():
            q_all = load_queue_rows(q_path)
            q = _filter_rows_today(q_all)
            if q:
                show_quotes = st.checkbox("Show bid/ask/ltp", value=False, key="show_quotes_main")
                show_sim = False
                show_trailing = st.checkbox("Show trailing columns", value=False, key="show_trailing_cols")
                auto_activate = False
                if _is_trader_mode():
                    auto_activate = st.checkbox("Auto-activate (use live LTP)", value=True, key="auto_activate_suggested")
                    trail_enable_paper = st.checkbox("Enable trailing (PAPER)", value=getattr(cfg, "TRAIL_ENABLE_PAPER", True), key="trail_enable_paper")
                    st.caption("Trailing applies after entry (ACTIVE). Suggested trades show plan only.")
                    st.caption("Simulation begins only after entry is triggered (ACTIVE). Before that, no P&L is shown.")
                else:
                    trail_enable_paper = bool(getattr(cfg, "TRAIL_ENABLE_PAPER", True))
                    show_sim = st.checkbox("Show Simulation Columns", value=False, key="show_sim_main")
                if show_sim:
                    st.caption("Simulation assumes option premium Δ points; 1-lot P&L shown. Not delta/IV based.")
                exec_mode = str(getattr(cfg, "EXECUTION_MODE", "PAPER") or "PAPER").upper()
                is_live_mode = exec_mode == "LIVE"
                trail_enabled = bool(getattr(cfg, "TRAIL_ENABLE", False)) if is_live_mode else bool(trail_enable_paper)
                need_chain = show_quotes or auto_activate or trail_enabled
                chain_map = _get_chain_map() if need_chain else {}
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
                if need_chain:
                    q_df = _hydrate_option_quotes(q_df, chain_map)
                    q_df = _add_entry_mismatch(q_df)
                meta_map = _get_instrument_meta_map()
                q_df = _with_expiry_dte(q_df, meta_map)
                q_df = _ensure_activation_fields(q_df)
                rr_default = float(getattr(cfg, "TARGET_RR_DEFAULT", 1.5))
                q_df, derived_targets = _ensure_targets(q_df, rr_default)
                q_df, activated, activated_rows = _activate_planning_rows(q_df, auto_activate=auto_activate)
                if activated:
                    _persist_queue_activation(q_path, q_all, q_df)
                    _log_activation_events(activated_rows, "review_queue")
                if derived_targets:
                    _persist_queue_targets(q_path, q_all, derived_targets, rr_default)
                has_active = False
                try:
                    has_active = (q_df["status"].astype(str).str.upper() == "ACTIVE").any()
                except Exception:
                    has_active = False
                if has_active and not need_chain:
                    chain_map = _get_chain_map()
                    q_df = _hydrate_option_quotes(q_df, chain_map)
                q_df = _add_live_pnl_columns(q_df, meta_map)
                if show_sim:
                    if has_active:
                        try:
                            sim_rows = q_df.apply(lambda r: pd.Series(simulate_row(r.to_dict(), meta_map)), axis=1)
                            q_df = pd.concat([q_df, sim_rows], axis=1)
                        except Exception as exc:
                            logger.warning("review_queue sim failed: %s", exc)
                min_offset = float(getattr(cfg, "TRAIL_OFFSET_MIN", 5.0))
                risk_mult = float(getattr(cfg, "TRAIL_OFFSET_RISK_MULT", 0.5))
                q_df, _trail_updated = _apply_trailing(
                    q_df,
                    "review_queue",
                    q_path,
                    q_all,
                    trail_enabled,
                    min_offset,
                    risk_mult,
                    is_live_mode,
                )
                q_df = apply_trailing_display_df(q_df)
                q_df = normalize_trade_df(q_df, meta_map)
                q_df = _mask_unresolved_prices(q_df)
                q_df = _add_upstox_links(q_df)
                q_df = normalize_table_df(q_df)
                q_df = _prepare_trade_display_df(q_df)
                if "status" not in q_df.columns:
                    q_df["status"] = "QUEUED_REVIEW"
                else:
                    q_df["status"] = q_df["status"].fillna("QUEUED_REVIEW")
                q_df_queue_raw = filter_trades_for_panel(q_df, "review")
                q_df_queue = select_display_df(_prepare_trade_display_df(q_df_queue_raw), "review")
                if "trade_key" not in q_df_queue.columns:
                    q_df_queue["trade_key"] = None
                display_cols = [c for c in q_df_queue.columns if c not in {"trade_key", "tradingsymbol"}]
                if display_cols and not q_df_queue.empty:
                    _render_upstox_table(q_df_queue.copy(), display_cols, "review_queue")
                else:
                    empty_state("No pending trades in review queue for today.")
                q_rows = q_df_queue_raw.to_dict("records")
                if st.button("Clear Queue"):
                    write_queue_rows(q_path, [])
                    st.success("Queue cleared.")
                    q = []
                    q_df = pd.DataFrame(q)
                    q_rows = []
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
    except _SkipSection:
        pass
    except Exception as e:
        logger.exception("review_queue_render_failed: %s", e)
        st.info("No trades pending manual review.")

    def _render_suggested_trades_section():
        section_header("Suggested Trades (Latest)")
        try:
            if not show_advisory_view:
                raise _SkipSection()
            status_payload = _load_live_suggestions_status()
            suggested_live_df = _load_live_suggestions_df(limit=100)
            show_exec_only = st.checkbox(
                "Executable only",
                value=False,
                key="suggested_trades_exec_only",
            )
            st.caption(
                "Main table shows engine-ranked opportunities from persisted top-opportunity snapshots. "
                "If snapshots are missing or empty, the table falls back to raw advisory rows."
            )
            top_frames = _load_top_opportunities_frames(
                limit=max(
                    int(getattr(cfg, "TOP_EXECUTABLE_OPPORTUNITIES_N", 5)),
                    int(getattr(cfg, "TOP_ADVISORY_OPPORTUNITIES_N", 5)),
                )
            )
            suggested_df, source_label = _select_advisory_table_source(
                show_exec_only=show_exec_only,
                top_frames=top_frames,
                suggested_live_df=suggested_live_df,
            )
            logger.info(
                "advisory_table_source=%s rows=%s",
                source_label,
                0 if suggested_df is None else len(suggested_df),
            )
            suggested_display = select_display_df(suggested_df, "advisory").head(25)
            show_cols = [c for c in suggested_display.columns if c not in {"trade_key", "tradingsymbol"}]
            if show_cols and not suggested_display.empty:
                class_series = suggested_display.get("candidate_class")
                if class_series is None:
                    class_series = suggested_display.get("candidate_status")
                if class_series is None:
                    class_series = pd.Series(["ADVISORY_ONLY"] * len(suggested_display), index=suggested_display.index)
                class_series = class_series.astype(str).str.strip().str.upper()
                class_series = class_series.replace(
                    {
                        "EXECUTABLE": "EXECUTABLE",
                        "NEAR_EXECUTABLE": "NEAR_EXECUTABLE",
                        "ADVISORY_ONLY": "ADVISORY_ONLY",
                        "EXE": "EXECUTABLE",
                        "ADVISORY": "ADVISORY_ONLY",
                    }
                )

                def _render_candidate_section(title: str, mask, key: str):
                    bucket = suggested_display.loc[mask].copy()
                    if bucket.empty:
                        return
                    st.caption(title)
                    _render_upstox_table(bucket, show_cols, key)

                _render_candidate_section(
                    "Top Opportunities",
                    class_series.eq("EXECUTABLE"),
                    "suggested_trades_executable",
                )
                _render_candidate_section(
                    "Watchlist / Near Executable",
                    class_series.eq("NEAR_EXECUTABLE"),
                    "suggested_trades_near",
                )
                _render_candidate_section(
                    "Advisory / Debug Candidates",
                    class_series.isin(["ADVISORY_ONLY", "ADVISORY"]),
                    "suggested_trades_advisory",
                )
                _render_candidate_section(
                    "Suppressed Candidates",
                    class_series.isin(["SUPPRESSED", "SUPPRESSED_BY_DOWNGRADE", "NO_TRADE_ONLY"]) | ~class_series.isin(["EXECUTABLE", "NEAR_EXECUTABLE", "ADVISORY_ONLY", "ADVISORY"]),
                    "suggested_trades_suppressed",
                )
                blocker_counts = _build_reject_reason_summary(suggested_display)
                if not blocker_counts.empty:
                    st.caption("Reject Reason Summary")
                    st.dataframe(blocker_counts.head(10), use_container_width=True, hide_index=True)
            else:
                primary_blocker = str(status_payload.get("primary_blocker") or status_payload.get("reason") or "NO_CANDIDATES")
                empty_state(f"No visible advisory rows right now. Primary blocker: {primary_blocker}.")
            top_exec = top_frames.get("top_executable", pd.DataFrame())
            top_adv = top_frames.get("top_advisory", pd.DataFrame())
            if not top_exec.empty or not top_adv.empty:
                with st.expander("Top Opportunities (Cycle)", expanded=False):
                    st.caption("Diagnostic view of persisted ranked opportunity snapshots (read-only).")
                    if not top_exec.empty:
                        st.caption("Top Executable Opportunities")
                        exec_display = select_display_df(top_exec, "advisory").head(
                            int(getattr(cfg, "TOP_EXECUTABLE_OPPORTUNITIES_N", 5))
                        )
                        exec_cols = [c for c in exec_display.columns if c not in {"trade_key", "tradingsymbol"}]
                        if exec_cols:
                            _render_upstox_table(exec_display, exec_cols, "top_exec_opportunities")
                    if not top_adv.empty:
                        st.caption("Top Advisory Opportunities")
                        adv_display = select_display_df(top_adv, "advisory").head(
                            int(getattr(cfg, "TOP_ADVISORY_OPPORTUNITIES_N", 5))
                        )
                        adv_cols = [c for c in adv_display.columns if c not in {"trade_key", "tradingsymbol"}]
                        if adv_cols:
                            _render_upstox_table(adv_display, adv_cols, "top_advisory_opportunities")
            if bool(getattr(cfg, "DASHBOARD_RUNTIME_METRICS_ENABLE", True)):
                runtime_metrics = _perf_timed_load(
                    "runtime_metrics",
                    load_runtime_metrics,
                    desk_id=str(getattr(cfg, "DESK_ID", "DEFAULT") or "DEFAULT"),
                    max_rows=int(getattr(cfg, "DASHBOARD_RUNTIME_METRICS_MAX_ROWS", 5000) or 5000),
                    cycle_limit=int(getattr(cfg, "DASHBOARD_RUNTIME_METRICS_CYCLE_LIMIT", 20) or 20),
                )
                with st.expander("Runtime Metrics", expanded=False):
                    st.caption("Read-only aggregates from persisted runtime artifacts. Missing files degrade to empty summaries.")
                    render_candidate_pool_summary(runtime_metrics)
                    render_score_distribution(runtime_metrics)
                    render_rejection_reason_breakdown(runtime_metrics)
                    render_allocation_summary(runtime_metrics)
                    notes = list(runtime_metrics.get("notes") or [])
                    if notes:
                        st.caption("Notes: " + " | ".join([str(note) for note in notes[:6]]))
        except _SkipSection:
            pass
        except Exception as exc:
            logger.exception("suggested_render_failed: %s", exc)
            st.info("No suggested trades right now.")

    if show_advisory_view:
        _render_home_trade_fragment("home_suggested_trades", _render_suggested_trades_section)

    if show_advisory_view and _is_trader_mode():
        st.caption("Trader mode active: research/admin panels are hidden. Switch Dashboard Mode to Ops/Research to view them.")

    if show_advisory_view and _is_ops_research_mode():
        section_header("Exploration Trades (Learning Mode)")
        section_header("Quick Trade Suggestions (Preview)")
        try:
            q2_path = QUICK_REVIEW_QUEUE_PATH
            if q2_path.exists():
                q2_all = load_queue_rows(q2_path)
                q2 = _filter_rows_today(q2_all)
                if q2:
                    show_quotes_q = st.checkbox("Show bid/ask/ltp", value=False, key="show_quotes_quick")
                    show_trailing_q = bool(st.session_state.get("show_trailing_cols", False))
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
                    meta_map_q = _get_instrument_meta_map()
                    q2_df = _with_expiry_dte(q2_df, meta_map_q)
                    q2_df = _ensure_activation_fields(q2_df)
                    q2_df = normalize_trade_df(q2_df, meta_map_q2)
                    q2_df = filter_by_permission(q2_df, "QUEUE_ONLY")
                    q2_df = _mask_unresolved_prices(q2_df)
                    q2_df = apply_trailing_display_df(q2_df)
                    q2_display = q2_df.drop(columns=["trade_id"], errors="ignore")
                    show_cols = _select_speed_trader_cols(
                        q2_df,
                        [
                            "tradable",
                            "tradable_reasons_blocking",
                            "ui_warning",
                            "entry_condition",
                            "entry_ref_price",
                        ],
                    )
                    if _is_ops_research_mode():
                        show_cols += [
                            c
                            for c in [
                                "raw_signal_confidence",
                                "permission_reason",
                                "countertrend",
                            ]
                            if c in q2_df.columns and c not in show_cols
                        ]
                    if show_trailing_q:
                        trail_preview_cols = [c for c in ["trail_enabled", "trail_rule", "trail_offset", "trail_start"] if c in q2_df.columns]
                        trail_live_cols = [c for c in ["mfe_price", "trail_stop", "current_stop", "profit_locked"] if c in q2_df.columns]
                        show_cols += [c for c in trail_preview_cols + trail_live_cols if c not in show_cols]
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

    if show_advisory_view:
        section_header("20-Point Profit Ideas (Advisory)")
        st.caption("Time column is shown in IST. Entry reflects executable quote only; unavailable quotes are shown as —.")
    try:
        if not show_advisory_view:
            raise _SkipSection()
        t20_path = TARGET_POINTS_QUEUE_PATH
        if t20_path.exists():
            t20_all = load_queue_rows(t20_path)
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
                t20_df = _with_expiry_dte(t20_df, meta_map_t20)
                if "instrument" in t20_df.columns:
                    t20_df = t20_df[t20_df["instrument"] == "OPT"]
                t20_df = _ensure_activation_fields(t20_df)
                auto_activate_t20 = st.checkbox(
                    "Auto-activate advisory rows (use live LTP)",
                    value=bool(st.session_state.get("auto_activate_suggested", True)),
                    key="auto_activate_t20",
                )
                st.session_state["auto_activate_suggested"] = bool(auto_activate_t20)
                if auto_activate_t20:
                    chain_map_t20 = _get_chain_map()
                    t20_df = _hydrate_option_quotes(t20_df, chain_map_t20)
                    t20_df, activated, activated_rows = _activate_planning_rows(t20_df, auto_activate=True)
                    if activated:
                        _persist_queue_activation(t20_path, t20_all, t20_df)
                        _log_activation_events(activated_rows, "target_points")
                if "target_points_min" in t20_df.columns:
                    t20_df["target_points_min"] = pd.to_numeric(t20_df["target_points_min"], errors="coerce").fillna(20.0)
                if "target_points" not in t20_df.columns:
                    t20_df["target_points"] = None
                if "target_premium" not in t20_df.columns:
                    t20_df["target_premium"] = None
                if "target" not in t20_df.columns:
                    t20_df["target"] = None
                try:
                    def _calc_points(row):
                        if row.get("target_points") is not None:
                            return row.get("target_points")
                        entry_val = _safe_float(row.get("entry"))
                        target_val = _safe_float(row.get("target"))
                        if entry_val is None or target_val is None:
                            return None
                        return round(abs(target_val - entry_val), 2)
                    t20_df["target_points"] = t20_df.apply(_calc_points, axis=1)
                    def _calc_premium(row):
                        if row.get("target_premium") is not None:
                            return row.get("target_premium")
                        return row.get("target_points")
                    t20_df["target_premium"] = t20_df.apply(_calc_premium, axis=1)
                except Exception as exc:
                    logger.warning("t20 target_points calc failed: %s", exc)
                derived_t20 = {}
                try:
                    def _derive_target(row):
                        if row.get("target") not in (None, "", "None"):
                            return row.get("target")
                        entry_val = _safe_float(row.get("entry"))
                        points_val = _safe_float(row.get("target_points_min") or row.get("target_points"))
                        if entry_val is None or points_val is None:
                            return None
                        side_val = str(row.get("side") or "BUY").upper()
                        if side_val == "SELL":
                            return round(entry_val - points_val, 2)
                        return round(entry_val + points_val, 2)
                    t20_df["target"] = t20_df.apply(_derive_target, axis=1)
                    for _, row in t20_df.iterrows():
                        tid = row.get("trade_id")
                        target_val = row.get("target")
                        if tid and target_val not in (None, "", "None"):
                            derived_t20[str(tid)] = float(target_val)
                except Exception as exc:
                    logger.warning("t20 target derivation failed: %s", exc)
                if derived_t20:
                    updated = False
                    for entry in t20_all:
                        tid = entry.get("trade_id")
                        if not tid or str(tid) not in derived_t20:
                            continue
                        if entry.get("target") not in (None, "", "None"):
                            continue
                        entry["target"] = derived_t20[str(tid)]
                        entry["target_derived"] = True
                        entry["target_source"] = "target_points_min"
                        updated = True
                    if updated:
                        try:
                            t20_path.write_text(json.dumps(t20_all, indent=2))
                        except Exception as exc:
                            logger.warning("t20 target persist failed: %s", exc)
                show_sim_t20 = st.checkbox("Show Simulation Columns", value=False, key="show_sim_t20")
                if show_sim_t20:
                    st.caption("Simulation assumes option premium Δ points; 1-lot P&L shown. Not delta/IV based.")
                    try:
                        sim_rows = t20_df.apply(lambda r: pd.Series(simulate_row(r.to_dict(), meta_map_t20)), axis=1)
                        t20_df = pd.concat([t20_df, sim_rows], axis=1)
                    except Exception as exc:
                        logger.warning("t20 sim failed: %s", exc)
                exec_mode = str(getattr(cfg, "EXECUTION_MODE", "PAPER") or "PAPER").upper()
                is_live_mode = exec_mode == "LIVE"
                trail_enabled = bool(getattr(cfg, "TRAIL_ENABLE", False)) if is_live_mode else bool(getattr(cfg, "TRAIL_ENABLE_PAPER", True))
                min_offset = float(getattr(cfg, "TRAIL_OFFSET_MIN", 5.0))
                risk_mult = float(getattr(cfg, "TRAIL_OFFSET_RISK_MULT", 0.5))
                t20_df, _trail_updated = _apply_trailing(
                    t20_df,
                    "target_points",
                    t20_path,
                    t20_all,
                    trail_enabled,
                    min_offset,
                    risk_mult,
                    is_live_mode,
                )
                t20_df = apply_trailing_display_df(t20_df)
                t20_df = normalize_trade_df(t20_df, meta_map_t20)
                t20_df = filter_non_active(filter_by_permission(t20_df, "ADVISORY_ONLY"))
                t20_df = dedupe_by_trade_key(t20_df, sort_by="global_confidence")
                t20_df = _cap_unknown_regime_advisory(t20_df)
                t20_df = _mask_unresolved_prices(t20_df)
                t20_df = _enforce_executable_entry_display(t20_df)
                t20_df = _add_upstox_links(t20_df)
                t20_df = normalize_table_df(t20_df)
                t20_df = _prepare_trade_display_df(t20_df)
                t20_display = select_display_df(_prepare_trade_display_df(t20_df), "advisory")
                if "trade_key" in t20_display.columns and "trade_key" in t20_df.columns:
                    diag_cols = [
                        c
                        for c in [
                            "entry_status",
                            "activation_gate_reason",
                            "activation_ui_flag",
                            "current_ltp",
                        ]
                        if c in t20_df.columns
                    ]
                    if diag_cols:
                        t20_display = t20_display.merge(
                            t20_df[["trade_key", *diag_cols]].drop_duplicates(subset=["trade_key"], keep="last"),
                            on="trade_key",
                            how="left",
                        )
                if show_sim_t20 and "trade_key" in t20_display.columns and "trade_key" in t20_df.columns:
                    sim_cols = _simulation_display_cols(t20_df)
                    if sim_cols:
                        t20_display = t20_display.merge(
                            t20_df[["trade_key", *sim_cols]].drop_duplicates(subset=["trade_key"], keep="last"),
                            on="trade_key",
                            how="left",
                        )
                t20_cols = [c for c in t20_display.columns if c not in {"trade_key", "tradingsymbol"}]
                if t20_cols and not t20_display.empty:
                    _render_upstox_table(t20_display, t20_cols, "t20_advisory")
                else:
                    empty_state("No 20-point ideas yet for today.")
                diag_source = t20_df.copy()
                if not diag_source.empty:
                    diag_last_seen = _series_first_non_null(
                        diag_source,
                        ["last_seen_ts", "timestamp"],
                        default=None,
                    )
                    token_series = _series_first_non_null(
                        diag_source,
                        ["instrument_token"],
                        default=None,
                    )
                    token_present = token_series.apply(
                        lambda value: bool(
                            value not in (None, "", "None")
                            and str(value).strip().lower() not in {"nan", "na", "n/a"}
                        )
                    )
                    diag_df = pd.DataFrame(
                        {
                            "last_seen_ts": diag_last_seen,
                            "symbol": _series_first_non_null(
                                diag_source,
                                ["symbol", "underlying"],
                                default="",
                            ).astype(str),
                            "option_token_present": token_present,
                            "option_ltp_age": pd.to_numeric(
                                _series_first_non_null(diag_source, ["price_age_sec"], default=None),
                                errors="coerce",
                            ).round(2),
                            "source(tick/rest)": _series_first_non_null(
                                diag_source,
                                ["option_ltp_source"],
                                default="unknown",
                            ).fillna("unknown"),
                            "entry_status": _series_first_non_null(
                                diag_source,
                                ["entry_status"],
                                default="",
                            ).astype(str),
                        }
                    )
                    diag_df = _safe_sort_by_last_seen(diag_df)
                    if "last_seen_ts" in diag_df.columns:
                        diag_df = diag_df.drop(columns=["last_seen_ts"], errors="ignore")
                    st.caption("Option entry diagnostics (live advisory): symbol | option_token_present | option_ltp_age | source(tick/rest) | entry_status")
                    st.dataframe(diag_df.head(25), use_container_width=True, hide_index=True)
                st.caption("Advisory queue only. Trades are still blocked unless readiness and approval gates pass.")
            else:
                empty_state("No 20-point ideas yet for today.")
        else:
            empty_state("No 20-point ideas generated yet.")
    except _SkipSection:
        pass
    except Exception as e:
        logger.exception("t20_render_failed: %s", e)
        st.info("No 20-point ideas available.")

    with st.expander("Zero-to-Hero (Lotto) Ideas", expanded=False):
        try:
            if not show_advisory_view:
                raise _SkipSection()
            zh_path = ZERO_HERO_QUEUE_PATH
            if zh_path.exists():
                zh_all = load_queue_rows(zh_path)
                zh = _filter_rows_today(zh_all)
                if zh:
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
                    zh_df = _with_expiry_dte(zh_df, meta_map_zh)
                    # show only single-leg options (OPT)
                    if "instrument" in zh_df.columns:
                        zh_df = zh_df[zh_df["instrument"] == "OPT"]
                    zh_df = _ensure_activation_fields(zh_df)
                    auto_activate_zh = bool(st.session_state.get("auto_activate_suggested", False))
                    if auto_activate_zh:
                        chain_map_zh = _get_chain_map()
                        zh_df = _hydrate_option_quotes(zh_df, chain_map_zh)
                        zh_df, activated, activated_rows = _activate_planning_rows(zh_df, auto_activate=True)
                        if activated:
                            _persist_queue_activation(zh_path, zh_all, zh_df)
                            _log_activation_events(activated_rows, "zero_to_hero")
                    zh_df = _add_live_pnl_columns(zh_df, meta_map_zh)
                    zh_df = normalize_trade_df(zh_df, meta_map_zh)
                    zh_df = filter_non_active(filter_by_permission(zh_df, "ADVISORY_ONLY"))
                    zh_df = dedupe_by_trade_key(zh_df, sort_by="global_confidence")
                    zh_df = _cap_unknown_regime_advisory(zh_df)
                    zh_df = _mask_unresolved_prices(zh_df)
                    if "option_type" not in zh_df.columns and "type" in zh_df.columns:
                        zh_df["option_type"] = zh_df["type"]
                    if "premium" not in zh_df.columns:
                        if "entry" in zh_df.columns:
                            zh_df["premium"] = zh_df["entry"]
                        elif "opt_ltp" in zh_df.columns:
                            zh_df["premium"] = zh_df["opt_ltp"]
                        else:
                            zh_df["premium"] = None
                    zh_df["note"] = "PAPER only, non-executable"
                    zh_df = _add_upstox_links(zh_df)
                    zh_df = normalize_table_df(zh_df)
                    zh_df = _prepare_trade_display_df(zh_df)
                    zh_display = select_display_df(_prepare_trade_display_df(zh_df), "advisory")
                    zh_cols = [c for c in zh_display.columns if c not in {"trade_key", "tradingsymbol"}]
                    if zh_cols and not zh_display.empty:
                        _render_upstox_table(zh_display, zh_cols, "zero_to_hero")
                    else:
                        empty_state("No Zero-to-Hero ideas yet for today.")
                    st.caption("PAPER-only advisory ideas. No auto-execution.")
                else:
                    empty_state("No Zero-to-Hero ideas yet for today.")
            else:
                empty_state("No Zero-to-Hero ideas generated yet.")
        except _SkipSection:
            st.caption("Select 'Advisory' view to load this panel.")
        except Exception as e:
            logger.exception("zero_to_hero_render_failed: %s", e)
            st.info("No Zero-to-Hero ideas available.")

    if show_advisory_view and _is_ops_research_mode():
        section_header("Scalp Trades (Range / Low Momentum)")
        try:
            sc_path = SCALP_QUEUE_PATH
            if sc_path.exists():
                sc_all = load_queue_rows(sc_path)
                sc = _filter_rows_today(sc_all)
                if sc:
                    show_quotes_sc = st.checkbox("Show bid/ask/ltp", value=False, key="show_quotes_sc")
                    show_trailing_sc = bool(st.session_state.get("show_trailing_cols", False))
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
                    sc_df = _ensure_activation_fields(sc_df)
                    sc_df = normalize_trade_df(sc_df, meta_map_sc)
                    sc_df = filter_by_permission(sc_df, "QUEUE_ONLY")
                    sc_df = _mask_unresolved_prices(sc_df)
                    sc_df = apply_trailing_display_df(sc_df)
                    sc_display = sc_df.drop(columns=["trade_id"], errors="ignore")
                    show_cols = _select_speed_trader_cols(
                        sc_df,
                        [
                            "qty",
                            "tradable",
                            "tradable_reasons_blocking",
                            "ui_warning",
                            "entry_condition",
                            "entry_ref_price",
                        ],
                    )
                    if show_trailing_sc:
                        trail_preview_cols = [c for c in ["trail_enabled", "trail_rule", "trail_offset", "trail_start"] if c in sc_df.columns]
                        trail_live_cols = [c for c in ["mfe_price", "trail_stop", "current_stop", "profit_locked"] if c in sc_df.columns]
                        show_cols += [c for c in trail_preview_cols + trail_live_cols if c not in show_cols]
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

    if show_advisory_view and _is_ops_research_mode():
        section_header("Top Candidates Despite Rejection")
        try:
            reject_path = _log_path("rejected_candidates.jsonl")
            debug_path = _log_path("debug_candidates.jsonl")
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

    if show_scorecards_view and _is_ops_research_mode():
        section_header("Reject Telemetry (Last 50)")
        try:
            reject_rows = get_recent_reject_telemetry(limit=50)
            if reject_rows:
                reject_df = pd.DataFrame(reject_rows)
                reject_df["timestamp"] = pd.to_datetime(
                    reject_df.get("timestamp_epoch_ms"),
                    unit="ms",
                    errors="coerce",
                    utc=True,
                )
                reject_df = reject_df.sort_values("timestamp_epoch_ms", ascending=False)
                show_cols = [
                    col
                    for col in [
                        "timestamp",
                        "symbol",
                        "strike",
                        "trade_side",
                        "reject_reason",
                        "quote_age_sec",
                        "spread_pct",
                        "feed_state",
                    ]
                    if col in reject_df.columns
                ]
                ui.table(reject_df[show_cols].head(50), use_container_width=True)
            else:
                empty_state("No reject telemetry recorded yet.")
        except Exception as exc:
            st.warning(f"Reject telemetry error: {exc}")

    if show_scorecards_view and _is_ops_research_mode():
        section_header("Signal Path (Latest)")
        try:
            sp_path = _log_path("signal_path.jsonl")
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
                    for col, default in (("source", "none"), ("quote_source", "none")):
                        if col in df_sp.columns:
                            df_sp[col] = df_sp[col].fillna(default)
                    sym_filter = st.selectbox("Signal Path Symbol", ["All"] + sorted(df_sp["symbol"].dropna().unique().tolist()), key="signal_path_symbol")
                    if sym_filter != "All":
                        df_sp = df_sp[df_sp["symbol"] == sym_filter]
                    show_cols = [c for c in ["timestamp", "symbol", "kind", "source", "quote_source", "regime", "direction", "score", "reason", "ltp_change_window", "atr", "threshold"] if c in df_sp.columns]
                    ui.table(df_sp.sort_values("timestamp", ascending=False)[show_cols].head(50), use_container_width=True)
                else:
                    empty_state("No signal path entries yet.")
            else:
                empty_state("No signal path log yet.")
        except Exception as e:
            st.warning(f"Signal path error: {e}")

        section_header("Suggestion Quality (Hits / Time)")
        try:
            eval_path = canonical_suggestion_eval_log_path()
            if not eval_path.exists():
                for candidate in suggestion_eval_log_paths():
                    if candidate.exists():
                        eval_path = candidate
                        break
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

    if show_scorecards_view and _is_ops_research_mode():
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
                    for m in _fetch_live_market_data_dashboard("daytype_relock", allow_stale_cache=True):
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

    if show_scorecards_view and _is_ops_research_mode():
        section_header("What Blocked Trades Today")
    try:
        if not (show_scorecards_view and _is_ops_research_mode()):
            raise _SkipSection()
        try:
            from config import config as cfg
            desk = getattr(cfg, "DESK_ID", "DEFAULT")
            desk_log_dir = Path(
                str(getattr(cfg, "DESK_LOG_DIR", str(logs_dir() / "desks" / str(desk))))
            )
        except Exception:
            desk = "DEFAULT"
            desk_log_dir = logs_dir() / f"desks/{desk}"
        blocked_path = desk_log_dir / "blocked_candidates.jsonl"
        legacy_path = _log_path("rejected_candidates.jsonl")
        rej_path = blocked_path if blocked_path.exists() else legacy_path
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
                if "reason" not in df_rej.columns and "reason_code" in df_rej.columns:
                    df_rej["reason"] = df_rej["reason_code"]
                if "reason" not in df_rej.columns and "primary_blocker" in df_rej.columns:
                    df_rej["reason"] = df_rej["primary_blocker"]
                if "timestamp" not in df_rej.columns and "ts_ist" in df_rej.columns:
                    df_rej["timestamp"] = df_rej["ts_ist"]
                if "timestamp" in df_rej.columns:
                    now = now_local()
                    df_rej["ts_local"] = df_rej["timestamp"].apply(lambda v: parse_ts_local(v))
                    df_rej = df_rej[df_rej["ts_local"].apply(lambda v: v is not None and v.date() == now.date())]
                if not df_rej.empty and "reason" in df_rej.columns:
                    latest_cols = [
                        c
                        for c in [
                            "timestamp",
                            "symbol",
                            "stage",
                            "reason",
                            "reason_text",
                            "ltp",
                            "vwap",
                            "atr",
                            "primary_regime",
                            "quote_ok",
                            "quote_source",
                        ]
                        if c in df_rej.columns
                    ]
                    latest_sort_col = "ts_epoch" if "ts_epoch" in df_rej.columns else "timestamp"
                    st.markdown("**Latest Blocked Candidates**")
                    ui.table(
                        df_rej.sort_values(latest_sort_col, ascending=False).head(50)[latest_cols],
                        use_container_width=True,
                    )
                    summary = df_rej["reason"].value_counts().head(8).reset_index()
                    summary.columns = ["reason", "count"]
                    ui.table(summary, use_container_width=True)
                    if "stage" in df_rej.columns:
                        dag_rows = df_rej[df_rej["stage"] == "decision_dag"]
                        if not dag_rows.empty:
                            st.markdown("**Decision DAG Blockers (Today)**")
                            dag_summary = dag_rows["reason"].value_counts().reset_index()
                            dag_summary.columns = ["reason", "count"]
                            ui.table(dag_summary.head(8), use_container_width=True)
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
                    out_path = _log_path("blocked_outcomes.jsonl")
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
                            detail_cols = [
                                c
                                for c in [
                                    "timestamp",
                                    "ts_epoch",
                                    "symbol",
                                    "stage",
                                    "reason",
                                    "reason_text",
                                    "ltp",
                                    "vwap",
                                    "atr",
                                    "primary_regime",
                                    "quote_ok",
                                    "quote_source",
                                    "strike",
                                    "type",
                                    "bid",
                                    "ask",
                                    "volume",
                                    "oi",
                                    "iv",
                                    "moneyness",
                                ]
                                if c in df_rej.columns
                            ]
                            ui.table(df_rej[df_rej["reason"] == sel_reason][detail_cols].head(200), use_container_width=True)
                        # Blocked outcomes (paper results)
                        out_path = _log_path("blocked_outcomes.jsonl")
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
    except _SkipSection:
        pass
    except Exception as e:
        st.warning(f"Blocked summary error: {e}")

    if show_scorecards_view and _is_ops_research_mode():
        section_header("Day‑Type History")
    try:
        if not (show_scorecards_view and _is_ops_research_mode()):
            raise _SkipSection()
        rows = _fetch_day_type_events_dashboard(caller="scorecards_daytype_history", max_rows=10000)
        if rows:
            df_dt = day_type_events_dataframe(rows)
            # Export CSV
            try:
                csv_path = _log_path("day_type_events.csv")
                sort_col = "ts_epoch" if "ts_epoch" in df_dt.columns else "ts"
                df_dt.sort_values(sort_col, ascending=True).to_csv(csv_path, index=False)
            except Exception:
                pass
            if st.button("Export Day‑Type History CSV", key="export_daytype_csv"):
                try:
                    st.success("Exported to logs/day_type_events.csv")
                except Exception:
                    pass
            table_sort_col = "ts_epoch" if "ts_epoch" in df_dt.columns else "ts"
            ui.table(df_dt.sort_values(table_sort_col, ascending=False).head(200), use_container_width=True)
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
    except _SkipSection:
        pass
    except Exception as e:
        st.warning(f"Day‑type history error: {e}")

elif nav == "Gemini":
    section_header("Gemini Summary (Day Plan)")
    try:
        provider = str(os.getenv("GPT_PROVIDER", "openai") or "openai").strip().lower()
        provider_label = "Gemini" if provider == "gemini" else "OpenAI"
        provider_model = (
            str(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
            if provider == "gemini"
            else str(os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        )
        st.caption(f"AI provider: {provider_label} | model: {provider_model}")
        st.session_state.setdefault("gpt_cooldown_sec", 10)
        st.session_state["gpt_cooldown_sec"] = st.slider("Gemini Panel Cooldown (sec)", 5, 60, st.session_state["gpt_cooldown_sec"], 5, key="gpt_panel_cd")
        auto = st.checkbox("Auto‑refresh Gemini Summary", value=False, key="gpt_summary_auto")
        cooldown = st.slider("Summary cooldown (sec)", 60, 900, 300, 30, key="gpt_summary_cooldown")
        if hasattr(st, "fragment") and auto:
            @st.fragment(run_every=cooldown)
            def _gpt_summary_fragment():
                with st.spinner("Requesting Gemini summary..."):
                    md = _fetch_live_market_data_dashboard("gpt_summary_fragment", allow_stale_cache=True)
                    summary = get_day_summary({"market": md})
                    st.session_state["gpt_summary"] = summary
                    st.json(summary)
            _gpt_summary_fragment()
        else:
            if st.button("Generate Gemini Summary", key="gpt_summary_btn"):
                with st.spinner("Requesting Gemini summary..."):
                    md = _fetch_live_market_data_dashboard("gpt_summary_button", allow_stale_cache=True)
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

    section_header("Gemini Diagnostics")
    try:
        provider = str(os.getenv("GPT_PROVIDER", "openai") or "openai").strip().lower()
        provider_label = "Gemini" if provider == "gemini" else "OpenAI"
        provider_model = (
            str(os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
            if provider == "gemini"
            else str(os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        )
        logs_root = logs_dir().resolve()
        st.caption(f"CWD: {Path.cwd()}")
        st.caption(f"Provider: {provider_label} | model: {provider_model}")
        st.caption(f"logs_dir: {logs_root}")

        tracked_files = [
            ("gpt_advice.jsonl", logs_root / "gpt_advice.jsonl"),
            ("gpt_pins.json", logs_root / "gpt_pins.json"),
            ("gpt_usage.json", logs_root / "gpt_usage.json"),
        ]
        diag_rows = []
        for name, file_path in tracked_files:
            exists = file_path.exists()
            size = file_path.stat().st_size if exists else 0
            mtime = (
                datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat()
                if exists
                else None
            )
            diag_rows.append(
                {
                    "file": name,
                    "path": str(file_path),
                    "exists": exists,
                    "size_bytes": size,
                    "mtime_utc": mtime,
                }
            )
        ui.table(pd.DataFrame(diag_rows), use_container_width=True)

        advice_path = logs_root / "gpt_advice.jsonl"
        if advice_path.exists():
            raw_lines = advice_path.read_text(encoding="utf-8").splitlines()
            sample = [ln for ln in raw_lines if ln.strip()][-3:]
            parsed_rows = []
            for ln in sample:
                try:
                    parsed_rows.append(json.loads(ln))
                except Exception:
                    parsed_rows.append({"raw": ln})
            if parsed_rows:
                st.caption("Last 3 advice entries")
                st.json(parsed_rows)
    except Exception as e:
        st.warning(f"Gemini diagnostics error: {e}")

    section_header("Gemini Advice History")
    try:
        hist_path = _log_path("gpt_advice.jsonl")
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
            hist_path = _log_path("gpt_advice.jsonl")
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
                md_list = _fetch_live_market_data_dashboard("manual_queue_analysis", allow_stale_cache=True)
                for m in md_list:
                    sym = m.get("symbol")
                    if sym and sym not in ltp_map:
                        ltp_map[sym] = m.get("ltp")
                    if sym and sym not in chain_map:
                        chain_map[sym] = m.get("option_chain", [])
            except Exception:
                ltp_map = {}
                chain_map = {}
            _analyze_queue(str(REVIEW_QUEUE_PATH), "Manual Review Queue", "manual_tab", ltp_map=ltp_map, chain_map=chain_map)
            _analyze_queue(str(QUICK_REVIEW_QUEUE_PATH), "Quick Trades", "quick_tab", ltp_map=ltp_map, chain_map=chain_map)
            _analyze_queue(str(ZERO_HERO_QUEUE_PATH), "Zero Hero", "zero_tab", ltp_map=ltp_map, chain_map=chain_map)
            _analyze_queue(str(SCALP_QUEUE_PATH), "Scalp Trades", "scalp_tab", ltp_map=ltp_map, chain_map=chain_map)
            # Rejected candidates
            rej_path = _log_path("rejected_candidates.jsonl")
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
    if _is_ops_research_mode():
        section_header("Approved Trades")
    try:
        if not _is_ops_research_mode():
            raise _SkipSection()
        a_path = REVIEW_APPROVED_PATH
        if a_path.exists():
            approved_rows, active_rows = _load_approved_trades(a_path)
            if approved_rows:
                df_app = pd.DataFrame(approved_rows)
                if "approved_epoch" in df_app.columns:
                    df_app["approved_ts"] = df_app["approved_epoch"].apply(
                        lambda v: datetime.fromtimestamp(float(v)).isoformat() if v not in (None, "") else None
                    )
                if "expires_epoch" in df_app.columns:
                    df_app["expires_ts"] = df_app["expires_epoch"].apply(
                        lambda v: datetime.fromtimestamp(float(v)).isoformat() if v not in (None, "") else None
                    )
                show_cols = [c for c in ["trade_id", "status", "approved_ts", "expires_ts", "legacy"] if c in df_app.columns]
                ui.table(df_app[show_cols] if show_cols else df_app, use_container_width=True)
                if active_rows:
                    st.caption("Active/Watch approvals are listed below until expired or resolved.")
                    df_active = pd.DataFrame(active_rows)
                    if "approved_epoch" in df_active.columns:
                        df_active["approved_ts"] = df_active["approved_epoch"].apply(
                            lambda v: datetime.fromtimestamp(float(v)).isoformat() if v not in (None, "") else None
                        )
                    if "expires_epoch" in df_active.columns:
                        df_active["expires_ts"] = df_active["expires_epoch"].apply(
                            lambda v: datetime.fromtimestamp(float(v)).isoformat() if v not in (None, "") else None
                        )
                    show_cols_active = [c for c in ["trade_id", "approved_ts", "expires_ts", "status", "legacy"] if c in df_active.columns]
                    st.subheader("Active/Watch Approvals")
                    ui.table(df_active[show_cols_active] if show_cols_active else df_active, use_container_width=True)
            else:
                empty_state("No approved trades yet.")
        else:
            empty_state("No approved trades file yet.")
    except _SkipSection:
        pass
    except Exception as e:
        st.warning(f"Approved trades error: {e}")

    if _is_ops_research_mode():
        section_header("Re-queue Trades")
    try:
        if not _is_ops_research_mode():
            raise _SkipSection()
        if "q" in locals() and q:
            st.info("Use Reject to remove; approved trades can be re-queued by ID.")
        a_path = REVIEW_APPROVED_PATH
        if a_path.exists():
            approved_rows, _active_rows = _load_approved_trades(a_path)
            approved_ids = [row.get("trade_id") for row in approved_rows if row.get("trade_id")]
            if approved_ids:
                tid = st.text_input("Trade ID to re-queue")
                if st.button("Re-queue"):
                    data = load_queue_rows(q_path) if q_path.exists() else []
                    data.append({"trade_id": tid, "timestamp": str(pd.Timestamp.now())})
                    write_queue_rows(q_path, data)
                    st.success(f"Re-queued {tid}")
    except _SkipSection:
        pass
    except Exception as e:
        st.warning(f"Re-queue error: {e}")

    if _is_ops_research_mode():
        section_header("Trade Scoring (Manual Entry)")
    try:
        if not _is_ops_research_mode():
            raise _SkipSection()
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
            md_list = _fetch_live_market_data_dashboard("manual_trade_builder", allow_stale_cache=True)
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
                raise RuntimeError("No live quote found for this strike/expiry. Please choose a strike with live quotes.")
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

            st.metric("Confidence", fmt_conf(conf))
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
                log_path = _log_path("scored_trades.jsonl")
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
    except _SkipSection:
        pass
    except Exception as e:
        msg = str(e)
        if "No live quote found for this strike/expiry" in msg:
            st.error(msg)
        else:
            st.warning(f"Trade scoring error: {e}")

    if _is_ops_research_mode():
        section_header("Scored Trades")
    try:
        if not _is_ops_research_mode():
            raise _SkipSection()
        scored_path = _log_path("scored_trades.jsonl")
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
    except _SkipSection:
        pass
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
            st.info("Using trade log for strategy stats (no strategy_perf.json yet).")
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
        cols, rows = _perf_timed_load("sqlite_recent_trades_100", _fetch_recent_trades_cached, 100, _trade_db_sig())
        if rows:
            db_df = pd.DataFrame(rows, columns=cols)
            db_df = _localize_ts(db_df, "timestamp")
            ui.table(db_df, use_container_width=True)
        else:
            empty_state("No trades in SQLite. Showing trade log file instead.")
            ui.table(df_local.tail(50) if "timestamp_local" in df_local.columns else df.tail(50), use_container_width=True)
    except Exception as e:
        st.warning(f"SQLite trades error: {e}")

    section_header("Recent Outcomes (SQLite)")
    try:
        cols, rows = _perf_timed_load("sqlite_recent_outcomes_100", _fetch_recent_outcomes_cached, 100, _trade_db_sig())
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
            empty_state("No PnL data in SQLite. Showing from trade log file.")
            df_sorted = df.sort_values("timestamp").copy()
            df_sorted["cum_pnl"] = df_sorted["pnl"].cumsum()
            df_sorted["drawdown"] = df_sorted["cum_pnl"] - df_sorted["cum_pnl"].cummax()
            st.line_chart(df_sorted.set_index("timestamp")[["cum_pnl", "drawdown"]])
    except Exception as e:
        st.warning(f"SQLite PnL error: {e}")

elif nav == "Strategy Timeline":
    try:
        _render_strategy_timeline_tab()
    except Exception as exc:
        logger.exception("strategy_timeline_render_failed: %s", exc)
        error_state(f"Strategy Timeline unavailable. {exc}")

elif nav == "Execution":
    with st.expander("Execution Status", expanded=False):
        try:
            enabled, allowed, total = _wf_lock_status()
            if enabled:
                if allowed is not None and total is not None:
                    st.caption(f"WF Lock: ACTIVE — {allowed}/{total} strategies allowed")
                    if allowed == 0:
                        st.caption("WF Lock is active but no strategies passed walk-forward.")
                else:
                    st.caption("WF Lock: ACTIVE")
            else:
                st.caption("WF Lock: OFF")
        except Exception:
            pass
        # Auto-tune status badge
        try:
            tune = _load_auto_tune()
            if tune.get("enabled"):
                st.caption(
                    "Auto‑Tune: ACTIVE — "
                    f"RR≥{tune.get('min_rr')} | "
                    f"Proba≥{tune.get('min_proba')} | "
                    f"Score≥{tune.get('trade_score_min')} "
                    f"(win_rate={tune.get('win_rate')}, avg_pnl={tune.get('avg_pnl')})"
                )
            else:
                st.caption("Auto‑Tune: OFF or insufficient trades")
        except Exception:
            pass
    with st.expander("Live Fills Status", expanded=False):
        try:
            status = "Disconnected"
            detail = "No recent fills"
            last_fill = None
            try:
                cols, rows = _perf_timed_load("sqlite_execution_stats_5", _fetch_execution_stats_cached, 5, _trade_db_sig())
                if rows:
                    df_exec = pd.DataFrame(rows, columns=cols)
                    if "timestamp" in df_exec.columns:
                        df_exec["timestamp"] = pd.to_datetime(df_exec["timestamp"], errors="coerce")
                        last_fill = df_exec["timestamp"].max()
                fills_db = db_dir() / "trades.db"
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
            st.caption(f"Live fills status error: {e}")

    with st.expander("Symbol Epsilon Stability", expanded=False):
        try:
            eps_path = logs_dir() / "symbol_eps_history.json"
            if eps_path.exists():
                eps_hist = json.loads(eps_path.read_text())
                eps_df = pd.DataFrame(eps_hist)
                eps_df["ts"] = pd.to_datetime(eps_df["ts"], unit="s")
                eps_expanded = eps_df["eps"].apply(pd.Series)
                eps_expanded["ts"] = eps_df["ts"]
                eps_expanded = eps_expanded.set_index("ts")
                st.line_chart(eps_expanded)
        except Exception as e:
            st.caption(f"Unable to load epsilon history: {e}")

    with st.expander("Execution Quality", expanded=False):
        try:
            from core.execution_engine import ExecutionEngine
            ee = ExecutionEngine()
            st.write("Per-instrument slippage bps (approx):", ee.instrument_slippage)
            cols, rows = _perf_timed_load("sqlite_recent_trades_200", _fetch_recent_trades_cached, 200, _trade_db_sig())
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
            cols2, rows2 = _perf_timed_load("sqlite_execution_stats_200", _fetch_execution_stats_cached, 200, _trade_db_sig())
            if rows2:
                ui.table(pd.DataFrame(rows2, columns=cols2), use_container_width=True)
        except Exception as e:
            st.caption(f"Execution quality error: {e}")

    with st.expander("Execution Analytics Summary", expanded=False):
        try:
            ea_path = logs_dir() / "execution_analytics.json"
            execution_vm = load_execution_vm(ea_path)
            if execution_vm.status == "missing":
                st.caption("Run scripts/run_execution_analytics.py to generate analytics.")
            else:
                render_execution_panel(execution_vm)
        except Exception as e:
            st.caption(f"Execution analytics error: {e}")

    with st.expander("Execution Intent vs Fill Accuracy", expanded=False):
        try:
            from config import config as cfg

            intents_path = Path(
                str(
                    getattr(
                        cfg,
                        "EXECUTION_INTENTS_LOG_PATH",
                        str(logs_dir() / "execution_intents.jsonl"),
                    )
                    or str(logs_dir() / "execution_intents.jsonl")
                )
            )
            fills_path = logs_dir() / "reconciliation_summary.json"
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
                st.caption("Run live mode to collect intents + reconciliation summary.")
        except Exception as e:
            st.caption(f"Execution intent accuracy error: {e}")

elif nav == "Reconciliation":
    with st.expander("Reconciliation Summary", expanded=False):
        try:
            from core.reconciliation import reconcile_execution_fills
            from config import config as cfg

            date_filter = st.text_input(
                "Exchange Date Filter (YYYY-MM-DD, optional)",
                value="",
                key="reconciliation_date_filter",
            ).strip() or None
            rec_summary_path = logs_dir() / "reconciliation_summary.json"
            rec_history_path = logs_dir() / "reconciliation_history.json"
            rec_csv_path = logs_dir() / "reconciliation_report.csv"
            exec_analytics_path = logs_dir() / "execution_analytics.json"
            eps_history_path = logs_dir() / "symbol_eps_history.json"
            expected_paths = [
                ("reconciliation_summary", rec_summary_path),
                ("reconciliation_report_csv", rec_csv_path),
                ("reconciliation_history", rec_history_path),
                ("execution_analytics", exec_analytics_path),
                ("symbol_eps_history", eps_history_path),
            ]
            diag_rows = []
            for label, p in expected_paths:
                exists = p.exists()
                size = p.stat().st_size if exists else 0
                mtime = (
                    datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
                    if exists
                    else None
                )
                diag_rows.append(
                    {
                        "name": label,
                        "path": str(p),
                        "exists": exists,
                        "size_bytes": size,
                        "mtime_utc": mtime,
                    }
                )
            st.caption("Reconciliation file diagnostics")
            ui.table(pd.DataFrame(diag_rows), use_container_width=True)

            auto_recon = st.checkbox(
                "Auto-generate reconciliation (offline, safe)",
                value=False,
                key="auto_reconcile_safe_toggle",
            )
            auto_recon_interval = int(
                st.number_input(
                    "Auto-reconcile interval (sec)",
                    min_value=30,
                    max_value=3600,
                    value=300,
                    step=30,
                    key="auto_reconcile_interval_sec",
                    disabled=not auto_recon,
                )
            )
            exec_mode = str(getattr(cfg, "EXECUTION_MODE", "PAPER") or "PAPER").upper()
            readiness_state = str((st.session_state.get("readiness_snapshot") or {}).get("state") or "UNKNOWN").upper()
            offhours_mode = is_offhours({"state": readiness_state})
            auto_allowed = (exec_mode != "LIVE") or offhours_mode
            if auto_recon and auto_allowed:
                now_ts = time.time()
                last_ts = float(st.session_state.get("auto_reconcile_last_ts", 0.0) or 0.0)
                if (now_ts - last_ts) >= float(auto_recon_interval):
                    cmd = [sys.executable, "scripts/reconcile_fills.py"]
                    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                    st.session_state["auto_reconcile_last_ts"] = now_ts
                    if result.returncode != 0:
                        st.warning("Auto-reconciliation failed; check script output.")
                        if result.stderr:
                            st.caption(result.stderr.strip()[-500:])
                    elif hasattr(st, "toast"):
                        st.toast("Auto-reconciliation refreshed.")
            elif auto_recon and not auto_allowed:
                st.caption("Auto-reconciliation is restricted in LIVE during market hours.")

            rows, rec = reconcile_execution_fills(trade_date=date_filter)
            # Prefer loader contract for artifact rendering; preserve existing table shape.
            recon_vm = load_recon_vm(rec_summary_path)
            if recon_vm.status in {"ok", "warning", "error"} and recon_vm.payload:
                render_recon_panel(recon_vm)
            else:
                ui.table(pd.DataFrame([rec]), use_container_width=True)
            if rec.get("avg_confidence") is not None:
                st.metric("Reconciliation Confidence", f"{float(rec['avg_confidence']):.2f}")
            if rec.get("error"):
                st.error(str(rec.get("error")))
            if rec.get("warning"):
                st.warning(str(rec.get("warning")))
            missing_any = any(not row["exists"] for row in diag_rows)
            if missing_any:
                st.info("Missing reconciliation artifacts. Run: PYTHONPATH=. python scripts/reconcile_fills.py")
            if rec.get("position_mismatch"):
                st.warning(
                    "Broker open positions do not match local trade ledger."
                    f" broker={rec.get('broker_open_positions')} local={rec.get('local_open_positions')}"
                )
            if rows:
                st.caption(f"Reconciled execution fills: {len(rows)}")
        except Exception as e:
            st.error(f"Reconciliation summary error: {e}")

    with st.expander("Execution Events Debug", expanded=False):
        try:
            from core.reconciliation import read_execution_fill_events
            from config import config as cfg

            events = read_execution_fill_events(limit=10)
            storage_path = str(getattr(cfg, "ANALYTICS_RUNTIME_DIR", "runtime/analytics") or "runtime/analytics")
            run_id = str(getattr(cfg, "RUN_ID", "") or getattr(cfg, "EXEC_RUN_ID", "") or "UNKNOWN_RUN")
            desk_id = str(getattr(cfg, "DESK_ID", "DEFAULT"))
            mode = str(getattr(cfg, "EXECUTION_MODE", "PAPER")).upper()

            col_a, col_b, col_c = st.columns(3)
            col_a.metric("run_id", run_id)
            col_b.metric("desk_id", desk_id)
            col_c.metric("mode", mode)
            st.caption(f"Execution event storage path: {storage_path}")

            if events:
                ui.table(pd.DataFrame(events), use_container_width=True)
            else:
                st.error(
                    "No EXECUTION_FILL events found. Reconciliation reads only execution-fill events "
                    "from runtime/analytics/*/events.jsonl."
                )
        except Exception as e:
            st.error(f"Execution events debug error: {e}")

    with st.expander("Reconciliation Match-Rate Trend", expanded=False):
        try:
            rec_hist = logs_dir() / "reconciliation_history.json"
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
                    st.error("No reconciliation history yet. Run scripts/reconcile_fills.py first.")
            else:
                st.error("No reconciliation history yet. Run scripts/reconcile_fills.py first.")
        except Exception as e:
            st.error(f"Reconciliation history error: {e}")

elif nav == "Risk & Governance":
    advanced = st.toggle("Advanced", value=False, key="adv_scorecard")
    if advanced:
        with st.expander("Top‑1% Readiness Scorecard", expanded=False):
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
                st.caption(f"Scorecard error: {e}")

    with st.expander("Arm Live Trades", expanded=False):
        try:
            arm_path = logs_dir() / "arm_live.json"
            arm_state = {"armed": False}
            if arm_path.exists():
                arm_state = json.loads(arm_path.read_text())
            confirm = st.checkbox("I understand this enables live order placement", value=False)
            if st.button("Arm Live Trades", disabled=not confirm):
                arm_state = {"armed": True, "timestamp": pd.Timestamp.now().isoformat()}
                arm_path.parent.mkdir(exist_ok=True)
                arm_path.write_text(json.dumps(arm_state, indent=2))
                st.caption("Live trading is armed (placement still guarded by config).")
            st.write(f"Current state: {'ARMED' if arm_state.get('armed') else 'NOT ARMED'}")
        except Exception as e:
            st.caption(f"Arm live trades error: {e}")

elif nav == "Data & SLA":
    with st.expander("Data & SLA Panels", expanded=False):
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
                    empty_state("No daily stats yet. Showing from trade log file.")
                    daily = df.groupby("date").agg(
                        pnl=("pnl", "sum"),
                        win_rate=("pnl", lambda x: (x > 0).mean())
                    ).reset_index()
                    ui.table(daily, use_container_width=True)
            else:
                empty_state("No trades.db yet.")
        except Exception as e:
            st.caption(f"Daily PF/Sharpe error: {e}")

        st.subheader("Daily Rollup Utility")
        try:
            import subprocess
            if st.button("Run Daily Rollup Now"):
                with st.spinner("Running daily rollup..."):
                    result = subprocess.run([sys.executable, "scripts/daily_rollup.py"], check=False, capture_output=True, text=True)
                    _log_path("daily_rollup.log").write_text((result.stdout or "") + "\n" + (result.stderr or ""))
                if result.returncode == 0:
                    st.caption("Daily rollup completed.")
                else:
                    st.caption("Daily rollup failed. Check logs/daily_rollup.log.")
        except Exception as e:
            st.caption(f"Daily rollup error: {e}")

        st.subheader("Data SLA Status")
        try:
            from core.freshness_sla import get_freshness_status
            sla = get_freshness_status(force=True)
            ui.table(pd.DataFrame([sla]), use_container_width=True)
        except Exception as e:
            st.caption(f"SLA status error: {e}")

        st.subheader("Option Chain Health")
        try:
            health_path = _log_path("option_chain_health.json")
            if health_path.exists():
                health = json.loads(health_path.read_text())
                if isinstance(health, dict) and health:
                    df_h = pd.DataFrame(health.values())
                    ui.table(df_h, use_container_width=True)
                    warn = df_h[df_h["status"] == "WARN"] if "status" in df_h.columns else pd.DataFrame()
                    if not warn.empty:
                        st.caption("Option chain health warnings detected.")
                else:
                    empty_state("No option chain health data yet.")
            else:
                st.caption("Run live market fetch to generate option chain health.")
        except Exception as e:
            st.caption(f"Option chain health error: {e}")

        st.subheader("Walk-Forward Risk Summary")
        try:
            summary_path = _log_path("walk_forward_risk_summary.json")
            strat_path = _log_path("walk_forward_strategy_summary.csv")
            if summary_path.exists():
                summary = json.loads(summary_path.read_text())
                if isinstance(summary, list) and summary:
                    ui.table(pd.DataFrame(summary), use_container_width=True)
                else:
                    ui.table(pd.DataFrame([summary]), use_container_width=True)
            else:
                st.caption("Run walk-forward backtest to generate risk summary.")
            if strat_path.exists():
                if strat_path.stat().st_size == 0:
                    df_s = pd.DataFrame()
                else:
                    df_s = pd.read_csv(strat_path)
                if not df_s.empty:
                    ui.table(df_s, use_container_width=True)
        except Exception as e:
            st.caption(f"Walk-forward summary error: {e}")

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
            strat_path = _log_path("walk_forward_strategy_summary.csv")
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
                            st.caption("WF lock is enabled but no strategies passed. Trades may be fully blocked.")
        except Exception as e:
            st.caption(f"WF lock error: {e}")

        st.subheader("Walk-Forward Backtest Settings")
        try:
            from config import config as cfg
            data_files = sorted([p for p in data_root().glob("*.csv")])
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
                    st.caption("No data file selected.")
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
                    st.caption("Backtest complete. Risk summary updated.")
        except Exception as e:
            st.caption(f"Backtest settings error: {e}")

elif nav == "ML/RL":
    st.subheader("Model Training Utilities")
    try:
        micro_paths = _micro_training_paths()
        micro_state = _compute_micro_training_status(micro_paths)
        micro_label, stale_artifact = _micro_model_badge_state(micro_paths, micro_state)
        micro_ready = bool(micro_state.get("ready"))
        micro_ready_reason = str(micro_state.get("ready_reason_code") or "").strip()
        rl_trained = _log_path("rl_metrics.json").exists()
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Micro Model", micro_label)
        col_s2.metric("RL Model", "Trained" if rl_trained else "Not trained")
        col_s3.metric("Micro Train Status", str(micro_state.get("status") or MICRO_TRAIN_STATUS_FAILED))
        if stale_artifact:
            st.caption("A stale micro-model artifact exists from an older run; latest training failed.")

        st.caption(f"Micro training log: {micro_state.get('log_path')}")
        st.caption(f"Micro model artifact: {micro_state.get('model_artifact_path')}")
        if not micro_ready and micro_ready_reason:
            st.caption(f"Micro model readiness: {micro_ready_reason}")
        if bool(micro_state.get("legacy_status_conflict")):
            st.warning(
                "Detected conflicting legacy micro status file at "
                f"{micro_state.get('legacy_status_path')}. Canonical status under .runtime/logs is used."
            )
        if not bool(micro_state.get("running")) and str(micro_state.get("status") or "").upper() == MICRO_TRAIN_STATUS_FAILED:
            fail_reason = micro_state.get("last_report_reason") or micro_state.get("error")
            if fail_reason:
                st.warning(f"Last micro training failed: {fail_reason}")
        micro_tail = list(micro_state.get("log_tail") or [])
        if micro_tail:
            st.code("\n".join(micro_tail[-50:]), language="text")
        else:
            st.caption("No micro training logs yet.")

        col_a, col_b, col_c, col_d = st.columns(4)
        if col_a.button("Train Micro Model", key="train_micro_model_button"):
            tf_timeout = float(getattr(cfg, "MICRO_TF_IMPORT_TIMEOUT_SEC", 5.0) or 5.0)
            tf_ok = check_tf_available(timeout_sec=tf_timeout)
            backend_override = None
            if not tf_ok:
                st.warning(
                    "TensorFlow not available/too slow to import in this environment. "
                    "Install supported TF build or use separate env."
                )
                backend_override = "sklearn"
            started, message = start_micro_training_subprocess(backend_override=backend_override, paths=micro_paths)
            if started:
                st.success(message)
            else:
                st.warning(message)
            micro_state = _compute_micro_training_status(micro_paths)
        if col_b.button(
            "Cancel training",
            key="cancel_micro_model_button",
            disabled=not bool(micro_state.get("running")),
        ):
            cancelled, message = cancel_micro_training(paths=micro_paths)
            if cancelled:
                st.warning(message)
            else:
                st.info(message)
            micro_state = _compute_micro_training_status(micro_paths)
        if "rl_training" not in st.session_state:
            st.session_state["rl_training"] = False
        if col_c.button("Train RL (Validate)", disabled=st.session_state["rl_training"]):
            st.session_state["rl_training"] = True
            result = None
            try:
                with st.spinner("Training RL model..."):
                    result = subprocess.run([sys.executable, "rl/train_validate_rl.py"], check=False, capture_output=True, text=True)
                    _log_path("train_rl.log").write_text((result.stdout or "") + "\n" + (result.stderr or ""))
            finally:
                st.session_state["rl_training"] = False
            if result and result.returncode == 0:
                st.success("RL training completed.")
            else:
                st.error("RL training failed or did not finish. Check the Training Console for details.")
        if col_d.button("Refresh IV Skew Data"):
            with st.spinner("Refreshing option chain..."):
                result = subprocess.run([sys.executable, "scripts/refresh_option_chain.py"], check=False, capture_output=True, text=True)
                _log_path("refresh_iv.log").write_text((result.stdout or "") + "\n" + (result.stderr or ""))
            st.success("IV skew refresh completed.")
    except Exception:
        st.warning("Training utilities error. Check application logs for details.")

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
            "Micro Train": _log_path("train_micro.log"),
            "RL Train": _log_path("train_rl.log"),
            "IV Refresh": _log_path("refresh_iv.log"),
        }
        choice = st.selectbox("Select log", list(log_files.keys()))
        log_path = log_files[choice]
        if log_path.exists():
            lines = _tail_log_lines(log_path, limit=50)
            text = "\n".join(lines)
            # simple color-coding for errors
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
        rl_path = _log_path("rl_metrics.json")
        if rl_path.exists():
            rld = pd.read_json(rl_path)
            rld["timestamp"] = pd.to_datetime(rld["timestamp"])
            rld = rld.sort_values("timestamp")
            st.line_chart(rld.set_index("timestamp")[["total_reward", "sharpe", "max_drawdown"]])
        else:
            empty_state("No RL metrics yet. Run rl/train_validate_rl.py if RL is enabled.")
    except Exception as e:
        st.warning(f"RL metrics error: {e}")

elif nav == "Market Depth":
    st.subheader("Depth Snapshots (SQLite)")
    try:
        depth_vm = load_depth_vm(Path(str(getattr(cfg, "TRADE_DB_PATH", ""))))
        render_depth_panel(depth_vm)
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

# Tab timing footer (debug)
_record_tab_render_duration(nav, _active_tab_render_start)
st.session_state["rerun_data_load_ms"] = float(round(_RERUN_PERF.get("data_load_ms", 0.0), 2))
st.session_state["rerun_data_load_steps"] = list(_RERUN_PERF.get("steps") or [])
_render_tab_timing_footer(nav)
_render_rerun_perf_footer(nav)

# End app shell container
end_shell()
