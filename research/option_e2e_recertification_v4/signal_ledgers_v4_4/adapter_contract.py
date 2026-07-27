from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalLedgerContract:
    strategy_or_hypothesis_id: str
    canonical_alias_group: str
    signal_id: str
    session: str
    feature_cutoff_ts: str
    signal_ts: str
    earliest_entry_ts: str
    direction: str
    signal_strength: str
    params_hash: str
    source_artifact_hash: str
    implementation_sha: str
    dataset_hash: str
    fold_id: str
    is_holdout: bool
    source_kind: str
    oracle_status: str
