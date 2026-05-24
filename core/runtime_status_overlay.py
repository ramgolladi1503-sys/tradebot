from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from config import config as cfg
from core.auth_manager import runtime_auth_snapshot
from core.events import write_json_atomic
from core.feed_health_truth import FeedHealthTruthDecision, classify_feed_health_truth
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


def _runtime_symbols(feed_payload: dict[str, Any]) -> tuple[str, ...]:
    symbols: set[str] = set()
    for key in (
        "option_feed_block_reason_by_symbol",
        "option_last_tick_age_by_symbol",
        "symbol_feed_ok_by_symbol",
        "feed_ok_by_symbol",
    ):
        values = feed_payload.get(key)
        if not isinstance(values, dict):
            continue
        for symbol in values:
            text = str(symbol or "").strip().upper()
            if text:
                symbols.add(text)
    return tuple(sorted(symbols))


def _canonical_feed_health_payload(feed_payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(feed_payload)
    effective_ws_connected = derive_effective_ws_connected(feed_payload)
    if effective_ws_connected is not None:
        payload["effective_ws_connected"] = effective_ws_connected
    return payload


def classify_runtime_feed_health(feed_payload: dict[str, Any]) -> FeedHealthTruthDecision:
    """Return the canonical feed-health decision used by runtime overlays.

    This keeps runtime overlay visibility aligned with core.feed_health_truth
    instead of maintaining a separate feed_ok policy in this module.
    """
    if not isinstance(feed_payload, dict):
        return classify_feed_health_truth(None)
    payload = _canonical_feed_health_payload(feed_payload)
    return classify_feed_health_truth(
        payload,
        symbols=_runtime_symbols(payload),
        max_option_tick_age_sec=float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)),
        max_ltp_age_sec=float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)),
        max_depth_age_sec=float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 6.0)),
    )


def derive_feed_ok(feed_payload: dict[str, Any]) -> bool:
    return bool(classify_runtime_feed_health(feed_payload).feed_ok)


def _primary_feed_blocker(feed_payload: dict[str, Any]) -> str:
    option_blockers = feed_payload.get("option_feed_block_reason_by_symbol") or {}
    if isinstance(option_blockers, dict):
        for value in option_blockers.values():
            text = str(value or "").strip().upper()
            if text and text != "OK":
                return text
    decision = classify_runtime_feed_health(feed_payload)
    if decision.reasons:
        return str(decision.reasons[0]).strip().upper()
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

    feed_truth = classify_runtime_feed_health(feed_payload)
    feed_truth_payload = feed_truth.to_payload()
    effective_ws_connected = feed_truth.websocket_ok
    feed_ok = bool(feed_truth.feed_ok)

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
                "feed_health_truth": feed_truth_payload,
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
                "feed_health_truth": feed_truth_payload,
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
                    "feed_health_truth": feed_truth_payload,
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
            "feed_health_truth": feed_truth_payload,
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
            "feed_health_truth": feed_truth_payload,
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
                "feed_health_truth": feed_truth_payload,
            },
        }
    )
    write_json_atomic(runtime_health_path, health_payload)
    return True
