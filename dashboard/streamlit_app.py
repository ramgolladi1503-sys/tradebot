"""Headless-safe entrypoint for the Streamlit dashboard.

Migration note:
Importing this module outside Streamlit runtime now avoids bootstrapping the full UI,
so smoke-import checks do not require local dashboard data files.
"""

from __future__ import annotations

import math
import logging
import os
from pathlib import Path
import runpy
import sqlite3
import time
import traceback

try:
    from streamlit_autorefresh import st_autorefresh as _st_autorefresh
except Exception:  # pragma: no cover
    _st_autorefresh = None


logger = logging.getLogger(__name__)


def fmt_conf(conf) -> str:
    try:
        val = float(conf)
    except Exception:
        return "n/a"
    if not math.isfinite(val):
        return "n/a"
    return f"{val:.2f}"


def _should_bootstrap_runtime() -> bool:
    if __name__ == "__main__":
        return True
    if os.getenv("STREAMLIT_SERVER_PORT"):
        return True
    if os.getenv("STREAMLIT_RUNTIME"):
        return True
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


def _bootstrap_runtime() -> None:
    runtime_path = Path(__file__).with_name("streamlit_app_runtime.py")
    try:
        # Execute runtime script on every Streamlit rerun; do not rely on module import cache.
        runpy.run_path(str(runtime_path), run_name="__main__")
    except Exception as exc:
        # Never leave operator with blank page: render a hard error panel with traceback.
        try:
            import streamlit as st

            st.error("Dashboard render failure.")
            st.exception(exc)
            st.code(traceback.format_exc())
        except Exception:
            # Last-resort fallback for non-Streamlit contexts.
            logger.exception("dashboard_bootstrap_failed error=%s", type(exc).__name__)


def _canonical_market_open() -> bool:
    try:
        from core.market_calendar import market_open

        return bool(market_open())
    except Exception:
        return False


def _compute_refresh_gate(st_module) -> tuple[bool, str]:
    # Default to manual-refresh mode unless operator explicitly enables live updates.
    enabled = bool(st_module.session_state.get("auto_refresh_enabled", False))
    if not enabled:
        return False, "disabled"
    if bool(st_module.session_state.get("ui_local_trade_refresh_enabled", False)):
        return False, "local_trade_fragment"
    mode = str(st_module.session_state.get("trade_refresh_mode") or "Market open only")
    feed_status = str(st_module.session_state.get("ui_feed_status") or "INACTIVE").upper()
    market_is_open = _canonical_market_open()
    if mode == "Always refresh (UI only)":
        return True, "always_ui"
    if mode == "Refresh when feed active":
        return (feed_status == "ACTIVE"), "feed_active"
    return market_is_open, "market_open"


def _refresh_interval_sec(st_module) -> float:
    try:
        from config import config as cfg

        configured = float(st_module.session_state.get("refresh_interval_sec") or getattr(cfg, "UI_REFRESH_SEC", 2.0))
    except Exception:
        configured = 2.0
    # Keep interval >= 2s so dashboard cache TTLs stay <= refresh cadence.
    return max(2.0, configured)


def _render_refresh_debug_banner(st_module, now_ts: float, market_is_open: bool, last_refresh_ts: float, refresh_interval_sec: float) -> None:
    try:
        from config import config as cfg

        db_path = str(getattr(cfg, "TRADE_DB_PATH", ""))
    except Exception:
        db_path = ""
    st_module.caption(
        "Refresh debug: "
        f"now_ts={now_ts:.3f} "
        f"market_open={market_is_open} "
        f"last_refresh_ts={last_refresh_ts:.3f} "
        f"refresh_interval_sec={refresh_interval_sec:.1f} "
        f"data_db_path={db_path}"
    )


def _schedule_autorefresh(st_module, interval_ms: int) -> bool:
    if interval_ms <= 0:
        return False
    try:
        auto_fn = getattr(st_module, "autorefresh", None)
        if callable(auto_fn):
            auto_fn(interval=interval_ms, key="dashboard_main_autorefresh")
            return True
    except Exception:
        pass
    try:
        if _st_autorefresh is not None:
            _st_autorefresh(interval=interval_ms, key="dashboard_main_autorefresh")
            return True
    except Exception:
        pass
    return False


def _latest_db_tick_epoch() -> float | None:
    try:
        from config import config as cfg
    except Exception:
        return None
    db_path = str(getattr(cfg, "TRADE_DB_PATH", "") or "").strip()
    if not db_path:
        return None
    path = Path(db_path).expanduser()
    if not path.exists():
        return None
    try:
        with sqlite3.connect(str(path), timeout=1.0) as conn:
            row = conn.execute("SELECT MAX(timestamp_epoch) FROM ticks").fetchone()
    except Exception:
        return None
    try:
        val = float((row or [None])[0])
        if val > 1e12:
            val = val / 1000.0
        return val
    except Exception:
        return None


def _feed_runtime_snapshot_age_sec(now_ts: float) -> float | None:
    try:
        from core.paths import logs_dir
    except Exception:
        return None
    path = logs_dir() / "feed_runtime_latest.json"
    if not path.exists():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        ts_epoch = payload.get("ts_epoch")
        ts_val = float(ts_epoch)
        if ts_val > 1e12:
            ts_val = ts_val / 1000.0
        return max(0.0, float(now_ts) - float(ts_val))
    except Exception:
        return None


def _should_break_refresh_deadlock(st_module, now_ts: float) -> bool:
    runtime_age = _feed_runtime_snapshot_age_sec(now_ts)
    try:
        from config import config as cfg

        stale_sec = float(getattr(cfg, "UI_RUNTIME_HEALTH_MAX_AGE_SEC", 120.0))
    except Exception:
        stale_sec = 120.0
    if runtime_age is None or runtime_age <= stale_sec:
        return False
    db_epoch = _latest_db_tick_epoch()
    if db_epoch is None:
        return False
    recent_tick_sec = float(st_module.session_state.get("ui_deadlock_recent_tick_sec", 8.0))
    if (float(now_ts) - float(db_epoch)) > recent_tick_sec:
        return False
    last_seen = float(st_module.session_state.get("last_seen_db_tick_epoch") or 0.0)
    if db_epoch > last_seen:
        st_module.session_state["last_seen_db_tick_epoch"] = float(db_epoch)
        return True
    return False


def _apply_refresh_loop_policy() -> None:
    try:
        import streamlit as st
    except Exception:
        return

    now_ts = float(time.time())
    refresh_interval_sec = _refresh_interval_sec(st)
    last_refresh_ts = float(st.session_state.get("last_refresh_ts") or 0.0)
    if last_refresh_ts <= 0.0:
        last_refresh_ts = now_ts
        st.session_state["last_refresh_ts"] = last_refresh_ts

    market_is_open = _canonical_market_open()
    should_refresh, mode_reason = _compute_refresh_gate(st)
    _render_refresh_debug_banner(st, now_ts, market_is_open, last_refresh_ts, refresh_interval_sec)
    try:
        last_refresh_dt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_refresh_ts))
    except Exception:
        last_refresh_dt = f"{last_refresh_ts:.3f}"
    st.caption(f"Last refreshed at: {last_refresh_dt}")

    if should_refresh and (now_ts - last_refresh_ts) >= refresh_interval_sec:
        st.session_state["last_refresh_ts"] = now_ts
    if should_refresh:
        interval_ms = int(max(2000.0, float(refresh_interval_sec) * 1000.0))
        scheduled = _schedule_autorefresh(st, interval_ms=interval_ms)
        if not scheduled:
            st.warning("Auto-refresh scheduler unavailable. Please refresh manually.")
    else:
        if mode_reason == "local_trade_fragment":
            st.caption("Auto-refresh handled by live trade fragment.")
        else:
            st.caption(f"Auto-refresh paused ({mode_reason}).")
    if should_refresh and _should_break_refresh_deadlock(st, now_ts):
        st.session_state["last_refresh_ts"] = now_ts
        st.rerun()


if _should_bootstrap_runtime():
    _bootstrap_runtime()
    _apply_refresh_loop_policy()
