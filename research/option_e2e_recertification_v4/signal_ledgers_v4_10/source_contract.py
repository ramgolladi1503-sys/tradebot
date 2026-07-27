from __future__ import annotations

from dataclasses import dataclass, field


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
    signal_artifact_patterns: tuple[str, ...] = field(default_factory=tuple)
    candidate_state_patterns: tuple[str, ...] = field(default_factory=tuple)
    required_dataset_patterns: tuple[str, ...] = field(default_factory=tuple)
    required_columns: tuple[str, ...] = field(default_factory=tuple)
    contract_paths: tuple[str, ...] = field(default_factory=tuple)
    contract_hashes: tuple[str, ...] = field(default_factory=tuple)
    known_evidence_roots: tuple[str, ...] = field(default_factory=tuple)
    development_holdout_policy: str = "fail_closed"
    discovery_status: str = "UNKNOWN"
    source_domain: str = "GENERIC_RESEARCH_REPORT"

