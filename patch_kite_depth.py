import re

with open("core/kite_depth_ws.py", "r") as f:
    content = f.read()

# 1. Add globals
content = content.replace(
    "_FEED_STARTUP_GRACE_SEC = 25.0",
    "_FEED_STARTUP_GRACE_SEC = 25.0\n_FEED_OK_CONSECUTIVE_BAD = 0\n_FEED_OK_CONSECUTIVE_GOOD = 0\n_FEED_OK_LAST = False"
)

# 2. Add kwargs to _write_feed_runtime_snapshot
content = content.replace(
    "    internal_retry_reason: str | None = None,\n) -> None:",
    "    internal_retry_reason: str | None = None,\n    feed_ok_hysteresis_state: dict | None = None,\n    start_epoch: float | None = None,\n) -> None:"
)

# 3. Add to JSON payload in _write_feed_runtime_snapshot
content = content.replace(
    "        \"disconnected_reason\": str(disconnected_reason_value or \"\").strip() or None,\n    }\n    if (",
    "        \"disconnected_reason\": str(disconnected_reason_value or \"\").strip() or None,\n        \"feed_ok_hysteresis_state\": dict(feed_ok_hysteresis_state) if feed_ok_hysteresis_state is not None else None,\n        \"start_epoch\": float(start_epoch) if start_epoch is not None else None,\n    }\n    if ("
)

# 4. Hysteresis logic in _persist_runtime_snapshot_row
hysteresis_code = """
    global _FEED_OK_CONSECUTIVE_BAD, _FEED_OK_CONSECUTIVE_GOOD, _FEED_OK_LAST
    from core.runtime_status_overlay import classify_runtime_feed_health
    from config import config as cfg
    health = classify_runtime_feed_health(payload)
    current_state = bool(health.feed_ok)
    if current_state:
        _FEED_OK_CONSECUTIVE_GOOD += 1
        _FEED_OK_CONSECUTIVE_BAD = 0
    else:
        _FEED_OK_CONSECUTIVE_BAD += 1
        _FEED_OK_CONSECUTIVE_GOOD = 0
        
    min_bad = int(cfg("FEED_STABILITY_HYSTERESIS_BAD_TICKS", 3))
    min_good = int(cfg("FEED_STABILITY_HYSTERESIS_GOOD_TICKS", 3))
    
    if current_state and not _FEED_OK_LAST and _FEED_OK_CONSECUTIVE_GOOD >= min_good:
        _FEED_OK_LAST = True
    elif not current_state and _FEED_OK_LAST and _FEED_OK_CONSECUTIVE_BAD >= min_bad:
        _FEED_OK_LAST = False
        
    payload["feed_ok_hysteresis_state"] = {
        "consecutive_bad": _FEED_OK_CONSECUTIVE_BAD,
        "consecutive_good": _FEED_OK_CONSECUTIVE_GOOD,
        "feed_ok": _FEED_OK_LAST,
    }
    
    ok = write_feed_runtime_snapshot(payload)
"""

content = content.replace(
    "    ok = write_feed_runtime_snapshot(payload)",
    hysteresis_code
)

# 5. Pass to _write_feed_runtime_snapshot in _persist_runtime_snapshot_row
content = content.replace(
    "        internal_retry_reason=internal_retry_reason,\n    )",
    "        internal_retry_reason=internal_retry_reason,\n        feed_ok_hysteresis_state=payload.get(\"feed_ok_hysteresis_state\"),\n        start_epoch=payload.get(\"start_epoch\"),\n    )"
)

# 6. Pass to _write_feed_runtime_snapshot in _handle_message
content = content.replace(
    "                restart_blocked_reason=None,\n            )",
    "                restart_blocked_reason=None,\n                feed_ok_hysteresis_state={\n                    \"consecutive_bad\": _FEED_OK_CONSECUTIVE_BAD,\n                    \"consecutive_good\": _FEED_OK_CONSECUTIVE_GOOD,\n                    \"feed_ok\": _FEED_OK_LAST,\n                },\n                start_epoch=float(_DEPTH_WS_START_EPOCH or 0.0),\n            )"
)

with open("core/kite_depth_ws.py", "w") as f:
    f.write(content)
