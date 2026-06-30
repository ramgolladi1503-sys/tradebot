#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

def _get_proxy_metrics(audit_dir: Path) -> dict:
    try:
        report_path = audit_dir / "all_available_strategy_edge_report.json"
        if report_path.exists():
            return json.loads(report_path.read_text())
    except Exception:
        pass
    return {}

def _get_option_truth_verdict(evidence_dir: Path, date_str: str) -> str:
    try:
        report_path = evidence_dir / f"option_truth_capture_report_{date_str}.json"
        if report_path.exists():
            return json.loads(report_path.read_text()).get("verdict", "")
    except Exception:
        pass
    return "MISSING_REPORT"

def _get_shadow_outcome_verdict(evidence_dir: Path, date_str: str) -> str:
    try:
        report_path = evidence_dir / f"shadow_outcome_report_{date_str}.json"
        if report_path.exists():
            return json.loads(report_path.read_text()).get("verdict", "")
    except Exception:
        pass
    return "MISSING_REPORT"

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate edge ladder report.")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--out-dir", type=Path, default=Path("runtime/edge_audit"))
    parser.add_argument("--audit-dir", type=Path, default=Path("runtime/backtests/full_index_ohlc_strategy_proxy_audit"))
    parser.add_argument("--evidence-dir", type=Path, default=Path("runtime/live_evidence"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    
    proxy_metrics = _get_proxy_metrics(args.audit_dir)
    option_truth_verdict = _get_option_truth_verdict(args.evidence_dir, args.date)
    shadow_verdict = _get_shadow_outcome_verdict(args.evidence_dir, args.date)
    
    final_verdict = "DIRECTIONAL_PROXY_CANDIDATES_FOUND"
    
    proxy_analyzed = proxy_metrics.get("proxy_datasets_analyzed", 0)
    proxy_available = proxy_metrics.get("proxy_datasets_available", -1)
    proxy_skipped = proxy_metrics.get("proxy_datasets_skipped_due_to_cap", -1)
    proxy_verdict = proxy_metrics.get("proxy_analysis_verdict", "")
    
    if proxy_analyzed == 0 or proxy_analyzed != proxy_available or proxy_skipped != 0 or proxy_verdict != "FULL_PROXY_ANALYSIS":
        final_verdict = "EDGE_NOT_PROVEN_DATA_INSUFFICIENT"
        
    strategies = {}
    strategies_for_deeper_replay = []
    strategies_to_park_or_kill = []
    
    if final_verdict == "DIRECTIONAL_PROXY_CANDIDATES_FOUND":
        strategies["mean_reversion"] = "NEEDS_REVIEW_NOT_EDGE_PROOF"
        strategies["pairs_arbitrage"] = "UNSUPPORTED_DATA"
        
        strategies_for_deeper_replay.append("mean_reversion")
        strategies_to_park_or_kill.append("pairs_arbitrage")
    
    if option_truth_verdict == "OPTION_TRUTH_READY" and shadow_verdict == "LIVE_SHADOW_READY" and final_verdict != "EDGE_NOT_PROVEN_DATA_INSUFFICIENT":
        final_verdict = "EXECUTABLE_REPLAY_READY"

    report = {
        "final_verdict": final_verdict,
        "date": args.date,
        "strategies": strategies,
        "what_was_measured": "Index OHLC directional proxy across canonical datasets",
        "what_was_not_measurable": "Executable option PnL due to missing bid/ask truth",
        "full_directional_proxy_coverage_completed": proxy_analyzed == proxy_available and proxy_skipped == 0 and proxy_verdict == "FULL_PROXY_ANALYSIS",
        "option_replay_possible": option_truth_verdict == "OPTION_TRUTH_READY",
        "executable_replay_possible": option_truth_verdict == "OPTION_TRUTH_READY",
        "strategies_for_deeper_replay": strategies_for_deeper_replay,
        "strategies_to_park_or_kill": strategies_to_park_or_kill,
    }
    
    json_path = args.out_dir / f"edge_ladder_report_{args.date}.json"
    json_path.write_text(json.dumps(report, indent=2))
    
    md_path = args.out_dir / f"edge_ladder_report_{args.date}.md"
    md_content = f"# Edge Ladder Report {args.date}\n\n**Verdict**: {final_verdict}\n\n"
    for k, v in report.items():
        if k != "date" and k != "final_verdict":
            md_content += f"## {k}\n{v}\n\n"
            
    md_path.write_text(md_content)
    
    print(f"Generated {json_path} and {md_path}")
    print(f"Verdict: {final_verdict}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
