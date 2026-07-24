from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VwapExecutionContract:
    strategy_id: str
    canonical_alias_group: str
    implementation_path: str
    implementation_commit: str
    implementation_file_hash: str
    adapter_path: str
    adapter_hash: str
    dataset_path: str
    dataset_hash: str
    params_contract_path: str
    params_hash: str
    development_boundary: str
    holdout_boundary: str
    required_columns: tuple[str, ...]
    timezone: str
    completed_bar_policy: str
    feature_cutoff_policy: str
    signal_timestamp_policy: str
    earliest_entry_policy: str

