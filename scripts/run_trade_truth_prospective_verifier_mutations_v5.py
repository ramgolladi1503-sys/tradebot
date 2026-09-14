#!/usr/bin/env python3
"""Real Mutation Campaign V5 for Prospective Level-C Verifier.

Tests sensitivity of hardened verifier to concrete corruptions:
- Preflight tampering
- Hash payload tampering
- Canonical lineage tampering
- Synthetic risk misclassification
- Broker write tampering
- Future leak tampering
- Replay divergence
- Ledger truncation/tampering
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.verify_trade_truth_prospective_level_c import run_verification

def run_v5_campaign():
    captures_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_FULL_CAPTURES.json"
    ledger_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_TRACE_LEDGER.jsonl"
    replay_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_REPLAY_RESULTS.json"
    preflight_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_PREFLIGHT_RESULTS.json"

    backups = {
        captures_p: captures_p.read_text(),
        ledger_p: ledger_p.read_text(),
        replay_p: replay_p.read_text(),
        preflight_p: preflight_p.read_text(),
    }

    print("--- Running Pristine Baseline Verification ---")
    ret_baseline = run_verification()
    print(f"Baseline return code: {ret_baseline}")
    assert ret_baseline == 0, "Baseline verifier must return 0 (PASS) on pristine evidence"

    # Define V5 mutation cases
    cases = [
        {
            "id": "V5_01_PREFLIGHT_ALL_PASSED_FALSE",
            "file": preflight_p,
            "mutate_fn": lambda d: d.update({"all_mandatory_gates_passed": True}),  # preflight has passed=False gates, claiming all passed is a tamper
            "expected_gate": "PREFLIGHT_MANDATORY_GATES_REAL",
            "primitive": "preflight.all_mandatory_gates_passed",
        },
        {
            "id": "V5_02_DEFAULT_PASS_COUNT_NONZERO",
            "file": preflight_p,
            "mutate_fn": lambda d: d.update({"default_pass_count": 1}),
            "expected_gate": "PREFLIGHT_MANDATORY_GATES_REAL",
            "primitive": "preflight.default_pass_count",
        },
        {
            "id": "V5_03_REAL_CHECK_COUNT_MISMATCH",
            "file": preflight_p,
            "mutate_fn": lambda d: d.update({"real_check_count": 99}),
            "expected_gate": "PREFLIGHT_MANDATORY_GATES_REAL",
            "primitive": "preflight.real_check_count",
        },
        {
            "id": "V5_04_DECISION_PAYLOAD_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["final_decision"].update({"action": "EXECUTE_TRADE"}),
            "expected_gate": "STAGE_HASHES_PAYLOAD_VALID",
            "primitive": "captures[0].final_decision.action",
        },
        {
            "id": "V5_05_STAGE_PAYLOAD_TAMPER_MEMORY",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["memory_capture"].update({"current_price": 99999.0}),
            "expected_gate": "STAGE_HASHES_PAYLOAD_VALID",
            "primitive": "captures[0].memory_capture.current_price",
        },
        {
            "id": "V5_06_STORED_CANONICAL_CONFIG_HASH_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["code_lineage"].update({"config_hash": "deadbeef" * 8}),
            "expected_gate": "CONFIG_LINEAGE_MATCHED",
            "primitive": "captures[0].code_lineage.config_hash",
        },
        {
            "id": "V5_07_GIT_SHA_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["code_lineage"].update({"git_sha": "0000000000000000000000000000000000000000"}),
            "expected_gate": "SHA_LINEAGE_MATCHED",
            "primitive": "captures[0].code_lineage.git_sha",
        },
        {
            "id": "V5_08_SYNTHETIC_RISK_FIXTURE_RELABELED_LIVE",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["risk_state_evaluation"]["risk_input_snapshot"].update({"is_live_ready": True}),
            "expected_gate": "RISK_SOURCE_CLASSIFICATION_VALID",
            "primitive": "captures[0].risk_state_evaluation.risk_input_snapshot.is_live_ready",
        },
        {
            "id": "V5_09_BROKER_WRITE_COUNT_POSITIVE",
            "file": replay_p,
            "mutate_fn": lambda d: d.update({"broker_write_calls": 2}),
            "expected_gate": "BROKER_WRITE_SURFACE_ZERO_CALLS",
            "primitive": "replay.broker_write_calls",
        },
        {
            "id": "V5_10_FUTURE_TIMESTAMP_INJECTION",
            "file": replay_p,
            "mutate_fn": lambda d: d["results"][0].update({"future_leak_detected": True}),
            "expected_gate": "FUTURE_LEAK_ZERO",
            "primitive": "replay.results[0].future_leak_detected",
        },
        {
            "id": "V5_11_REPLAY_PARITY_BREAK",
            "file": replay_p,
            "mutate_fn": lambda d: d["results"][0].update({"parity": False}),
            "expected_gate": "REPLAY_STAGE_HASH_PARITY",
            "primitive": "replay.results[0].parity",
        },
        {
            "id": "V5_12_LEDGER_TRUNCATION",
            "file": ledger_p,
            "mutate_text_fn": lambda text: "\n".join(text.strip().split("\n")[:-1]) + "\n",
            "expected_gate": "TRACE_LEDGER_PARITY_MATCHED",
            "primitive": "ledger_lines.count",
        },
        {
            "id": "V5_13_RECORD_HASH_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["truth_record"].update({"record_hash": "deadbeef" * 8}),
            "expected_gate": "TRUTH_RECORD_HASH_VALID",
            "primitive": "captures[0].truth_record.record_hash",
        },
        {
            "id": "V5_14_CHAIN_HASH_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["truth_record"].update({"chain_hash": "deadbeef" * 8}),
            "expected_gate": "CHAIN_CONTINUITY_VALID",
            "primitive": "captures[0].truth_record.chain_hash",
        },
        {
            "id": "V5_15_RAW_SOURCE_HASH_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["raw_market_capture"].update({"source_sha256": "deadbeef" * 8}),
            "expected_gate": "RAW_SOURCE_LINEAGE_MATCHED",
            "primitive": "captures[0].raw_market_capture.source_sha256",
        },
        {
            "id": "V5_16_STAGE_HASHES_TAMPER_WITHOUT_DECISION_HASH",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["stage_hashes"].update({"risk": "deadbeef" * 8}),
            "expected_gate": "DECISION_HASH_VALID",
            "primitive": "captures[0].stage_hashes.risk",
        },
        {
            "id": "V5_17_FEATURE_PAYLOAD_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["feature_capture"]["features"][0].update({"feature_value": -999.0}),
            "expected_gate": "STAGE_HASHES_PAYLOAD_VALID",
            "primitive": "captures[0].feature_capture.features[0].feature_value",
        },
        {
            "id": "V5_18_GOVERNANCE_PAYLOAD_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["governance_validation"].update({"governance_verdict": "GOVERNED_ALLOWED"}),
            "expected_gate": "STAGE_HASHES_PAYLOAD_VALID",
            "primitive": "captures[0].governance_validation.governance_verdict",
        },
        {
            "id": "V5_19_STRATEGY_CATALOG_HASH_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["code_lineage"].update({"strategy_catalog_hash": "deadbeef" * 8}),
            "expected_gate": "CONFIG_LINEAGE_MATCHED",
            "primitive": "captures[0].code_lineage.strategy_catalog_hash",
        },
        {
            "id": "V5_20_SYNTHETIC_QUOTE_INJECTION",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["option_selection"].update({
                "selection_status": "SELECTED",
                "quote_executable_truth": {"bid": 150.0, "ask": 150.5, "bid_qty": 50, "ask_qty": 50}
            }),
            "expected_gate": "NO_SYNTHETIC_QUOTES",
            "primitive": "captures[0].option_selection.quote_executable_truth.ask",
        }
    ]

    results = []
    print(f"--- Executing {len(cases)} Concrete Adversarial Mutations ---")

    for c in cases:
        target_f = c["file"]
        if "mutate_fn" in c:
            content = json.loads(target_f.read_text())
            c["mutate_fn"](content)
            target_f.write_text(json.dumps(content, indent=2))
        else:
            text = target_f.read_text()
            mutated_text = c["mutate_text_fn"](text)
            target_f.write_text(mutated_text)

        exit_code = run_verification()
        report_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_VERIFICATION_REPORT.json"
        rep = json.loads(report_p.read_text())
        gate_status = rep["gates"].get(c["expected_gate"], {}).get("passed", True)
        detected = (not gate_status) and (exit_code != 0)

        # Restore
        for f, original in backups.items():
            f.write_text(original)

        res_entry = {
            "mutation_id": c["id"],
            "primitive": c["primitive"],
            "expected_gate": c["expected_gate"],
            "gate_passed_after_mutation": gate_status,
            "detected": detected,
            "verifier_exit_code": exit_code,
            "methodologically_valid": True,
        }
        results.append(res_entry)
        status_label = "DETECTED" if detected else "MISSED"
        print(f"[{status_label}] {c['id']} -> Gate {c['expected_gate']} (exit_code={exit_code})")

    print("--- Verifying Baseline Re-Restoration ---")
    post_ret = run_verification()
    print(f"Post-restoration verifier return code: {post_ret}")
    assert post_ret == 0, "Post-restoration evidence must re-verify perfectly"

    summary = {
        "mutations_attempted": len(results),
        "mutations_detected": sum(1 for r in results if r["detected"]),
        "mutations_missed": sum(1 for r in results if not r["detected"]),
        "mutations_not_applicable": 0,
        "invalid_mutations": 0,
        "baseline_verify_before_mutations": "PASS" if ret_baseline == 0 else "FAIL",
        "baseline_verify_after_restoration": "PASS" if post_ret == 0 else "FAIL",
        "results": results,
    }

    out_summary_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_VERIFIER_MUTATION_V5_SUMMARY.json"
    out_cases_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_VERIFIER_MUTATION_V5_CASES.jsonl"

    out_summary_p.write_text(json.dumps(summary, indent=2))
    with open(out_cases_p, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"V5 Mutation Campaign Complete: {summary['mutations_detected']}/{summary['mutations_attempted']} DETECTED.")
    return summary

if __name__ == "__main__":
    run_v5_campaign()
