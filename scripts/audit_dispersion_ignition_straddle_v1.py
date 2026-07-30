#!/usr/bin/env python3
"""Independent audit for dispersion-ignition straddle V1 evidence.

This audit intentionally does not import candidate-generation, pair-selection,
or P&L functions from the campaign implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FRICTIONS = {"base_return": 0.005, "stress_return": 0.010, "severe_return": 0.015}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def semantic_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def audit_ledger(path: Path) -> list[str]:
    failures: list[str] = []
    if not path.exists():
        return failures
    frame = pd.read_csv(path)
    if frame.empty:
        return failures
    required = {
        "session", "signal_timestamp", "entry_timestamp", "exit_timestamp",
        "ce_entry", "pe_entry", "ce_exit", "pe_exit", "entered_premium",
        "gross_return", "base_return", "stress_return", "severe_return", "expiry", "strike",
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
    if (frame["exit_timestamp"] < frame["entry_timestamp"]).any():
        failures.append(f"{path.name}:exit_before_entry")
    entered = pd.to_numeric(frame["ce_entry"], errors="coerce") + pd.to_numeric(frame["pe_entry"], errors="coerce")
    expected_gross = (
        pd.to_numeric(frame["ce_exit"], errors="coerce")
        + pd.to_numeric(frame["pe_exit"], errors="coerce")
        - entered
    ) / entered
    if not np.allclose(entered, pd.to_numeric(frame["entered_premium"], errors="coerce"), atol=1e-12, rtol=1e-10):
        failures.append(f"{path.name}:entered_premium_mismatch")
    if not np.allclose(expected_gross, pd.to_numeric(frame["gross_return"], errors="coerce"), atol=1e-12, rtol=1e-10):
        failures.append(f"{path.name}:gross_return_mismatch")
    for column, friction in FRICTIONS.items():
        if not np.allclose(expected_gross - friction, pd.to_numeric(frame[column], errors="coerce"), atol=1e-12, rtol=1e-10):
            failures.append(f"{path.name}:{column}_mismatch")
    duplicate_keys = frame.duplicated(
        ["session", "signal_timestamp", "variant", "horizon", "expiry", "strike", "extra_entry_delay"],
        keep=False,
    )
    if duplicate_keys.any():
        failures.append(f"{path.name}:duplicate_trade_keys:{int(duplicate_keys.sum())}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, default=Path("runtime/research/dispersion_ignition_straddle_v1"))
    evidence = parser.parse_args().evidence_dir.resolve()
    failures: list[str] = []
    required_json = ["data_contract_report.json", "session_split_manifest.json", "pre_outcome_freeze.json", "oof_screen.json", "final_decision.json"]
    for name in required_json:
        if not (evidence / name).exists():
            failures.append(f"missing:{name}")
    if failures:
        stable_write(evidence / "independent_audit_report.json", {"verdict": "FAIL_INDEPENDENT_AUDIT", "failures": failures})
        return 2

    contract = read_json(evidence / "data_contract_report.json")
    split = read_json(evidence / "session_split_manifest.json")
    freeze = read_json(evidence / "pre_outcome_freeze.json")
    final = read_json(evidence / "final_decision.json")
    research, validation, holdout = split.get("research", []), split.get("validation", []), split.get("holdout", [])
    if not research or not validation or not holdout:
        failures.append("empty_chronological_split")
    elif not (max(research) < min(validation) and max(validation) < min(holdout)):
        failures.append("non_chronological_split")
    if freeze.get("membership_uses_future_entry_price") is not False:
        failures.append("future_entry_membership_not_explicitly_false")
    if freeze.get("campaign_wide_variants") != len(freeze.get("variants", [])):
        failures.append("variant_count_mismatch")
    expected_tests = len(freeze.get("variants", [])) * len(freeze.get("exit_horizons_minutes", []))
    if freeze.get("campaign_wide_tests") != expected_tests:
        failures.append("multiplicity_count_mismatch")
    if contract.get("historical_bid_ask_available") is not False:
        failures.append("bid_ask_claim_not_fail_closed")
    if contract.get("allowed_for_live_execution") is not False:
        failures.append("live_execution_not_false")

    for name in ("oof_straddle_ledger.csv", "delayed_entry_ledger.csv", "validation_ledger.csv", "holdout_ledger.csv"):
        failures.extend(audit_ledger(evidence / name))
    if not final.get("validation_opened", False) and (evidence / "validation_ledger.csv").exists() and (evidence / "validation_ledger.csv").stat().st_size > 1:
        failures.append("validation_artifact_exists_while_gate_closed")
    if not final.get("holdout_opened", False) and (evidence / "holdout_ledger.csv").exists() and (evidence / "holdout_ledger.csv").stat().st_size > 1:
        failures.append("holdout_artifact_exists_while_gate_closed")

    evidence_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(evidence.glob("*"))
        if path.is_file() and path.name != "independent_audit_report.json"
    }
    report = {
        "verdict": "PASS_INDEPENDENT_AUDIT" if not failures else "FAIL_INDEPENDENT_AUDIT",
        "failures": failures,
        "principal_verdict": final.get("principal_verdict"),
        "evidence_hashes": evidence_hashes,
        "semantic_sha256": semantic_hash(evidence_hashes),
        "audit_imports_campaign_logic": False,
        "read_only": True,
        "allowed_for_live_execution": False,
    }
    stable_write(evidence / "independent_audit_report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
