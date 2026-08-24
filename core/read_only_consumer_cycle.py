"""One-cycle downstream consumer coordinator for the canonical observer.

This coordinator is deliberately evidence-first: missing inputs produce
PENDING/BLOCKED states, not synthetic candidates or PASS results.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from core.live_candidate_contract import candidate_from_mapping
from core.live_ranking_contract import rank_advisory_candidates
from core.advisory_queue_contract import append_advisory
from core.read_only_option_eligibility import build_option_surface, evaluate_candidate_eligibility


CONSUMERS = (
    "regime", "strategies", "cas_v2", "candidate_pool", "option_surface",
    "eligibility", "ranking", "advisory_queue", "ui", "monitoring", "evidence",
)


def _state(verdict: str, *, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    payload = {"verdict": verdict, **extra}
    if reason:
        payload["reason"] = reason
    return payload


def run_consumer_cycle(
    *, runtime_outputs: Mapping[str, Any], output_root: str | Path,
    session_id: str, source_sha: str,
) -> dict[str, Any]:
    root = Path(output_root)
    market = runtime_outputs.get("market_snapshot")
    regime = market.get("regime") if isinstance(market, Mapping) else None
    rows = []
    advisory = runtime_outputs.get("advisory_latest")
    if isinstance(advisory, Mapping) and isinstance(advisory.get("rows"), list):
        rows = [row for row in advisory["rows"] if isinstance(row, Mapping)]

    valid_candidates = []
    rejected = 0
    for row in rows:
        try:
            valid_candidates.append(candidate_from_mapping(row).to_dict())
        except (TypeError, ValueError, KeyError):
            rejected += 1

    result: dict[str, Any] = {
        "schema_version": 1,
        "session_id": session_id,
        "source_sha": source_sha,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_execution_authorized": False,
        "broker_order_calls": 0,
        "consumers": {},
    }
    result["consumers"]["regime"] = _state(
        "PASS" if isinstance(regime, Mapping) and regime else "PENDING",
        reason=None if isinstance(regime, Mapping) and regime else "regime_evidence_missing",
        observed=isinstance(regime, Mapping) and bool(regime),
    )
    result["consumers"]["strategies"] = _state(
        "PASS" if valid_candidates else "PENDING",
        reason=None if valid_candidates else "no_validated_strategy_candidates",
        candidate_count=len(valid_candidates),
    )
    result["consumers"]["cas_v2"] = _state("PENDING", reason="completed_pre_freeze_inputs_not_supplied")
    result["consumers"]["candidate_pool"] = _state(
        "PASS" if valid_candidates else "PENDING", candidate_count=len(valid_candidates), rejected_count=rejected,
    )
    option_rows = runtime_outputs.get("option_surface")
    option_evidence_by_candidate = option_rows if isinstance(option_rows, Mapping) else {}
    surfaces = [
        build_option_surface(
            candidate=candidate,
            option_evidence=option_evidence_by_candidate.get(candidate["candidate_id"]),
        )
        for candidate in valid_candidates
    ]
    option_ready_count = sum(surface["verdict"] == "PASS" for surface in surfaces)
    result["consumers"]["option_surface"] = _state(
        "PASS" if valid_candidates and option_ready_count == len(valid_candidates) else "PENDING",
        reason=None if valid_candidates and option_ready_count == len(valid_candidates) else "current_option_surface_evidence_missing",
        candidate_count=len(valid_candidates), ready_count=option_ready_count,
    )
    eligibility_rows = [
        evaluate_candidate_eligibility(candidate=candidate, option_surface=surface, regime=regime)
        for candidate, surface in zip(valid_candidates, surfaces)
    ]
    eligible_candidates = [
        candidate for candidate, eligibility in zip(valid_candidates, eligibility_rows)
        if eligibility.get("status") == "eligible"
    ]
    result["consumers"]["eligibility"] = _state(
        "PASS" if eligible_candidates else "PENDING",
        reason=None if eligible_candidates else "no_candidates_passed_common_eligibility",
        candidate_count=len(valid_candidates), eligible_count=len(eligible_candidates),
    )
    ranked: list[dict[str, Any]] = []
    if eligible_candidates:
        try:
            ranked = rank_advisory_candidates(eligible_candidates)
        except (TypeError, ValueError):
            ranked = []
    result["consumers"]["ranking"] = _state(
        "PASS" if ranked else "PENDING", reason=None if ranked else "no_rankable_candidates",
        ranked_count=len(ranked),
    )
    advisory_path = root / "advisory_queue.jsonl"
    appended = 0
    for row in ranked:
        try:
            append_advisory(
                advisory_path,
                {**row, "source_sha": source_sha},
                session_id=session_id,
            )
            appended += 1
        except (TypeError, ValueError, OSError):
            continue
    result["consumers"]["advisory_queue"] = _state(
        "PASS" if appended else "PENDING", reason=None if appended else "no_advisory_rows_appended",
        appended_count=appended,
    )
    for name in ("ui", "monitoring", "evidence"):
        result["consumers"][name] = _state("PENDING", reason="consumer_artifact_not_yet_sealed")
    destination = root / "consumer_cycle_latest.json"
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(result, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return result
