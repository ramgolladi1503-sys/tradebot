from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InvariantDefinition:
    code: str
    description: str


class InvariantViolation(Exception):
    def __init__(self, code: str, message: str, evidence: dict[str, Any] | None = None):
        self.code = str(code)
        self.message = str(message)
        self.evidence: dict[str, Any] = dict(evidence or {})
        super().__init__(f"{self.code}: {self.message}")


INVARIANTS: list[InvariantDefinition] = [
    InvariantDefinition(
        code="INV_SCHEMA_FIELDS_REQUIRED",
        description="Snapshot must include schema_version and snapshot_id.",
    ),
    InvariantDefinition(
        code="INV_TIMESTAMP_EPOCH_REQUIRED",
        description="Snapshot must include timestamp_epoch as float seconds.",
    ),
    InvariantDefinition(
        code="INV_TIMESTAMP_KEYS_FORBIDDEN",
        description="Snapshot payload must not contain ts/ts_epoch keys; use timestamp_epoch only.",
    ),
    InvariantDefinition(
        code="INV_TOKEN_COVERAGE_REQUIRED",
        description="Snapshot must include token_coverage.index_token and token_coverage.option_tokens_count.",
    ),
    InvariantDefinition(
        code="INV_FRESHNESS_REQUIRED",
        description="Snapshot must include freshness.max_tick_age_sec and freshness.sla_threshold_sec.",
    ),
    InvariantDefinition(
        code="INV_DATA_SOURCES_DB_ONLY",
        description="Snapshot data_sources must include DB-derived tick reads and must not include memory source.",
    ),
]


_FORBIDDEN_TIMESTAMP_KEYS = {"ts", "ts_epoch"}
_DB_DERIVED_SOURCES = {"db", "sqlite", "sqlite_db"}


def _raise(code: str, message: str, *, stage: str, evidence: dict[str, Any] | None = None) -> None:
    payload = {"stage": stage}
    if evidence:
        payload.update(evidence)
    raise InvariantViolation(code=code, message=message, evidence=payload)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _walk_forbidden_keys(value: Any, path: str = "snapshot") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_str = str(key)
            next_path = f"{path}.{key_str}"
            if key_str in _FORBIDDEN_TIMESTAMP_KEYS:
                hits.append(next_path)
            hits.extend(_walk_forbidden_keys(child, next_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            hits.extend(_walk_forbidden_keys(child, f"{path}[{idx}]"))
    return hits


def assert_invariants(snapshot: dict, *, stage: str) -> None:
    if not isinstance(snapshot, dict):
        _raise(
            "INV_SNAPSHOT_TYPE",
            "Snapshot must be a dict.",
            stage=stage,
            evidence={"actual_type": type(snapshot).__name__},
        )

    if "schema_version" not in snapshot or "snapshot_id" not in snapshot:
        missing = [
            key
            for key in ("schema_version", "snapshot_id")
            if key not in snapshot
        ]
        _raise(
            "INV_SCHEMA_FIELDS_REQUIRED",
            "Snapshot missing required schema fields.",
            stage=stage,
            evidence={"missing_fields": missing},
        )

    ts_epoch = snapshot.get("timestamp_epoch")
    if not _is_number(ts_epoch):
        _raise(
            "INV_TIMESTAMP_EPOCH_REQUIRED",
            "Snapshot.timestamp_epoch must be float seconds.",
            stage=stage,
            evidence={"timestamp_epoch": ts_epoch},
        )

    forbidden_hits = _walk_forbidden_keys(snapshot)
    if forbidden_hits:
        _raise(
            "INV_TIMESTAMP_KEYS_FORBIDDEN",
            "Forbidden timestamp keys present; use timestamp_epoch only.",
            stage=stage,
            evidence={"forbidden_paths": forbidden_hits},
        )

    token_coverage = snapshot.get("token_coverage")
    if not isinstance(token_coverage, dict):
        _raise(
            "INV_TOKEN_COVERAGE_REQUIRED",
            "Snapshot.token_coverage must be a dict.",
            stage=stage,
            evidence={"token_coverage_type": type(token_coverage).__name__},
        )
    if "index_token" not in token_coverage or "option_tokens_count" not in token_coverage:
        missing = [
            key
            for key in ("index_token", "option_tokens_count")
            if key not in token_coverage
        ]
        _raise(
            "INV_TOKEN_COVERAGE_REQUIRED",
            "Snapshot.token_coverage missing required fields.",
            stage=stage,
            evidence={"missing_fields": missing},
        )

    freshness = snapshot.get("freshness")
    if not isinstance(freshness, dict):
        _raise(
            "INV_FRESHNESS_REQUIRED",
            "Snapshot.freshness must be a dict.",
            stage=stage,
            evidence={"freshness_type": type(freshness).__name__},
        )
    if "max_tick_age_sec" not in freshness or "sla_threshold_sec" not in freshness:
        missing = [
            key
            for key in ("max_tick_age_sec", "sla_threshold_sec")
            if key not in freshness
        ]
        _raise(
            "INV_FRESHNESS_REQUIRED",
            "Snapshot.freshness missing required fields.",
            stage=stage,
            evidence={"missing_fields": missing},
        )

    data_sources = snapshot.get("data_sources")
    if not data_sources:
        _raise(
            "INV_DATA_SOURCES_DB_ONLY",
            "Snapshot.data_sources must be present.",
            stage=stage,
            evidence={"data_sources": data_sources},
        )

    if isinstance(data_sources, dict):
        source_values = [str(v).strip().lower() for v in data_sources.values()]
    elif isinstance(data_sources, list):
        source_values = [str(v).strip().lower() for v in data_sources]
    else:
        _raise(
            "INV_DATA_SOURCES_DB_ONLY",
            "Snapshot.data_sources must be dict or list.",
            stage=stage,
            evidence={"data_sources_type": type(data_sources).__name__},
        )

    if "memory" in source_values:
        _raise(
            "INV_DATA_SOURCES_DB_ONLY",
            "Memory source is not allowed for ticks.",
            stage=stage,
            evidence={"data_sources": source_values},
        )

    if not any(src in _DB_DERIVED_SOURCES for src in source_values):
        _raise(
            "INV_DATA_SOURCES_DB_ONLY",
            "DB-derived tick source is required.",
            stage=stage,
            evidence={"data_sources": source_values},
        )
