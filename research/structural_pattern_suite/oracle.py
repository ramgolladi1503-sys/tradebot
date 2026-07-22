from __future__ import annotations

from .contracts import Candidate


def assert_candidate_invariants(candidate: Candidate) -> None:
    if candidate.entry_timestamp <= candidate.decision_timestamp:
        raise AssertionError("same-bar or pre-decision entry detected")
    if candidate.execution_eligibility is not False or candidate.research_only is not True:
        raise AssertionError("research-only execution flags were modified")
    if not candidate.source_manifest_hash or not candidate.feature_contract_hash:
        raise AssertionError("candidate provenance hashes are required")


def audit_candidates(candidates: list[Candidate]) -> dict[str, object]:
    for candidate in candidates:
        assert_candidate_invariants(candidate)
    return {
        "status": "PASS",
        "candidate_count": len(candidates),
        "checked": ["future_bar_leakage_guard", "same_bar_entry_guard", "provenance_hash_presence", "research_only_flags"],
    }

