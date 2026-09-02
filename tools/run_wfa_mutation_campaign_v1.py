"""Run bounded adversarial mutations against the independent WFA oracle."""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import pandas as pd
from core.backtesting.wfa import validate_feature_causality_ledger

from tools.wfa_independent_oracle_v1 import (
    assert_cost_accounting,
    assert_causal_feature,
    assert_parameter_freeze,
    assert_train_only_scaler,
    primitive_frame,
    session_isolated_events,
)


def _case(name, expected, operation):
    try:
        operation()
    except ValueError as exc:
        return {"mutation": name, "expected": expected, "detected": True, "reason": str(exc)}
    return {"mutation": name, "expected": expected, "detected": False, "reason": "not_rejected"}


def run_campaign() -> list[dict[str, object]]:
    clean = primitive_frame([
        {"timestamp": "2026-01-01 09:15:00", "feature": 1.0, "feature_source_timestamp": "2026-01-01 09:15:00"},
        {"timestamp": "2026-01-01 09:16:00", "feature": 1.0, "feature_source_timestamp": "2026-01-01 09:16:00"},
    ])
    authority = {
        "feature_name": "feature", "feature_source_start_timestamp": "2026-01-01 09:15",
        "feature_source_end_timestamp": "2026-01-01 09:15", "decision_timestamp": "2026-01-01 09:16",
        "feature_cutoff_ts": "2026-01-01 09:16", "feature_source_timestamp": "2026-01-01 09:15",
        "session_id": "2026-01-01", "fold_id": 1, "available_at_decision": True,
        "feature_builder_sha256": "builder", "feature_builder_id": "builder-v1",
        "source_partition_sha256": "source", "corpus_freeze_sha256": "corpus",
        "normalization_fit_scope": "PASS_NOT_APPLICABLE", "normalization_fit_source_sha256": "source",
        "fit_uses_test_data": False, "leakage_detected": False,
    }
    def reject(field, value):
        row = dict(authority); row[field] = value
        return validate_feature_causality_ledger(
            [row], expected_builder_sha256="builder", expected_builder_id="builder-v1",
            expected_source_sha256="source", expected_corpus_freeze_sha256="corpus",
            expected_normalization_source_sha256="source", expected_fold_ids={1})
    return [
        _case("future_feature", True, lambda: assert_causal_feature(clean.assign(feature_source_timestamp=pd.Timestamp("2026-01-01 09:17:00")), feature="feature")),
        _case("test_fitted_scaler", True, lambda: assert_train_only_scaler(fit_end="2026-01-02 09:16", test_start="2026-01-02 09:16")),
        _case("test_selected_parameter", True, lambda: assert_parameter_freeze(selection_end="2026-01-02 09:17", freeze_time="2026-01-02 09:17", test_start="2026-01-02 09:16")),
        _case("cross_session_exit", True, lambda: session_isolated_events([{"entry_timestamp":"2026-01-01 15:29", "exit_timestamp":"2026-01-02 09:16", "session":"2026-01-01", "gross_bps":100.0}])),
        _case("duplicate_timestamp", True, lambda: primitive_frame([{"timestamp":"2026-01-01 09:15"},{"timestamp":"2026-01-01 09:15"}])),
        _case("omitted_or_double_cost", True, lambda: assert_cost_accounting(gross_bps=100.0, observed_net_bps=100.0, entry_cost_bps=7.0, exit_cost_bps=8.0)),
        _case("builder_sha_tamper", True, lambda: reject("feature_builder_sha256", "tampered")),
        _case("unknown_builder_id", True, lambda: reject("feature_builder_id", "unknown")),
        _case("source_partition_sha_tamper", True, lambda: reject("source_partition_sha256", "tampered")),
        _case("corpus_freeze_sha_tamper", True, lambda: reject("corpus_freeze_sha256", "tampered")),
        _case("normalization_source_sha_tamper", True, lambda: reject("normalization_fit_source_sha256", "tampered")),
        _case("normalization_test_data", True, lambda: reject("fit_uses_test_data", True)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = run_campaign()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["mutation", "expected", "detected", "reason"])
        writer.writeheader()
        writer.writerows(rows)
    return 0 if all(row["detected"] is True for row in rows) else 1


if __name__ == "__main__":
    # Some imported research modules leave interpreter-shutdown work pending
    # after the ledger is fully written. Flush the evidence and exit
    # deterministically so certification supervision can observe completion.
    result = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(result)
