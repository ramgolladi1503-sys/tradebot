#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _run_pipeline_mode(args: argparse.Namespace) -> int:
    from core.strategy_pipeline.adapter_runtime import (
        AdapterRuntimeError,
        PipelineAdapterRuntime,
    )
    from core.strategy_pipeline.outcomes_stage_adapter import (
        OutcomesStageError,
        run_outcomes_stage,
    )
    from core.strategy_pipeline.pipeline_models import EngineType

    try:
        runtime = PipelineAdapterRuntime.from_environment(
            EngineType.OUTCOMES,
            repo_root=REPO_ROOT,
        )
    except AdapterRuntimeError as exc:
        print(f"OUTCOMES_ADAPTER_RUNTIME_INVALID:{exc}", file=sys.stderr)
        return 2

    if not args.cost_config:
        result = runtime.write_blocked(
            verdict="OUTCOMES_STAGE_BLOCKED",
            blockers=["cost_config_required_in_pipeline_mode"],
        )
    else:
        try:
            result = run_outcomes_stage(
                runtime,
                candidate_file=args.candidate_file,
                trace_file=args.option_trace,
                cost_config_file=args.cost_config,
            )
        except (OutcomesStageError, ValueError) as exc:
            result = runtime.write_blocked(
                verdict="OUTCOMES_STAGE_BLOCKED",
                blockers=[str(exc)],
            )

    print(
        json.dumps(
            {
                "engine": result.engine.value,
                "state": result.state.value,
                "strategy_id": result.strategy_id,
                "run_id": result.run_id,
                "verdict": result.verdict,
                "result_manifest": result.manifest_path,
                "blockers": result.blockers,
            },
            sort_keys=True,
        )
    )
    return 0


def _run_legacy_mode(args: argparse.Namespace) -> int:
    from core.outcome_evidence.cost_model import IndianIndexOptionsCostModel
    from core.outcome_evidence.replay_runner import OutcomeEvidenceRunner

    run_id = str(uuid.uuid4())
    store_dir = Path("runtime/outcome_evidence")
    runner = OutcomeEvidenceRunner(
        run_id=run_id,
        store_dir=store_dir,
        cost_model=IndianIndexOptionsCostModel(),
    )

    candidate_path = Path(args.candidate_file)
    trace_path = Path(args.option_trace)
    regime_path = Path(args.regime_file) if args.regime_file else None

    if not candidate_path.exists():
        message = f"Error: Candidate file not found at {candidate_path}"
        print(json.dumps({"error": message}) if args.json else message)
        return 1
    if not trace_path.exists():
        message = f"Error: Trace file not found at {trace_path}"
        print(json.dumps({"error": message}) if args.json else message)
        return 1

    summary = runner.run(
        candidate_file=candidate_path,
        option_trace_file=trace_path,
        regime_file=regime_path,
        dry_run=args.dry_run,
    )
    payload = {
        "run_id": summary.run_id,
        "status": summary.run_status,
        "total_candidates": summary.total_candidates,
        "executable_count": summary.executable_count,
        "rejected_count": summary.rejected_count,
        "insufficient_evidence_count": summary.insufficient_evidence_count,
        "ambiguous_count": summary.ambiguous_count,
        "weak_ltp_count": summary.weak_ltp_count,
    }
    if args.json:
        print(json.dumps(payload))
    else:
        print("=== Outcome Evidence Run Summary ===")
        for key, value in payload.items():
            print(f"{key}: {value}")
        print("====================================")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Outcome Evidence Replay")
    parser.add_argument("--candidate-file", required=True)
    parser.add_argument("--option-trace", required=True)
    parser.add_argument("--cost-config")
    parser.add_argument("--regime-file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if os.environ.get("TRADEBOT_PIPELINE_RESULT_MANIFEST"):
        return _run_pipeline_mode(args)
    return _run_legacy_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
