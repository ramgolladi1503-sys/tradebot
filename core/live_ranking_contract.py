"""Read-only ranking boundary; comparison only, never edge creation or execution."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from core.live_candidate_contract import candidate_from_mapping


def rank_advisory_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rank already validated candidates by supplied confidence, preserving status."""
    validated = []
    for row in candidates:
        candidate = candidate_from_mapping(row)
        output = candidate.to_dict()
        output["candidate_status"] = str(row.get("candidate_status") or "advisory_only")
        if output["candidate_status"] not in {"eligible", "near_eligible", "advisory_only", "rejected"}:
            raise ValueError("live_candidate_status_invalid")
        output["ranking_basis"] = "supplied_confidence_only"
        validated.append(output)
    validated.sort(key=lambda row: (-(row["confidence_raw"] if row["confidence_raw"] is not None else -1.0), row["candidate_id"]))
    for rank, row in enumerate(validated, start=1):
        row["rank"] = rank
    return validated
