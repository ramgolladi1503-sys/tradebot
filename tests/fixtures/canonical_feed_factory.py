"""Real canonical feed artifacts for offline currentness tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.feed.artifact_loader import _INTEGRITY_EXCLUDED_KEYS
from core.feed.artifact_provenance import stamp_feed_runtime_provenance, stamp_feed_truth_provenance
from core.feed.lineage import build_truth_lineage
from core.runtime_truth_integrity import truth_hash_from_mapping


def _with_hash(payload: dict[str, Any]) -> dict[str, Any]:
    payload["snapshot_hash"] = truth_hash_from_mapping(payload, exclude_keys=_INTEGRITY_EXCLUDED_KEYS)
    payload["snapshot_hash_version"] = 1
    payload["truth_integrity_status"] = "OK"
    return payload


def make_valid_canonical_feed_pair(
    root: Path,
    *,
    feed_ok: bool = True,
    truth_updates: dict[str, Any] | None = None,
    runtime_updates: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write a mutually valid truth/runtime pair through production contracts."""
    root.mkdir(parents=True, exist_ok=True)
    truth_payload = {
        "feed_ok": bool(feed_ok),
        "feed_truth_state": "LIVE" if feed_ok else "DEGRADED",
        "feed_truth_reason_code": "OK" if feed_ok else "FEED_UNHEALTHY",
        "ws_connected": bool(feed_ok),
        "ts_epoch": 10.0,
    }
    truth_payload.update(dict(truth_updates or {}))
    truth = stamp_feed_truth_provenance(truth_payload)
    truth = _with_hash(truth)
    runtime_payload = {
        "feed_ok": bool(feed_ok),
        "execution_feed_ready": bool(feed_ok),
        "feed_truth_state": "LIVE" if feed_ok else "DEGRADED",
        "feed_truth_reason_code": "OK" if feed_ok else "FEED_UNHEALTHY",
        "ws_connected": bool(feed_ok),
        "last_tick_age_sec": 0.0,
        "last_depth_age_sec": 0.0,
        "ts_epoch": 10.0,
    }
    runtime_payload.update(dict(runtime_updates or {}))
    runtime = stamp_feed_runtime_provenance(runtime_payload, truth_payload=truth)
    runtime["truth_lineage"] = build_truth_lineage(truth)
    runtime = _with_hash(runtime)
    truth_path = root / "feed_truth_latest.json"
    runtime_path = root / "feed_runtime_latest.json"
    truth_path.write_text(json.dumps(truth, sort_keys=True), encoding="utf-8")
    runtime_path.write_text(json.dumps(runtime, sort_keys=True), encoding="utf-8")
    return truth_path, runtime_path
