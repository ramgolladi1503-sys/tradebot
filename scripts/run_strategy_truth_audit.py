from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _default_serializer(obj):
    if hasattr(obj, "value"):  # Enums
        return obj.value
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def _run_pipeline_mode(strategy_id: str | None) -> int:
    from core.strategy_pipeline.adapter_runtime import (
        AdapterRuntimeError,
        PipelineAdapterRuntime,
    )
    from core.strategy_pipeline.pipeline_models import EngineType
    from core.strategy_pipeline.truth_stage_adapter import (
        TruthStageError,
        run_truth_stage,
    )

    try:
        runtime = PipelineAdapterRuntime.from_environment(
            EngineType.TRUTH,
            repo_root=REPO_ROOT,
        )
    except AdapterRuntimeError as exc:
        print(f"TRUTH_ADAPTER_RUNTIME_INVALID:{exc}", file=sys.stderr)
        return 2

    if strategy_id != runtime.strategy_id:
        result = runtime.write_blocked(
            verdict="TRUTH_STAGE_BLOCKED",
            blockers=["strategy_argument_mismatch"],
        )
    else:
        try:
            result = run_truth_stage(runtime)
        except (TruthStageError, ValueError) as exc:
            result = runtime.write_blocked(
                verdict="TRUTH_STAGE_BLOCKED",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Strategy Truth Engine.")
    parser.add_argument("--strategy", type=str, help="Audit a specific strategy ID")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary in JSON format",
    )
    args = parser.parse_args()

    if os.environ.get("TRADEBOT_PIPELINE_RESULT_MANIFEST"):
        raise SystemExit(_run_pipeline_mode(args.strategy))

    from core.strategy_truth.audit_engine import AuditEngine
    from core.strategy_truth.report_generator import ReportGenerator

    try:
        engine = AuditEngine()
        summary = engine.run_all(target_strategy_id=args.strategy)

        generator = ReportGenerator()
        generator.write_reports(summary)

        if args.json:
            print(
                json.dumps(
                    dataclasses.asdict(summary),
                    default=_default_serializer,
                    indent=2,
                )
            )
        else:
            print("=" * 40)
            print("Strategy Truth Engine Summary")
            print("=" * 40)
            print(f"Total Strategies Evaluated: {summary.total_strategies}")
            print(f"Fully Verified: {summary.fully_verified_count}")
            print(f"Partially Verified: {summary.partially_verified_count}")
            print(f"Implementation Mismatch: {summary.mismatch_count}")
            print(f"Registry Incomplete: {summary.registry_incomplete_count}")
            print("=" * 40)
            print("Detailed markdown reports generated in docs/strategy_truth/")
            print("Done.")

        raise SystemExit(0)

    except Exception as exc:
        print(f"Tool failure: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
