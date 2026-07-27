from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .git_provenance import EXPECTED_LEDGER_SHA256, EXPECTED_ROW_COUNT, search_non_outcome_provenance
from .search_policy import SELF_AUDIT_PREFIXES, is_self_audit_path


def search_preexisting_non_outcome_provenance(
    repo_root: Path,
    external_roots: Iterable[Path] = (),
    *,
    ledger_sha256: str = EXPECTED_LEDGER_SHA256,
    row_count: int = EXPECTED_ROW_COUNT,
) -> list[dict[str, Any]]:
    raw_records = search_non_outcome_provenance(
        repo_root,
        external_roots,
        ledger_sha256=ledger_sha256,
        row_count=row_count,
    )
    cleaned: list[dict[str, Any]] = []
    for record in raw_records:
        inspected = list(record.get("inspected_candidate_paths", []))
        scope_excluded = sorted(path for path in inspected if is_self_audit_path(path))
        retained_inspected = [path for path in inspected if not is_self_audit_path(path)]
        retained_matches = [
            match
            for match in record.get("matching_records", [])
            if not is_self_audit_path(str(match.get("semantic_path", "")))
        ]
        adjusted = dict(record)
        adjusted["raw_candidate_count"] = record.get("candidate_count", 0)
        adjusted["candidate_count"] = max(0, int(record.get("candidate_count", 0)) - len(scope_excluded))
        adjusted["inspected_candidate_paths"] = retained_inspected
        adjusted["inspected_candidate_count"] = len(retained_inspected)
        adjusted["matching_records"] = retained_matches
        adjusted["scope_exclusion_prefixes"] = list(SELF_AUDIT_PREFIXES)
        adjusted["scope_excluded_candidate_count"] = len(scope_excluded)
        adjusted["scope_excluded_candidate_paths"] = scope_excluded
        cleaned.append(adjusted)
    return cleaned


__all__ = ["search_preexisting_non_outcome_provenance"]
