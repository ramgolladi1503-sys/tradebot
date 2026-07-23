from pathlib import Path

import pytest

from core.strategy_pipeline.pipeline_context import PipelineContext
from core.strategy_pipeline.pipeline_models import EngineResult, EngineType, PipelineState
from core.strategy_pipeline.pipeline_validator import PipelineValidationError, PipelineValidator
from core.strategy_pipeline.result_manifest import sha256_file


def _blocked_with_artifact(tmp_path: Path, context: PipelineContext) -> EngineResult:
    artifact = (
        tmp_path
        / "runtime"
        / "strategy_pipeline"
        / "s1"
        / context.run_id
        / "truth.blocked.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"decision":"IMPLEMENTATION_MISMATCH"}\n', encoding="utf-8")
    return EngineResult(
        engine=EngineType.TRUTH,
        state=PipelineState.BLOCKED,
        run_id=context.run_id,
        strategy_id="s1",
        artifacts_generated=[str(artifact)],
        output_hashes={str(artifact.resolve()): sha256_file(artifact)},
        blockers=["rule_mismatch"],
        verdict="IMPLEMENTATION_MISMATCH",
        verified=True,
        exit_code=0,
    )


def test_blocked_result_may_attach_verified_diagnostic_artifact(tmp_path):
    context = PipelineContext(run_id="run12345")
    PipelineValidator().validate_pre_run("s1", context)
    result = _blocked_with_artifact(tmp_path, context)

    PipelineValidator().validate_engine_result(
        result,
        EngineType.TRUTH,
        "s1",
        context,
        base_dir=tmp_path,
    )

    assert result.state == PipelineState.BLOCKED
    assert result.verdict == "IMPLEMENTATION_MISMATCH"


def test_blocked_diagnostic_artifact_tampering_is_rejected(tmp_path):
    context = PipelineContext(run_id="run12345")
    PipelineValidator().validate_pre_run("s1", context)
    result = _blocked_with_artifact(tmp_path, context)
    Path(result.artifacts_generated[0]).write_text("tampered", encoding="utf-8")

    with pytest.raises(PipelineValidationError, match="result_artifact_hash_mismatch"):
        PipelineValidator().validate_engine_result(
            result,
            EngineType.TRUTH,
            "s1",
            context,
            base_dir=tmp_path,
        )
