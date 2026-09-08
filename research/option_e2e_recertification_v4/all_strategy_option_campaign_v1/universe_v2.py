from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path

from .universe import (
    CampaignUniverse,
    CampaignUniverseEntry,
    _canonical_hash,
    build_campaign_universe as _build_v1,
    write_campaign_universe,
)


_NONACTIVE_DUPLICATE_CLASSES = {
    "ALIAS",
    "CANONICAL_NONRUNNABLE_ENTITY",
    "DISCOVERED_SUPPORT_FILE",
}


def _reclassify_strategy_registry(
    row: CampaignUniverseEntry,
) -> CampaignUniverseEntry:
    if row.source_path != "strategies/strategy_registry.py":
        return row
    return replace(
        row,
        entity_class="DISCOVERED_SUPPORT_FILE",
        strategy_kind="support_file",
        certification_supported=False,
        option_campaign_action="EXCLUDE_SUPPORT_ENTITY",
        adapter_status="NOT_APPLICABLE",
        inclusion_reason=(
            "The strategy registry is inventory and registration infrastructure, "
            "not a standalone trading strategy."
        ),
        blocked_reason=None,
    )


def build_campaign_universe(repo_root: Path | None = None) -> CampaignUniverse:
    base = _build_v1(repo_root)
    rows = tuple(_reclassify_strategy_registry(row) for row in base.entries)

    actions: dict[str, int] = {}
    adapter_statuses: dict[str, int] = {}
    for row in rows:
        actions[row.option_campaign_action] = actions.get(row.option_campaign_action, 0) + 1
        adapter_statuses[row.adapter_status] = adapter_statuses.get(row.adapter_status, 0) + 1

    active_rows = [
        row for row in rows if row.entity_class not in _NONACTIVE_DUPLICATE_CLASSES
    ]
    duplicate_active_ids = sorted(
        entity_id
        for entity_id in {row.entity_id for row in active_rows}
        if sum(1 for row in active_rows if row.entity_id == entity_id) > 1
    )
    unclassified_files = sorted(
        row.source_path
        for row in rows
        if row.entity_class == "UNCLASSIFIED_STRATEGY_FILE" and row.source_path
    )
    historical_unclassified = sorted(
        row.entity_id
        for row in rows
        if row.entity_class == "HISTORICAL_UNCLASSIFIED_ENTITY"
    )
    hard_gaps = sorted(
        set(unclassified_files)
        | {f"historical_id:{value}" for value in historical_unclassified}
        | {f"duplicate_active_id:{value}" for value in duplicate_active_ids}
    )

    summary_without_hash = dict(base.summary)
    summary_without_hash.update(
        {
            "schema_version": "all_strategy_option_campaign_universe_v2",
            "universe_row_count": len(rows),
            "action_counts": dict(sorted(actions.items())),
            "adapter_status_counts": dict(sorted(adapter_statuses.items())),
            "hard_gap_count": len(hard_gaps),
            "hard_gaps": hard_gaps,
            "coverage_complete": len(hard_gaps) == 0,
            "duplicate_rule": (
                "Duplicate IDs are blocking only among active strategy or hypothesis rows; "
                "support-file basenames such as __init__.py are non-entities."
            ),
        }
    )
    summary_without_hash.pop("semantic_hash", None)
    summary = dict(summary_without_hash)
    summary["semantic_hash"] = _canonical_hash(
        {
            "summary": summary_without_hash,
            "entries": [asdict(row) for row in rows],
        }
    )
    return CampaignUniverse(entries=rows, summary=summary)


__all__ = [
    "CampaignUniverse",
    "CampaignUniverseEntry",
    "build_campaign_universe",
    "write_campaign_universe",
]
