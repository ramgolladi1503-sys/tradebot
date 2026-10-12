"""Validated environment settings for callback and restart coordination.

These settings intentionally live outside ``config/config.py``, whose source
hash is pinned by a governed immutability check.
"""

from __future__ import annotations

import math
import os


def _raw_value(name: str, legacy_value):
    """Read an explicit environment value, then a legacy runtime override."""
    if name in os.environ:
        return os.environ[name], True
    if legacy_value is not None:
        return legacy_value, False
    return None, False


def _bounded_int(name: str, default: int, minimum: int, maximum: int, legacy_value=None) -> int:
    raw, from_env = _raw_value(name, legacy_value)
    if raw is None:
        return default
    try:
        # Reject fractional values rather than silently truncating them.
        parsed = int(str(raw).strip())
    except (TypeError, ValueError, OverflowError):
        return default
    if isinstance(raw, float) and not math.isfinite(raw):
        return default
    if not from_env and isinstance(raw, bool):
        return default
    return min(maximum, max(minimum, parsed))


def _bounded_float(
    name: str,
    default: float,
    minimum: float,
    maximum: float,
    legacy_value=None,
) -> float:
    raw, _from_env = _raw_value(name, legacy_value)
    if raw is None:
        return default
    try:
        parsed = float(raw)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(parsed):
        return default
    return min(maximum, max(minimum, parsed))


def callback_queue_max_pending(legacy_value=None) -> int:
    return _bounded_int(
        "DEPTH_WS_CALLBACK_QUEUE_MAX_PENDING", 64, 1, 4096, legacy_value
    )


def callback_transition_timeout_sec(legacy_value=None) -> float:
    return _bounded_float(
        "DEPTH_WS_CALLBACK_TRANSITION_TIMEOUT_SEC", 10.0, 0.01, 120.0, legacy_value
    )


def restart_lifecycle_wait_sec(legacy_value=None) -> float:
    return _bounded_float("FEED_RESTART_LIFECYCLE_WAIT_SEC", 10.0, 0.0, 30.0, legacy_value)


def restart_verify_block_log_cooldown_sec(legacy_value=None) -> float:
    return _bounded_float(
        "FEED_RESTART_VERIFY_BLOCK_LOG_COOLDOWN_SEC", 30.0, 0.0, 3600.0, legacy_value
    )
