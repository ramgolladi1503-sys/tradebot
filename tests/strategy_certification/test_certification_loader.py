import json
from datetime import date
from pathlib import Path

import pytest

from core.strategy_certification.certification_errors import (
    CertificationInputMissingError,
    CertificationValidationError,
)
from core.strategy_certification.certification_loader import DiskCertificationLoader
from core.strategy_registry.strategy_contract import StrategyContract
from core.strategy_registry.strategy_manifest import StrategyManifest


@pytest.fixture
def test_dir(tmp_path):
    (tmp_path / "strategies").mkdir()
    (tmp_path / "docs" / "strategy_truth").mkdir(parents=True)
    (tmp_path / "docs" / "statistical_validation").mkdir(parents=True)
    (tmp_path / "runtime" / "outcome_evidence").mkdir(parents=True)
    return tmp_path


def create_mock_truth_file(base_dir: Path, strategy_id: str, content: dict):
    path = base_dir / "docs" / "strategy_truth" / f"{strategy_id}_truth.json"
    path.write_text(json.dumps(content), encoding="utf-8")


def create_mock_evidence_file(base_dir: Path, strategy_id: str, content: dict):
    path = base_dir / "runtime" / "outcome_evidence" / f"{strategy_id}_evidence_summary.json"
    path.write_text(json.dumps(content), encoding="utf-8")


def create_mock_stats_file(base_dir: Path, strategy_id: str, content: dict):
    path = base_dir / "docs" / "statistical_validation" / f"{strategy_id}_statistics.json"
    path.write_text(json.dumps(content), encoding="utf-8")


def _get_valid_manifest(strategy_id: str):
    return StrategyManifest(
        contract=StrategyContract(
            strategy_id=strategy_id,
            strategy_name="T",
            version="1",
            owner="T",
            created_date=date.today(),
            description="T",
            market_hypothesis="T",
            primary_market="T",
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
            known_assumptions=[],
        ),
        file_path="t",
        module_path="t",
    )


def _valid_truth(strategy_id: str) -> dict:
    return {
        "strategy_id": strategy_id,
        "is_registry_complete": True,
        "verdict": "IMPLEMENTATION_VERIFIED",
    }


def _valid_evidence(strategy_id: str) -> dict:
    return {
        "strategy_id": strategy_id,
        "run_id": "run-1",
        "run_status": "COMPLETED",
        "total_candidates": 10,
        "executable_count": 4,
        "rejected_count": 6,
        "insufficient_evidence_count": 0,
        "ambiguous_count": 0,
        "weak_ltp_count": 0,
        "start_time": 1.0,
        "end_time": 2.0,
    }


def _complete_stats_shape(strategy_id: str) -> dict:
    return {
        "strategy_id": strategy_id,
        "sample_validation": {},
        "expectancy": {},
        "profit_factor": {},
        "drawdown": {},
        "distribution": {},
        "bootstrap": {},
        "cost_sensitivity": {},
        "regime_analysis": {},
        "walk_forward": {},
        "stability": {},
    }


def _loader(test_dir: Path, monkeypatch, strategy_id: str) -> DiskCertificationLoader:
    loader = DiskCertificationLoader(str(test_dir))
    monkeypatch.setattr(loader, "_load_manifest", lambda sid: _get_valid_manifest(sid))
    return loader


def test_loader_blocks_until_strict_statistics_deserializer(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    create_mock_truth_file(test_dir, strategy_id, _valid_truth(strategy_id))
    create_mock_evidence_file(test_dir, strategy_id, _valid_evidence(strategy_id))
    create_mock_stats_file(test_dir, strategy_id, _complete_stats_shape(strategy_id))

    loader = _loader(test_dir, monkeypatch, strategy_id)
    with pytest.raises(
        CertificationValidationError,
        match="STRICT_STATISTICS_DESERIALIZER_REQUIRED",
    ):
        loader.load_certification_inputs(strategy_id)


def test_loader_missing_truth_artifact(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    loader = _loader(test_dir, monkeypatch, strategy_id)
    with pytest.raises(CertificationInputMissingError, match="Strategy Truth missing"):
        loader.load_certification_inputs(strategy_id)


def test_loader_missing_outcome_artifact(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    create_mock_truth_file(test_dir, strategy_id, _valid_truth(strategy_id))

    loader = _loader(test_dir, monkeypatch, strategy_id)
    with pytest.raises(CertificationInputMissingError, match="Outcome Evidence missing"):
        loader.load_certification_inputs(strategy_id)


def test_loader_missing_statistical_artifact(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    create_mock_truth_file(test_dir, strategy_id, _valid_truth(strategy_id))
    create_mock_evidence_file(test_dir, strategy_id, _valid_evidence(strategy_id))

    loader = _loader(test_dir, monkeypatch, strategy_id)
    with pytest.raises(CertificationInputMissingError, match="Statistical Validation missing"):
        loader.load_certification_inputs(strategy_id)


def test_loader_mismatched_strategy_id(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    create_mock_truth_file(
        test_dir,
        strategy_id,
        {
            "strategy_id": "different_strategy",
            "is_registry_complete": True,
            "verdict": "IMPLEMENTATION_VERIFIED",
        },
    )

    loader = _loader(test_dir, monkeypatch, strategy_id)
    with pytest.raises(CertificationValidationError, match="mismatch"):
        loader.load_certification_inputs(strategy_id)


def test_loader_malformed_report(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    path = test_dir / "docs" / "strategy_truth" / f"{strategy_id}_truth.json"
    path.write_text("invalid json", encoding="utf-8")

    loader = _loader(test_dir, monkeypatch, strategy_id)
    with pytest.raises(CertificationValidationError, match="Failed to parse Strategy Truth"):
        loader.load_certification_inputs(strategy_id)


def test_loader_rejects_incomplete_outcome_evidence(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    create_mock_truth_file(test_dir, strategy_id, _valid_truth(strategy_id))
    create_mock_evidence_file(
        test_dir,
        strategy_id,
        {"strategy_id": strategy_id, "run_id": "run-1"},
    )

    loader = _loader(test_dir, monkeypatch, strategy_id)
    with pytest.raises(CertificationValidationError, match="missing required fields"):
        loader.load_certification_inputs(strategy_id)


def test_loader_rejects_zero_executable_records(test_dir, monkeypatch):
    strategy_id = "test_strategy"
    evidence = _valid_evidence(strategy_id)
    evidence["executable_count"] = 0
    create_mock_truth_file(test_dir, strategy_id, _valid_truth(strategy_id))
    create_mock_evidence_file(test_dir, strategy_id, evidence)

    loader = _loader(test_dir, monkeypatch, strategy_id)
    with pytest.raises(CertificationValidationError, match="zero executable records"):
        loader.load_certification_inputs(strategy_id)
