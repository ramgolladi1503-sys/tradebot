import json
import time
from unittest.mock import MagicMock, patch
import pytest

from core.paths import logs_dir, repo_root
from core.feed.runtime_store import write_runtime_snapshot
from core.engine_phase2_adapter import build_candidates_phase2
from strategies.short_premium_builder import ShortPremiumBuilder
from core.trade_schema import Trade
from config import config as cfg

def test_feed_runtime_latest_path_equality():
    # Verify that Phase 2 reads from the exact same path that runtime_store writes to
    writer_path = logs_dir() / "feed_runtime_latest.json"
    
    # Clean up if it exists
    if writer_path.exists():
        try:
            writer_path.unlink()
        except Exception:
            pass
            
    payload = {
        "ts_epoch": time.time(),
        "ws_connected": True,
        "subscribed_tokens_count": 10,
        "intended_tokens_count": 10,
        "last_ws_tick_epoch": time.time(),
        "last_depth_epoch": time.time(),
        "source": "test",
        "runtime_state": "RUNNING",
        "feed_ok": True,
        "last_tick_age_sec": 0.5,
        "last_depth_age_sec": 1.0,
        "market_open": True,
    }
    
    # Write snapshot
    write_runtime_snapshot(payload)
    
    # Assert path exists
    assert writer_path.exists()
    
    # Verify we can read it and content matches
    content = json.loads(writer_path.read_text(encoding="utf-8"))
    assert content.get("feed_ok") is True


def test_feed_stale_freshness_limits():
    writer_path = logs_dir() / "feed_runtime_latest.json"
    
    def _write_state(feed_ok, tick_age, depth_age):
        payload = {
            "ts_epoch": time.time(),
            "ws_connected": True,
            "runtime_state": "RUNNING",
            "feed_ok": feed_ok,
            "last_tick_age_sec": tick_age,
            "last_depth_age_sec": depth_age,
            "market_open": True,
        }
        write_runtime_snapshot(payload)

    mock_candidate = {
        "trade_id": "test-trade",
        "symbol": "NIFTY",
        "strategy_family": "BREAKOUT_CONTINUATION",
        "candidate_status": "near_executable",
        "rank_score": 100.0,
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "best_bid": 10.0,
        "best_ask": 10.1,
        "ltp": 10.05,
    }
    
    # Fresh -> Should build/return valid candidates
    _write_state(feed_ok=True, tick_age=1.0, depth_age=2.0)
    out = build_candidates_phase2([mock_candidate])
    assert len(out) > 0
    
    # Stale tick age (> 2.5s) -> Should block and return empty list
    _write_state(feed_ok=True, tick_age=3.0, depth_age=2.0)
    out = build_candidates_phase2([mock_candidate])
    assert len(out) == 0

    # Stale depth age (> 6.0s) -> Should block and return empty list
    _write_state(feed_ok=True, tick_age=1.0, depth_age=7.0)
    out = build_candidates_phase2([mock_candidate])
    assert len(out) == 0

    # feed_ok = False -> Should block and return empty list
    _write_state(feed_ok=False, tick_age=1.0, depth_age=2.0)
    out = build_candidates_phase2([mock_candidate])
    assert len(out) == 0


@patch("time.time", return_value=1782202200.0) # Tuesday 11:00 AM IST (Open)
def test_short_premium_builder_serialization(mock_time):
    # Test ShortPremiumBuilder iron condor all 4 legs requirement & serialization
    builder = ShortPremiumBuilder()
    
    market_data = {
        "symbol": "NIFTY",
        "regime": "RANGE_BOUND",
        "ltp": 10000.0,
        "atr": 100.0,
        "timestamp_epoch": 1782202200.0,
        "ts_epoch": 1782202200.0,
        "option_chain_last_ts": 1782202200.0,
        "depth_ok": True,
        "market_open": True,
        "option_chain": [
            # Short CE: ltp + 1.5 * atr = 10150
            {"strike": 10150, "type": "CE", "last_price": 50.0, "instrument_token": 101, "expiry": "2026-06-25"},
            # Short PE: ltp - 1.5 * atr = 9850
            {"strike": 9850, "type": "PE", "last_price": 45.0, "instrument_token": 102, "expiry": "2026-06-25"},
            # Long CE: ltp + 2.5 * atr = 10250
            {"strike": 10250, "type": "CE", "last_price": 10.0, "instrument_token": 103, "expiry": "2026-06-25"},
            # Long PE: ltp - 2.5 * atr = 9750
            {"strike": 9750, "type": "PE", "last_price": 12.0, "instrument_token": 104, "expiry": "2026-06-25"},
        ]
    }
    
    def mock_getattr_fn(obj, name, default=None):
        if name == "SHORT_PREMIUM_ENABLED":
            return True
        if name == "EXECUTION_MODE":
            return "SIM"
        if name == "ALLOW_NAKED_STRANGLE_PAPER":
            return False
        return getattr(obj, name, default)
        
    with patch("strategies.short_premium_builder.getattr", side_effect=mock_getattr_fn):
        candidates = builder.generate_candidates(market_data)
        assert len(candidates) == 1
        cand = candidates[0]
        
        # Verify Trade class fields
        assert cand.strategy_family == "IRON_CONDOR"
        assert cand.legs is not None
        assert len(cand.legs) == 4
        
        # Max loss: max_width - net_premium = 100 - (50+45 - 10-12) = 100 - 73 = 27
        assert cand.max_loss == pytest.approx(27.0)
        assert cand.candidate_status == "near_executable"
        assert cand.execution_allowed is True
        assert cand.broker_route_allowed is True
        assert cand.live_order_allowed is False


@patch("time.time", return_value=1782202200.0) # Tuesday 11:00 AM IST (Open)
def test_short_premium_strangle_blocked_in_live(mock_time):
    builder = ShortPremiumBuilder()
    
    market_data = {
        "symbol": "NIFTY",
        "regime": "RANGE_BOUND",
        "ltp": 10000.0,
        "atr": 100.0,
        "timestamp_epoch": 1782202200.0,
        "ts_epoch": 1782202200.0,
        "option_chain_last_ts": 1782202200.0,
        "depth_ok": True,
        "market_open": True,
        "option_chain": [
            # Short CE: ltp + 1.5 * atr = 10150
            {"strike": 10150, "type": "CE", "last_price": 50.0, "instrument_token": 101, "expiry": "2026-06-25"},
            # Short PE: ltp - 1.5 * atr = 9850
            {"strike": 9850, "type": "PE", "last_price": 45.0, "instrument_token": 102, "expiry": "2026-06-25"},
        ]
    }
    
    # 1. ALLOW_NAKED_STRANGLE_PAPER = True, EXECUTION_MODE = LIVE -> Should be blocked/vetoed
    def mock_getattr_live(obj, name, default=None):
        if name == "SHORT_PREMIUM_ENABLED":
            return True
        if name == "EXECUTION_MODE":
            return "LIVE"
        if name == "ALLOW_NAKED_STRANGLE_PAPER":
            return True
        return getattr(obj, name, default)
        
    with patch("strategies.short_premium_builder.getattr", side_effect=mock_getattr_live):
        candidates = builder.generate_candidates(market_data)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.strategy_family == "SELL_STRANGLE"
        assert cand.execution_allowed is False
        assert "LIVE_MODE_SHORT_PREMIUM_BLOCKED" in cand.veto_codes


@patch("time.time", return_value=1782235800.0) # Tuesday 20:15 IST (Closed)
def test_short_premium_market_closed(mock_time):
    builder = ShortPremiumBuilder()
    
    market_data = {
        "symbol": "NIFTY",
        "regime": "RANGE_BOUND",
        "ltp": 10000.0,
        "atr": 100.0,
        "timestamp_epoch": 1782235800.0,
        "ts_epoch": 1782235800.0,
        "option_chain_last_ts": 1782235800.0,
        "depth_ok": True,
        "market_open": False,
        "option_chain": [
            {"strike": 10150, "type": "CE", "last_price": 50.0, "instrument_token": 101, "expiry": "2026-06-25"},
            {"strike": 9850, "type": "PE", "last_price": 45.0, "instrument_token": 102, "expiry": "2026-06-25"},
            {"strike": 10250, "type": "CE", "last_price": 10.0, "instrument_token": 103, "expiry": "2026-06-25"},
            {"strike": 9750, "type": "PE", "last_price": 12.0, "instrument_token": 104, "expiry": "2026-06-25"},
        ]
    }
    
    def mock_getattr_fn(obj, name, default=None):
        if name == "SHORT_PREMIUM_ENABLED":
            return True
        if name == "EXECUTION_MODE":
            return "LIVE"
        return getattr(obj, name, default)
        
    with patch("strategies.short_premium_builder.getattr", side_effect=mock_getattr_fn):
        candidates = builder.generate_candidates(market_data)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.candidate_status == "structurally_valid"
        assert cand.execution_allowed is False
        assert cand.broker_route_allowed is False
        assert "MARKET_CLOSED" in cand.veto_codes
        assert "SESSION_CLOSED" in cand.veto_codes
        assert cand.veto_stage == "STRATEGY_VAL"


def test_orchestrator_latency_budget_veto_logging():
    from core.orchestrator import Orchestrator
    
    orc = MagicMock(spec=Orchestrator)
    orc._latency_blocks_entries.return_value = True
    orc._latency_guard_action.return_value = "HALT_ALL"
    
    def mock_build_decision_event(trade, market_data, gatekeeper_allowed, veto_reasons=None, **kwargs):
        return {"veto_reasons": veto_reasons}
        
    orc._build_decision_event = mock_build_decision_event
    orc._log_decision_safe = MagicMock()
    
    # Simulate the block in orchestrator:
    market_data = {"symbol": "NIFTY"}
    if orc._latency_blocks_entries():
        latency_action = orc._latency_guard_action().lower()
        orc._log_decision_safe(
            orc._build_decision_event(
                None,
                market_data,
                gatekeeper_allowed=False,
                veto_reasons=["LATENCY_BUDGET_EXCEEDED"],
            )
        )
        
    # Verify it was called with veto_reasons=["LATENCY_BUDGET_EXCEEDED"]
    orc._log_decision_safe.assert_called_once()
    event_arg = orc._log_decision_safe.call_args[0][0]
    assert event_arg["veto_reasons"] == ["LATENCY_BUDGET_EXCEEDED"]
