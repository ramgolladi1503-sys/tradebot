import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.strategy_pipeline.artifact_locator import ArtifactLocator
from core.strategy_pipeline.dependency_resolver import DependencyResolver
from core.strategy_pipeline.pipeline_context import PipelineContext
from core.strategy_pipeline.pipeline_engine import StrategyPipelineEngine
from core.strategy_pipeline.pipeline_models import (
    EngineResult,
    EngineType,
    FinalDecision,
    PipelineState,
)
from core.strategy_pipeline.pipeline_state import PipelineStateTracker
from core.strategy_pipeline.pipeline_validator import (
    PipelineValidationError,
    PipelineValidator,
)
from core.strategy_pipeline.report_generator import ReportGenerator


# --- Models and state tracking ---


def test_pipeline_state_enum():
    assert PipelineState.PENDING.value == "PENDING"
    assert PipelineState.RUNNING.value == "RUNNING"
    assert PipelineState.SUCCESS.value == "SUCCESS"
    assert PipelineState.FAILED.value == "FAILED"
    assert PipelineState.BLOCKED.value == "BLOCKED"
    assert PipelineState.DEGRADED.value == "DEGRADED"


def test_engine_type_enum():
    assert [engine.value for engine in EngineType] == [
        "RESEARCH",
        "REGISTRY",
        "TRUTH",
        "OUTCOMES",
        "STATISTICS",
        "CERTIFICATION",
        "DRIFT",
    ]


def test_engine_result_initialization():
    result = EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS)
    assert result.engine == EngineType.RESEARCH
    assert result.state == PipelineState.SUCCESS
    assert result.cached is False
    assert result.artifacts_generated == []
    assert result.input_hashes == {}
    assert result.output_hashes == {}


def test_final_decision_initialization():
    decision = FinalDecision(
        strategy_id="test1",
        certification_status="Research Only",
        reason="Just starting",
    )
    assert decision.strategy_id == "test1"
    assert decision.certification_status == "Research Only"
    assert decision.reason == "Just starting"
    assert decision.blockers == []


def test_tracker_initialization():
    tracker = PipelineStateTracker(strategy_id="s1")
    assert tracker.strategy_id == "s1"
    assert tracker.global_state == PipelineState.PENDING
    assert tracker.engine_results == {}


def test_tracker_records_success_without_promoting_global_state():
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.update_engine_result(
        EngineType.RESEARCH,
        EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS),
    )
    assert tracker.get_engine_state(EngineType.RESEARCH) == PipelineState.SUCCESS
    assert tracker.global_state == PipelineState.PENDING


def test_tracker_records_failure():
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.update_engine_result(
        EngineType.RESEARCH,
        EngineResult(
            engine=EngineType.RESEARCH,
            state=PipelineState.FAILED,
            errors=["failure"],
        ),
    )
    assert tracker.global_state == PipelineState.FAILED


def test_tracker_records_blocker_and_stage():
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.update_engine_result(
        EngineType.OUTCOMES,
        EngineResult(
            engine=EngineType.OUTCOMES,
            state=PipelineState.BLOCKED,
            blockers=["missing input"],
        ),
    )
    assert tracker.global_state == PipelineState.BLOCKED
    assert tracker.blocked_at == EngineType.OUTCOMES


def test_tracker_missing_engine_is_pending():
    tracker = PipelineStateTracker(strategy_id="s1")
    assert tracker.get_engine_state(EngineType.OUTCOMES) == PipelineState.PENDING


# --- Context ---


def test_context_initialization():
    context = PipelineContext()
    assert context.strategy_id is None
    assert context.run_id is None
    assert context.base_commit is None
    assert context.paper_only is True
    assert context.force_refresh is False
    assert context.run_all is False
    assert context.dry_run is False
    assert context.reports_dir == "docs/strategy_pipeline"


def test_context_artifacts():
    context = PipelineContext()
    context.set_artifact("key1", "val1")
    assert context.get_artifact("key1") == "val1"
    assert context.get_artifact("missing") is None


# --- Artifact locator ---


def test_locator_init():
    locator = ArtifactLocator(base_dir="/fake/dir")
    assert locator.base_dir == Path("/fake/dir")


@pytest.mark.parametrize(
    "method_name",
    [
        "locate_research_hypothesis",
        "locate_strategy_contract",
        "locate_truth_report",
        "locate_evidence_file",
        "locate_statistics_report",
        "locate_certification_report",
        "locate_live_drift_report",
    ],
)
def test_locator_missing_files(method_name, tmp_path):
    locator = ArtifactLocator(base_dir=str(tmp_path))
    assert getattr(locator, method_name)("s1") is None


def _create_locator_artifacts(tmp_path: Path) -> None:
    (tmp_path / "docs" / "research_registry").mkdir(parents=True)
    (tmp_path / "docs" / "research_registry" / "01_hypothesis_inventory.md").touch()

    (tmp_path / "strategies").mkdir(parents=True)
    (tmp_path / "strategies" / "s1.py").touch()

    (tmp_path / "docs" / "strategy_truth").mkdir(parents=True)
    (tmp_path / "docs" / "strategy_truth" / "s1_truth.md").touch()

    (tmp_path / "runtime" / "outcome_evidence").mkdir(parents=True)
    (tmp_path / "runtime" / "outcome_evidence" / "evidence_1.jsonl").touch()

    (tmp_path / "docs" / "statistical_validation").mkdir(parents=True)
    (tmp_path / "docs" / "statistical_validation" / "01_expectancy.md").touch()

    (tmp_path / "docs" / "strategy_certification").mkdir(parents=True)
    (tmp_path / "docs" / "strategy_certification" / "s1_cert.md").touch()

    (tmp_path / "docs" / "live_drift").mkdir(parents=True)
    (tmp_path / "docs" / "live_drift" / "06_certification_status.md").touch()


@pytest.mark.parametrize("engine_type", list(EngineType))
def test_engine_get_cached_path_exists(engine_type, tmp_path):
    _create_locator_artifacts(tmp_path)
    engine = StrategyPipelineEngine(locator=ArtifactLocator(base_dir=str(tmp_path)))
    assert engine._get_cached_path(engine_type, "s1") is not None


# --- Dependency resolver ---


def test_resolver_dependencies_are_ordered():
    resolver = DependencyResolver()
    assert resolver.dependencies[EngineType.RESEARCH] == []
    assert resolver.dependencies[EngineType.REGISTRY] == [EngineType.RESEARCH]
    assert resolver.dependencies[EngineType.TRUTH] == [EngineType.REGISTRY]
    assert resolver.dependencies[EngineType.OUTCOMES] == [EngineType.TRUTH]
    assert resolver.dependencies[EngineType.STATISTICS] == [EngineType.OUTCOMES]
    assert resolver.dependencies[EngineType.CERTIFICATION] == [
        EngineType.STATISTICS,
        EngineType.TRUTH,
    ]


def test_resolver_allows_research_without_dependencies():
    resolver = DependencyResolver()
    assert resolver.can_run(EngineType.RESEARCH, PipelineStateTracker("s1")) is True


def test_resolver_rejects_pending_or_failed_dependency():
    resolver = DependencyResolver()
    tracker = PipelineStateTracker("s1")
    assert resolver.can_run(EngineType.REGISTRY, tracker) is False

    tracker.update_engine_result(
        EngineType.RESEARCH,
        EngineResult(
            engine=EngineType.RESEARCH,
            state=PipelineState.FAILED,
            errors=["failed"],
        ),
    )
    assert resolver.can_run(EngineType.REGISTRY, tracker) is False


def test_resolver_accepts_successful_dependency():
    resolver = DependencyResolver()
    tracker = PipelineStateTracker("s1")
    tracker.update_engine_result(
        EngineType.RESEARCH,
        EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS),
    )
    assert resolver.can_run(EngineType.REGISTRY, tracker) is True


# --- Validator ---


def test_validator_legacy_no_argument_calls_remain_safe():
    PipelineValidator.validate_pre_run()
    PipelineValidator.validate_post_run()


def test_validator_rejects_non_paper_context():
    context = PipelineContext(strategy_id="s1", run_id="r1", paper_only=False)
    with pytest.raises(PipelineValidationError, match="paper-only"):
        PipelineValidator.validate_pre_run(context)


def test_validator_rejects_success_without_provenance():
    result = EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS)
    with pytest.raises(PipelineValidationError, match="run provenance"):
        PipelineValidator.validate_engine_result(result)


# --- Engine orchestration ---


def _verified_success(stage: EngineType, strategy_id: str, context: PipelineContext) -> EngineResult:
    return EngineResult(
        engine=stage,
        state=PipelineState.SUCCESS,
        run_id=context.run_id,
        strategy_id=strategy_id,
        verdict="VERIFIED_TEST_OUTPUT",
        exit_code=0,
        artifacts_generated=[f"{stage.value.lower()}.json"],
        output_hashes={f"{stage.value.lower()}.json": "test-sha256"},
    )


def test_engine_init():
    engine = StrategyPipelineEngine()
    assert engine.locator is not None
    assert engine.resolver is not None
    assert engine.validator is not None


def test_initial_pipeline_success_stops_before_drift():
    engine = StrategyPipelineEngine()
    context = PipelineContext(run_id="r1")

    with patch.object(engine, "_run_engine", side_effect=_verified_success):
        tracker = engine.run("s1", context)

    assert tracker.global_state == PipelineState.SUCCESS
    assert tracker.final_decision is not None
    assert tracker.final_decision.certification_status == "Paper Eligible Review"
    for stage in (
        EngineType.RESEARCH,
        EngineType.REGISTRY,
        EngineType.TRUTH,
        EngineType.OUTCOMES,
        EngineType.STATISTICS,
        EngineType.CERTIFICATION,
    ):
        assert tracker.get_engine_state(stage) == PipelineState.SUCCESS
    assert tracker.get_engine_state(EngineType.DRIFT) == PipelineState.PENDING


def test_explicit_drift_requires_and_runs_after_certification():
    engine = StrategyPipelineEngine()
    context = PipelineContext(run_id="r1")
    context.set_artifact("include_drift", True)
    context.set_artifact("certified_baseline", "baseline.json")
    context.set_artifact("paper_snapshot", "snapshot.json")

    with patch.object(engine, "_run_engine", side_effect=_verified_success):
        tracker = engine.run("s1", context)

    assert tracker.global_state == PipelineState.SUCCESS
    assert tracker.get_engine_state(EngineType.DRIFT) == PipelineState.SUCCESS


def test_engine_failure_aborts_downstream_stages():
    engine = StrategyPipelineEngine()
    context = PipelineContext(run_id="r1")

    def run_stage(stage, strategy_id, ctx):
        if stage == EngineType.REGISTRY:
            return EngineResult(
                engine=stage,
                state=PipelineState.FAILED,
                run_id=ctx.run_id,
                strategy_id=strategy_id,
                verdict="PROCESS_FAILED",
                exit_code=1,
                errors=["registry failure"],
            )
        return _verified_success(stage, strategy_id, ctx)

    with patch.object(engine, "_run_engine", side_effect=run_stage):
        tracker = engine.run("s1", context)

    assert tracker.global_state == PipelineState.FAILED
    assert tracker.get_engine_state(EngineType.RESEARCH) == PipelineState.SUCCESS
    assert tracker.get_engine_state(EngineType.REGISTRY) == PipelineState.FAILED
    assert tracker.get_engine_state(EngineType.TRUTH) == PipelineState.PENDING
    assert "registry failure" in tracker.final_decision.blockers


def test_invalid_success_is_converted_to_failure():
    engine = StrategyPipelineEngine()
    context = PipelineContext(run_id="r1")

    with patch.object(
        engine,
        "_run_engine",
        return_value=EngineResult(
            engine=EngineType.RESEARCH,
            state=PipelineState.SUCCESS,
        ),
    ):
        tracker = engine.run("s1", context)

    assert tracker.global_state == PipelineState.FAILED
    assert tracker.engine_results[EngineType.RESEARCH].verdict == "INVALID_ENGINE_RESULT"
    assert "run provenance" in tracker.engine_results[EngineType.RESEARCH].errors[0]


def test_reports_only_mode_blocks_without_verified_artifact():
    engine = StrategyPipelineEngine()
    tracker = engine.run(
        "s1",
        PipelineContext(run_id="r1", dry_run=True, force_refresh=True),
    )
    assert tracker.global_state == PipelineState.BLOCKED
    result = tracker.engine_results[EngineType.RESEARCH]
    assert result.state == PipelineState.BLOCKED
    assert "DRY_RUN_HAS_NO_VERIFIED_ARTIFACT" in result.blockers


def test_cache_without_manifest_is_not_reused(tmp_path):
    artifact = tmp_path / "research.md"
    artifact.write_text("research", encoding="utf-8")
    locator = ArtifactLocator(base_dir=str(tmp_path))
    locator.locate_research_hypothesis = MagicMock(return_value=artifact)
    engine = StrategyPipelineEngine(locator=locator)
    context = PipelineContext(strategy_id="s1", run_id="r1")

    assert engine._load_verified_cache(EngineType.RESEARCH, "s1", context) is None


def test_verified_cache_is_reused(tmp_path):
    artifact = tmp_path / "research.md"
    artifact.write_text("research", encoding="utf-8")
    digest = PipelineValidator.sha256(artifact)
    Path(f"{artifact}.manifest.json").write_text(
        json.dumps(
            {
                "strategy_id": "s1",
                "engine": "RESEARCH",
                "artifact_sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    locator = ArtifactLocator(base_dir=str(tmp_path))
    locator.locate_research_hypothesis = MagicMock(return_value=artifact)
    engine = StrategyPipelineEngine(locator=locator)
    context = PipelineContext(strategy_id="s1", run_id="r1")

    result = engine._load_verified_cache(EngineType.RESEARCH, "s1", context)
    assert result is not None
    assert result.cached is True
    assert result.output_hashes[str(artifact)] == digest


def test_tampered_cache_is_rejected(tmp_path):
    artifact = tmp_path / "research.md"
    artifact.write_text("original", encoding="utf-8")
    digest = PipelineValidator.sha256(artifact)
    Path(f"{artifact}.manifest.json").write_text(
        json.dumps(
            {
                "strategy_id": "s1",
                "engine": "RESEARCH",
                "artifact_sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    artifact.write_text("tampered", encoding="utf-8")
    locator = ArtifactLocator(base_dir=str(tmp_path))
    locator.locate_research_hypothesis = MagicMock(return_value=artifact)
    engine = StrategyPipelineEngine(locator=locator)
    context = PipelineContext(strategy_id="s1", run_id="r1")

    assert engine._load_verified_cache(EngineType.RESEARCH, "s1", context) is None


# --- Report generation ---


def test_report_generator_init():
    generator = ReportGenerator(output_dir="fake/dir")
    assert generator.output_dir == Path("fake/dir")


def test_report_generator_all(tmp_path):
    generator = ReportGenerator(output_dir=str(tmp_path))
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.final_decision = FinalDecision(
        strategy_id="s1",
        certification_status="Paper Eligible Review",
        reason="Verified artifacts",
        blockers=["B1"],
        limitations=["L1"],
    )

    generator.generate_all(tracker)

    strategy_dir = tmp_path / "s1"
    expected_files = [
        "01_pipeline_summary.md",
        "02_registry.md",
        "03_truth.md",
        "04_outcomes.md",
        "05_statistics.md",
        "06_certification.md",
        "07_live_drift.md",
        "08_blockers.md",
        "09_limitations.md",
        "10_final_decision.md",
    ]
    for filename in expected_files:
        assert (strategy_dir / filename).exists()

    assert "Paper Eligible Review" in (
        strategy_dir / "10_final_decision.md"
    ).read_text(encoding="utf-8")
    assert "B1" in (strategy_dir / "08_blockers.md").read_text(encoding="utf-8")


def test_report_generator_empty_decision(tmp_path):
    generator = ReportGenerator(output_dir=str(tmp_path))
    tracker = PipelineStateTracker(strategy_id="s1")
    generator.generate_all(tracker)

    strategy_dir = tmp_path / "s1"
    assert "Unknown. Pipeline did not complete." in (
        strategy_dir / "10_final_decision.md"
    ).read_text(encoding="utf-8")
    assert "None." in (strategy_dir / "08_blockers.md").read_text(encoding="utf-8")


def test_report_generator_pipeline_summary(tmp_path):
    generator = ReportGenerator(output_dir=str(tmp_path))
    tracker = PipelineStateTracker(
        strategy_id="test_strat",
        global_state=PipelineState.FAILED,
    )
    strategy_dir = tmp_path / "test_strat"
    strategy_dir.mkdir(parents=True)

    generator._write_pipeline_summary(strategy_dir, tracker)
    content = (strategy_dir / "01_pipeline_summary.md").read_text(encoding="utf-8")
    assert "test_strat" in content
    assert "FAILED" in content


@pytest.mark.parametrize(
    "file_name,method_name",
    [
        ("02_registry.md", "_write_registry"),
        ("03_truth.md", "_write_truth"),
        ("04_outcomes.md", "_write_outcomes"),
        ("05_statistics.md", "_write_statistics"),
        ("06_certification.md", "_write_certification"),
        ("07_live_drift.md", "_write_live_drift"),
    ],
)
def test_report_generator_simple_reports(tmp_path, file_name, method_name):
    generator = ReportGenerator(output_dir=str(tmp_path))
    strategy_dir = tmp_path / "s1"
    strategy_dir.mkdir(parents=True)

    getattr(generator, method_name)(strategy_dir)
    assert (strategy_dir / file_name).exists()
