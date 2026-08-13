"""Canonical provenance stamping for current feed artifacts (M2)."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Any, Mapping

from core.feed.feed_epoch import current_feed_epoch
from core.runtime_boot_identity import get_runtime_boot_identity

FEED_TRUTH_SCHEMA_VERSION = 1
FEED_RUNTIME_SCHEMA_VERSION = 1
FEED_TRUTH_CANONICAL_WRITER = "feed_truth.canonical"
FEED_RUNTIME_CANONICAL_WRITER = "feed_runtime.canonical"


def stamp_feed_truth_provenance(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return _stamp(payload, schema_version=FEED_TRUTH_SCHEMA_VERSION, writer=FEED_TRUTH_CANONICAL_WRITER)


def stamp_feed_runtime_provenance(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return _stamp(payload, schema_version=FEED_RUNTIME_SCHEMA_VERSION, writer=FEED_RUNTIME_CANONICAL_WRITER)


def _stamp(payload: Mapping[str, Any] | None, *, schema_version: int, writer: str) -> dict[str, Any]:
    identity = get_runtime_boot_identity()
    out = deepcopy(dict(payload or {}))
    out["run_id"] = identity.run_id
    out["boot_epoch"] = float(identity.boot_epoch)
    out["feed_epoch"] = int(current_feed_epoch())
    out["writer"] = writer
    out["schema_version"] = int(schema_version)
    out["produced_at"] = float(time.time())
    return out


__all__ = [
    "FEED_TRUTH_SCHEMA_VERSION",
    "FEED_RUNTIME_SCHEMA_VERSION",
    "FEED_TRUTH_CANONICAL_WRITER",
    "FEED_RUNTIME_CANONICAL_WRITER",
    "stamp_feed_truth_provenance",
    "stamp_feed_runtime_provenance",
]
