#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.strategy_pipeline.adapter_runtime import (  # noqa: E402
    AdapterRuntimeError,
    PipelineAdapterRuntime,
)
from core.strategy_pipeline.pipeline_models import EngineType  # noqa: E402
from core.strategy_pipeline.registry_stage_adapter import (  # noqa: E402
    RegistryStageError,
    run_registry_stage,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify one exact strategy contract for the strategy pipeline."
    )
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--implementation-file", required=True)
    args = parser.parse_args()

    try:
        runtime = PipelineAdapterRuntime.from_environment(
            EngineType.REGISTRY,
            repo_root=REPO_ROOT,
        )
    except AdapterRuntimeError as exc:
        print(f"REGISTRY_ADAPTER_RUNTIME_INVALID:{exc}", file=sys.stderr)
        return 2

    if args.strategy != runtime.strategy_id:
        result = runtime.write_blocked(
            verdict="REGISTRY_STAGE_BLOCKED",
            blockers=["strategy_argument_mismatch"],
        )
    else:
        try:
            result = run_registry_stage(
                runtime,
                implementation_file=args.implementation_file,
            )
        except (RegistryStageError, ValueError) as exc:
            result = runtime.write_blocked(
                verdict="REGISTRY_STAGE_BLOCKED",
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
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
