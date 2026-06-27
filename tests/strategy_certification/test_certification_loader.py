import pytest
import json
from pathlib import Path

from core.strategy_registry.strategy_manifest import StrategyManifest
from core.strategy_registry.strategy_contract import StrategyContract
from core.strategy_truth.truth_models import StrategyTruthReport
from core.outcome_evidence.evidence_models import OutcomeEvidenceRunSummary
from core.statistical_validation.statistics_models import StatisticalValidationReport
from core.strategy_certification.certification_errors import CertificationInputMissingError, CertificationValidationError
from core.strategy_certification.certification_loader import DiskCertificationLoader
from datetime import date

@pytest.fixture
def test_dir(tmp_path):
    # Setup standard folder structure
    (tmp_path / "strategies").mkdir()
    (tmp_path / "docs" / "strategy_truth").mkdir(parents=True)
    (tmp_path / "docs" / "statistical_validation").mkdir(parents=True)
    (tmp_path / "runtime" / "outcome_evidence").mkdir(parents=True)
    return tmp_path

def create_mock_strategy_file(base_dir: Path, strategy_id: str):
    code = f"""
from datetime import date
from core.strategy_registry.strategy_contract import StrategyContract

contract = StrategyContract(
    strategy_id="{strategy_id}",
    strategy_name="Test Strat",
    version="1.0",
    owner="tester",
    created_date=date.today(),
    description="Test",
    market_hypothesis="Test",
    primary_market="NSE",
    supported_indices=[],
    supported_option_types=[],
    entry_rules_summary="E",
    exit_rules_summary="X",
    stop_logic_summary="S",
    target_logic_summary="T",
    time_stop="15:15",
    required_indicators=["PRICE"],
    required_market_data=["PRICE"],
    required_option_data=[],
    required_sessions=[],
    required_liquidity="HIGH",
    allowed_regimes=[],
    forbidden_regimes=[],
    required_confirmations=[],
    known_limitations=[],
    known_assumptions=[]
)
"""
    (base_dir / "strategies" / f"{strategy_id}.py").write_text(code)

def create_mock_truth_file(base_dir: Path, strategy_id: str, content: dict):
    (base_dir / "docs" / "strategy_truth" / f"{strategy_id}_truth.json").write_text(json.dumps(content))

def create_mock_evidence_file(base_dir: Path, strategy_id: str, content: dict):
    (base_dir / "runtime" / "outcome_evidence" / f"{strategy_id}_evidence_summary.json").write_text(json.dumps(content))

def create_mock_stats_file(base_dir: Path, strategy_id: str, content: dict):
    (base_dir / "docs" / "statistical_validation" / f"{strategy_id}_statistics.json").write_text(json.dumps(content))

def _get_valid_manifest(sid: str):
    return StrategyManifest(
        contract=StrategyContract(
            strategy_id=sid, strategy_name="T", version="1", owner="T", created_date=date.today(), 
            description="T", market_hypothesis="T", primary_market="T", supported_indices=[], 
            supported_option_types=[], entry_rules_summary="E", exit_rules_summary="X", 
            stop_logic_summary="S", target_logic_summary="T", time_stop="15:15", 
            required_indicators=["PRICE"], required_market_data=["PRICE"], required_option_data=[], 
            required_sessions=[], required_liquidity="HIGH", allowed_regimes=[], forbidden_regimes=[], 
            required_confirmations=[], known_limitations=[], known_assumptions=[]
        ), 
        file_path="t", module_path="t"
    )

def test_loader_all_artifacts_present(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    create_mock_truth_file(test_dir, strategy_id, {"strategy_id": strategy_id, "is_registry_complete": True, "verdict": "IMPLEMENTATION_VERIFIED"})
    create_mock_evidence_file(test_dir, strategy_id, {"strategy_id": strategy_id, "run_id": "test", "total_candidates": 100})
    create_mock_stats_file(test_dir, strategy_id, {"strategy_id": strategy_id, "run_id": "test"})
    
    loader = DiskCertificationLoader(str(test_dir))
    monkeypatch.setattr(loader, "_load_manifest", lambda sid: _get_valid_manifest(sid))
    manifest, truth, evidence, stats = loader.load_certification_inputs(strategy_id)
    
    assert isinstance(manifest, StrategyManifest)
    assert isinstance(truth, StrategyTruthReport)
    assert isinstance(evidence, OutcomeEvidenceRunSummary)
    assert isinstance(stats, StatisticalValidationReport)
    assert truth.strategy_id == strategy_id

def test_loader_missing_truth_artifact(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    
    loader = DiskCertificationLoader(str(test_dir))
    monkeypatch.setattr(loader, "_load_manifest", lambda sid: _get_valid_manifest(sid))
    with pytest.raises(CertificationInputMissingError) as exc:
        loader.load_certification_inputs(strategy_id)
    assert "Truth report" in str(exc.value)

def test_loader_missing_outcome_artifact(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    create_mock_truth_file(test_dir, strategy_id, {"strategy_id": strategy_id, "verdict": "IMPLEMENTATION_VERIFIED"})
    
    loader = DiskCertificationLoader(str(test_dir))
    monkeypatch.setattr(loader, "_load_manifest", lambda sid: _get_valid_manifest(sid))
    with pytest.raises(CertificationInputMissingError) as exc:
        loader.load_certification_inputs(strategy_id)
    assert "Evidence summary" in str(exc.value)

def test_loader_missing_statistical_artifact(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    create_mock_truth_file(test_dir, strategy_id, {"strategy_id": strategy_id, "verdict": "IMPLEMENTATION_VERIFIED"})
    create_mock_evidence_file(test_dir, strategy_id, {"strategy_id": strategy_id})
    
    loader = DiskCertificationLoader(str(test_dir))
    monkeypatch.setattr(loader, "_load_manifest", lambda sid: _get_valid_manifest(sid))
    with pytest.raises(CertificationInputMissingError) as exc:
        loader.load_certification_inputs(strategy_id)
    assert "Statistics report" in str(exc.value)

def test_loader_mismatched_strategy_id(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    create_mock_truth_file(test_dir, strategy_id, {"strategy_id": "different_strategy", "verdict": "IMPLEMENTATION_VERIFIED"})
    
    loader = DiskCertificationLoader(str(test_dir))
    monkeypatch.setattr(loader, "_load_manifest", lambda sid: _get_valid_manifest(sid))
    with pytest.raises(CertificationValidationError) as exc:
        loader.load_certification_inputs(strategy_id)
    assert "mismatch" in str(exc.value)

def test_loader_malformed_report(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    # Write invalid JSON
    (test_dir / "docs" / "strategy_truth" / f"{strategy_id}_truth.json").write_text("invalid json")
    
    loader = DiskCertificationLoader(str(test_dir))
    monkeypatch.setattr(loader, "_load_manifest", lambda sid: _get_valid_manifest(sid))
    with pytest.raises(CertificationValidationError) as exc:
        loader.load_certification_inputs(strategy_id)
    assert "Failed to parse JSON file" in str(exc.value)
