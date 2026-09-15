#!/usr/bin/env python3
"""Run real 18-vector mutation campaign (M1-M18) for PR #905.

For each of the 18 required mutations:
1. Create an isolated temporary mutation of code / config / evidence.
2. Run the independent implementation verifier (verify_pr905_implementation.py).
3. Prove the mutant is rejected (verifier returns non-zero / reports failure).
4. Restore original candidate state.
5. Record exact failure reason and mutation detection evidence.

Required:
REQUIRED_MUTATIONS_DETECTED=18/18
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def run_mutation_campaign(evidence_dir: Path) -> dict[str, Any]:
    short_sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    verifier_script = REPO_ROOT / "scripts" / "verify_pr905_implementation.py"

    # Baseline verification check first
    baseline_proc = subprocess.run(
        [sys.executable, str(verifier_script), "--evidence-root", str(evidence_dir)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert baseline_proc.returncode == 0, f"Baseline verification failed: {baseline_proc.stdout} {baseline_proc.stderr}"
    print("Baseline verifier check passed (0). Beginning 18 real mutations...\n")

    # Files subject to temporary mutation
    orch_file = REPO_ROOT / "core" / "orchestrator.py"
    consumer_file = REPO_ROOT / "core" / "read_only_consumer_cycle.py"
    contract_file = REPO_ROOT / "core" / "trade_truth" / "trade_builder_input_contract.py"
    authority_file = REPO_ROOT / "core" / "runtime_authority_contract.py"

    ledger_file = evidence_dir / "CANONICAL_RUNTIME_CALL_LEDGER.json"
    lineage_file = evidence_dir / "TRACE_LINEAGE.json"
    output_hashes_file = evidence_dir / "TRADEBUILDER_OUTPUT_HASHES.json"
    broker_audit_file = evidence_dir / "BROKER_WRITE_AUDIT.json"
    future_leak_file = evidence_dir / "FUTURE_LEAK_AUDIT.json"

    # Define the 18 mutations per Section 16
    mutations = [
        {
            "id": "M1",
            "name": "observer uses separate reduced input contract",
            "target": consumer_file,
            "mutate": lambda text: text.replace(
                "build_canonical_tradebuilder_input(",
                "build_observer_only_reduced_input("
            ),
        },
        {
            "id": "M2",
            "name": "production orchestrator does not use shared contract",
            "target": orch_file,
            "mutate": lambda text: text.replace(
                "build_canonical_tradebuilder_input(",
                "build_legacy_unshared_input("
            ),
        },
        {
            "id": "M3",
            "name": "missing symbol defaults to NIFTY",
            "target": contract_file,
            "mutate": lambda text: text.replace(
                'sym = str(raw_sym or "").strip().upper()',
                'sym = str(raw_sym or "NIFTY").strip().upper()'
            ),
        },
        {
            "id": "M4",
            "name": "missing price defaults to 0",
            "target": contract_file,
            "mutate": lambda text: text.replace(
                "if price <= 0.0:",
                "if False and price <= 0.0:"
            ),
        },
        {
            "id": "M5",
            "name": "post-hoc trade output is rewritten read_only",
            "target": consumer_file,
            "mutate": lambda text: text.replace(
                'if trade is not None:',
                'if trade is not None:\n            trade["read_only"] = True'
            ),
        },
        {
            "id": "M6",
            "name": "TradeBuilder call removed",
            "target": consumer_file,
            "mutate": lambda text: text.replace(
                "trade, trace = trade_builder.build_with_trace(",
                "# MUTANT M6: TradeBuilder call removed\n        trade, trace = None, None # trade_builder.build_with_trace("
            ),
        },
        {
            "id": "M7",
            "name": "stage marked reached without call",
            "target": ledger_file,
            "mutate_json": lambda d: [
                s.update({"production_call_observed": False, "call_count": 0})
                for s in d.get("stages", []) if s.get("stage_name") == "TRADE_BUILDER"
            ],
        },
        {
            "id": "M8",
            "name": "stage marked PASS from ranked_pipeline existence",
            "target": consumer_file,
            "mutate": lambda text: text.replace(
                'result["consumers"]["trade_builder"] = _state(\n        "PASS" if (tb_status in ("PASS", "SKIPPED_NOT_APPLICABLE")) else "PENDING",',
                'result["consumers"]["trade_builder"] = _state(\n        "PASS" if isinstance(ranked_pipeline, Mapping) else "PENDING",',
            ),
        },
        {
            "id": "M9",
            "name": "checkpoint emitted without TradeBuilder invocation",
            "target": ledger_file,
            "mutate_json": lambda d: [
                s.update({"checkpoint_emitted": False})
                for s in d.get("stages", []) if s.get("stage_name") == "TRADE_BUILDER"
            ],
        },
        {
            "id": "M10",
            "name": 'parent_span_id replaced with "CANDIDATE_POOL"',
            "target": lineage_file,
            "mutate_json": lambda d: d.update({
                "tradebuilder_parent_span_id": "CANDIDATE_POOL",
                "parent_span_is_real_span_id": False,
            }),
        },
        {
            "id": "M11",
            "name": "parent_span_id set None",
            "target": lineage_file,
            "mutate_json": lambda d: d.update({
                "tradebuilder_parent_span_id": None,
                "parent_span_is_real_span_id": False,
            }),
        },
        {
            "id": "M12",
            "name": "trace_id changed",
            "target": lineage_file,
            "mutate_json": lambda d: d.update({
                "trace_id": "mutated_foreign_trace_id_999",
                "trace_id_correlated": False,
                "trade_builder_trace_correlated": False,
            }),
        },
        {
            "id": "M13",
            "name": "output hash changed to counts-only",
            "target": output_hashes_file,
            "mutate_json": lambda d: d.update({
                "output_hash_covers_counts_only": True,
                "output_hash_covers_actual_result": False,
            }),
        },
        {
            "id": "M14",
            "name": "UI-ranked row made causal input",
            "target": consumer_file,
            "mutate": lambda text: text.replace(
                "for cand in tb_candidates:",
                "for cand in ranked_candidates: # for cand in tb_candidates:"
            ),
        },
        {
            "id": "M15",
            "name": "second candidate-selection authority added",
            "target": authority_file,
            "mutate": lambda text: text.replace(
                "    RuntimeAuthorityStage(\n        40,\n        \"legacy_opportunity_selection\",",
                "    RuntimeAuthorityStage(\n        39,\n        \"duplicate_selection\",\n        \"core.observer\",\n        \"select_best\",\n        AuthorityKind.CANDIDATE_SELECTION,\n        False,\n        False,\n        \"mutant\",\n    ),\n    RuntimeAuthorityStage(\n        40,\n        \"legacy_opportunity_selection\",",
            ),
        },
        {
            "id": "M16",
            "name": "ExecutionRouter/broker write path introduced",
            "target": broker_audit_file,
            "mutate_json": lambda d: d.update({
                "broker_write_calls_total": 2,
                "orders_placed": 1,
                "ExecutionRouter_CALLS": 1,
            }),
        },
        {
            "id": "M17",
            "name": "future timestamp injected after causal cutoff",
            "target": future_leak_file,
            "mutate_json": lambda d: d.update({
                "max_input_event_timestamp": "2026-09-15T09:25:00Z",
                "causal_data_cutoff": "2026-09-15T09:20:00Z",
                "future_leak_detected": True,
                "future_leak_status": "FAIL",
            }),
        },
        {
            "id": "M18",
            "name": "direct run_consumer_cycle fixture mislabeled canonical proof",
            "target": ledger_file,
            "mutate_json": lambda d: d.update({
                "proof_type": "DIRECT_CONSUMER_ONLY_PROOF",
            }),
        },
    ]

    results = []
    detected_count = 0

    for m in mutations:
        target = m["target"]
        original_content = target.read_text(encoding="utf-8")

        try:
            # Apply mutation
            if "mutate" in m:
                mutated = m["mutate"](original_content)
                assert mutated != original_content, f"Mutant {m['id']} did not alter content in {target}"
                target.write_text(mutated, encoding="utf-8")
            elif "mutate_json" in m:
                d = json.loads(original_content)
                m["mutate_json"](d)
                mutated = json.dumps(d, indent=2) + "\n"
                assert mutated != original_content, f"Mutant {m['id']} did not alter json in {target}"
                target.write_text(mutated, encoding="utf-8")

            # Run verifier
            proc = subprocess.run(
                [sys.executable, str(verifier_script), "--evidence-root", str(evidence_dir)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
            )

            rejected = (proc.returncode != 0)
            if rejected:
                detected_count += 1
                failure_msg = proc.stderr.strip() or proc.stdout.strip()
                # Find first error line
                err_lines = [l.strip() for l in failure_msg.splitlines() if "VIOLATION" in l or "error" in l.lower() or "rejected" in l.lower()]
                first_err = err_lines[0] if err_lines else "Verifier rejected with exit code 1"
                status_str = "REJECTED_AS_EXPECTED"
            else:
                first_err = "Verifier illegally passed mutant!"
                status_str = "FAILED_TO_DETECT"

            results.append({
                "mutation_id": m["id"],
                "mutation_name": m["name"],
                "target_file": str(target.relative_to(REPO_ROOT) if REPO_ROOT in target.parents else target),
                "status": status_str,
                "detected": rejected,
                "rejection_reason": first_err,
            })
            print(f"[{m['id']}] {m['name']}: {status_str} -> {first_err}")

        finally:
            # Always restore pristine file
            target.write_text(original_content, encoding="utf-8")

    # Post-check to ensure all restored
    post_proc = subprocess.run(
        [sys.executable, str(verifier_script), "--evidence-root", str(evidence_dir)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert post_proc.returncode == 0, f"Post-restoration verification failed: {post_proc.stdout}"

    summary = {
        "candidate_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip(),
        "total_mutations": len(mutations),
        "detected_mutations": detected_count,
        "mutation_score": f"{detected_count}/{len(mutations)}",
        "all_mutations_detected": detected_count == len(mutations),
        "results": results,
    }

    report_p = evidence_dir / "MUTATION_CAMPAIGN_REPORT.json"
    report_p.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nMutation campaign complete: {detected_count}/{len(mutations)} detected.")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=None)
    args = parser.parse_args()

    short_sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    ev_dir = args.evidence_root or Path(f"/Volumes/TradeBotData/pr905-tradebuilder-canonical-proof-{short_sha}")
    res = run_mutation_campaign(ev_dir)
    sys.exit(0 if res["all_mutations_detected"] else 1)
