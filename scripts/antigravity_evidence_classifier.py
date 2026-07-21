import json
import csv
import os

ANTIGRAVITY_DIR = "/Users/madhuram/antigravity_evidence_checkout/runtime/research/upstream_backtest_integrity_antigravity"
OUT_DIR = "runtime/research/upstream_backtest_integrity_codex_validation"

# Files from antigravity branch
EXPECTED_FILES = [
    "capital_reuse_results.json",
    "cost_unit_results.json",
    "feature_causality_results.json",
    "quote_age_results.json",
    "signal_limit_results.json",
    "slippage_results.json",
    "state_machine_results.json",
    "stop_target_ambiguity_results.json",
    "timeout_mismatch_results.json",
    "timezone_results.json",
    "validation_metrics_results.json",
    "vector_index_results.json",
    "wfa_results.json",
    "evidence_repair/pre_repair_manifest.json",
    "evidence_repair/prior_evidence_hash_manifest.json",
    "evidence_repair/suspect2_reproducer.json",
    "evidence_repair/suspect3_reproducer.json",
    "evidence_repair/suspect4_reproducer.json"
]

classification = {}

for f in EXPECTED_FILES:
    path = os.path.join(ANTIGRAVITY_DIR, f)
    if not os.path.exists(path):
        classification[f] = "MISSING_REQUIRED_EVIDENCE"
    elif "manifest.json" in f:
        classification[f] = "STALE_METADATA"
    elif "reproducer.json" in f:
        classification[f] = "PARTIAL_EVIDENCE"
    else:
        # Check contents for exact inputs and outputs
        with open(path, 'r') as file:
            content = file.read()
            if "actual_value" in content and "expected_value" in content:
                classification[f] = "SYNTHETIC_ONLY"
            else:
                classification[f] = "UNUSABLE"
                
# Missing authoritative files
MISSING = [
    "suspect_matrix.json",
    "production_path_invocation_matrix.json",
    "contract_test_matrix.json",
    "repository_discovery_results.json",
    "independent_oracle_report.json",
    "affected_strategy_matrix.json",
    "impact_estimates.json",
    "final_audit_report.json",
    "final_summary.md",
    "artifact_hash_manifest.json",
    "two_run_determinism_report.json"
]

for m in MISSING:
    classification[m] = "MISSING_REQUIRED_EVIDENCE"

with open(f"{OUT_DIR}/antigravity_evidence_review.json", "w") as out_json:
    json.dump(classification, out_json, indent=2)

with open(f"{OUT_DIR}/antigravity_file_classification.csv", "w", newline="") as out_csv:
    writer = csv.writer(out_csv)
    writer.writerow(["file", "classification"])
    for k, v in classification.items():
        writer.writerow([k, v])
