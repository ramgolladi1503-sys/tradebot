from __future__ import annotations

FEATURE_FLAGS = {
    "ENABLE_MEMORY": True,
    "ENABLE_MTF": True,
    "ENABLE_KEY_LEVELS": True,
    "ENABLE_EVENT_AWARENESS": True,
    "ENABLE_STATE_TRANSITIONS": True,
    "ENABLE_CALIBRATION": True,
}


def is_enabled(flag: str) -> bool:
    return bool(FEATURE_FLAGS.get(flag, False))
