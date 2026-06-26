import json
from pathlib import Path
from typing import Any, Optional
from config import config as cfg
from core.feed_state_model import FeedSnapshot, FeedHysteresisState

_HYSTERESIS_GOOD_COUNT = 0
_HYSTERESIS_BAD_COUNT = 0
_HYSTERESIS_CURRENT_STATE = False

def _get_min_bad() -> int:
    return int(getattr(cfg, "FEED_OK_MIN_BAD_CYCLES", 3))

def _get_min_good() -> int:
    return int(getattr(cfg, "FEED_OK_MIN_GOOD_CYCLES", 3))

def build_feed_snapshot(*, raw_payload: dict[str, Any], now_epoch: float) -> FeedSnapshot:
    """Builds a FeedSnapshot from raw facts."""
    start_epoch = raw_payload.get("start_epoch")

    # Handle feed_ok_hysteresis_state safely
    hysteresis_raw = raw_payload.get("feed_ok_hysteresis_state")
    if isinstance(hysteresis_raw, dict):
        hysteresis_state = FeedHysteresisState(
            consecutive_good=int(hysteresis_raw.get("consecutive_good", 0)),
            consecutive_bad=int(hysteresis_raw.get("consecutive_bad", 0)),
            feed_ok=bool(hysteresis_raw.get("feed_ok", False)),
        )
    elif isinstance(hysteresis_raw, FeedHysteresisState):
        hysteresis_state = hysteresis_raw
    else:
        if hysteresis_raw is None:
            feed_ok = _HYSTERESIS_CURRENT_STATE
        else:
            feed_ok = bool(hysteresis_raw)
        hysteresis_state = FeedHysteresisState(
            consecutive_good=0,
            consecutive_bad=0,
            feed_ok=feed_ok,
        )

    return FeedSnapshot(
        ts_epoch=float(raw_payload.get("ts_epoch", now_epoch)),
        start_epoch=float(start_epoch) if start_epoch is not None else None,
        runtime_state=str(raw_payload.get("runtime_state", "UNKNOWN")),
        ws_connected=bool(raw_payload.get("ws_connected", False)),
        effective_ws_connected=bool(raw_payload.get("effective_ws_connected", False)),
        market_open=bool(raw_payload.get("market_open", False)),
        last_tick_age_sec=raw_payload.get("last_tick_age_sec"),
        last_depth_age_sec=raw_payload.get("last_depth_age_sec"),
        latest_ltp_age_sec=raw_payload.get("latest_ltp_age_sec"),
        latest_option_tick_age_sec=raw_payload.get("latest_option_tick_age_sec"),
        subscribed_tokens_count=int(raw_payload.get("subscribed_tokens_count", 0)),
        subscribed_option_tokens_count=int(raw_payload.get("subscribed_option_tokens_count", 0)),
        missing_option_tokens_count=int(raw_payload.get("missing_option_tokens_count", 0)),
        process_restart_required=bool(raw_payload.get("process_restart_required", False)),
        recovery_blocked=bool(raw_payload.get("recovery_blocked", False)),
        recovery_state=str(raw_payload.get("recovery_state", "NONE")),
        feed_error_code=str(raw_payload.get("feed_error_code", "")),
        feed_error_reason=str(raw_payload.get("feed_error_reason", "")),
        feed_ok_hysteresis_state=hysteresis_state,
    )

def update_hysteresis(snapshot: FeedSnapshot, raw_feed_ok: bool) -> FeedSnapshot:
    """Updates internal counters and returns a modified snapshot."""
    global _HYSTERESIS_GOOD_COUNT, _HYSTERESIS_BAD_COUNT, _HYSTERESIS_CURRENT_STATE

    if raw_feed_ok:
        _HYSTERESIS_BAD_COUNT = 0
        _HYSTERESIS_GOOD_COUNT += 1
        if _HYSTERESIS_GOOD_COUNT >= _get_min_good():
            _HYSTERESIS_CURRENT_STATE = True
    else:
        _HYSTERESIS_GOOD_COUNT = 0
        _HYSTERESIS_BAD_COUNT += 1
        if _HYSTERESIS_BAD_COUNT >= _get_min_bad():
            _HYSTERESIS_CURRENT_STATE = False

    payload = snapshot.to_payload()
    payload["feed_ok_hysteresis_state"] = {
        "consecutive_good": _HYSTERESIS_GOOD_COUNT,
        "consecutive_bad": _HYSTERESIS_BAD_COUNT,
        "feed_ok": _HYSTERESIS_CURRENT_STATE,
    }
    return build_feed_snapshot(raw_payload=payload, now_epoch=snapshot.ts_epoch)

def write_feed_snapshot(snapshot: FeedSnapshot, path: Path) -> None:
    """Writes the snapshot payload to JSON safely."""
    payload = snapshot.to_payload()
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w") as f:
        json.dump(payload, f)
    temp_path.replace(path)
