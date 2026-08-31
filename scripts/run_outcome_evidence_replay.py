#!/usr/bin/env python3
import argparse
import sys
import uuid
from pathlib import Path

from core.outcome_evidence.replay_runner import OutcomeEvidenceRunner
from core.outcome_evidence.cost_model import IndianIndexOptionsCostModel


def main():
    parser = argparse.ArgumentParser(description="Outcome Evidence Replay")
    parser.add_argument("--candidate-file", type=str, required=True, help="Path to candidate_decisions.jsonl")
    parser.add_argument("--option-trace", type=str, required=True, help="Path to option_price_trace.jsonl")
    parser.add_argument("--regime-file", type=str, help="Path to regime_monitor.jsonl (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing to DB")
    parser.add_argument("--json", action="store_true", help="Output summary as JSON")

    args = parser.parse_args()

    run_id = str(uuid.uuid4())
    store_dir = Path("runtime/outcome_evidence")

    runner = OutcomeEvidenceRunner(
        run_id=run_id,
        store_dir=store_dir,
        cost_model=IndianIndexOptionsCostModel()
    )

    candidate_path = Path(args.candidate_file)
    trace_path = Path(args.option_trace)
    regime_path = Path(args.regime_file) if args.regime_file else None

    if not candidate_path.exists():
        msg = f"Error: Candidate file not found at {candidate_path}"
        if args.json:
            import json
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        sys.exit(1)

    if not trace_path.exists():
        msg = f"Error: Trace file not found at {trace_path}"
        if args.json:
            import json
            print(json.dumps({"error": msg}))
        else:
            print(msg)
        sys.exit(1)

    summary = runner.run(
        candidate_file=candidate_path,
        option_trace_file=trace_path,
        regime_file=regime_path,
        dry_run=args.dry_run
    )

    if args.json:
        import json
        print(json.dumps({
            "run_id": summary.run_id,
            "status": summary.run_status,
            "total_candidates": summary.total_candidates,
            "executable_count": summary.executable_count,
            "rejected_count": summary.rejected_count,
            "insufficient_evidence_count": summary.insufficient_evidence_count,
            "ambiguous_count": summary.ambiguous_count,
            "weak_ltp_count": summary.weak_ltp_count
        }))
    else:
        print("=== Outcome Evidence Run Summary ===")
        print(f"Run ID: {summary.run_id}")
        print(f"Status: {summary.run_status}")
        print(f"Total Candidates: {summary.total_candidates}")
        print(f"Executable: {summary.executable_count}")
        print(f"Rejected: {summary.rejected_count}")
        print(f"Insufficient: {summary.insufficient_evidence_count}")
        print(f"Ambiguous Both Hit: {summary.ambiguous_count}")
        print("====================================")


if __name__ == "__main__":
    main()
