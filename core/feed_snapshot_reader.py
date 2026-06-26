import json
import logging
from pathlib import Path
from typing import Any, Optional
from core.feed_state_model import FeedSnapshot, FeedHysteresisState
import time

logger = logging.getLogger(__name__)

def normalize_legacy_snapshot(payload: dict[str, Any]) -> FeedSnapshot:
    """Safely normalizes legacy payloads into a canonical FeedSnapshot."""
    payload = dict(payload or {})
    if isinstance(payload.get("canonical_feed_truth"), dict):
        payload = {**payload, **payload["canonical_feed_truth"]}
        
    now_epoch = time.time()
    ts_epoch = float(payload.get("ts_epoch") or payload.get("timestamp_epoch") or now_epoch)
    
    # Preserve missing start_epoch as None
    start_epoch_raw = payload.get("start_epoch")
    start_epoch = float(start_epoch_raw) if start_epoch_raw is not None else None

    # Default effective_ws_connected to ws_connected if missing
    ws_connected = bool(payload.get("ws_connected", False))
    effective_ws_connected_raw = payload.get("effective_ws_connected")
    if effective_ws_connected_raw is None:
        effective_ws_connected = ws_connected
    else:
        effective_ws_connected = bool(effective_ws_connected_raw)

    def _to_float_or_none(val: Any) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    # Handle feed_ok_hysteresis_state safely
    raw_hysteresis = payload.get("feed_ok_hysteresis_state")
    if isinstance(raw_hysteresis, dict):
        consecutive_good = int(raw_hysteresis.get("consecutive_good", 0))
        consecutive_bad = int(raw_hysteresis.get("consecutive_bad", 0))
        feed_ok = bool(raw_hysteresis.get("feed_ok", True))
    else:
        if raw_hysteresis is None:
            feed_ok = bool(payload.get("feed_ok", True))
        else:
            feed_ok = bool(raw_hysteresis)
        consecutive_good = 0
        consecutive_bad = 0
    
    hysteresis_state = FeedHysteresisState(
        consecutive_good=consecutive_good,
        consecutive_bad=consecutive_bad,
        feed_ok=feed_ok,
    )
    
    # Map legacy keys to process_restart_required and recovery_blocked
    process_restart_required = bool(payload.get("process_restart_required", False))
    runtime_state = str(payload.get("runtime_state") or payload.get("state") or "")
    feed_truth_reason_code = str(payload.get("feed_truth_reason_code") or payload.get("reason_code") or "")
    
    state_machine = payload.get("state_machine")
    if isinstance(state_machine, dict):
        if not runtime_state:
            runtime_state = str(state_machine.get("state") or "UNKNOWN")
        if not feed_truth_reason_code:
            feed_truth_reason_code = str(state_machine.get("reason") or "")
    else:
        if not runtime_state:
            runtime_state = "UNKNOWN"
    reconnect_blocked_reason = str(payload.get("reconnect_blocked_reason") or "")

    restart_states = {
        "RESTART_REQUIRED",
        "WS1006_PROCESS_RESTART_REQUIRED",
        "REACTOR_NOT_RESTARTABLE_PROCESS_RESTART_REQUIRED",
        "RESTART_VERIFY_FAILED",
        "FEED_LIFECYCLE_FATAL",
    }
    if (runtime_state.upper() in restart_states or 
        feed_truth_reason_code.upper() in restart_states or 
        reconnect_blocked_reason.upper() in restart_states):
        process_restart_required = True

    recovery_blocked = bool(payload.get("recovery_blocked", False))
    recovery_blocked_states = {"RECOVERY_BLOCKED", "RECONNECT_BLOCKED", "FEED_LIFECYCLE_FATAL"}
    if (process_restart_required or 
        runtime_state.upper() in recovery_blocked_states or 
        reconnect_blocked_reason.upper() in recovery_blocked_states):
        recovery_blocked = True
    
    return FeedSnapshot(
        ts_epoch=ts_epoch,
        start_epoch=start_epoch,
        runtime_state=runtime_state,
        ws_connected=ws_connected,
        effective_ws_connected=effective_ws_connected,
        market_open=bool(
            payload.get("market_open") 
            if payload.get("market_open") is not None 
            else (runtime_state in {
                "BOOTING", "STARTING", "CONNECTING", "SUBSCRIBED", 
                "VERIFYING_OPTION_TICKS", "VERIFIED_HEALTHY", "LIVE", 
                "DEGRADED", "RECOVERING"
            })
        ),
        last_tick_age_sec=_to_float_or_none(payload.get("last_tick_age_sec")),
        last_depth_age_sec=_to_float_or_none(payload.get("last_depth_age_sec")),
        latest_ltp_age_sec=_to_float_or_none(payload.get("latest_ltp_age_sec")),
        latest_option_tick_age_sec=_to_float_or_none(payload.get("latest_option_tick_age_sec")),
        subscribed_tokens_count=int(payload.get("subscribed_tokens_count") or 0),
        subscribed_option_tokens_count=int(payload.get("subscribed_option_tokens_count") or 0),
        missing_option_tokens_count=int(payload.get("missing_option_tokens_count") or 0),
        process_restart_required=process_restart_required,
        recovery_blocked=recovery_blocked,
        recovery_state=str(payload.get("recovery_state", "NONE")),
        feed_error_code=str(payload.get("feed_error_code", "")),
        feed_error_reason=str(payload.get("feed_error_reason", "")),
        feed_ok_hysteresis_state=hysteresis_state,
        reason_code=str(payload.get("reason_code") or payload.get("feed_truth_reason_code") or ""),
    )

def read_feed_snapshot(path: Path) -> Optional[FeedSnapshot]:
    """Reads a JSON snapshot file and normalizes it."""
    try:
        if not path.exists():
            return None
        with open(path, "r") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return None
        return normalize_legacy_snapshot(payload)
    except Exception as exc:
        logger.warning(f"Failed to read feed snapshot from {path}: {exc}")
        return None
