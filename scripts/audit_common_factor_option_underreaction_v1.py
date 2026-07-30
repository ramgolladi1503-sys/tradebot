#!/usr/bin/env python3
"""Independent audit for common-factor option-underreaction evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def audit_ledger(path: Path) -> list[str]:
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    if frame.empty:
        return []
    failures: list[str] = []
    required = {
        "session", "signal_timestamp", "entry_timestamp", "exit_timestamp", "direction",
        "selected_option_type", "mirror_option_type", "expiry", "strike", "selected_entry",
        "selected_exit", "mirror_entry", "mirror_exit", "gross_return", "stress_return",
        "severe_return", "mirror_stress_return", "extra_entry_delay",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        return [f"{path.name}:missing_columns:{missing}"]
    for column in ("signal_timestamp", "entry_timestamp", "exit_timestamp"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    if frame[["signal_timestamp", "entry_timestamp", "exit_timestamp"]].isna().any().any():
        failures.append(f"{path.name}:invalid_timestamps")
    if (frame["entry_timestamp"] < frame["signal_timestamp"]).any():
        failures.append(f"{path.name}:entry_before_signal")
    gross = pd.to_numeric(frame["selected_exit"], errors="coerce") / pd.to_numeric(frame["selected_entry"], errors="coerce") - 1.0
    mirror = pd.to_numeric(frame["mirror_exit"], errors="coerce") / pd.to_numeric(frame["mirror_entry"], errors="coerce") - 1.0
    checks = {
        "gross_return": gross,
        "stress_return": gross - 0.010,
        "severe_return": gross - 0.015,
        "mirror_stress_return": mirror - 0.010,
    }
    for column, expected in checks.items():
        if not np.allclose(expected, pd.to_numeric(frame[column], errors="coerce"), atol=1e-12, rtol=1e-10):
            failures.append(f"{path.name}:{column}_mismatch")
    expected_type = np.where(pd.to_numeric(frame["direction"], errors="coerce") > 0, "CE", "PE")
    if not np.array_equal(expected_type, frame["selected_option_type"].astype(str).to_numpy()):
        failures.append(f"{path.name}:direction_option_type_mismatch")
    duplicates = frame.duplicated(
        ["session", "signal_timestamp", "variant", "horizon", "expiry", "strike", "extra_entry_delay"],
        keep=False,
    )
    if duplicates.any():
        failures.append(f"{path.name}:duplicate_trade_keys:{int(duplicates.sum())}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, default=Path("runtime/research/common_factor_option_underreaction_v1"))
    root = parser.parse_args().evidence_dir.resolve()
    failures: list[str] = []
    for name in ("data_contract_report.json", "session_split_manifest.json", "pre_outcome_freeze.json", "oof_screen.json", "final_decision.json"):
        if not (root / name).exists():
            failures.append(f"missing:{name}")
    if failures:
        stable_write(root / "independent_audit_report.json", {"verdict": "FAIL_INDEPENDENT_AUDIT", "failures": failures})
        return 2
    contract = read_json(root / "data_contract_report.json")
    split = read_json(root / "session_split_manifest.json")
    freeze = read_json(root / "pre_outcome_freeze.json")
    final = read_json(root / "final_decision.json")
    research, validation, holdout = split.get("research", []), split.get("validation", []), split.get("holdout", [])
    if not research or not validation or not holdout or not (max(research) < min(validation) < min(holdout)):
        failures.append("invalid_chronological_split")
    if freeze.get("membership_uses_future_entry_price") is not False:
        failures.append("future_entry_membership_not_false")
    if freeze.get("campaign_wide_tests") != len(freeze.get("variants", [])) * len(freeze.get("horizons", [])):
        failures.append("multiplicity_count_mismatch")
    if contract.get("historical_bid_ask_available") is not False or contract.get("allowed_for_live_execution") is not False:
        failures.append("claim_boundary_failure")
    for name in ("oof_trade_ledger.csv", "delayed_entry_ledger.csv", "validation_ledger.csv", "holdout_ledger.csv"):
        failures.extend(audit_ledger(root / name))
    if not final.get("validation_opened", False) and (root / "validation_ledger.csv").exists() and (root / "validation_ledger.csv").stat().st_size > 1:
        failures.append("validation_gate_bypassed")
    if not final.get("holdout_opened", False) and (root / "holdout_ledger.csv").exists() and (root / "holdout_ledger.csv").stat().st_size > 1:
        failures.append("holdout_gate_bypassed")
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.glob("*"))
        if path.is_file() and path.name != "independent_audit_report.json"
    }
    report = {
        "verdict": "PASS_INDEPENDENT_AUDIT" if not failures else "FAIL_INDEPENDENT_AUDIT",
        "principal_verdict": final.get("principal_verdict"),
        "failures": failures,
        "evidence_hashes": hashes,
        "audit_imports_campaign_logic": False,
        "read_only": True,
        "allowed_for_live_execution": False,
    }
    stable_write(root / "independent_audit_report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
