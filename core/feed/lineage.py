"""M7 binding between feed-derived artifacts and canonical feed truth."""

from __future__ import annotations

from typing import Any, Mapping

from core.feed.artifact_provenance import (
    FEED_TRUTH_CANONICAL_WRITER,
    FEED_TRUTH_SCHEMA_VERSION,
)
from core.runtime_truth_integrity import truth_hash_from_mapping


LINEAGE_KEY = "truth_lineage"


def truth_integrity(payload: Mapping[str, Any]) -> str:
    return str(payload.get("snapshot_hash") or truth_hash_from_mapping(payload))


def build_truth_lineage(truth: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(truth, Mapping):
        return {}
    return {
        "truth_run_id": truth.get("run_id"),
        "truth_boot_epoch": truth.get("boot_epoch"),
        "truth_feed_epoch": truth.get("feed_epoch"),
        "truth_writer": truth.get("writer"),
        "truth_schema_version": truth.get("schema_version"),
        "truth_integrity": truth_integrity(truth),
    }


def validate_truth_lineage(
    artifact: Mapping[str, Any],
    truth: Mapping[str, Any] | None,
) -> tuple[bool, str]:
    lineage = artifact.get(LINEAGE_KEY)
    if not isinstance(lineage, Mapping):
        return False, "MISSING_LINEAGE_REFERENCE"
    if not isinstance(truth, Mapping):
        return False, "CANONICAL_TRUTH_INVALID"
    expected = build_truth_lineage(truth)
    checks = (
        ("truth_run_id", "LINEAGE_RUN_ID_MISMATCH"),
        ("truth_boot_epoch", "LINEAGE_BOOT_EPOCH_MISMATCH"),
        ("truth_feed_epoch", "LINEAGE_FEED_EPOCH_MISMATCH"),
        ("truth_writer", "LINEAGE_WRITER_MISMATCH"),
        ("truth_schema_version", "LINEAGE_SCHEMA_MISMATCH"),
        ("truth_integrity", "LINEAGE_INTEGRITY_MISMATCH"),
    )
    for key, reason in checks:
        if lineage.get(key) != expected.get(key):
            return False, reason
    if expected["truth_writer"] != FEED_TRUTH_CANONICAL_WRITER:
        return False, "LINEAGE_WRITER_MISMATCH"
    if expected["truth_schema_version"] != FEED_TRUTH_SCHEMA_VERSION:
        return False, "LINEAGE_SCHEMA_MISMATCH"
    return True, "VALID_LINEAGE"


__all__ = ["LINEAGE_KEY", "build_truth_lineage", "validate_truth_lineage", "truth_integrity"]
