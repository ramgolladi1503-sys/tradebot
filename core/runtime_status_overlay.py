from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from config import config as cfg
from core.auth_manager import runtime_auth_snapshot
from core.events import write_json_atomic
from core.paths import logs_dir


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def derive_effective_ws_connected(feed_payload: dict[str, Any]) -> bool | None:
    ws_connected = feed_payload.get("ws_connected")
    if ws_connected is not True:
        if ws_connected is False:
            return False
        return None
    state_machine = feed_payload.get("state_machine") or {}
    state = str(state_machine.get("state") or "").strip().upper()
    reason = str(state_machine.get("reason") or "").strip().lower()
    if state == "DOWN" and (reason == "ws_disconnected" or reason.startswith("no_ws_messages")):
        return False
    return True


def derive_feed_ok(feed_payload: dict[str, Any]) -> bool:
    explicit = feed_payload.get("feed_ok")
    if isinstance(explicit, bool):
        return explicit
    state_machine = feed_payload.get("state_machine") or {}
    state = str(state_machine.get("state") or "").strip().upper()
    runtime_state = str(feed_payload.get("runtime_state") or "").strip().upper()
    option_blockers = feed_payload.get("option_feed_block_reason_by_symbol") or {}
    option_ok = True
    if isinstance(option_blockers, dict) and option_blockers:
        option_ok = all(str(v or "").strip().upper() == "OK" for v in option_blockers.values())
    last_tick_age_sec = feed_payload.get("last_tick_age_sec")
    last_depth_age_sec = feed_payload.get("last_depth_age_sec")
    try:
        last_tick_age_val = float(last_tick_age_sec) if last_tick_age_sec is not None else None
    except Exception:
        last_tick_age_val = None
    try:
        last_depth_age_val = float(last_depth_age_sec) if last_depth_age_sec is not None else None
    except Exception:
        last_depth_age_val = None
    effective_ws = derive_effective_ws_connected(feed_payload)
    return bool(
        effective_ws is True
        and state == "LIVE"
        and runtime_state == "RUNNING"
        and option_ok
        and (last_tick_age_val is None or last_tick_age_val <= float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)))
        and (last_depth_age_val is None or last_depth_age_val <= float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 6.0)))
    )


def _primary_feed_blocker(feed_payload: dict[str, Any]) -> str:
    option_blockers = feed_payload.get("option_feed_block_reason_by_symbol") or {}
    if isinstance(option_blockers, dict):
        for value in option_blockers.values():
            text = str(value or "").strip().upper()
            if text and text != "OK":
                return text
    state_machine = feed_payload.get("state_machine") or {}
    reason = str(state_machine.get("reason") or "").strip()
    if reason:
        return reason.upper()
    return "FEED_UNHEALTHY"


def _is_feed_runtime_overlay(payload: dict[str, Any]) -> bool:
    return str(payload.get("overlay_source") or "").strip() == "feed_runtime_overlay"


def publish_feed_unhealthy_status_overlay(
    *,
    feed_payload: dict[str, Any],
    logs_root: Path | str | None = None,
    now_epoch: float | None = None,
) -> bool:
    if not bool(getattr(cfg, "FEED_RUNTIME_STATUS_OVERLAY_ENABLE", True)):
        return False
    if not isinstance(feed_payload, dict):
        return False
    if not bool(feed_payload.get("market_open", False)):
        return False

    effective_ws_connected = derive_effective_ws_connected(feed_payload)
    feed_ok = derive_feed_ok(feed_payload)

    target_logs_root = Path(logs_root) if logs_root is not None else logs_dir()
    target_logs_root.mkdir(parents=True, exist_ok=True)
    ts_epoch = float(now_epoch if now_epoch is not None else time.time())
    ts_local = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts_epoch))
    auth = runtime_auth_snapshot()

    suggestions_path = target_logs_root / "suggestions_status.json"
    current_suggestions = _read_json(suggestions_path)
    engine_path = target_logs_root / "engine_cycle_status.json"
    current_engine = _read_json(engine_path)
    runtime_health_path = target_logs_root / "runtime_health_latest.json"
    current_health = _read_json(runtime_health_path)
    runtime_state = str(feed_payload.get("runtime_state") or "").strip().upper() or "UNKNOWN"
    subscribed_option_tokens_count = int(feed_payload.get("subscribed_option_tokens_count") or 0)
    missing_option_tokens_count = int(feed_payload.get("missing_option_tokens_count") or 0)
    subscribed_tokens_count = int(feed_payload.get("subscribed_tokens_count") or 0)

    if feed_ok and effective_ws_connected is not False:
        should_heal = _is_feed_runtime_overlay(current_suggestions) or _is_feed_runtime_overlay(current_engine)
        if not should_heal:
            return False

        suggestions_payload = dict(current_suggestions)
        suggestions_payload.update(
            {
                "ts_epoch": ts_epoch,
                "ts_local": ts_local,
                "status": "blocked",
                "reason": "feed_recovered_waiting_cycle_refresh",
                "subreason": "",
                "primary_blocker": None,
                "visible_suggestion_count": 0,
                "visible_advisory_count": 0,
                "visible_queue_only_count": 0,
                "visible_executable_count": 0,
                "suggestion_count": 0,
                "feed_ok": True,
                "ws_connected": effective_ws_connected,
                "auth_ok": bool(auth.get("auth_ok", True)),
                "auth_state": str(auth.get("auth_state") or "UNKNOWN"),
                "auth_reason": str(auth.get("auth_reason") or ""),
                "subscribed_option_tokens_count": subscribed_option_tokens_count,
                "missing_option_tokens_count": missing_option_tokens_count,
                "overlay_source": "feed_runtime_overlay",
                "overlay_state": "feed_recovered_waiting_cycle_refresh",
            }
        )
        write_json_atomic(suggestions_path, suggestions_payload)

        engine_payload = dict(current_engine)
        engine_payload.update(
            {
                "ts_epoch": ts_epoch,
                "cycle_ok": False,
                "cycle_stage": "waiting_cycle_refresh",
                "reason": "feed_recovered_waiting_cycle_refresh",
                "subreason": "",
                "primary_blocker": None,
                "visible_suggestion_count": 0,
                "visible_advisory_count": 0,
                "visible_queue_only_count": 0,
                "visible_executable_count": 0,
                "feed_ok": True,
                "ws_connected": effective_ws_connected,
                "auth_ok": bool(auth.get("auth_ok", True)),
                "auth_state": str(auth.get("auth_state") or "UNKNOWN"),
                "auth_reason": str(auth.get("auth_reason") or ""),
                "subscribed_option_tokens_count": subscribed_option_tokens_count,
                "missing_option_tokens_count": missing_option_tokens_count,
                "last_error": str(feed_payload.get("last_error") or ""),
                "overlay_source": "feed_runtime_overlay",
                "overlay_state": "feed_recovered_waiting_cycle_refresh",
            }
        )
        write_json_atomic(engine_path, engine_payload)

        health_payload = dict(current_health)
        health_payload.update(
            {
                "ts_epoch": ts_epoch,
                "snapshot_ts_epoch": ts_epoch,
                "snapshot_age_sec": 0.0,
                "market_open": bool(feed_payload.get("market_open", False)),
                "mode": "LIVE",
                "feed": {
                    "runtime_state": runtime_state,
                    "ws_connected": effective_ws_connected,
                    "sla_status": "OK",
                    "sla_state": "LIVE",
                    "allow_stale_quotes": False,
                    "blockers": [],
                    "reasons": [],
                    "ltp_required": True,
                    "depth_required": True,
                    "subscribed_option_tokens_count": subscribed_option_tokens_count,
                    "subscribed_tokens_count": subscribed_tokens_count,
                    "subscriptions_count": subscribed_tokens_count,
                    "missing_option_tokens_count": missing_option_tokens_count,
                },
            }
        )
        write_json_atomic(runtime_health_path, health_payload)
        return True

    blocker = _primary_feed_blocker(feed_payload)
    suggestions_payload = dict(current_suggestions)
    suggestions_payload.update(
        {
            "ts_epoch": ts_epoch,
            "ts_local": ts_local,
            "status": "blocked",
            "reason": "feed_unhealthy",
            "subreason": blocker,
            "primary_blocker": blocker,
            "visible_suggestion_count": 0,
            "visible_advisory_count": 0,
            "visible_queue_only_count": 0,
            "visible_executable_count": 0,
            "suggestion_count": 0,
            "feed_ok": False,
            "ws_connected": effective_ws_connected,
            "auth_ok": bool(auth.get("auth_ok", True)),
            "auth_state": str(auth.get("auth_state") or "UNKNOWN"),
            "auth_reason": str(auth.get("auth_reason") or ""),
            "subscribed_option_tokens_count": subscribed_option_tokens_count,
            "missing_option_tokens_count": missing_option_tokens_count,
            "overlay_source": "feed_runtime_overlay",
            "overlay_state": "feed_unhealthy",
        }
    )
    write_json_atomic(suggestions_path, suggestions_payload)

    engine_payload = dict(current_engine)
    engine_payload.update(
        {
            "ts_epoch": ts_epoch,
            "cycle_ok": False,
            "cycle_stage": "blocked",
            "reason": "feed_unhealthy",
            "subreason": blocker,
            "primary_blocker": blocker,
            "visible_suggestion_count": 0,
            "visible_advisory_count": 0,
            "visible_queue_only_count": 0,
            "visible_executable_count": 0,
            "feed_ok": False,
            "ws_connected": effective_ws_connected,
            "auth_ok": bool(auth.get("auth_ok", True)),
            "auth_state": str(auth.get("auth_state") or "UNKNOWN"),
            "auth_reason": str(auth.get("auth_reason") or ""),
            "subscribed_option_tokens_count": subscribed_option_tokens_count,
            "missing_option_tokens_count": missing_option_tokens_count,
            "last_error": str(feed_payload.get("last_error") or ""),
            "overlay_source": "feed_runtime_overlay",
            "overlay_state": "feed_unhealthy",
        }
    )
    write_json_atomic(engine_path, engine_payload)

    health_payload = dict(current_health)
    health_payload.update(
        {
            "ts_epoch": ts_epoch,
            "snapshot_ts_epoch": ts_epoch,
            "snapshot_age_sec": 0.0,
            "market_open": bool(feed_payload.get("market_open", False)),
            "mode": "LIVE",
            "feed": {
                "runtime_state": runtime_state,
                "ws_connected": effective_ws_connected,
                "sla_status": "FAIL",
                "sla_state": "LIVE",
                "allow_stale_quotes": False,
                "blockers": [blocker],
                "reasons": [blocker],
                "ltp_required": True,
                "depth_required": True,
                "subscribed_option_tokens_count": subscribed_option_tokens_count,
                "subscribed_tokens_count": subscribed_tokens_count,
                "subscriptions_count": subscribed_tokens_count,
                "missing_option_tokens_count": missing_option_tokens_count,
            },
        }
    )
    write_json_atomic(runtime_health_path, health_payload)
    return True
