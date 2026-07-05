import pytest
import time
import os
import yaml
from unittest.mock import Mock
from pathlib import Path
from core.movement_contract import StrategyCandidate, StrategyContext
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
        yaml.dump({"lifecycle_state": state}, f)
        
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
    assert len(signals) == 1
    assert signals[0]["live_allowed"] is False
    assert signals[0]["paper_live_allowed"] is False
    assert signals[0]["broker_order_allowed"] is False
    assert signals[0]["execution_allowed"] is False
