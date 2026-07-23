from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.audit_reconstructed_proxy_evidence import REQUIRED_FROZEN_FILES, audit

DECISION_TIMES = ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:15"]
TAXONOMY = [
    "NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT",
    "PROXY_SUPPORTS_PURCHASING_AUTHORITATIVE_DATA",
    "PROXY_DOES_NOT_SUPPORT_PURCHASING_AUTHORITATIVE_DATA",
    "INSUFFICIENT_PROXY_OHLCV",
    "INSUFFICIENT_INSTRUMENT_RESOLUTION",
    "INSUFFICIENT_CONSTITUENT_COVERAGE",
    "PROXY_EVALUATION_FAILED_DATA_CONTRACT",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def build_pass_campaign(root: Path) -> Path:
    (root / "evaluation").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "manifests").mkdir()
    inputs = root / "inputs"
    inputs.mkdir()

    session_rows = []
    state_rows = []
    coverage_rows = []
    sessions = pd.bdate_range("2025-01-01", periods=120)
    for day in sessions:
        session = day.strftime("%Y-%m-%d")
        session_rows.append({"session": session, "session_classification": "REGULAR_SESSION_COMPLETE"})
        for time in DECISION_TIMES:
            ts = pd.Timestamp(f"{session} {time}", tz="Asia/Kolkata").tz_convert("UTC").isoformat()
            state_rows.append({
                "session": session,
                "decision_time": time,
                "decision_timestamp": ts,
                "side": "NONE",
                "reason": "index_already_caught_up",
                "count_coverage": 1.0,
                "weight_coverage": 1.0,
            })
            coverage_rows.append({
                "session": session,
                "decision_time": time,
                "decision_timestamp": ts,
                "count_coverage": 1.0,
                "weight_coverage": 1.0,
                "passes_count_coverage": True,
                "passes_weight_coverage": True,
            })

    session_grid = inputs / "session_grid.csv"
    pd.DataFrame(session_rows).to_csv(session_grid, index=False)
    for name in REQUIRED_FROZEN_FILES - {"session_grid"}:
        path = inputs / f"{name}.txt"
        path.write_text(f"frozen:{name}\n")

    weighted = root / "evaluation/signal_states_weighted.csv"
    unweighted = root / "evaluation/signal_states_unweighted.csv"
    coverage = root / "reports/membership_coverage.csv"
    pd.DataFrame(state_rows).to_csv(weighted, index=False)
    pd.DataFrame(state_rows).to_csv(unweighted, index=False)
    pd.DataFrame(coverage_rows).to_csv(coverage, index=False)
    pd.DataFrame(columns=["status"]).to_csv(root / "evaluation/trade_outcomes_weighted.csv", index=False)
    pd.DataFrame(columns=["status"]).to_csv(root / "evaluation/trade_outcomes_unweighted.csv", index=False)
    pd.DataFrame(columns=["status"]).to_csv(root / "evaluation/matched_control.csv", index=False)
    pd.DataFrame(columns=["status"]).to_csv(root / "evaluation/delayed_entry_outcomes.csv", index=False)

    control = {"result": "NOT_APPLICABLE_ZERO_SIGNALS", "signal_count": 0}
    delay = {"result": "NOT_APPLICABLE_ZERO_SIGNALS", "signal_count": 0}
    concentration = {"result": "NOT_APPLICABLE_ZERO_SIGNALS", "signals": 0}
    folds = {"folds": [], "positive_mean_folds": 0, "positive_median_folds": 0}
    coverage_summary = {
        "states": len(coverage_rows),
        "both_gates_pass_rate": 1.0,
        "state_count_coverage_mismatches": 0,
        "state_weight_coverage_mismatches": 0,
    }
    _write_json(root / "evaluation/control_summary.json", control)
    _write_json(root / "evaluation/delay_sensitivity.json", delay)
    _write_json(root / "evaluation/concentration.json", concentration)
    _write_json(root / "evaluation/chronological_folds.json", folds)
    _write_json(root / "reports/membership_coverage_summary.json", coverage_summary)

    frozen_files = {}
    for name in REQUIRED_FROZEN_FILES:
        path = session_grid if name == "session_grid" else inputs / f"{name}.txt"
        frozen_files[name] = {"path": str(path), "sha256": _sha(path)}
    freeze = {
        "freeze_version": "constituent_lead_lag_proxy_v3",
        "frozen_files": frozen_files,
        "campaign_window": {"start": sessions[0].strftime("%Y-%m-%d"), "end": sessions[-1].strftime("%Y-%m-%d")},
        "decision_times": DECISION_TIMES,
        "final_taxonomy": TAXONOMY,
    }
    freeze_path = root / "pre_outcome_freeze.json"
    _write_json(freeze_path, freeze)

    reason_counts = {"index_already_caught_up": len(state_rows)}
    summary = {
        "campaign_window": freeze["campaign_window"],
        "completed_regular_sessions": 120,
        "post_warmup_sessions": 100,
        "decision_times": DECISION_TIMES,
        "theoretical_max_state_rows": len(state_rows),
        "state_rows": len(state_rows),
        "unweighted_state_rows": len(state_rows),
        "weighted_signals": 0,
        "unweighted_signals": 0,
        "state_reason_counts": reason_counts,
        "unweighted_state_reason_counts": reason_counts,
        "coverage_summary": coverage_summary,
        "control_result": control,
        "delay_sensitivity": delay,
        "concentration": concentration,
        "chronological_folds": folds,
        "pre_outcome_freeze_sha256": _sha(freeze_path),
        "proxy_final_decision": "NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT",
    }
    _write_json(root / "evaluation/summary.json", summary)

    artifacts = [
        "evaluation/signal_states_weighted.csv",
        "evaluation/trade_outcomes_weighted.csv",
        "evaluation/signal_states_unweighted.csv",
        "evaluation/trade_outcomes_unweighted.csv",
        "evaluation/matched_control.csv",
        "evaluation/delayed_entry_outcomes.csv",
        "reports/membership_coverage.csv",
        "reports/membership_coverage_summary.json",
        "evaluation/summary.json",
        "evaluation/control_summary.json",
        "evaluation/delay_sensitivity.json",
        "evaluation/concentration.json",
        "evaluation/chronological_folds.json",
    ]
    _write_json(root / "manifests/artifact_manifest.json", {relative: _sha(root / relative) for relative in artifacts})
    return root


def test_oracle_passes_complete_fixture(tmp_path: Path):
    root = build_pass_campaign(tmp_path / "campaign")
    report = audit(root, tmp_path / "oracle")
    assert report["verdict"] == "PASS", report
    assert all(report["checks"].values())


@pytest.mark.parametrize(
    "target,mutator",
    [
        ("evaluation/summary.json", lambda path: path.write_text(path.read_text().replace('"state_rows": 1200', '"state_rows": 1199'))),
        ("evaluation/signal_states_weighted.csv", lambda path: path.write_text(path.read_text().replace("NONE", "LONG", 1))),
        ("reports/membership_coverage.csv", lambda path: path.write_text(path.read_text().replace(",1.0,1.0,True,True", ",0.5,1.0,False,True", 1))),
        ("inputs/normalized_bars.txt", lambda path: path.write_text("tampered\n")),
    ],
)
def test_oracle_tamper_changes_pass_to_fail(tmp_path: Path, target: str, mutator):
    root = build_pass_campaign(tmp_path / "campaign")
    assert audit(root, tmp_path / "oracle_before")["verdict"] == "PASS"
    mutator(root / target)
    assert audit(root, tmp_path / "oracle_after")["verdict"] == "FAIL"
