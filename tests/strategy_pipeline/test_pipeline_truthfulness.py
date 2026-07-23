import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.strategy_pipeline.artifact_locator import ArtifactLocator
from core.strategy_pipeline.pipeline_context import PipelineContext
from core.strategy_pipeline.pipeline_engine import StrategyPipelineEngine
from core.strategy_pipeline.pipeline_models import EngineResult, EngineType, PipelineState
from core.strategy_pipeline.pipeline_validator import PipelineValidationError, PipelineValidator


def test_pre_run_rejects_non_paper_mode():
    context = PipelineContext(strategy_id="s1", run_id="r1", paper_only=False)
    with pytest.raises(PipelineValidationError, match="paper-only"):
        PipelineValidator.validate_pre_run(context)


def test_success_requires_provenance_and_verdict():
    result = EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS)
    with pytest.raises(PipelineValidationError, match="run provenance"):
        PipelineValidator.validate_engine_result(result)


def test_success_requires_verified_outputs_for_non_registry():
    result = EngineResult(
        engine=EngineType.TRUTH,
        state=PipelineState.SUCCESS,
        run_id="r1",
        strategy_id="s1",
        verdict="OK",
        exit_code=0,
    )
    with pytest.raises(PipelineValidationError, match="verified outputs"):
        PipelineValidator.validate_engine_result(result)


def test_outcomes_never_guesses_candidate_or_trace_files():
    engine = StrategyPipelineEngine()
    context = PipelineContext(strategy_id="s1", run_id="r1")
    assert engine._build_command(EngineType.OUTCOMES, "s1", context) is None


def test_statistics_never_selects_latest_file():
    engine = StrategyPipelineEngine()
    context = PipelineContext(strategy_id="s1", run_id="r1")
    assert engine._build_command(EngineType.STATISTICS, "s1", context) is None
    context.set_artifact("outcome_evidence_file", "/tmp/exact.jsonl")
    command = engine._build_command(EngineType.STATISTICS, "s1", context)
    assert command[-1] == "/tmp/exact.jsonl"


def test_cache_without_manifest_is_not_accepted(tmp_path):
    artifact = tmp_path / "truth.json"
    artifact.write_text("{}", encoding="utf-8")
    locator = ArtifactLocator(base_dir=str(tmp_path))
    locator.locate_truth_report = lambda strategy_id: artifact
    engine = StrategyPipelineEngine(locator=locator)
    context = PipelineContext(strategy_id="s1", run_id="r1")
    assert engine._load_verified_cache(EngineType.TRUTH, "s1", context) is None


def test_cache_with_wrong_strategy_is_not_accepted(tmp_path):
    artifact = tmp_path / "truth.json"
    artifact.write_text("{}", encoding="utf-8")
    digest = PipelineValidator.sha256(artifact)
    Path(f"{artifact}.manifest.json").write_text(
        json.dumps({
            "strategy_id": "other",
            "engine": "TRUTH",
            "artifact_sha256": digest,
        }),
        encoding="utf-8",
    )
    locator = ArtifactLocator(base_dir=str(tmp_path))
    locator.locate_truth_report = lambda strategy_id: artifact
    engine = StrategyPipelineEngine(locator=locator)
    context = PipelineContext(strategy_id="s1", run_id="r1")
    assert engine._load_verified_cache(EngineType.TRUTH, "s1", context) is None


def test_verified_cache_requires_matching_hash(tmp_path):
    artifact = tmp_path / "truth.json"
    artifact.write_text("original", encoding="utf-8")
    digest = PipelineValidator.sha256(artifact)
    Path(f"{artifact}.manifest.json").write_text(
        json.dumps({
            "strategy_id": "s1",
            "engine": "TRUTH",
            "artifact_sha256": digest,
        }),
        encoding="utf-8",
    )
    artifact.write_text("tampered", encoding="utf-8")
    locator = ArtifactLocator(base_dir=str(tmp_path))
    locator.locate_truth_report = lambda strategy_id: artifact
    engine = StrategyPipelineEngine(locator=locator)
    context = PipelineContext(strategy_id="s1", run_id="r1")
    assert engine._load_verified_cache(EngineType.TRUTH, "s1", context) is None


def test_drift_not_in_initial_pipeline():
    engine = StrategyPipelineEngine()
    context = PipelineContext(run_id="r1")

    def success(stage, strategy_id, ctx):
        return EngineResult(
            engine=stage,
            state=PipelineState.SUCCESS,
            run_id=ctx.run_id,
            strategy_id=strategy_id,
            verdict="OK",
            exit_code=0,
            output_hashes={"artifact": "hash"},
        )

    with patch.object(engine, "_run_engine", side_effect=success):
        tracker = engine.run("s1", context)
    assert tracker.get_engine_state(EngineType.CERTIFICATION) == PipelineState.SUCCESS
    assert tracker.get_engine_state(EngineType.DRIFT) == PipelineState.PENDING
