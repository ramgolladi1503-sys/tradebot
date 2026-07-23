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
from core.strategy_pipeline.research_stage_adapter import (  # noqa: E402
    ResearchStageError,
    run_research_stage,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify one governed frozen hypothesis for the strategy pipeline."
    )
    parser.add_argument("--governed-run-dir", required=True)
    args = parser.parse_args()

    try:
        runtime = PipelineAdapterRuntime.from_environment(
            EngineType.RESEARCH,
            repo_root=REPO_ROOT,
        )
    except AdapterRuntimeError as exc:
        print(f"RESEARCH_ADAPTER_RUNTIME_INVALID:{exc}", file=sys.stderr)
        return 2

    try:
        result = run_research_stage(
            runtime,
            governed_run_dir=args.governed_run_dir,
        )
    except ResearchStageError as exc:
        result = runtime.write_blocked(
            verdict="RESEARCH_STAGE_BLOCKED",
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
