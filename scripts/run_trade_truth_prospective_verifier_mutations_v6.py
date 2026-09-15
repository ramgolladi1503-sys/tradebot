#!/usr/bin/env python3
"""Real Subprocess-Isolated Mutation Campaign V6 with Hash Proofs.

Verifies sensitivity of hardened V6 verifier to concrete semantic corruptions:
- T01: one-trace evidence SHA mismatch
- T02: all-traces coherent wrong evidence SHA
- T03: decision timestamp string one day earlier than epoch
- T04: decision epoch one day later than string
- T05: source-session date mismatch
- T06: future raw/bar timestamp injection
- T07: schema instance required field removed
- T08: config hash tamper
- T09: bar payload tamper
- T10: risk payload tamper
- T11: quote injected into NOT_REACHED stage using non-magic price (151.35)
- T12: record hash tamper
- T13: chain hash tamper
- T14: ledger truncation
- T15: broker write count positive
- T16: synthetic risk relabeled live
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def run_v6_campaign():
    captures_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_FULL_CAPTURES.json"
    ledger_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_TRACE_LEDGER.jsonl"
    replay_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_REPLAY_RESULTS.json"
    preflight_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_PREFLIGHT_RESULTS.json"

    files_to_track = [captures_p, ledger_p, replay_p, preflight_p]
    backups = {f: f.read_text() for f in files_to_track}
    pristine_hashes = {f: sha256_text(backups[f]) for f in files_to_track}

    print("--- Running Pristine Baseline Verification (Subprocess) ---")
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/verify_trade_truth_prospective_level_c.py"), "--expected-evidence-sha", "9760ce3e3eb5b86bf65953a227fbf866dd158841"],
        capture_output=True,
        text=True,
    )
    print(f"Baseline return code: {proc.returncode}")
    assert proc.returncode == 0, f"Baseline verifier must PASS (0). Stderr: {proc.stderr}"

    cases = [
        {
            "id": "T01_ONE_TRACE_EVIDENCE_SHA_MISMATCH",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["code_lineage"].update({"git_sha": "0000000000000000000000000000000000000000"}),
            "expected_gate": "EVIDENCE_SHA_INTERNAL_CONSISTENCY",
            "primitive": "captures[0].code_lineage.git_sha",
            "primitive_before": "9760ce3e3eb5b86bf65953a227fbf866dd158841",
            "primitive_after": "0000000000000000000000000000000000000000",
        },
        {
            "id": "T02_ALL_TRACES_COHERENT_WRONG_SHA",
            "file": captures_p,
            "mutate_fn": lambda d: [c["code_lineage"].update({"git_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}) for c in d],
            "expected_gate": "EVIDENCE_SHA_MATCHES_EXPECTED_AUTHORITY",
            "primitive": "all captures.code_lineage.git_sha",
            "primitive_before": "9760ce3e3eb5b86bf65953a227fbf866dd158841",
            "primitive_after": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        },
        {
            "id": "T03_DECISION_TS_STR_ONE_DAY_EARLIER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0].update({"decision_ts_str": "2026-09-09 09:22:00"}),
            "expected_gate": "TIME_IDENTITY_VALID",
            "primitive": "captures[0].decision_ts_str",
            "primitive_before": "2026-09-10 09:22:00",
            "primitive_after": "2026-09-09 09:22:00",
            "cli_flags": ["--enforce-strict-time-identity"],
        },
        {
            "id": "T04_DECISION_EPOCH_ONE_DAY_LATER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0].update({"decision_ts_epoch": 1789185120.0}),
            "expected_gate": "TIME_IDENTITY_VALID",
            "primitive": "captures[0].decision_ts_epoch",
            "primitive_before": "1789098720.0",
            "primitive_after": "1789185120.0",
            "cli_flags": ["--enforce-strict-time-identity"],
        },
        {
            "id": "T05_SOURCE_SESSION_DATE_MISMATCH",
            "file": captures_p,
            "mutate_fn": lambda d: d[0].update({"session_date": "2026-09-11"}),
            "expected_gate": "TIME_IDENTITY_VALID",
            "primitive": "captures[0].session_date",
            "primitive_before": "2026-09-10",
            "primitive_after": "2026-09-11",
            "cli_flags": ["--enforce-strict-time-identity"],
        },
        {
            "id": "T06_FUTURE_RAW_TIMESTAMP_INJECTION",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["raw_market_capture"].update({"last_event_ts": 1789199999.0}),
            "expected_gate": "FUTURE_LEAK_ZERO",
            "primitive": "captures[0].raw_market_capture.last_event_ts",
            "primitive_before": "1789034399.873431",
            "primitive_after": "1789199999.0",
        },
        {
            "id": "T07_SCHEMA_INSTANCE_REQUIRED_FIELD_REMOVED",
            "file": ledger_p,
            "mutate_text_fn": lambda text: text.replace("\"terminal_trace_status\": \"CAPTURE_PARTIAL\", ", ""),
            "expected_gate": "SCHEMA_INSTANCE_VALID",
            "primitive": "ledger_lines[0].terminal_trace_status",
            "primitive_before": "CAPTURE_PARTIAL",
            "primitive_after": "[REMOVED]",
        },
        {
            "id": "T08_CONFIG_HASH_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["code_lineage"].update({"config_hash": "deadbeef" * 8}),
            "expected_gate": "CONFIG_LINEAGE_MATCHED",
            "primitive": "captures[0].code_lineage.config_hash",
            "primitive_before": "4b1a70ce24c718c2...",
            "primitive_after": "deadbeef" * 8,
        },
        {
            "id": "T09_BAR_PAYLOAD_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["stage_hashes"].update({"bars": "deadbeef" * 8}),
            "expected_gate": "STAGE_HASHES_PAYLOAD_VALID",
            "primitive": "captures[0].stage_hashes.bars",
            "primitive_before": "2adbfcff2f6df940...",
            "primitive_after": "deadbeef" * 8,
        },
        {
            "id": "T10_RISK_PAYLOAD_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["risk_state_evaluation"]["risk_input_snapshot"].update({"capital": 500000.0}),
            "expected_gate": "STAGE_HASHES_PAYLOAD_VALID",
            "primitive": "captures[0].risk_state_evaluation.risk_input_snapshot.capital",
            "primitive_before": "1000000.0",
            "primitive_after": "500000.0",
        },
        {
            "id": "T11_QUOTE_INJECTED_INTO_NOT_REACHED_NON_MAGIC",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["option_selection"].update({
                "selection_status": "SELECTION_STAGE_NOT_REACHED",
                "quote_executable_truth": {"bid": 151.30, "ask": 151.35, "bid_qty": 75, "ask_qty": 75}
            }),
            "expected_gate": "OPTION_QUOTE_SEMANTIC_VALID",
            "primitive": "captures[0].option_selection.quote_executable_truth",
            "primitive_before": "None",
            "primitive_after": "{bid: 151.30, ask: 151.35}",
        },
        {
            "id": "T12_RECORD_HASH_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["truth_record"].update({"record_hash": "deadbeef" * 8}),
            "expected_gate": "TRUTH_RECORD_HASH_VALID",
            "primitive": "captures[0].truth_record.record_hash",
            "primitive_before": "d937b069ace28efb...",
            "primitive_after": "deadbeef" * 8,
        },
        {
            "id": "T13_CHAIN_HASH_TAMPER",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["truth_record"].update({"chain_hash": "deadbeef" * 8}),
            "expected_gate": "CHAIN_CONTINUITY_VALID",
            "primitive": "captures[0].truth_record.chain_hash",
            "primitive_before": "9bec995d10e13482...",
            "primitive_after": "deadbeef" * 8,
        },
        {
            "id": "T14_LEDGER_TRUNCATION",
            "file": ledger_p,
            "mutate_text_fn": lambda text: "\n".join(text.strip().split("\n")[:-1]) + "\n",
            "expected_gate": "TRACE_LEDGER_PARITY_MATCHED",
            "primitive": "ledger_lines.count",
            "primitive_before": "5 lines",
            "primitive_after": "4 lines",
        },
        {
            "id": "T15_BROKER_WRITE_COUNT_POSITIVE",
            "file": replay_p,
            "mutate_fn": lambda d: d.update({"broker_write_calls": 3}),
            "expected_gate": "BROKER_WRITE_SURFACE_ZERO_CALLS",
            "primitive": "replay.broker_write_calls",
            "primitive_before": "0",
            "primitive_after": "3",
        },
        {
            "id": "T16_SYNTHETIC_RISK_RELABELED_LIVE",
            "file": captures_p,
            "mutate_fn": lambda d: d[0]["risk_state_evaluation"]["risk_input_snapshot"].update({"is_live_ready": True}),
            "expected_gate": "RISK_SOURCE_CLASSIFICATION_VALID",
            "primitive": "captures[0].risk_state_evaluation.risk_input_snapshot.is_live_ready",
            "primitive_before": "False",
            "primitive_after": "True",
        },
    ]

    results = []
    print(f"--- Executing {len(cases)} V6 Subprocess Mutations ---")

    for c in cases:
        target_f = c["file"]
        pristine_sha = pristine_hashes[target_f]

        # Apply mutation
        if "mutate_fn" in c:
            content = json.loads(target_f.read_text())
            c["mutate_fn"](content)
            mutated_text = json.dumps(content, indent=2)
            target_f.write_text(mutated_text)
        else:
            text = target_f.read_text()
            mutated_text = c["mutate_text_fn"](text)
            target_f.write_text(mutated_text)

        mutated_sha = sha256_text(mutated_text)
        assert pristine_sha != mutated_sha, f"Mutation {c['id']} failed to change file content!"

        # Run verifier in subprocess
        cmd = [sys.executable, str(REPO_ROOT / "scripts/verify_trade_truth_prospective_level_c.py"), "--expected-evidence-sha", "9760ce3e3eb5b86bf65953a227fbf866dd158841"]
        if "cli_flags" in c:
            cmd.extend(c["cli_flags"])

        proc_mut = subprocess.run(cmd, capture_output=True, text=True)
        exit_code = proc_mut.returncode

        report_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_VERIFICATION_REPORT.json"
        rep = json.loads(report_p.read_text())
        gate_status = rep["gates"].get(c["expected_gate"], {}).get("passed", True)
        detected = (not gate_status) and (exit_code != 0)

        # Restore file
        target_f.write_text(backups[target_f])
        restored_sha = sha256_text(target_f.read_text())
        assert restored_sha == pristine_sha, f"Restoration failed for {target_f}"

        res_entry = {
            "mutation_id": c["id"],
            "primitive": c["primitive"],
            "expected_gate": c["expected_gate"],
            "pristine_file_sha256": pristine_sha,
            "mutated_file_sha256": mutated_sha,
            "primitive_before": c["primitive_before"],
            "primitive_after": c["primitive_after"],
            "primitive_changed": True,
            "verifier_process_mode": "SUBPROCESS",
            "verifier_exit_code": exit_code,
            "gate_passed_after_mutation": gate_status,
            "detected": detected,
            "restored_file_sha256": restored_sha,
            "restoration_exact": True,
        }
        results.append(res_entry)
        status_label = "DETECTED" if detected else "MISSED"
        print(f"[{status_label}] {c['id']} -> Gate {c['expected_gate']} (exit={exit_code})")

    print("--- Verifying Baseline Re-Restoration (Subprocess) ---")
    post_proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/verify_trade_truth_prospective_level_c.py"), "--expected-evidence-sha", "9760ce3e3eb5b86bf65953a227fbf866dd158841"],
        capture_output=True,
        text=True,
    )
    print(f"Post-restoration verifier return code: {post_proc.returncode}")
    assert post_proc.returncode == 0, "Post-restoration evidence must re-verify perfectly"

    summary = {
        "campaign_version": "V6_SUBPROCESS_MUTATION_CAMPAIGN",
        "mutations_attempted": len(results),
        "mutations_detected": sum(1 for r in results if r["detected"]),
        "mutations_missed": sum(1 for r in results if not r["detected"]),
        "mutations_not_applicable": 0,
        "invalid_mutations": 0,
        "mutation_subprocess_isolation": True,
        "mutation_restoration_hash_proof": True,
        "baseline_verify_before_mutations": "PASS" if proc.returncode == 0 else "FAIL",
        "baseline_verify_after_restoration": "PASS" if post_proc.returncode == 0 else "FAIL",
        "results": results,
    }

    out_summary_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_VERIFIER_MUTATION_V6_SUMMARY.json"
    out_cases_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_VERIFIER_MUTATION_V6_CASES.jsonl"

    out_summary_p.write_text(json.dumps(summary, indent=2))
    with open(out_cases_p, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"V6 Mutation Campaign Complete: {summary['mutations_detected']}/{summary['mutations_attempted']} DETECTED.")
    return summary

if __name__ == "__main__":
    run_v6_campaign()
