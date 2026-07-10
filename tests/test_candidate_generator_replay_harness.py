import pytest
import time
import os
from unittest.mock import Mock
from pathlib import Path
from core.movement_contract import StrategyCandidate, StrategyContext
from core.yaml_compat import dump as yaml_dump
from scripts.replay_candidate_generator_strategy import replay_strategy
from config import config

@pytest.fixture(autouse=True)
def setup_config():
    config.STRIKE_STEP_BY_SYMBOL = {"NIFTY": 50, "BANKNIFTY": 100}
    yield

def _create_state(tmp_path, strategy_id, state):
    runtime_dir = tmp_path / "runtime" / "strategy_validation" / strategy_id
    runtime_dir.mkdir(parents=True, exist_ok=True)
    with open(runtime_dir / "strategy_lifecycle_state.yaml", "w") as f:
        yaml_dump({"lifecycle_state": state}, f)
        
def create_mock_candidate(status="VALIDATED_CANDIDATE", evidence=None, confidence=60):
    candidate = Mock(spec=StrategyCandidate)
    candidate.executable_eligible = True
    candidate.status = status
    candidate.blockers = ()
    candidate.evidence = evidence or {}
    candidate.metadata = {}
    candidate.params = {}
    candidate.direction = "BUY_CALL"
    candidate.symbol = "NIFTY"
    candidate.strategy_id = "TEST_STRAT"
    candidate.generated_epoch = time.time()
    candidate.confidence_score = confidence / 100.0
    return candidate

def test_valid_adapter_approved_candidate_enters_replay(tmp_path, monkeypatch):
    import scripts.replay_candidate_generator_strategy as replay_mod
    monkeypatch.setattr(replay_mod, "Path", lambda *args, **kwargs: tmp_path / "runtime" / "strategy_validation" / args[0] if len(args)>0 and "runtime" in args[0] else Path(*args, **kwargs))
    _create_state(tmp_path, "TEST_STRAT", "CANDIDATE_GENERATOR_CONTRACT_PASSED")

    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    ctx.metadata = {"expiry": "CURRENT_WEEK"}
    
    candidate = create_mock_candidate(evidence={"quote_source": "upstox_historical", "option_ltp": 150.0, "stop_loss": 100.0, "target": 300.0, "time_stop": 60})
    
    state, msg = replay_strategy("TEST_STRAT", [candidate], ctx)
    assert state == "CANDIDATE_REPLAY_PASSED"

def test_advisory_candidate_does_not_replay(tmp_path, monkeypatch):
    import scripts.replay_candidate_generator_strategy as replay_mod
    monkeypatch.setattr(replay_mod, "Path", lambda *args, **kwargs: tmp_path / "runtime" / "strategy_validation" / args[0] if len(args)>0 and "runtime" in args[0] else Path(*args, **kwargs))
    _create_state(tmp_path, "TEST_STRAT", "CANDIDATE_GENERATOR_CONTRACT_PASSED")
    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    
    candidate = create_mock_candidate(status="ADVISORY")
    state, msg = replay_strategy("TEST_STRAT", [candidate], ctx)
    assert state in ("CANDIDATE_REPLAY_DATA_BLOCKED", "CANDIDATE_REPLAY_FAILED")

def test_fallback_candidate_does_not_replay(tmp_path, monkeypatch):
    import scripts.replay_candidate_generator_strategy as replay_mod
    monkeypatch.setattr(replay_mod, "Path", lambda *args, **kwargs: tmp_path / "runtime" / "strategy_validation" / args[0] if len(args)>0 and "runtime" in args[0] else Path(*args, **kwargs))
    _create_state(tmp_path, "TEST_STRAT", "CANDIDATE_GENERATOR_CONTRACT_PASSED")
    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    
    candidate = create_mock_candidate(status="FALLBACK")
    state, msg = replay_strategy("TEST_STRAT", [candidate], ctx)
    assert state in ("CANDIDATE_REPLAY_DATA_BLOCKED", "CANDIDATE_REPLAY_FAILED")

def test_recovered_candidate_does_not_replay(tmp_path, monkeypatch):
    import scripts.replay_candidate_generator_strategy as replay_mod
    monkeypatch.setattr(replay_mod, "Path", lambda *args, **kwargs: tmp_path / "runtime" / "strategy_validation" / args[0] if len(args)>0 and "runtime" in args[0] else Path(*args, **kwargs))
    _create_state(tmp_path, "TEST_STRAT", "CANDIDATE_GENERATOR_CONTRACT_PASSED")
    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    
    candidate = create_mock_candidate(status="RECOVERED")
    state, msg = replay_strategy("TEST_STRAT", [candidate], ctx)
    assert state in ("CANDIDATE_REPLAY_DATA_BLOCKED", "CANDIDATE_REPLAY_FAILED")

def test_stale_quote_candidate_does_not_replay(tmp_path, monkeypatch):
    import scripts.replay_candidate_generator_strategy as replay_mod
    monkeypatch.setattr(replay_mod, "Path", lambda *args, **kwargs: tmp_path / "runtime" / "strategy_validation" / args[0] if len(args)>0 and "runtime" in args[0] else Path(*args, **kwargs))
    _create_state(tmp_path, "TEST_STRAT", "CANDIDATE_GENERATOR_CONTRACT_PASSED")
    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    
    candidate = create_mock_candidate(evidence={"stale_quote": "true", "option_ltp": 150.0})
    state, msg = replay_strategy("TEST_STRAT", [candidate], ctx)
    assert state in ("CANDIDATE_REPLAY_DATA_BLOCKED", "CANDIDATE_REPLAY_FAILED")

def test_missing_option_ltp_blocks_replay(tmp_path, monkeypatch):
    import scripts.replay_candidate_generator_strategy as replay_mod
    monkeypatch.setattr(replay_mod, "Path", lambda *args, **kwargs: tmp_path / "runtime" / "strategy_validation" / args[0] if len(args)>0 and "runtime" in args[0] else Path(*args, **kwargs))

    _create_state(tmp_path, "TEST_STRAT", "CANDIDATE_GENERATOR_CONTRACT_PASSED")
    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    ctx.metadata = {"expiry": "CURRENT_WEEK"}
    
    candidate = create_mock_candidate(evidence={"quote_source": "upstox_historical", "stop_loss": 100.0, "target": 300.0, "time_stop": 60})
    state, msg = replay_strategy("TEST_STRAT", [candidate], ctx)
    assert state == "CANDIDATE_REPLAY_DATA_BLOCKED"
    assert "VALID_OPTION_LTP" in msg or "MISSING_VALID_OPTION_LTP" in msg

def test_missing_stop_target_blocks_replay(tmp_path, monkeypatch):
    import scripts.replay_candidate_generator_strategy as replay_mod
    monkeypatch.setattr(replay_mod, "Path", lambda *args, **kwargs: tmp_path / "runtime" / "strategy_validation" / args[0] if len(args)>0 and "runtime" in args[0] else Path(*args, **kwargs))

    _create_state(tmp_path, "TEST_STRAT", "CANDIDATE_GENERATOR_CONTRACT_PASSED")
    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    ctx.metadata = {"expiry": "CURRENT_WEEK"}
    
    candidate = create_mock_candidate(evidence={"quote_source": "upstox_historical", "option_ltp": 150.0})
    state, msg = replay_strategy("TEST_STRAT", [candidate], ctx)
    assert state == "CANDIDATE_REPLAY_DATA_BLOCKED"
    assert "RISK_REWARD" in msg or "MISSING_RISK_REWARD_CONTRACT" in msg

def test_synthetic_data_blocks_replay(tmp_path, monkeypatch):
    import scripts.replay_candidate_generator_strategy as replay_mod
    monkeypatch.setattr(replay_mod, "Path", lambda *args, **kwargs: tmp_path / "runtime" / "strategy_validation" / args[0] if len(args)>0 and "runtime" in args[0] else Path(*args, **kwargs))

    _create_state(tmp_path, "TEST_STRAT", "CANDIDATE_GENERATOR_CONTRACT_PASSED")
    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    ctx.metadata = {"expiry": "CURRENT_WEEK"}
    
    candidate = create_mock_candidate(evidence={"quote_source": "synthetic", "option_ltp": 150.0, "stop_loss": 100.0, "target": 300.0, "time_stop": 60})
    state, msg = replay_strategy("TEST_STRAT", [candidate], ctx)
    assert state in ("CANDIDATE_REPLAY_DATA_BLOCKED", "CANDIDATE_REPLAY_FAILED")

def test_stress_cost_model_required():
    from scripts.replay_candidate_generator_strategy import run_historical_option_replay
    with pytest.raises(ValueError, match="stress"):
        run_historical_option_replay([], cost_model="standard")

def test_no_live_flags_modified():
    from core.candidate_to_signal_adapter import adapt_candidate_to_signals
    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    ctx.metadata = {"expiry": "CURRENT_WEEK"}
    
    candidate = create_mock_candidate(evidence={"quote_source": "upstox_historical", "option_ltp": 150.0, "stop_loss": 100.0, "target": 300.0, "time_stop": 60})
    signals = adapt_candidate_to_signals(candidate, ctx, mode="real")
    _len = len(signals)
    assert _len == 1
    assert signals[0]["live_allowed"] is False
    assert signals[0]["paper_live_allowed"] is False
    assert signals[0]["broker_order_allowed"] is False
    assert signals[0]["execution_allowed"] is False

def test_missing_token_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    import scripts.replay_candidate_generator_strategy as replay_mod
    status, reason, meta = replay_mod.fetch_upstox_historical("NIFTY", "2026-07-01", "2026-07-05")
    assert status == "DATA_BLOCKED_UPSTOX_TOKEN_MISSING"

def test_auth_failure_fails_closed(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "invalid")
    import scripts.replay_candidate_generator_strategy as replay_mod
    class MockRes:
        status_code = 401
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockRes())
    status, reason, meta = replay_mod.fetch_upstox_historical("NIFTY", "2026-07-01", "2026-07-05")
    assert status == "DATA_BLOCKED_UPSTOX_FETCH_FAILED"
    
def test_empty_candles_fails_closed(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "valid")
    import scripts.replay_candidate_generator_strategy as replay_mod
    class MockRes:
        status_code = 200
        def json(self): return {"data": {"candles": []}}
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockRes())
    status, reason, meta = replay_mod.fetch_upstox_historical("NIFTY", "2026-07-01", "2026-07-05")
    assert status == "DATA_BLOCKED_UPSTOX_UNAVAILABLE"

def test_fixture_data_non_certifiable():
    import scripts.replay_candidate_generator_strategy as replay_mod
    passed, reason = replay_mod.run_historical_option_replay([{"data_source": "synthetic_test_fixture"}])
    assert passed is False

def test_missing_option_ltp_blocks_approval():
    from core.candidate_to_signal_adapter import adapt_candidate_to_signals
    ctx = Mock(spec=StrategyContext)
    ctx.spot_ltp = 20000.0
    ctx.metadata = {"expiry": "CURRENT_WEEK"}
    
    candidate = create_mock_candidate(evidence={"quote_source": "upstox_historical"})
    signals = adapt_candidate_to_signals(candidate, ctx, mode="real")
    # missing option_ltp -> should be rejected by adapter
    assert not signals or signals[0].get("lifecycle_state") == "CANDIDATE_TO_SIGNAL_ADAPTER_REQUIRED"

def test_no_synthetic_proxy_manual_stub_certifies():
    import scripts.replay_candidate_generator_strategy as replay_mod
    for source in ["mock", "proxy", "manual_stub"]:
        passed, reason = replay_mod.run_historical_option_replay([{"quote_source": source}])
        assert passed is False

def test_upstox_ohlc_returns_no_tick_spread_truth(monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "valid")
    import scripts.replay_candidate_generator_strategy as replay_mod
    class MockRes:
        status_code = 200
        def json(self): return {"data": {"candles": [[1,2,3,4,5]]}}
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockRes())
    status, reason, meta = replay_mod.fetch_upstox_historical("NIFTY", "2026-07-01", "2026-07-05")
    assert status == "DATA_BLOCKED_UPSTOX_NO_TICK_OR_SPREAD_TRUTH"

def test_auth_failure_no_provenance(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "invalid")
    import scripts.replay_candidate_generator_strategy as replay_mod
    class MockRes:
        status_code = 401
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: MockRes())
    import sys
    monkeypatch.setattr(sys, "argv", ["prog", "--strategy", "TEST", "--fetch-missing-data", "--data-provider", "real_upstox"])
    # mock Path to write to tmp_path
    monkeypatch.chdir(tmp_path)
    try:
        replay_mod.main()
    except SystemExit:
        pass
    import json
    report = json.load(open("runtime/strategy_validation/TEST/candidate_replay_report.json"))
    assert report["requested_data_provider"] == "real_upstox"
    assert report["provenance"] == []
    assert report["certifiable_data"] is False
    assert report["adapter_approved_for_replay"] is False
    assert report["data_fetch_status"] == "DATA_BLOCKED_UPSTOX_FETCH_FAILED"
    

def test_missing_token_blocker_format(monkeypatch, tmp_path):
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    import scripts.replay_candidate_generator_strategy as replay_mod
    import sys, json
    monkeypatch.setattr(sys, "argv", ["prog", "--strategy", "TEST_FORMAT", "--fetch-missing-data", "--data-provider", "real_upstox"])
    monkeypatch.chdir(tmp_path)
    try:
        replay_mod.main()
    except SystemExit:
        pass
    report = json.load(open("runtime/strategy_validation/TEST_FORMAT/candidate_replay_report.json"))
    assert report["data_fetch_status"] == "DATA_BLOCKED_UPSTOX_TOKEN_MISSING"
    assert "DATA_BLOCKED_UPSTOX_TOKEN_MISSING" in report["data_fetch_blockers"]
    _len = len(report["data_fetch_blocker_details"])
    assert _len > 0
    assert "UPSTOX_ACCESS_TOKEN" in report["data_fetch_blocker_details"]["DATA_BLOCKED_UPSTOX_TOKEN_MISSING"]

def test_data_capability_classification_underlying_only():
    from scripts.replay_candidate_generator_strategy import determine_data_capability
    cap = determine_data_capability(100, 0, "real_upstox")
    assert cap["underlying_data_capability"] == "UNDERLYING_OHLC_ONLY"
    assert cap["option_data_capability"] == "OPTION_DATA_MISSING"
    assert cap["stress_replay_supported"] is False
    assert cap["candle_replay_supported"] is False
    assert "DATA_BLOCKED_UNDERLYING_ONLY_NO_OPTION_TRUTH" in cap["certification_blockers"]

def test_data_capability_classification_option_ohlc():
    from scripts.replay_candidate_generator_strategy import determine_data_capability
    cap = determine_data_capability(100, 100, "real_upstox")
    assert cap["underlying_data_capability"] == "UNDERLYING_OHLC"
    assert cap["option_data_capability"] == "OPTION_OHLC"
    assert cap["option_ltp_truth_available"] is True
    assert cap["stress_replay_supported"] is False
    assert cap["candle_replay_supported"] is True
    assert "DATA_BLOCKED_OPTION_OHLC_NO_SPREAD_TRUTH" in cap["certification_blockers"]

def test_data_capability_classification_live_captured():
    from scripts.replay_candidate_generator_strategy import determine_data_capability
    cap = determine_data_capability(100, 100, "live_captured")
    assert cap["option_data_capability"] == "OPTION_QUOTE_OR_DEPTH_TRUTH"
    assert cap["spread_truth_available"] is True
    assert cap["tick_truth_available"] is True
    assert cap["depth_truth_available"] is True
    assert cap["option_ltp_truth_available"] is True
    assert cap["stress_replay_supported"] is True
    assert cap["candle_replay_supported"] is True
    _len = len(cap["certification_blockers"])
    assert _len == 0

def test_offline_replay_no_fetch_produces_not_requested(monkeypatch, tmp_path):
    import scripts.replay_candidate_generator_strategy as replay_mod
    import sys, json
    monkeypatch.setattr(sys, "argv", ["prog", "--strategy", "TEST_NO_FETCH"])
    monkeypatch.chdir(tmp_path)
    try:
        replay_mod.main()
    except SystemExit:
        pass
    report = json.load(open("runtime/strategy_validation/TEST_NO_FETCH/candidate_replay_report.json"))
    assert report["data_fetch_status"] == "DATA_FETCH_NOT_REQUESTED"
    assert report["data_fetch_attempted"] is False
    assert "DATA_FETCH_NOT_REQUESTED" in report["data_fetch_blockers"]
    _len = len(report["data_fetch_blocker_details"])
    assert _len > 0
    assert "Fetch was not requested" in report["data_fetch_blocker_details"]["DATA_FETCH_NOT_REQUESTED"]
