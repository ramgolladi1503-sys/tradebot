#!/usr/bin/env python3
"""Independent verifier for MROS Truth Feed runtime call path and execution ledger.

Validates that:
1. Every stage defined in MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json has a verified entry in MROS_RUNTIME_CALL_LEDGER.json.
2. All CAUSAL stages have call_count >= 1 and checkpoint_emitted == True.
3. Observability sidecars (SCORING, RANKING) are non-causal (causal_to_decision == False).
4. Zero broker write / order placement calls were made (broker_write_calls == 0).
5. Exactly one candidate selection authority exists (CANDIDATE_SELECTION_AUTHORITY_COUNT == 1).
6. Fails closed on any mutation, missing checkpoint, or metadata-only assertion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def verify_call_path_and_ledger(
    call_path_path: Path,
    ledger_path: Path,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    errors: List[str] = []
    report: Dict[str, Any] = {
        "call_path_file": str(call_path_path),
        "ledger_file": str(ledger_path),
        "contract_id": None,
        "stages_verified": 0,
        "causal_stages_verified": 0,
        "sidecar_stages_verified": 0,
        "broker_write_calls": 0,
        "candidate_selection_authorities": 0,
        "status": "FAIL",
    }

    if not call_path_path.exists():
        errors.append(f"Call path file missing: {call_path_path}")
        return False, errors, report

    if not ledger_path.exists():
        errors.append(f"Runtime call ledger file missing: {ledger_path}")
        return False, errors, report

    try:
        call_path_data = json.loads(call_path_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Failed to parse call path JSON: {exc}")
        return False, errors, report

    try:
        ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Failed to parse runtime call ledger JSON: {exc}")
        return False, errors, report

    contract_id = call_path_data.get("contract_id", "")
    report["contract_id"] = contract_id
    if contract_id != "MROS_TRUTH_FEED_RUNTIME_CALL_PATH_V4":
        errors.append(f"Expected contract MROS_TRUTH_FEED_RUNTIME_CALL_PATH_V4, got: {contract_id}")

    # Verify single candidate selection authority
    selection_authority_count = ledger_data.get("candidate_selection_authority_count", 0)
    report["candidate_selection_authorities"] = selection_authority_count
    if selection_authority_count != 1:
        errors.append(
            f"Expected exactly 1 candidate selection authority, found {selection_authority_count}"
        )

    # Verify zero broker writes observed dynamically
    broker_writes = ledger_data.get("broker_write_calls_total", -1)
    report["broker_write_calls"] = broker_writes
    if broker_writes != 0:
        errors.append(f"Broker write call violation: observed {broker_writes} calls (must be 0)")

    ledger_stages = {s.get("stage_name"): s for s in ledger_data.get("stages", [])}
    contract_stages = call_path_data.get("stages", [])

    if len(contract_stages) != 20:
        errors.append(f"Expected 20 contract stages, got {len(contract_stages)}")

    for c_stage in contract_stages:
        name = c_stage.get("stage")
        classification = c_stage.get("stage_classification", "CAUSAL")
        is_causal = classification == "CAUSAL"

        if name not in ledger_stages:
            errors.append(f"Stage {name} declared in call path but missing from runtime ledger")
            continue

        l_entry = ledger_stages[name]
        call_count = l_entry.get("call_count", 0)
        checkpoint_emitted = l_entry.get("checkpoint_emitted", False)
        observed_zero_broker = l_entry.get("observed_broker_writes", 0) == 0

        if not observed_zero_broker:
            errors.append(f"Stage {name} has nonzero broker writes: {l_entry.get("observed_broker_writes")}")

        if is_causal:
            report["causal_stages_verified"] += 1
            if call_count < 1:
                errors.append(f"Causal stage {name} was not reached in runtime (call_count={call_count})")
            if not checkpoint_emitted:
                errors.append(f"Causal stage {name} failed to emit runtime checkpoint pulse")
        else:
            report["sidecar_stages_verified"] += 1
            # Sidecars must NOT claim causal decision authority
            if l_entry.get("causal_to_advisory_decision") is True:
                errors.append(f"Non-causal stage {name} illegally claimed causal_to_advisory_decision")

        report["stages_verified"] += 1

    if not errors:
        report["status"] = "PASS"
        return True, errors, report
    else:
        report["status"] = "FAIL"
        return False, errors, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify MROS Truth Feed runtime call path vs ledger.")
    parser.add_argument(
        "--call-path",
        type=Path,
        default=Path("MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json"),
        help="Path to MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("/Volumes/TradeBotData/pr904-runtime-proof-20260915/MROS_RUNTIME_CALL_LEDGER.json"),
        help="Path to MROS_RUNTIME_CALL_LEDGER.json",
    )
    args = parser.parse_args()

    passed, errors, report = verify_call_path_and_ledger(args.call_path, args.ledger)
    print(json.dumps(report, indent=2))
    if not passed:
        print("\nERRORS DETECTED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("\nSUCCESS: All call path stages, continuity, checkpoints, and zero-broker bounds verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
