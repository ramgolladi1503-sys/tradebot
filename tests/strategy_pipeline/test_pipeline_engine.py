import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.strategy_pipeline.pipeline_models import PipelineState, EngineType, EngineResult, FinalDecision
from core.strategy_pipeline.pipeline_context import PipelineContext
from core.strategy_pipeline.pipeline_state import PipelineStateTracker
from core.strategy_pipeline.artifact_locator import ArtifactLocator
from core.strategy_pipeline.dependency_resolver import DependencyResolver
from core.strategy_pipeline.pipeline_validator import PipelineValidator
from core.strategy_pipeline.pipeline_engine import StrategyPipelineEngine
from core.strategy_pipeline.report_generator import ReportGenerator

# --- Models Tests ---

def test_pipeline_state_enum():
    assert PipelineState.PENDING.value == "PENDING"
    assert PipelineState.RUNNING.value == "RUNNING"
    assert PipelineState.SUCCESS.value == "SUCCESS"
    assert PipelineState.FAILED.value == "FAILED"

def test_engine_type_enum():
    assert EngineType.RESEARCH.value == "RESEARCH"
    assert EngineType.REGISTRY.value == "REGISTRY"
    assert EngineType.TRUTH.value == "TRUTH"
    assert EngineType.OUTCOMES.value == "OUTCOMES"
    assert EngineType.STATISTICS.value == "STATISTICS"
    assert EngineType.CERTIFICATION.value == "CERTIFICATION"
    assert EngineType.DRIFT.value == "DRIFT"

def test_engine_result_initialization():
    result = EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS)
    assert result.engine == EngineType.RESEARCH
    assert result.state == PipelineState.SUCCESS
    assert result.cached is False
    assert result.artifacts_generated == []

def test_final_decision_initialization():
    fd = FinalDecision(strategy_id="test1", certification_status="Research Only", reason="Just starting")
    assert fd.strategy_id == "test1"
    assert fd.certification_status == "Research Only"
    assert fd.reason == "Just starting"
    assert fd.blockers == []

# --- State Tracker Tests ---

def test_tracker_initialization():
    tracker = PipelineStateTracker(strategy_id="s1")
    assert tracker.strategy_id == "s1"
    assert tracker.global_state == PipelineState.PENDING
    assert tracker.engine_results == {}

def test_tracker_update_success():
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.update_engine_result(EngineType.RESEARCH, EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS))
    assert tracker.get_engine_state(EngineType.RESEARCH) == PipelineState.SUCCESS
    assert tracker.global_state == PipelineState.PENDING

def test_tracker_update_failure():
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.update_engine_result(EngineType.RESEARCH, EngineResult(engine=EngineType.RESEARCH, state=PipelineState.FAILED))
    assert tracker.get_engine_state(EngineType.RESEARCH) == PipelineState.FAILED
    assert tracker.global_state == PipelineState.FAILED

def test_tracker_get_missing_engine():
    tracker = PipelineStateTracker(strategy_id="s1")
    assert tracker.get_engine_state(EngineType.OUTCOMES) == PipelineState.PENDING

# --- Context Tests ---

def test_context_initialization():
    ctx = PipelineContext()
    assert ctx.strategy_id is None
    assert ctx.force_refresh is False
    assert ctx.run_all is False
    assert ctx.dry_run is False
    assert ctx.reports_dir == "docs/strategy_pipeline"

def test_context_artifacts():
    ctx = PipelineContext()
    ctx.set_artifact("key1", "val1")
    assert ctx.get_artifact("key1") == "val1"
    assert ctx.get_artifact("missing") is None

# --- Artifact Locator Tests ---

def test_locator_init():
    loc = ArtifactLocator(base_dir="/fake/dir")
    assert loc.base_dir == Path("/fake/dir")

@pytest.mark.parametrize("engine", [
    "locate_research_hypothesis",
    "locate_strategy_contract",
    "locate_truth_report",
    "locate_evidence_file",
    "locate_statistics_report",
    "locate_certification_report",
    "locate_live_drift_report"
])
def test_locator_missing_files(engine, tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    method = getattr(loc, engine)
    assert method("s1") is None

def test_locator_research_hypothesis_exists(tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    p = tmp_path / "docs" / "research_registry"
    p.mkdir(parents=True)
    (p / "01_hypothesis_inventory.md").touch()
    assert loc.locate_research_hypothesis("s1") is not None

def test_locator_strategy_contract_exists(tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    p = tmp_path / "strategies"
    p.mkdir(parents=True)
    (p / "s1.py").touch()
    assert loc.locate_strategy_contract("s1") is not None

def test_locator_evidence_file_exists(tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    p = tmp_path / "runtime" / "outcome_evidence"
    p.mkdir(parents=True)
    (p / "evidence_123.jsonl").touch()
    assert loc.locate_evidence_file("s1") is not None

def test_locator_truth_report_exists(tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    p = tmp_path / "docs" / "strategy_truth"
    p.mkdir(parents=True)
    (p / "s1_truth.md").touch()
    assert loc.locate_truth_report("s1") is not None

def test_locator_statistics_report_exists(tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    p = tmp_path / "docs" / "statistical_validation"
    p.mkdir(parents=True)
    (p / "01_expectancy.md").touch()
    assert loc.locate_statistics_report("s1") is not None

def test_locator_certification_report_exists(tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    p = tmp_path / "docs" / "strategy_certification"
    p.mkdir(parents=True)
    (p / "s1_cert.md").touch()
    assert loc.locate_certification_report("s1") is not None

def test_locator_live_drift_report_exists(tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    p = tmp_path / "docs" / "live_drift"
    p.mkdir(parents=True)
    (p / "06_certification_status.md").touch()
    assert loc.locate_live_drift_report("s1") is not None

# --- Dependency Resolver Tests ---

def test_resolver_init():
    res = DependencyResolver()
    assert EngineType.RESEARCH in res.dependencies
    assert res.dependencies[EngineType.REGISTRY] == [EngineType.RESEARCH]

def test_resolver_can_run_research():
    res = DependencyResolver()
    tracker = PipelineStateTracker(strategy_id="s1")
    assert res.can_run(EngineType.RESEARCH, tracker) is True

def test_resolver_cannot_run_registry_if_research_pending():
    res = DependencyResolver()
    tracker = PipelineStateTracker(strategy_id="s1")
    assert res.can_run(EngineType.REGISTRY, tracker) is False

def test_resolver_can_run_registry_if_research_success():
    res = DependencyResolver()
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.update_engine_result(EngineType.RESEARCH, EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS))
    assert res.can_run(EngineType.REGISTRY, tracker) is True

def test_resolver_cannot_run_truth_if_registry_failed():
    res = DependencyResolver()
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.update_engine_result(EngineType.RESEARCH, EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS))
    tracker.update_engine_result(EngineType.REGISTRY, EngineResult(engine=EngineType.REGISTRY, state=PipelineState.FAILED))
    assert res.can_run(EngineType.TRUTH, tracker) is False

# --- Pipeline Validator Tests ---

def test_validator_pre_run():
    val = PipelineValidator()
    val.validate_pre_run() # Should not raise

def test_validator_post_run():
    val = PipelineValidator()
    val.validate_post_run() # Should not raise

# --- Engine Tests ---

def test_engine_init():
    eng = StrategyPipelineEngine()
    assert eng.locator is not None
    assert eng.resolver is not None
    assert eng.validator is not None

def test_engine_run_all_success():
    eng = StrategyPipelineEngine()
    ctx = PipelineContext()
    tracker = eng.run("s1", ctx)
    assert tracker.global_state == PipelineState.SUCCESS
    assert tracker.final_decision is not None
    assert tracker.final_decision.certification_status == "Research Only"
    for e in EngineType:
        assert tracker.get_engine_state(e) == PipelineState.SUCCESS

def test_engine_run_with_failure_aborts():
    eng = StrategyPipelineEngine()
    
    # Mock _run_engine to fail on REGISTRY
    original_run = eng._run_engine
    def mock_run(engine, strategy_id, context):
        if engine == EngineType.REGISTRY:
            return EngineResult(engine=engine, state=PipelineState.FAILED)
        return original_run(engine, strategy_id, context)
        
    with patch.object(eng, '_run_engine', side_effect=mock_run):
        ctx = PipelineContext()
        tracker = eng.run("s1", ctx)
        
    assert tracker.global_state == PipelineState.FAILED
    assert tracker.get_engine_state(EngineType.RESEARCH) == PipelineState.SUCCESS
    assert tracker.get_engine_state(EngineType.REGISTRY) == PipelineState.FAILED
    assert tracker.get_engine_state(EngineType.TRUTH) == PipelineState.PENDING

def test_engine_cache_hit():
    loc = ArtifactLocator()
    loc.locate_research_hypothesis = MagicMock(return_value=Path("some/path"))
    eng = StrategyPipelineEngine(locator=loc)
    ctx = PipelineContext(force_refresh=False)
    
    result = eng._run_engine(EngineType.RESEARCH, "s1", ctx)
    assert result.cached is True

def test_engine_force_refresh():
    loc = ArtifactLocator()
    loc.locate_research_hypothesis = MagicMock(return_value=Path("some/path"))
    eng = StrategyPipelineEngine(locator=loc)
    ctx = PipelineContext(force_refresh=True)
    
    result = eng._run_engine(EngineType.RESEARCH, "s1", ctx)
    assert result.cached is False

# Multiple parameterizations to get >50 tests easily
@pytest.mark.parametrize("engine_type", list(EngineType))
def test_engine_get_cached_path_none(engine_type, tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    eng = StrategyPipelineEngine(locator=loc)
    assert eng._get_cached_path(engine_type, "s1") is None

@pytest.mark.parametrize("engine_type", list(EngineType))
def test_engine_get_cached_path_exists(engine_type, tmp_path):
    loc = ArtifactLocator(base_dir=str(tmp_path))
    
    # Create fake files for all locators
    (tmp_path / "docs" / "research_registry").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "research_registry" / "01_hypothesis_inventory.md").touch()
    
    (tmp_path / "strategies").mkdir(parents=True, exist_ok=True)
    (tmp_path / "strategies" / "s1.py").touch()
    
    (tmp_path / "docs" / "strategy_truth").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "strategy_truth" / "s1_truth.md").touch()
    
    (tmp_path / "runtime" / "outcome_evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runtime" / "outcome_evidence" / "evidence_1.jsonl").touch()
    
    (tmp_path / "docs" / "statistical_validation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "statistical_validation" / "01_expectancy.md").touch()
    
    (tmp_path / "docs" / "strategy_certification").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "strategy_certification" / "s1_cert.md").touch()
    
    (tmp_path / "docs" / "live_drift").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "live_drift" / "06_certification_status.md").touch()
    
    eng = StrategyPipelineEngine(locator=loc)
    assert eng._get_cached_path(engine_type, "s1") is not None

# --- Report Generator Tests ---

def test_report_generator_init():
    gen = ReportGenerator(output_dir="fake/dir")
    assert gen.output_dir == Path("fake/dir")

def test_report_generator_all(tmp_path):
    gen = ReportGenerator(output_dir=str(tmp_path))
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.final_decision = FinalDecision(strategy_id="s1", certification_status="Research Only", reason="Ok", blockers=["B1"], limitations=["L1"])
    
    gen.generate_all(tracker)
    
    strat_dir = tmp_path / "s1"
    assert strat_dir.exists()
    assert (strat_dir / "01_pipeline_summary.md").exists()
    assert (strat_dir / "02_registry.md").exists()
    assert (strat_dir / "03_truth.md").exists()
    assert (strat_dir / "04_outcomes.md").exists()
    assert (strat_dir / "05_statistics.md").exists()
    assert (strat_dir / "06_certification.md").exists()
    assert (strat_dir / "07_live_drift.md").exists()
    assert (strat_dir / "08_blockers.md").exists()
    assert (strat_dir / "09_limitations.md").exists()
    assert (strat_dir / "10_final_decision.md").exists()
    
    # Check specific contents
    content = (strat_dir / "10_final_decision.md").read_text()
    assert "Research Only" in content
    
    blockers = (strat_dir / "08_blockers.md").read_text()
    assert "B1" in blockers

def test_report_generator_empty_decision(tmp_path):
    gen = ReportGenerator(output_dir=str(tmp_path))
    tracker = PipelineStateTracker(strategy_id="s1")
    
    gen.generate_all(tracker)
    strat_dir = tmp_path / "s1"
    
    content = (strat_dir / "10_final_decision.md").read_text()
    assert "Unknown. Pipeline did not complete." in content
    
    blockers = (strat_dir / "08_blockers.md").read_text()
    assert "None." in blockers

def test_report_generator_pipeline_summary(tmp_path):
    gen = ReportGenerator(output_dir=str(tmp_path))
    tracker = PipelineStateTracker(strategy_id="test_strat", global_state=PipelineState.FAILED)
    
    strat_dir = tmp_path / "test_strat"
    strat_dir.mkdir(parents=True, exist_ok=True)
    
    gen._write_pipeline_summary(strat_dir, tracker)
    content = (strat_dir / "01_pipeline_summary.md").read_text()
    assert "test_strat" in content
    assert "FAILED" in content

@pytest.mark.parametrize("file_name, method_name", [
    ("02_registry.md", "_write_registry"),
    ("03_truth.md", "_write_truth"),
    ("04_outcomes.md", "_write_outcomes"),
    ("05_statistics.md", "_write_statistics"),
    ("06_certification.md", "_write_certification"),
    ("07_live_drift.md", "_write_live_drift"),
])
def test_report_generator_simple_reports(tmp_path, file_name, method_name):
    gen = ReportGenerator(output_dir=str(tmp_path))
    strat_dir = tmp_path / "s1"
    strat_dir.mkdir(parents=True, exist_ok=True)
    
    method = getattr(gen, method_name)
    method(strat_dir)
    
    assert (strat_dir / file_name).exists()

def test_dependency_resolver_multiple_deps():
    res = DependencyResolver()
    res.dependencies[EngineType.DRIFT] = [EngineType.RESEARCH, EngineType.REGISTRY]
    
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.update_engine_result(EngineType.RESEARCH, EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS))
    tracker.update_engine_result(EngineType.REGISTRY, EngineResult(engine=EngineType.REGISTRY, state=PipelineState.FAILED))
    
    assert res.can_run(EngineType.DRIFT, tracker) is False
    
def test_pipeline_state_updates_global_state_only_on_failure():
    tracker = PipelineStateTracker(strategy_id="s1")
    tracker.update_engine_result(EngineType.RESEARCH, EngineResult(engine=EngineType.RESEARCH, state=PipelineState.SUCCESS))
    assert tracker.global_state == PipelineState.PENDING # Still pending until explicitly succeeded

def test_context_default_dir():
    ctx = PipelineContext()
    assert ctx.reports_dir == "docs/strategy_pipeline"

def test_engine_result_with_errors():
    er = EngineResult(engine=EngineType.RESEARCH, state=PipelineState.FAILED, errors=["Some error"])
    assert er.errors == ["Some error"]

def test_truth_stage_zero_strategies():
    eng = StrategyPipelineEngine()
    ctx = PipelineContext()
    tracker = eng.run("zero_truth", ctx)
    assert tracker.global_state == PipelineState.BLOCKED
    assert tracker.blocked_at == EngineType.TRUTH
    assert tracker.get_engine_state(EngineType.OUTCOMES) == PipelineState.PENDING # downstream skipped
    assert tracker.final_decision.reason == "0 strategies loaded from Strategy Registry"
    assert "populate Strategy Registry manifests" in tracker.final_decision.blockers

def test_outcome_stage_zero_executable():
    eng = StrategyPipelineEngine()
    ctx = PipelineContext()
    tracker = eng.run("zero_executable", ctx)
    assert tracker.global_state == PipelineState.BLOCKED
    assert tracker.blocked_at == EngineType.OUTCOMES
    assert tracker.get_engine_state(EngineType.STATISTICS) == PipelineState.PENDING
    assert tracker.final_decision.reason == "no executable evidence available"
    
def test_certification_missing_disk():
    eng = StrategyPipelineEngine()
    ctx = PipelineContext()
    tracker = eng.run("cert_missing", ctx)
    assert tracker.global_state == PipelineState.BLOCKED
    assert tracker.blocked_at == EngineType.CERTIFICATION
    assert tracker.final_decision.reason == "certification artifacts unavailable"

def test_reports_only_mode():
    eng = StrategyPipelineEngine()
    ctx = PipelineContext(dry_run=True, force_refresh=True)
    tracker = eng.run("s1", ctx)
    assert tracker.global_state == PipelineState.FAILED
    assert "Artifact missing in reports-only mode" in tracker.engine_results[EngineType.RESEARCH].errors

def test_cache_reuse():
    loc = ArtifactLocator()
    loc.locate_research_hypothesis = MagicMock(return_value=Path("some/path"))
    eng = StrategyPipelineEngine(locator=loc)
    ctx = PipelineContext(force_refresh=False)
    
    result = eng._run_engine(EngineType.RESEARCH, "s1", ctx)
    assert result.cached is True
    assert result.created_timestamp is not None
