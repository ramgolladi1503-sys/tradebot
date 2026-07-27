from __future__ import annotations


REQUIRED_SIGNAL_FIELDS = (
    "strategy_or_hypothesis_id",
    "canonical_alias_group",
    "signal_id",
    "session",
    "feature_cutoff_ts",
    "signal_ts",
    "earliest_entry_ts",
    "direction",
    "signal_strength",
    "params_hash",
    "source_artifact_hash",
    "strategy_implementation_sha",
    "strategy_file_hashes",
    "adapter_sha",
    "dataset_hash",
    "fold_id",
    "is_holdout",
)

