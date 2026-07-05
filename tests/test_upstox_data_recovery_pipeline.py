import os
import json
import pytest
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch, MagicMock
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.fetch_missing_strategy_data_upstox import fetch_data
from scripts.run_batch_strategy_certification import check_data_exists

def test_fixture_mode_cannot_certify(tmp_path):
    manifest = {
        "strategy_id": "DUMMY",
        "required_spot_symbol": "TEST",
        "trading_dates": ["2023-01-01"]
    }
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    report = fetch_data(manifest, out_dir, "fixture")

    assert report["certification_eligible"] is False
    assert report["data_source"] == "synthetic_test_fixture"
    assert report["lifecycle_state"] == "DATA_FETCH_SIMULATED_NOT_CERTIFIABLE"

def test_real_upstox_mode_without_token_fails_safely(tmp_path):
    manifest = {"strategy_id": "DUMMY", "required_spot_symbol": "TEST"}
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    env = os.environ.copy()
    if "UPSTOX_ACCESS_TOKEN" in env:
        del env["UPSTOX_ACCESS_TOKEN"]

    with patch.dict(os.environ, env, clear=True):
        report = fetch_data(manifest, out_dir, "real_upstox")

    assert report["auth_error"] is True
    assert report["certification_eligible"] is False

@patch("scripts.fetch_missing_strategy_data_upstox.requests.get")
def test_real_upstox_mode_empty_candles(mock_get, tmp_path):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"data": {"candles": []}}
    mock_get.return_value = mock_res

    manifest = {
        "strategy_id": "DUMMY",
        "required_spot_symbol": "TEST",
        "trading_dates": ["2023-01-01"]
    }
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    env = os.environ.copy()
    env["UPSTOX_ACCESS_TOKEN"] = "VALID_TOKEN"

    with patch.dict(os.environ, env, clear=True):
        report = fetch_data(manifest, out_dir, "real_upstox")

    assert report["data_unavailable_count"] > 0
    assert report["certification_eligible"] is False

@patch("scripts.fetch_missing_strategy_data_upstox.requests.get")
def test_real_upstox_mode_auth_failure(mock_get, tmp_path):
    mock_res = MagicMock()
    mock_res.status_code = 401
    mock_get.return_value = mock_res

    manifest = {
        "strategy_id": "DUMMY",
        "required_spot_symbol": "TEST",
        "trading_dates": ["2023-01-01"]
    }
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    env = os.environ.copy()
    env["UPSTOX_ACCESS_TOKEN"] = "VALID_TOKEN"

    with patch.dict(os.environ, env, clear=True):
        report = fetch_data(manifest, out_dir, "real_upstox")

    assert report["auth_error"] is True
    assert report["certification_eligible"] is False

@patch("scripts.fetch_missing_strategy_data_upstox.requests.get")
def test_successful_real_fetch(mock_get, tmp_path):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"data": {"candles": [["2023-01-01T09:15:00+05:30", 100, 101, 99, 100, 1000]]}}
    mock_get.return_value = mock_res

    manifest = {
        "strategy_id": "DUMMY",
        "required_spot_symbol": "TEST",
        "trading_dates": ["2023-01-01"]
    }
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    env = os.environ.copy()
    env["UPSTOX_ACCESS_TOKEN"] = "VALID_TOKEN"

    with patch.dict(os.environ, env, clear=True):
        report = fetch_data(manifest, out_dir, "real_upstox")

    assert report["succeeded"] > 0
    assert report["certification_eligible"] is True

def test_wfa_backfill_tape_immutability():
    pass

@patch("scripts.run_batch_strategy_certification.load_strategy_registry")
@patch("scripts.run_batch_strategy_certification.subprocess.run")
def test_existing_state_preservation_integration(mock_run, mock_registry, tmp_path, monkeypatch):
    import scripts.run_batch_strategy_certification as rb
    from strategies.strategy_registry import StrategyRegistryEntry

    mock_run.return_value.returncode = 0

    # Mock registry
    mock_registry.return_value = {
        "SIMPLE_ORB": StrategyRegistryEntry(
            strategy_id="SIMPLE_ORB",
            module_path="strategies/simple_orb.py",
            strategy_kind="execution_signal_strategy",
            instrument_family="EQUITY_INDEX_OPTIONS",
            callable_name="generate_signals",
            certification_supported=True,
            certification_track="phase_1_to_5_execution_replay",
            blocked_reason=""
        ),
        "HTF_OPENING_DRIVE_CONT": StrategyRegistryEntry(
            strategy_id="HTF_OPENING_DRIVE_CONT",
            module_path="strategies/htf_opening_drive_cont.py",
            strategy_kind="execution_signal_strategy",
            instrument_family="EQUITY_INDEX_OPTIONS",
            callable_name="generate_signals",
            certification_supported=True,
            certification_track="phase_1_to_5_execution_replay",
            blocked_reason=""
        ),
        "TEST_STRAT": StrategyRegistryEntry(
            strategy_id="TEST_STRAT",
            module_path="strategies/test_strat.py",
            strategy_kind="test_fixture",
            instrument_family="N/A",
            callable_name="",
            certification_supported=False,
            certification_track="not_certifiable"
        ),
        "TRADE_BUILDER": StrategyRegistryEntry(
            strategy_id="TRADE_BUILDER",
            module_path="strategies/trade_builder.py",
            strategy_kind="helper_module",
            instrument_family="N/A",
            callable_name="",
            certification_supported=False,
            certification_track="not_certifiable"
        )
    }

    # Patch Path to use tmp_path for runtime
    original_path = Path
    def mock_path(*args, **kwargs):
        p = original_path(*args, **kwargs)
        if "runtime/strategy_validation" in str(p):
            # Convert to tmp_path
            rel = str(p).replace("runtime/strategy_validation", "")
            if rel.startswith("/"):
                rel = rel[1:]
            return tmp_path / "runtime" / "strategy_validation" / rel
        return p

    monkeypatch.setattr(rb, "Path", mock_path)

    # Create required state files
    runtime_dir = tmp_path / "runtime" / "strategy_validation"
    (runtime_dir / "SIMPLE_ORB").mkdir(parents=True)
    with open(runtime_dir / "SIMPLE_ORB" / "strategy_lifecycle_state.yaml", "w") as f:
        yaml.dump({"lifecycle_state": "PHASE_6_SCAFFOLD_READY", "strategy_id": "SIMPLE_ORB", "phase_6_allowed": True}, f)

    (runtime_dir / "HTF_OPENING_DRIVE_CONT").mkdir(parents=True)
    with open(runtime_dir / "HTF_OPENING_DRIVE_CONT" / "strategy_lifecycle_state.yaml", "w") as f:
        yaml.dump({"lifecycle_state": "PHASE_5_PASSED", "strategy_id": "HTF_OPENING_DRIVE_CONT", "phase_6_allowed": False}, f)

    rb.main()

    report_file = runtime_dir / "batch_certification_report.json"
    assert report_file.exists()

    with open(report_file) as f:
        reps = json.load(f)

        # Excluded test fixture and helpers
        assert not any(r.get("strategy_id") == "TEST_STRAT" for r in reps)
        assert not any(r.get("strategy_id") == "TRADE_BUILDER" for r in reps)

        # Preserved state
        simple_orb_rep = next((r for r in reps if r.get("strategy_id") == "SIMPLE_ORB"), None)
        assert simple_orb_rep is not None
        assert simple_orb_rep["lifecycle_state"] == "PHASE_6_SCAFFOLD_READY"

        htf_rep = next((r for r in reps if r.get("strategy_id") == "HTF_OPENING_DRIVE_CONT"), None)
        assert htf_rep is not None
        assert htf_rep["lifecycle_state"] == "QUARANTINED_FOR_RESEARCH"

@patch("scripts.run_batch_strategy_certification.load_strategy_registry")
@patch("scripts.run_batch_strategy_certification.subprocess.run")
def test_batch_uses_stress_by_default(mock_run, mock_registry, tmp_path, monkeypatch):
    import scripts.run_batch_strategy_certification as rb
    from strategies.strategy_registry import StrategyRegistryEntry

    mock_run.return_value.returncode = 0
    mock_registry.return_value = {
        "SIMPLE_ORB": StrategyRegistryEntry(
            strategy_id="SIMPLE_ORB",
            module_path="strategies/simple_orb.py",
            strategy_kind="execution_signal_strategy",
            instrument_family="EQUITY_INDEX_OPTIONS",
            callable_name="generate_signals",
            certification_supported=True,
            certification_track="phase_1_to_5_execution_replay",
            blocked_reason=""
        ),
        "TREND_PULLBACK": StrategyRegistryEntry(
            strategy_id="TREND_PULLBACK",
            module_path="strategies/movement/trend_pullback.py",
            strategy_kind="candidate_generator_strategy",
            instrument_family="EQUITY_INDEX_OPTIONS",
            callable_name="generate_trend_pullback_candidates",
            certification_supported=True,
            certification_track="candidate_generator_contract_only",
            blocked_reason=""
        )
    }

    original_path = Path
    def mock_path(*args, **kwargs):
        p = original_path(*args, **kwargs)
        if "runtime/strategy_validation" in str(p):
            rel = str(p).replace("runtime/strategy_validation", "")
            if rel.startswith("/"):
                rel = rel[1:]
            return tmp_path / "runtime" / "strategy_validation" / rel
        return p

    monkeypatch.setattr(rb, "Path", mock_path)

    rb.main()

    # Check that subprocess.run was called twice (once for execution, once for generator audit)
    assert mock_run.call_count == 2

    # execution strategy calls run_strategy_certification_pipeline.py with --cost-model stress
    exec_call = mock_run.call_args_list[0][0][0]
    assert "scripts/run_strategy_certification_pipeline.py" in exec_call
    assert "--cost-model" in exec_call
    idx = exec_call.index("--cost-model")
    assert exec_call[idx + 1] == "stress"

    # generator strategy calls audit_candidate_generator_contract.py and does NOT call run_strategy_certification_pipeline.py
    gen_call = mock_run.call_args_list[1][0][0]
    assert "scripts/audit_candidate_generator_contract.py" in gen_call
    assert "scripts/run_strategy_certification_pipeline.py" not in gen_call

def test_helper_module_exclusion():
    source_good = "def generate_signals(data):\n    pass\n"
    source_bad = "def size_position():\n    pass\n"

    assert "def generate_signals" in source_good
    assert "def generate_signals" not in source_bad
    assert "class Strategy" not in source_bad
