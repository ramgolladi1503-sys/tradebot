import argparse
import json
from pathlib import Path
from collections import Counter

def parse_args():
    parser = argparse.ArgumentParser(description="Generate pipeline health report.")
    parser.add_argument("--strategy", type=str, required=True, help="Strategy to report on")
    return parser.parse_args()

def main():
    args = parse_args()
    strategy = args.strategy
    runtime_dir = Path(f"runtime/strategy_validation/{strategy}")
    
    contract_file = runtime_dir / "pipeline_contract_audit.json"
    lineage_file = runtime_dir / "lineage_audit.json"
    ranking_file = runtime_dir / "ranking_safety_audit.json"
    outcome_file = runtime_dir / "blocker_outcome_replay.json"
    
    if not contract_file.exists():
        print(f"Error: Required audit files not found in {runtime_dir}")
        return
        
    with open(contract_file, "r") as f:
        contract_data = json.load(f).get("conservation", {})
        
    with open(lineage_file, "r") as f:
        lineage_data = json.load(f)
        
    with open(ranking_file, "r") as f:
        ranking_data = json.load(f)
        
    outcome_available = False
    outcome_indicated = False
    outcome_proven = False
    original_boundary_count = 0
    reconstructed_boundary_count = 0
    missing_boundary_count = 0
    option_path_count = 0
    underlying_proxy_path_count = 0
    insufficient_data_count = 0
    
    if outcome_file.exists():
        with open(outcome_file, "r") as f:
            outcome_data = json.load(f)
            if len(outcome_data) > 0:
                outcome_available = True
                for row in outcome_data:
                    original_boundary_count += row.get("original_boundary_count", 0)
                    reconstructed_boundary_count += row.get("reconstructed_boundary_count", 0)
                    missing_boundary_count += row.get("missing_boundary_count", 0)
                    option_path_count += row.get("option_path_count", 0)
                    underlying_proxy_path_count += row.get("underlying_proxy_path_count", 0)
                    insufficient_data_count += row.get("insufficient_data_count", 0)
                    
                    if row.get("blocker_outcome_correctness_indicated"):
                        outcome_indicated = True
                        
                if original_boundary_count > 0 and option_path_count > 0 and reconstructed_boundary_count == 0 and underlying_proxy_path_count == 0:
                    # Plus quote truth must be REAL_BID_ASK, handled later if we merge state
                    outcome_proven = True
        
    # Verdict logic
    silent_drops = contract_data.get("silent_drops", 0)
    invalid_ranked = contract_data.get("invalid_ranked_candidates", 0)
    candidates_generated = contract_data.get("candidates_generated", 0)
    feed_snapshots_seen = contract_data.get("feed_snapshots_seen", 0)
    option_chain_ready = contract_data.get("option_chain_ready", 0)
    
    real_market_lineage = contract_data.get("real_market_lineage", 0)
    replay_partial_lineage = contract_data.get("replay_partial_lineage", 0)
    synthetic_lineage = contract_data.get("synthetic_lineage", 0)
    real_bid_ask = contract_data.get("real_bid_ask", 0)
    mocked_bid_ask = contract_data.get("mocked_bid_ask", 0)
    quote_evidence_failures = contract_data.get("quote_evidence_failures", 0)
    
    verdict = "FULL PASS"
    warnings = []
    failures = []
    
    if silent_drops > 0:
        verdict = "FAIL"
        failures.append(f"{silent_drops} silent drops detected.")
    
    if invalid_ranked > 0:
        verdict = "FAIL"
        failures.append(f"{invalid_ranked} invalid ranked candidates detected.")
        
    if feed_snapshots_seen == 0:
        verdict = "FAIL"
        failures.append("No feed snapshots recorded! Pipeline observability is incomplete.")
        if real_market_lineage == 0 and replay_partial_lineage > 0:
            verdict = "PARTIAL PASS" if verdict == "FULL PASS" else verdict
            warnings.append("FEED_VOLUME_AUDITED: Aggregate upstream counts exist, but object-level lineage is replay-derived, not real market truth (FEED_OBJECT_LINEAGE_NOT_FULLY_AUDITED).")
        elif real_market_lineage == 0 and replay_partial_lineage == 0 and synthetic_lineage == 0:
            verdict = "PARTIAL PASS" if verdict == "FULL PASS" else verdict
            warnings.append("FEED_VOLUME_AUDITED: Aggregate upstream counts exist, but no object-level feed snapshot references present (FEED_OBJECT_LINEAGE_NOT_FULLY_AUDITED).")
        
    if option_chain_ready == 0:
        verdict = "FAIL"
        failures.append("No option chain snapshots recorded! Pipeline observability is incomplete.")
        
    if quote_evidence_failures > 0:
        verdict = "FAIL"
        failures.append(f"{quote_evidence_failures} ranked executable candidates lack quote truth or valid evidence.")
        
    if mocked_bid_ask > 0:
        if verdict == "FULL PASS":
            verdict = "PARTIAL PASS"
        warnings.append(f"{mocked_bid_ask} candidates have 'quote evidence shape complete', but lack true 'quote truth' (quotes were mocked from LTP).")
        
    if synthetic_lineage > 0 and verdict not in ["FAIL", "PARTIAL PASS"]:
        verdict = "WARN"
        warnings.append(f"{synthetic_lineage} synthetic IDs used. True object-level lineage is not proven.")
        
    # Warnings
    if sum(lineage_data.get("missing_fields", {}).values()) > 0:
        if verdict not in ["FAIL", "PARTIAL PASS"]:
            verdict = "WARN"
        warnings.append("Missing lineage fields detected.")
        
    report = {
        "strategy": strategy,
        "verdict": verdict,
        "failures": failures,
        "warnings": warnings,
        "conservation_metrics": contract_data,
        "missing_lineage_fields": lineage_data.get("missing_fields", {}),
        "blocker_classification_proven": lineage_data.get("blocker_classification_proven", False),
        "blocker_outcome_replay_available": outcome_available,
        "blocker_outcome_correctness_indicated": outcome_indicated,
        "blocker_outcome_correctness_proven": outcome_proven,
        "blocker_evidence_metrics": {
            "original_boundary_count": original_boundary_count,
            "reconstructed_boundary_count": reconstructed_boundary_count,
            "missing_boundary_count": missing_boundary_count,
            "option_path_count": option_path_count,
            "underlying_proxy_path_count": underlying_proxy_path_count,
            "insufficient_data_count": insufficient_data_count
        },
        "ranking_safety_issues": ranking_data.get("invalid_count", 0)
    }
    
    with open(runtime_dir / "pipeline_health_report.json", "w") as f:
        json.dump(report, f, indent=2)
        
    with open(runtime_dir / "pipeline_health_report.md", "w") as f:
        f.write(f"# Pipeline Health Report: {strategy}\n\n")
        f.write(f"**Verdict:** {verdict}\n\n")
        
        if failures:
            f.write("### Failures\n")
            for fail in failures:
                f.write(f"- {fail}\n")
            f.write("\n")
            
        if warnings:
            f.write("### Warnings\n")
            for warn in warnings:
                f.write(f"- {warn}\n")
            f.write("\n")
            
        f.write("### Conservation Metrics\n")
        f.write("```json\n")
        f.write(json.dumps(contract_data, indent=2))
        f.write("\n```\n\n")
        
        f.write("### Missing Lineage Fields\n")
        f.write("```json\n")
        f.write(json.dumps(lineage_data, indent=2))
        f.write("\n```\n\n")

if __name__ == "__main__":
    main()
