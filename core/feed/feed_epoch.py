"""Isolated authoritative feed-epoch foundation.

M1 deliberately does not stamp artifacts or wire lifecycle callbacks.  Later
 slices may use this module as the sole feed-currentness authority.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from typing import Any

from core.runtime_boot_identity import get_runtime_boot_identity

_LOCK = threading.RLock()
_EPOCH = 0
_ADVANCEMENT_AUDIT: list[dict[str, Any]] = []


def current_feed_epoch() -> int:
    """Return the current session-local epoch without mutating state."""
    with _LOCK:
        return int(_EPOCH)


def advance_feed_epoch(reason: str, metadata: Mapping[str, Any] | None = None) -> int:
    """Atomically advance the epoch and record an auditable transition."""
    global _EPOCH
    reason_text = str(reason or "").strip()
    if not reason_text:
        raise ValueError("feed epoch advancement requires a non-empty reason")
    metadata_copy = dict(metadata or {})
    identity = get_runtime_boot_identity()
    with _LOCK:
        old_epoch = int(_EPOCH)
        _EPOCH = old_epoch + 1
        _ADVANCEMENT_AUDIT.append(
            {
                "old_epoch": old_epoch,
                "new_epoch": int(_EPOCH),
                "reason": reason_text,
                "timestamp": float(time.time()),
                "run_id": identity.run_id,
                "boot_epoch": float(identity.boot_epoch),
                "metadata": metadata_copy,
            }
        )
        return int(_EPOCH)


def feed_epoch_audit() -> tuple[dict[str, Any], ...]:
    """Return an immutable snapshot of advancement evidence."""
    with _LOCK:
        return tuple(dict(item) for item in _ADVANCEMENT_AUDIT)


def _reset_feed_epoch_for_tests() -> None:
    """Reset only the process-local foundation state for isolated unit tests."""
    global _EPOCH
    with _LOCK:
        _EPOCH = 0
        _ADVANCEMENT_AUDIT.clear()


__all__ = ["current_feed_epoch", "advance_feed_epoch", "feed_epoch_audit"]
