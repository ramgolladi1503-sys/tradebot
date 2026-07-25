from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceContract:
    strategy_or_hypothesis_id: str
    canonical_alias_group: str
    economic_family: str
    directional_eligibility: str
    current_implementation_paths: tuple[str, ...]
    historical_branch_candidates: tuple[str, ...]
    historical_commit_candidates: tuple[str, ...]
    signal_artifact_patterns: tuple[str, ...]
    candidate_state_patterns: tuple[str, ...]
    required_underlying_dataset_patterns: tuple[str, ...]
    expected_required_columns: tuple[str, ...]
    known_evidence_roots: tuple[str, ...]
    contract_paths: tuple[str, ...]
    development_holdout_policy: str
    source_resolution_status: str
    source_domain: str
