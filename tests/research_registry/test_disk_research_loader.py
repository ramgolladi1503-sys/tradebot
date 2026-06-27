import json
import pytest
from pathlib import Path

from core.research_registry.hypothesis_registry import HypothesisRegistry
from core.research_registry.experiment_registry import ExperimentRegistry
from core.research_registry.experiment_loader import DiskResearchLoader, ResearchLoaderError


@pytest.fixture
def empty_registries() -> tuple[HypothesisRegistry, ExperimentRegistry]:
    return HypothesisRegistry(), ExperimentRegistry()


@pytest.fixture
def temp_research_dir(tmp_path: Path) -> Path:
    base = tmp_path / "research"
    (base / "hypotheses").mkdir(parents=True)
    (base / "experiments").mkdir(parents=True)
    return base


def test_loader_empty_directory(temp_research_dir: Path, empty_registries: tuple[HypothesisRegistry, ExperimentRegistry]):
    h_reg, e_reg = empty_registries
    loader = DiskResearchLoader(h_reg, e_reg, base_dir=temp_research_dir)
    loader.load_all()
    assert len(h_reg.list_all()) == 0
    assert len(e_reg.list_all()) == 0


def test_loader_valid_hypothesis_and_experiment(temp_research_dir: Path, empty_registries: tuple[HypothesisRegistry, ExperimentRegistry]):
    h_reg, e_reg = empty_registries
    
    hyp_data = {
        "hypothesis_id": "HYP-TEST",
        "title": "Test Title",
        "description": "Test Desc",
        "created_timestamp": "2026-06-27T00:00:00Z",
        "author": "tester"
    }
    with open(temp_research_dir / "hypotheses" / "hyp1.json", "w") as f:
        json.dump(hyp_data, f)
        
    exp_data = {
        "experiment_id": "EXP-TEST",
        "parent_hypothesis_id": "HYP-TEST",
        "versions": [{
            "version_id": "V1",
            "created_timestamp": "2026-06-27T00:01:00Z",
            "author": "tester",
            "branch": "main",
            "commit": "abc1234",
            "market_universe": {
                "dataset": "us_eq",
                "market": "SPY",
                "timeframe": "1D"
            },
            "parameters": {
                "parameters": {"param1": "value1"}
            },
            "reason": "Initial",
            "result": {
                "expected_behavior": "Good",
                "actual_behavior": "Good",
                "limitations": [],
                "conclusion": "Good"
            },
            "stage": "TESTED"
        }]
    }
    with open(temp_research_dir / "experiments" / "exp1.json", "w") as f:
        json.dump(exp_data, f)
        
    loader = DiskResearchLoader(h_reg, e_reg, base_dir=temp_research_dir)
    loader.load_all()
    
    assert len(h_reg.list_all()) == 1
    assert h_reg.get("HYP-TEST") is not None
    assert len(e_reg.list_all()) == 1
    assert e_reg.get("EXP-TEST") is not None
    
    exp = e_reg.get("EXP-TEST")
    assert exp is not None
    assert len(exp.versions) == 1
    assert exp.versions[0].version_id == "V1"


def test_loader_duplicate_hypothesis_id(temp_research_dir: Path, empty_registries: tuple[HypothesisRegistry, ExperimentRegistry]):
    h_reg, e_reg = empty_registries
    
    hyp_data = {
        "hypothesis_id": "HYP-DUP",
        "title": "Test", "description": "Test",
        "created_timestamp": "2026-06-27T00:00:00Z", "author": "tester"
    }
    with open(temp_research_dir / "hypotheses" / "hyp1.json", "w") as f:
        json.dump(hyp_data, f)
    with open(temp_research_dir / "hypotheses" / "hyp2.json", "w") as f:
        json.dump(hyp_data, f)
        
    loader = DiskResearchLoader(h_reg, e_reg, base_dir=temp_research_dir)
    with pytest.raises(ResearchLoaderError, match="Duplicate hypothesis_id: HYP-DUP"):
        loader.load_all()


def test_loader_malformed_json(temp_research_dir: Path, empty_registries: tuple[HypothesisRegistry, ExperimentRegistry]):
    h_reg, e_reg = empty_registries
    
    with open(temp_research_dir / "hypotheses" / "bad.json", "w") as f:
        f.write("{ bad json ")
        
    loader = DiskResearchLoader(h_reg, e_reg, base_dir=temp_research_dir)
    with pytest.raises(ResearchLoaderError, match="Malformed JSON"):
        loader.load_all()


def test_loader_missing_required_field(temp_research_dir: Path, empty_registries: tuple[HypothesisRegistry, ExperimentRegistry]):
    h_reg, e_reg = empty_registries
    
    hyp_data = {
        "hypothesis_id": "HYP-TEST",
        "title": "Test Title"
        # missing description, created_timestamp, author
    }
    with open(temp_research_dir / "hypotheses" / "hyp1.json", "w") as f:
        json.dump(hyp_data, f)
        
    loader = DiskResearchLoader(h_reg, e_reg, base_dir=temp_research_dir)
    with pytest.raises(ResearchLoaderError, match="Missing 'description'"):
        loader.load_all()


def test_loader_duplicate_version_id(temp_research_dir: Path, empty_registries: tuple[HypothesisRegistry, ExperimentRegistry]):
    h_reg, e_reg = empty_registries
    
    exp_data = {
        "experiment_id": "EXP-TEST",
        "parent_hypothesis_id": "HYP-TEST",
        "versions": [
            {
                "version_id": "V1", "created_timestamp": "2026-06-27T00:01:00Z", "author": "tester",
                "branch": "main", "commit": "abc1234", "market_universe": {"dataset": "a", "market": "b", "timeframe": "c"},
                "parameters": {"parameters": {}}, "reason": "a", "result": {"expected_behavior": "a", "actual_behavior": "a", "limitations": [], "conclusion": "a"},
                "stage": "TESTED"
            },
            {
                "version_id": "V1", "created_timestamp": "2026-06-27T00:02:00Z", "author": "tester",
                "branch": "main", "commit": "abc1234", "market_universe": {"dataset": "a", "market": "b", "timeframe": "c"},
                "parameters": {"parameters": {}}, "reason": "a", "result": {"expected_behavior": "a", "actual_behavior": "a", "limitations": [], "conclusion": "a"},
                "stage": "TESTED"
            }
        ]
    }
    with open(temp_research_dir / "experiments" / "exp1.json", "w") as f:
        json.dump(exp_data, f)
        
    loader = DiskResearchLoader(h_reg, e_reg, base_dir=temp_research_dir)
    with pytest.raises(ResearchLoaderError, match="Duplicate version_id 'V1'"):
        loader.load_all()


def test_loader_invalid_stage(temp_research_dir: Path, empty_registries: tuple[HypothesisRegistry, ExperimentRegistry]):
    h_reg, e_reg = empty_registries
    
    exp_data = {
        "experiment_id": "EXP-TEST",
        "parent_hypothesis_id": "HYP-TEST",
        "versions": [{
            "version_id": "V1", "created_timestamp": "2026-06-27T00:01:00Z", "author": "tester",
            "branch": "main", "commit": "abc1234", "market_universe": {"dataset": "a", "market": "b", "timeframe": "c"},
            "parameters": {"parameters": {}}, "reason": "a", "result": {"expected_behavior": "a", "actual_behavior": "a", "limitations": [], "conclusion": "a"},
            "stage": "INVALID_STAGE_HERE"
        }]
    }
    with open(temp_research_dir / "experiments" / "exp1.json", "w") as f:
        json.dump(exp_data, f)
        
    loader = DiskResearchLoader(h_reg, e_reg, base_dir=temp_research_dir)
    with pytest.raises(ResearchLoaderError, match="Invalid stage 'INVALID_STAGE_HERE'"):
        loader.load_all()
