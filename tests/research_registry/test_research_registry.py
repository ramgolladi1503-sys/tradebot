import pytest
from datetime import datetime
from core.research_registry import (
    ResearchStage, PromotionStatus, ResearchHypothesis, ResearchExperiment,
    ExperimentVersion, ExperimentResultReference, ParameterSet, MarketUniverse,
    ResearchEngine, HypothesisRegistry, ExperimentRegistry, ExperimentValidator,
    PromotionPolicy, ResearchEvidence, DependencyGraph, LineageTracker,
    ResearchRegistryValidator
)

def _mock_hypothesis(id="HYP-1"):
    return ResearchHypothesis(id, "T", "D", datetime.utcnow(), "auth")

def _mock_universe():
    return MarketUniverse("D", "M", "1D")

def _mock_result(expect="Sharpe > 1", actual="Tested", conclusion="Pass"):
    return ExperimentResultReference(expect, actual, ["limit"], conclusion)

def _mock_version(vid="V1", stage=ResearchStage.IDEA):
    return ExperimentVersion(vid, datetime.utcnow(), "auth", "branch", "commit", _mock_universe(), ParameterSet(), "reason", _mock_result(), stage)


# --- 1. Immutability Tests ---
def test_hypothesis_immutable():
    hyp = _mock_hypothesis()
    with pytest.raises(Exception):
        hyp.title = "New"

def test_experiment_immutable_attributes():
    exp = ResearchExperiment("EXP-1", "HYP-1")
    with pytest.raises(Exception):
        exp.experiment_id = "NEW"

def test_version_immutable():
    v = _mock_version()
    with pytest.raises(Exception):
        v.author = "NEW"

def test_universe_immutable():
    u = _mock_universe()
    with pytest.raises(Exception):
        u.market = "NEW"

def test_result_immutable():
    r = _mock_result()
    with pytest.raises(Exception):
        r.conclusion = "NEW"

def test_evidence_immutable():
    e = ResearchEvidence()
    with pytest.raises(Exception):
        e.strategy_registry_id = "NEW"

# --- 2. Duplicate IDs ---
def test_duplicate_hypothesis():
    hr = HypothesisRegistry()
    hr.register(_mock_hypothesis("H1"))
    with pytest.raises(ValueError, match="Duplicate"):
        hr.register(_mock_hypothesis("H1"))
        
def test_duplicate_experiment():
    er = ExperimentRegistry()
    er.register(ResearchExperiment("E1", "H1"))
    with pytest.raises(ValueError, match="Duplicate"):
        er.register(ResearchExperiment("E1", "H2"))

def test_duplicate_version_in_engine():
    en = ResearchEngine()
    en.register_hypothesis(_mock_hypothesis("H1"))
    en.register_experiment(ResearchExperiment("E1", "H1"))
    en.add_experiment_version("E1", _mock_version("V1"))
    with pytest.raises(ValueError, match="Duplicate"):
        en.add_experiment_version("E1", _mock_version("V1"))

# --- 3. Lineage and Dependency Tracking ---
def test_dependency_graph_empty():
    graph = DependencyGraph(HypothesisRegistry(), ExperimentRegistry()).build_full_lineage_graph()
    assert graph == {}
    
def test_dependency_graph_links():
    hr, er = HypothesisRegistry(), ExperimentRegistry()
    hr.register(_mock_hypothesis("H1"))
    er.register(ResearchExperiment("E1", "H1"))
    graph = DependencyGraph(hr, er).build_full_lineage_graph()
    assert "H1" in graph
    assert graph["H1"]["experiments"][0]["experiment_id"] == "E1"

def test_dependency_graph_evidence_links():
    hr, er = HypothesisRegistry(), ExperimentRegistry()
    hr.register(_mock_hypothesis("H1"))
    er.register(ResearchExperiment("E1", "H1", evidence=ResearchEvidence(strategy_registry_id="STR-1")))
    graph = DependencyGraph(hr, er).build_full_lineage_graph()
    assert graph["H1"]["experiments"][0]["evidence_links"]["strategy"] == "STR-1"

def test_lineage_tracker_history():
    exp = ResearchExperiment("E1", "H1")
    v1 = _mock_version("V1")
    v2 = _mock_version("V2")
    exp.versions.extend([v1, v2])
    hist = LineageTracker.get_version_history(exp)
    assert hist[0].version_id == "V1"
    assert hist[1].version_id == "V2"

def test_lineage_parameter_evolution():
    exp = ResearchExperiment("E1", "H1")
    v1 = ExperimentVersion("V1", datetime.utcnow(), "a", "b", "c", _mock_universe(), ParameterSet({"a": "1"}), "r", _mock_result(), ResearchStage.IDEA)
    exp.versions.append(v1)
    evo = LineageTracker.extract_parameter_evolution(exp)
    assert evo[0]["parameters"]["a"] == "1"

# --- 4. Promotion Recommendations ---
def test_promo_idea_missing_behavior():
    v = _mock_version(stage=ResearchStage.IDEA)
    v = ExperimentVersion("V1", datetime.utcnow(), "a", "b", "c", _mock_universe(), ParameterSet(), "r", _mock_result(expect=""), ResearchStage.IDEA)
    rec = PromotionPolicy.evaluate(v)
    assert rec.status == PromotionStatus.REQUIRES_MORE_DATA

def test_promo_idea_to_hyp():
    v = _mock_version(stage=ResearchStage.IDEA)
    rec = PromotionPolicy.evaluate(v)
    assert rec.status == PromotionStatus.READY_FOR_IMPLEMENTATION
    assert rec.target_stage == ResearchStage.HYPOTHESIS

def test_promo_hyp_to_design():
    v = _mock_version(stage=ResearchStage.HYPOTHESIS)
    rec = PromotionPolicy.evaluate(v)
    assert rec.target_stage == ResearchStage.DESIGN

def test_promo_design_to_implemented():
    v = _mock_version(stage=ResearchStage.DESIGN)
    rec = PromotionPolicy.evaluate(v)
    assert rec.target_stage == ResearchStage.IMPLEMENTED

def test_promo_implemented_to_tested():
    v = _mock_version(stage=ResearchStage.IMPLEMENTED)
    rec = PromotionPolicy.evaluate(v)
    assert rec.target_stage == ResearchStage.TESTED

def test_promo_tested_failed():
    v = ExperimentVersion("V1", datetime.utcnow(), "a", "b", "c", _mock_universe(), ParameterSet(), "r", _mock_result(conclusion="failed"), ResearchStage.TESTED)
    rec = PromotionPolicy.evaluate(v)
    assert rec.status == PromotionStatus.DO_NOT_PROMOTE
    assert rec.target_stage == ResearchStage.FAILED

def test_promo_tested_passed_requires_governed_evidence():
    v = _mock_version(stage=ResearchStage.TESTED)
    rec = PromotionPolicy.evaluate(v)
    assert rec.status == PromotionStatus.REQUIRES_MORE_DATA
    assert rec.target_stage is None
    assert any("cannot authorize PAPER_READY" in reason for reason in rec.reasons)

def test_promo_paper_to_shadow_requires_governed_authority_evidence():
    v = _mock_version(stage=ResearchStage.PAPER_READY)
    rec = PromotionPolicy.evaluate(v)
    assert rec.status == PromotionStatus.REQUIRES_MORE_DATA
    assert rec.target_stage is None
    assert any("cannot authorize SHADOW_READY" in reason for reason in rec.reasons)

def test_promo_shadow_to_strategy_requires_governed_authority_evidence():
    v = _mock_version(stage=ResearchStage.SHADOW_READY)
    rec = PromotionPolicy.evaluate(v)
    assert rec.status == PromotionStatus.REQUIRES_MORE_DATA
    assert rec.target_stage is None
    assert any("cannot authorize STRATEGY_REGISTRY" in reason for reason in rec.reasons)

def test_promo_failed_stays_failed():
    v = _mock_version(stage=ResearchStage.FAILED)
    rec = PromotionPolicy.evaluate(v)
    assert rec.status == PromotionStatus.DO_NOT_PROMOTE

def test_promo_registry_keeps_research():
    v = _mock_version(stage=ResearchStage.STRATEGY_REGISTRY)
    rec = PromotionPolicy.evaluate(v)
    assert rec.status == PromotionStatus.KEEP_RESEARCH

# --- 5. Validations and Missing Fields ---
def test_val_missing_author():
    v = ExperimentVersion("V1", datetime.utcnow(), "", "b", "c", _mock_universe(), ParameterSet(), "r", _mock_result(), ResearchStage.IDEA)
    errs = ExperimentValidator.validate_version(v)
    assert "author" in errs[0]

def test_val_missing_branch():
    v = ExperimentVersion("V1", datetime.utcnow(), "a", "", "c", _mock_universe(), ParameterSet(), "r", _mock_result(), ResearchStage.IDEA)
    errs = ExperimentValidator.validate_version(v)
    assert "branch" in errs[0]

def test_val_missing_commit():
    v = ExperimentVersion("V1", datetime.utcnow(), "a", "b", "", _mock_universe(), ParameterSet(), "r", _mock_result(), ResearchStage.IDEA)
    errs = ExperimentValidator.validate_version(v)
    assert "commit" in errs[0]

def test_val_missing_expected():
    v = ExperimentVersion("V1", datetime.utcnow(), "a", "b", "c", _mock_universe(), ParameterSet(), "r", _mock_result(expect=""), ResearchStage.IDEA)
    errs = ExperimentValidator.validate_version(v)
    assert "expected" in errs[0]

# --- 6. Orphan and Lineage Errors ---
def test_orphan_experiment_fails_validation():
    er, hr = ExperimentRegistry(), HypothesisRegistry()
    er.register(ResearchExperiment("E1", "H-MISSING"))
    with pytest.raises(ValueError, match="Orphan"):
        ResearchRegistryValidator.assert_no_orphans(er, hr)

def test_broken_lineage_invalid_transition():
    er = ExperimentRegistry()
    exp = ResearchExperiment("E1", "H1")
    v1 = _mock_version("V1", ResearchStage.IDEA)
    v2 = _mock_version("V2", ResearchStage.TESTED) # INVALID SKIP
    exp.versions.extend([v1, v2])
    er.register(exp)
    with pytest.raises(ValueError, match="invalid version V2"):
        ResearchRegistryValidator.assert_versions_valid(er)

def test_valid_lineage_transition():
    er = ExperimentRegistry()
    exp = ResearchExperiment("E1", "H1")
    v1 = _mock_version("V1", ResearchStage.IDEA)
    v2 = _mock_version("V2", ResearchStage.HYPOTHESIS)
    exp.versions.extend([v1, v2])
    er.register(exp)
    ResearchRegistryValidator.assert_versions_valid(er) # Should not raise

def test_valid_failed_revival():
    er = ExperimentRegistry()
    exp = ResearchExperiment("E1", "H1")
    v1 = _mock_version("V1", ResearchStage.FAILED)
    v2 = _mock_version("V2", ResearchStage.DESIGN)
    exp.versions.extend([v1, v2])
    er.register(exp)
    ResearchRegistryValidator.assert_versions_valid(er)

# --- 7. Engine Integration ---
def test_engine_missing_exp():
    en = ResearchEngine()
    with pytest.raises(ValueError, match="not found"):
        en.add_experiment_version("MISSING", _mock_version())

def test_engine_evaluate_empty():
    en = ResearchEngine()
    en.register_experiment(ResearchExperiment("E1", "H1"))
    assert en.evaluate_experiment("E1", "auth") is None

def test_engine_evaluate_success():
    en = ResearchEngine()
    en.register_experiment(ResearchExperiment("E1", "H1"))
    en.add_experiment_version("E1", _mock_version("V1"))
    dec = en.evaluate_experiment("E1", "auth")
    assert dec.recommendation.status == PromotionStatus.READY_FOR_IMPLEMENTATION

def test_engine_report_generation():
    en = ResearchEngine()
    en.register_hypothesis(_mock_hypothesis("H1"))
    en.register_experiment(ResearchExperiment("E1", "H1"))
    en.add_experiment_version("E1", _mock_version("V1"))
    rep = en.generate_report_model()
    assert rep.hypotheses[0].hypothesis_id == "H1"
    assert rep.experiments[0].experiment_id == "E1"

def test_engine_report_validates_orphans():
    en = ResearchEngine()
    en.register_experiment(ResearchExperiment("E1", "H1")) # Orphan!
    with pytest.raises(ValueError, match="Orphan"):
        en.generate_report_model()

def test_registry_lists():
    hr = HypothesisRegistry()
    hr.register(_mock_hypothesis("H1"))
    hr.register(_mock_hypothesis("H2"))
    assert len(hr.list_all()) == 2

    er = ExperimentRegistry()
    er.register(ResearchExperiment("E1", "H1"))
    er.register(ResearchExperiment("E2", "H1"))
    assert len(er.list_all()) == 2

def test_registry_gets():
    hr = HypothesisRegistry()
    hr.register(_mock_hypothesis("H1"))
    assert hr.get("H1").title == "T"
    assert hr.get("MISSING") is None

def test_execution_influence_is_false():
    assert ResearchRegistryValidator.assert_no_execution_influence() is True


def test_evidence_linker():
    from core.research_registry.evidence_linker import EvidenceLinker
    er = ExperimentRegistry()
    er.register(ResearchExperiment("E1", "H1", evidence=ResearchEvidence(strategy_registry_id="STR-1")))
    linker = EvidenceLinker(er)
    ev = linker.get_evidence("E1")
    assert ev.strategy_registry_id == "STR-1"
    assert linker.get_evidence("MISSING") is None
