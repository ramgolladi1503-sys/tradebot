from __future__ import annotations

from typing import Any


REQUIRED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "snapshot_id",
    "timestamp_epoch",
    "token_coverage",
    "freshness",
    "data_sources",
}

DB_DERIVED_SOURCES = {"db", "sqlite", "sqlite_db"}


def _blocker(code: str, message: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "priority": "P0",
        "message": message,
        "evidence": evidence,
    }


def evaluate_runtime_snapshot_health(
    snapshot: dict[str, Any],
    *,
    feed_connected: bool,
    db_ok: bool,
    min_option_token_count: int = 1,
) -> dict[str, Any]:
    """Pure offline runtime-health evaluator for safe CI checks.

    This function intentionally has no broker, Streamlit, Kite, TensorFlow, or filesystem
    dependency. It validates the contract shape and the minimum live-readiness signals
    that matter before a runtime can be trusted.
    """

    blockers: list[dict[str, Any]] = []

    if not isinstance(snapshot, dict):
        return {
            "ok": False,
            "blockers": [
                _blocker(
                    "SNAPSHOT_TYPE_INVALID",
                    "Runtime snapshot must be a dictionary.",
                    {"actual_type": type(snapshot).__name__},
                )
            ],
        }

    missing = sorted(field for field in REQUIRED_TOP_LEVEL_FIELDS if field not in snapshot)
    if missing:
        blockers.append(
            _blocker(
                "SNAPSHOT_REQUIRED_FIELDS_MISSING",
                "Runtime snapshot is missing required fields.",
                {"missing_fields": missing},
            )
        )
        return {"ok": False, "blockers": blockers}

    token_coverage = snapshot.get("token_coverage")
    if not isinstance(token_coverage, dict):
        blockers.append(
            _blocker(
                "TOKEN_COVERAGE_INVALID",
                "token_coverage must be a dictionary.",
                {"actual_type": type(token_coverage).__name__},
            )
        )
    else:
        option_count = int(token_coverage.get("option_tokens_count") or 0)
        if option_count < max(1, int(min_option_token_count)):
            blockers.append(
                _blocker(
                    "TOKEN_COVERAGE_BELOW_THRESHOLD",
                    "Option token coverage is below the minimum executable threshold.",
                    {
                        "option_tokens_count": option_count,
                        "min_option_token_count": max(1, int(min_option_token_count)),
                        "snapshot_id": snapshot.get("snapshot_id"),
                    },
                )
            )

    freshness = snapshot.get("freshness")
    if not isinstance(freshness, dict):
        blockers.append(
            _blocker(
                "FRESHNESS_INVALID",
                "freshness must be a dictionary.",
                {"actual_type": type(freshness).__name__},
            )
        )
    else:
        try:
            max_tick_age = float(freshness.get("max_tick_age_sec"))
            sla_threshold = float(freshness.get("sla_threshold_sec"))
        except (TypeError, ValueError):
            blockers.append(
                _blocker(
                    "FRESHNESS_VALUES_INVALID",
                    "Freshness values must be numeric.",
                    {
                        "max_tick_age_sec": freshness.get("max_tick_age_sec"),
                        "sla_threshold_sec": freshness.get("sla_threshold_sec"),
                    },
                )
            )
        else:
            if max_tick_age > sla_threshold:
                blockers.append(
                    _blocker(
                        "FRESHNESS_STALE",
                        "Tick freshness exceeds SLA threshold.",
                        {
                            "max_tick_age_sec": max_tick_age,
                            "sla_threshold_sec": sla_threshold,
                            "snapshot_id": snapshot.get("snapshot_id"),
                        },
                    )
                )

    data_sources = snapshot.get("data_sources")
    if isinstance(data_sources, dict):
        source_values = {str(value).strip().lower() for value in data_sources.values()}
    elif isinstance(data_sources, list):
        source_values = {str(value).strip().lower() for value in data_sources}
    else:
        source_values = set()
        blockers.append(
            _blocker(
                "DATA_SOURCES_INVALID",
                "data_sources must be a dictionary or list.",
                {"actual_type": type(data_sources).__name__},
            )
        )

    if "memory" in source_values:
        blockers.append(
            _blocker(
                "MEMORY_SOURCE_FORBIDDEN",
                "Runtime snapshot must not use memory-only tick source.",
                {"data_sources": sorted(source_values)},
            )
        )

    if source_values and not any(source in DB_DERIVED_SOURCES for source in source_values):
        blockers.append(
            _blocker(
                "DB_DERIVED_SOURCE_REQUIRED",
                "Runtime snapshot must include a DB-derived tick source.",
                {"data_sources": sorted(source_values)},
            )
        )

    if not db_ok:
        blockers.append(
            _blocker(
                "DB_UNAVAILABLE",
                "SQLite/runtime data source is not healthy.",
                {"db_ok": False, "snapshot_id": snapshot.get("snapshot_id")},
            )
        )

    if not feed_connected:
        blockers.append(
            _blocker(
                "FEED_DISCONNECTED",
                "Live feed is not connected.",
                {"feed_connected": False, "snapshot_id": snapshot.get("snapshot_id")},
            )
        )

    return {"ok": len(blockers) == 0, "blockers": blockers}
