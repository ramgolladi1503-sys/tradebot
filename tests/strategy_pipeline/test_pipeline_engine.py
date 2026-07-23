from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from core.strategy_pipeline.artifact_locator import ArtifactLocator
from core.strategy_pipeline.pipeline_context import PipelineContext
from core.strategy_pipeline.pipeline_engine import StrategyPipelineEngine
from core.strategy_pipeline.pipeline_models import (
    EngineResult,
    EngineType,
    PipelineState,
)
from core.strategy_pipeline.pipeline_state import PipelineStateTracker
from core.strategy_pipeline.pipeline_validator import (
    PipelineValidationError,
    PipelineValidator,
)
from core.strategy_pipeline.result_manifest import (
    ResultManifestError,
    load_engine_result_manifest,
    sha256_file,
    write_engine_result_manifest,
)


def _success_result(
    root: Path,
    *,
    engine: EngineType,
    context: PipelineContext,
    strategy_id: str = "s1",
) -> EngineResult:
    run_root = root / "runtime" / "strategy_pipeline" / strategy_id / context.run_id
    artifact = run_root / f"{engine.value.lower()}.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"ok": true}\n', encoding="utf-8")
    result = EngineResult(
        engine=engine,
        state=PipelineState.SUCCESS,
        run_id=context.run_id,
        strategy_id=strategy_id,
        artifacts_generated=[str(artifact)],
        input_hashes=context.engine_input_hashes.get(engine.value, {}),
        output_hashes={str(artifact.resolve()): sha256_file(artifact)},
        verdict="PASS",
        exit_code=0,
        verified=True,
    )
    manifest = run_root / f"{engine.value.lower()}.result.json"
    write_engine_result_manifest(manifest, result)
    result.manifest_path = str(manifest)
    return result


def test_context_defaults_to_research_and_excludes_drift():
    context = PipelineContext()
    assert context.execution_mode == "RESEARCH"
    assert context.include_drift is False
    assert re.fullmatch(r"[0-9a-f]{32}", context.run_id)


def test_pre_run_rejects_live_mode():
    with pytest.raises(PipelineValidationError, match="unsafe_execution_mode"):
        PipelineValidator().validate_pre_run(
            "s1",
            PipelineContext(execution_mode="LIVE"),
        )


def test_pre_run_rejects_live_environment(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "LIVE")
    with pytest.raises(PipelineValidationError, match="live_environment_forbidden"):
        PipelineValidator().validate_pre_run("s1", PipelineContext())


def test_pre_run_hashes_exact_inputs(tmp_path):
    source = tmp_path / "candidate.jsonl"
    source.write_text('{"candidate_id":"1"}\n', encoding="utf-8")
    context = PipelineContext(engine_inputs={"OUTCOMES": [str(source)]})
    PipelineValidator().validate_pre_run("s1", context)
    assert context.engine_input_hashes["OUTCOMES"][str(source.resolve())] == sha256_file(source)


def test_pre_run_rejects_missing_input(tmp_path):
    context = PipelineContext(engine_inputs={"OUTCOMES": [str(tmp_path / "missing.jsonl")]})
    with pytest.raises(PipelineValidationError, match="engine_input_missing"):
        PipelineValidator().validate_pre_run("s1", context)


def test_artifact_locator_is_run_scoped(tmp_path):
    locator = ArtifactLocator(tmp_path)
    path = locator.result_manifest_path(EngineType.RESEARCH, "s1", "run12345")
    assert path == (
        tmp_path.resolve()
        / "runtime"
        / "strategy_pipeline"
        / "s1"
        / "run12345"
        / "research.result.json"
    )


def test_result_manifest_round_trip(tmp_path):
    context = PipelineContext(run_id="run12345")
    result = _success_result(tmp_path, engine=EngineType.RESEARCH, context=context)
    loaded = load_engine_result_manifest(result.manifest_path)
    assert loaded.engine == EngineType.RESEARCH
    assert loaded.state == PipelineState.SUCCESS
    assert loaded.strategy_id == "s1"
    assert loaded.verified is True


def test_result_manifest_internal_hash_forgery_is_rejected(tmp_path):
    context = PipelineContext(run_id="run12345")
    result = _success_result(tmp_path, engine=EngineType.RESEARCH, context=context)
    manifest = Path(result.manifest_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["verdict"] = "FORGED"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ResultManifestError, match="hash_mismatch"):
        load_engine_result_manifest(manifest)


def test_validator_rejects_success_without_artifacts(tmp_path):
    context = PipelineContext(run_id="run12345")
    PipelineValidator().validate_pre_run("s1", context)
    result = EngineResult(
        engine=EngineType.RESEARCH,
        state=PipelineState.SUCCESS,
        run_id=context.run_id,
        strategy_id="s1",
        verdict="PASS",
        exit_code=0,
        verified=True,
    )
    with pytest.raises(PipelineValidationError, match="artifacts_required"):
        PipelineValidator().validate_engine_result(
            result,
            EngineType.RESEARCH,
            "s1",
            context,
            base_dir=tmp_path,
        )


def test_validator_rejects_tampered_output(tmp_path):
    context = PipelineContext(run_id="run12345")
    PipelineValidator().validate_pre_run("s1", context)
    result = _success_result(tmp_path, engine=EngineType.RESEARCH, context=context)
    Path(result.artifacts_generated[0]).write_text("tampered", encoding="utf-8")
    with pytest.raises(PipelineValidationError, match="hash_mismatch"):
        PipelineValidator().validate_engine_result(
            result,
            EngineType.RESEARCH,
            "s1",
            context,
            base_dir=tmp_path,
        )


def test_tracker_preserves_degraded_state():
    tracker = PipelineStateTracker(strategy_id="s1", global_state=PipelineState.RUNNING)
    tracker.update_engine_result(
        EngineType.RESEARCH,
        EngineResult(
            engine=EngineType.RESEARCH,
            state=PipelineState.DEGRADED,
            errors=["limited evidence"],
        ),
    )
    tracker.finalize([EngineType.RESEARCH])
    assert tracker.global_state == PipelineState.DEGRADED


def test_engine_sequence_excludes_drift_by_default(tmp_path):
    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))
    assert EngineType.DRIFT not in engine._engine_sequence(PipelineContext())
    assert EngineType.DRIFT in engine._engine_sequence(PipelineContext(include_drift=True))


def test_downstream_inputs_bind_upstream_manifest(tmp_path):
    context = PipelineContext(run_id="run12345")
    PipelineValidator().validate_pre_run("s1", context)
    upstream = _success_result(tmp_path, engine=EngineType.RESEARCH, context=context)
    tracker = PipelineStateTracker(strategy_id="s1", global_state=PipelineState.RUNNING)
    tracker.update_engine_result(EngineType.RESEARCH, upstream)
    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))

    blocker = engine._bind_upstream_inputs(
        EngineType.REGISTRY,
        "s1",
        context,
        tracker,
    )

    manifest = str(Path(upstream.manifest_path).resolve())
    assert blocker is None
    assert context.engine_input_hashes["REGISTRY"][manifest] == sha256_file(manifest)


def test_outcomes_requires_exact_arguments(tmp_path):
    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))
    context = PipelineContext(run_id="run12345")
    PipelineValidator().validate_pre_run("s1", context)
    result = engine._build_command(
        EngineType.OUTCOMES,
        "s1",
        context,
        "scripts/run_outcome_evidence_replay.py",
    )
    assert isinstance(result, EngineResult)
    assert result.state == PipelineState.BLOCKED
    assert result.verdict == "ENGINE_ARGUMENTS_MISSING"


def test_statistics_does_not_discover_latest_file(tmp_path):
    evidence_dir = tmp_path / "runtime" / "outcome_evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "evidence_old.jsonl").write_text("{}\n", encoding="utf-8")
    (evidence_dir / "evidence_new.jsonl").write_text("{}\n", encoding="utf-8")
    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))
    context = PipelineContext(run_id="run12345")
    PipelineValidator().validate_pre_run("s1", context)
    result = engine._build_command(
        EngineType.STATISTICS,
        "s1",
        context,
        "scripts/run_statistical_validation.py",
    )
    assert isinstance(result, EngineResult)
    assert result.verdict == "ENGINE_ARGUMENTS_MISSING"


def test_bare_zero_exit_without_manifest_is_blocked(tmp_path):
    script = tmp_path / "scripts" / "run_research_registry.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('done')\n", encoding="utf-8")
    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))
    context = PipelineContext(run_id="run12345", force_refresh=True)
    PipelineValidator().validate_pre_run("s1", context)

    completed = type("Completed", (), {"returncode": 0, "stdout": "done", "stderr": ""})()
    with patch("core.strategy_pipeline.pipeline_engine.subprocess.run", return_value=completed):
        result = engine._run_engine(EngineType.RESEARCH, "s1", context)

    assert result.state == PipelineState.BLOCKED
    assert result.verdict == "RESULT_MANIFEST_MISSING"


def test_registry_missing_adapter_is_blocked(tmp_path):
    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))
    context = PipelineContext(run_id="run12345", force_refresh=True)
    PipelineValidator().validate_pre_run("s1", context)
    result = engine._run_engine(EngineType.REGISTRY, "s1", context)
    assert result.state == PipelineState.BLOCKED
    assert result.verdict == "ENGINE_ADAPTER_MISSING"


def test_invalid_mock_success_is_converted_to_failure(tmp_path):
    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))
    context = PipelineContext(run_id="run12345", force_refresh=True)

    invalid = EngineResult(
        engine=EngineType.RESEARCH,
        state=PipelineState.SUCCESS,
        run_id=context.run_id,
        strategy_id="s1",
        verdict="PASS",
        verified=True,
        exit_code=0,
    )
    with patch.object(engine, "_run_engine", return_value=invalid):
        tracker = engine.run("s1", context)

    assert tracker.global_state == PipelineState.FAILED
    result = tracker.engine_results[EngineType.RESEARCH]
    assert result.verdict == "INVALID_ENGINE_RESULT"
    assert "success_result_artifacts_required" in result.errors[0]


def test_verified_cache_manifest_can_be_reused(tmp_path):
    context = PipelineContext(run_id="run12345")
    PipelineValidator().validate_pre_run("s1", context)
    result = _success_result(tmp_path, engine=EngineType.RESEARCH, context=context)
    context.cache_manifests["RESEARCH"] = str(result.manifest_path)

    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))
    cached = engine._run_engine(EngineType.RESEARCH, "s1", context)
    PipelineValidator().validate_engine_result(
        cached,
        EngineType.RESEARCH,
        "s1",
        context,
        base_dir=tmp_path,
    )
    assert cached.cached is True


def test_cache_with_wrong_strategy_is_rejected_by_run(tmp_path):
    context = PipelineContext(run_id="run12345")
    PipelineValidator().validate_pre_run("s1", context)
    result = _success_result(
        tmp_path,
        engine=EngineType.RESEARCH,
        context=context,
        strategy_id="other",
    )
    context.cache_manifests["RESEARCH"] = str(result.manifest_path)

    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))
    tracker = engine.run("s1", context)
    assert tracker.global_state == PipelineState.FAILED
    assert "engine_result_strategy_mismatch" in tracker.engine_results[EngineType.RESEARCH].errors[0]


def test_full_verified_mock_pipeline_finishes_research_only(tmp_path):
    context = PipelineContext(run_id="run12345", force_refresh=True)
    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))

    def fake_run(stage, strategy_id, current_context):
        return _success_result(
            tmp_path,
            engine=stage,
            context=current_context,
            strategy_id=strategy_id,
        )

    with patch.object(engine, "_run_engine", side_effect=fake_run):
        tracker = engine.run("s1", context)

    assert tracker.global_state == PipelineState.SUCCESS
    assert tracker.final_decision.certification_status == "Research Only"
    assert tracker.final_decision.reason == "VERIFIED_RESEARCH_PIPELINE_COMPLETE"
    assert EngineType.DRIFT not in tracker.engine_results


def test_blocked_result_drives_truthful_final_decision(tmp_path):
    context = PipelineContext(run_id="run12345", force_refresh=True)
    engine = StrategyPipelineEngine(locator=ArtifactLocator(tmp_path))

    blocked = EngineResult(
        engine=EngineType.RESEARCH,
        state=PipelineState.BLOCKED,
        run_id=context.run_id,
        strategy_id="s1",
        blockers=["frozen hypothesis missing"],
        verdict="RESEARCH_INPUT_MISSING",
    )
    with patch.object(engine, "_run_engine", return_value=blocked):
        tracker = engine.run("s1", context)

    assert tracker.global_state == PipelineState.BLOCKED
    assert tracker.final_decision.reason == "RESEARCH_INPUT_MISSING"
    assert tracker.final_decision.blockers == ["frozen hypothesis missing"]
