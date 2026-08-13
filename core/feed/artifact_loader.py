"""Fail-closed loaders for canonical feed artifacts (M3)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.feed.artifact_provenance import (
    FEED_RUNTIME_CANONICAL_WRITER,
    FEED_RUNTIME_SCHEMA_VERSION,
    FEED_TRUTH_CANONICAL_WRITER,
    FEED_TRUTH_SCHEMA_VERSION,
)
from core.feed.feed_epoch import current_feed_epoch
from core.paths import logs_dir
from core.runtime_boot_identity import get_runtime_boot_identity
from core.runtime_truth_integrity import truth_hash_from_mapping
from core.feed.lineage import LINEAGE_KEY, validate_truth_lineage

FEED_TRUTH_FILENAME = "feed_truth_latest.json"
FEED_RUNTIME_FILENAME = "feed_runtime_latest.json"
_INTEGRITY_EXCLUDED_KEYS = (
    "snapshot_hash", "snapshot_hash_version", "transport_heartbeat", "transport_heartbeat_epoch",
    "transport_heartbeat_age_sec", "transport_heartbeat_source", "transport_heartbeat_state",
    "transport_heartbeat_reason", "truth_integrity", "truth_integrity_alerts",
    "truth_integrity_alert_count", "truth_integrity_status",
)


def load_current_feed_truth(path: str | Path | None = None) -> dict[str, Any]:
    return _load(path or logs_dir() / FEED_TRUTH_FILENAME, "feed_truth", FEED_TRUTH_CANONICAL_WRITER, FEED_TRUTH_SCHEMA_VERSION, ("run_id", "boot_epoch", "feed_epoch", "writer", "schema_version", "produced_at"))


def load_current_feed_runtime(path: str | Path | None = None, truth_path: str | Path | None = None) -> dict[str, Any]:
    result = _load(path or logs_dir() / FEED_RUNTIME_FILENAME, "feed_runtime", FEED_RUNTIME_CANONICAL_WRITER, FEED_RUNTIME_SCHEMA_VERSION, ("run_id", "boot_epoch", "feed_epoch", "writer", "schema_version", "produced_at", "feed_ok", LINEAGE_KEY))
    if not result.get("valid"):
        return result
    runtime_path = Path(path or logs_dir() / FEED_RUNTIME_FILENAME)
    truth_result = load_current_feed_truth(truth_path or runtime_path.parent / FEED_TRUTH_FILENAME)
    if not truth_result.get("valid"):
        return _invalid(Path(path or logs_dir() / FEED_RUNTIME_FILENAME), "feed_runtime", "CANONICAL_TRUTH_INVALID", [truth_result.get("reason_code", "truth_invalid")])
    ok, reason = validate_truth_lineage(result["payload"], truth_result["payload"])
    if not ok:
        return _invalid(Path(path or logs_dir() / FEED_RUNTIME_FILENAME), "feed_runtime", reason, [reason])
    return result


def _invalid(path: Path, artifact_type: str, reason_code: str, reasons: list[str], **extra: Any) -> dict[str, Any]:
    return {"valid": False, "artifact_type": artifact_type, "path": str(path), "payload": None, "reason_code": reason_code, "reasons": reasons, **extra}


def _diagnostic_fields(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: raw[key] for key in ("ws_connected", "runtime_state", "intended_tokens_count", "subscribed_option_tokens_count", "option_feed_block_reason_by_symbol") if key in raw}


def _load(path_value: str | Path, artifact_type: str, expected_writer: str, expected_schema: int, required: tuple[str, ...]) -> dict[str, Any]:
    path = Path(path_value)
    if not path.exists():
        return _invalid(path, artifact_type, "MISSING_ARTIFACT", ["artifact_not_found"])
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _invalid(path, artifact_type, "MALFORMED_ARTIFACT", ["invalid_json"])
    if not isinstance(raw, dict):
        return _invalid(path, artifact_type, "MALFORMED_ARTIFACT", ["artifact_not_object"])
    observed_hash = raw.get("snapshot_hash")
    expected_hash = truth_hash_from_mapping(raw, exclude_keys=_INTEGRITY_EXCLUDED_KEYS)
    missing = [field for field in required if field not in raw]
    if missing:
        return _invalid(path, artifact_type, "MISSING_REQUIRED_FIELD", missing, observed_snapshot_hash=observed_hash, expected_snapshot_hash=expected_hash, diagnostic_fields=_diagnostic_fields(raw))
    if raw.get("writer") != expected_writer:
        return _invalid(path, artifact_type, "WRITER_MISMATCH", ["writer_mismatch"], observed_writer=raw.get("writer"))
    if type(raw.get("schema_version")) is not int or raw["schema_version"] != expected_schema:
        return _invalid(path, artifact_type, "SCHEMA_MISMATCH", ["schema_version_mismatch"], observed_schema_version=raw.get("schema_version"))
    identity = get_runtime_boot_identity()
    if raw.get("run_id") != identity.run_id:
        return _invalid(path, artifact_type, "SESSION_MISMATCH", ["run_id_mismatch"])
    boot_epoch = raw.get("boot_epoch")
    if type(boot_epoch) not in (int, float) or isinstance(boot_epoch, bool) or float(boot_epoch) != float(identity.boot_epoch):
        return _invalid(path, artifact_type, "SESSION_MISMATCH", ["boot_epoch_mismatch"])
    feed_epoch = raw.get("feed_epoch")
    if type(feed_epoch) is not int or feed_epoch != current_feed_epoch():
        return _invalid(path, artifact_type, "EPOCH_MISMATCH", ["feed_epoch_invalid_or_not_current"])
    if type(raw.get("produced_at")) not in (int, float) or isinstance(raw.get("produced_at"), bool):
        return _invalid(path, artifact_type, "MISSING_REQUIRED_FIELD", ["produced_at_invalid"])
    if observed_hash != expected_hash:
        return _invalid(path, artifact_type, "INTEGRITY_MISMATCH", ["snapshot_hash_mismatch"], observed_snapshot_hash=observed_hash, expected_snapshot_hash=expected_hash)
    return {"valid": True, "artifact_type": artifact_type, "path": str(path), "payload": deepcopy(raw), "reason_code": "VALID_CURRENT_ARTIFACT", "reasons": []}


__all__ = ["load_current_feed_truth", "load_current_feed_runtime"]
