from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceContract:
    strategy_or_hypothesis_id: str
    canonical_alias_group: str
    economic_family: str
    directional_eligibility: str
    current_implementation_paths: tuple[str, ...]
    implementation_file_hashes: tuple[str, ...]
    current_implementation_commit: str
    historical_branch_candidates: tuple[str, ...]
    historical_commit_candidates: tuple[str, ...]
    signal_artifact_patterns: tuple[str, ...]
    candidate_state_patterns: tuple[str, ...]
    required_dataset_patterns: tuple[str, ...]
    required_columns: tuple[str, ...]
    contract_paths: tuple[str, ...]
    contract_hashes: tuple[str, ...]
    known_evidence_roots: tuple[str, ...]
    development_holdout_policy: str
    discovery_status: str
    source_domain: str
