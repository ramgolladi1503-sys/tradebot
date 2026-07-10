import pytest
import time
from types import SimpleNamespace

from config import config as cfg
from core.market_data_monitor import FeedHealth, FeedState
from core.feed_recovery_coordinator import FeedRecoveryCoordinator, get_feed_recovery_coordinator
from core.execution_router import ExecutionRouter
from core.approval_store import approve_order_intent
from core.orders.order_intent import OrderIntent
from core.feed.runtime import FeedHealthMachine, FeedGroupMetrics, FeedGroupKey, FeedHealthState, get_runtime_feed_health
from core.feed.gate import check_execution_allowed

def _trade(trade_id: str = "T-FEED-HEALTH"):
    return SimpleNamespace(
        trade_id=trade_id,
        symbol="NIFTY",
        instrument="OPT",
        instrument_id="NIFTY|2026-02-12|25200|CE",
        instrument_token=12345,
        side="BUY",
        entry_price=102.0,
        stop_loss=98.0,
        target=108.0,
        qty=10,
        confidence=0.8,
        tradable=True,
        tradable_reasons_blocking=[],
        order_type="LIMIT",
        expiry="2026-02-12",
        strike=25200,
        right="CE",
        exchange="NFO",
        product="MIS",
    )

def _snapshot():
    return {"bid": 100.0, "ask": 101.0, "ts": time.time(), "depth": {}}

@pytest.fixture
def execution_env(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ALLOW_LIVE_PLACEMENT", True, raising=False)
    monkeypatch.setattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", False, raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_ON_EXEC", False, raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "", raising=False)
    monkeypatch.setattr(cfg, "LIVE_REQUIRE_ARMED_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "feed_health.db"), raising=False)
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

@pytest.fixture(autouse=True)
def reset_feed_coordinator():
    coordinator = get_feed_recovery_coordinator()
    coordinator.reset()
    yield
    coordinator.reset()

def test_scenario_1_immediate_disconnect_before_freshness_timeout(execution_env, monkeypatch):
    """
    Scenario 1: Immediate disconnect before freshness timeout
    Hypothesis: TradeBot may temporarily allow a new executable entry after the WebSocket has disconnected
    because tick freshness hasn't exceeded the threshold.
    """
    feed = FeedHealth(index_ok_age_sec=3.0, index_down_no_msg_sec=5.0)
    coordinator = get_feed_recovery_coordinator()
    
    # 1. Initialize feed health as healthy & record fresh tick
    base_time = 100.0
    feed.on_tick(token=111, symbol="NIFTY", ts_epoch=base_time, is_index=True, now_epoch=base_time)
    
    # Verify feed is OK
    assert feed.snapshot(now_epoch=base_time).state == FeedState.OK

    # 3. Confirm new entries are allowed
    trade = _trade("T-S1")
    hash_val = OrderIntent.from_trade(trade, mode="LIVE").order_intent_hash()
    approve_order_intent(hash_val, approver_id="tester", ttl_sec=600)
    
    # 4. Move WebSocket/recovery state to RECONNECTING (simulated via 1006 drop)
    monkeypatch.setattr(coordinator, "_now_epoch", lambda: base_time + 1.0)
    decision = coordinator.request_recovery(source="on_close", code=1006, reason="peer dropped")
    assert decision.action == "SOFT_RECONNECT"
    assert coordinator.state.recovery_in_progress is True

    # 5. Do not advance time beyond the feed freshness threshold (now_epoch = base_time + 1.0)
    # The freshness threshold is 3.0s, so we are well within it.
    
    # Check the gate directly since we want to know what the feed gate outputs
    allowed, state, reason = feed.gate_live_entries()
    
    # The fix ensures it gets blocked by FEED_RECOVERY_IN_PROGRESS
    assert allowed is False
    assert state == "down:FEED_RECOVERY_IN_PROGRESS"

def test_scenario_2_terminal_recovery_failure(execution_env, monkeypatch):
    """
    Scenario 2: Terminal recovery failure
    """
    feed = FeedHealth(index_ok_age_sec=3.0, index_down_no_msg_sec=5.0)
    coordinator = get_feed_recovery_coordinator()
    base_time = 100.0
    feed.on_tick(token=111, symbol="NIFTY", ts_epoch=base_time, is_index=True, now_epoch=base_time)
    
    # Trigger terminal recovery failure (e.g., auth failure)
    monkeypatch.setattr(coordinator, "_now_epoch", lambda: base_time + 1.0)
    decision = coordinator.request_recovery(source="on_error", code=401, reason="token expired")
    assert decision.action == "AUTH_REQUIRED"
    assert coordinator.state.auth_required is True
    assert coordinator.state.recovery_blocked is True
    
    # Check the gate directly
    allowed, state, reason = feed.gate_live_entries()
    
    # Because FeedHealth now reads coordinator state, it should be DOWN with FEED_AUTH_REQUIRED
    assert allowed is False
    assert state == "down:FEED_AUTH_REQUIRED"

def test_scenario_3_connected_socket_but_no_fresh_ticks(execution_env, monkeypatch):
    """
    Scenario 3: Connected socket but no fresh ticks
    """
    feed = FeedHealth(index_ok_age_sec=3.0, index_down_no_msg_sec=5.0)
    base_time = 100.0
    
    # Feed tick arrived a long time ago
    feed.on_tick(token=111, symbol="NIFTY", ts_epoch=base_time - 10.0, is_index=True, now_epoch=base_time - 10.0)
    
    # But socket is still receiving generic messages (like heartbeat), keeping ws_msg_age_sec young
    feed.on_ws_message(now_epoch=base_time)
    
    trade = _trade("T-S3")
    hash_val = OrderIntent.from_trade(trade, mode="LIVE").order_intent_hash()
    approve_order_intent(hash_val, approver_id="tester", ttl_sec=600)
    
    router = ExecutionRouter(feed_health=feed)
    monkeypatch.setattr(time, "time", lambda: base_time)
    import core.market_data_monitor as mdm
    monkeypatch.setattr(mdm, "now_utc_epoch", lambda: base_time)
    
    # Check the gate directly since we want to know what the feed gate outputs
    allowed, state, reason = feed.gate_live_entries(now_epoch=base_time)
    
    # It should be DEGRADED because index is stale (age > 3.0s). 
    # DEGRADED blocks live entries.
    assert allowed is False
    assert state.startswith("degraded:")

def test_scenario_4_socket_disconnected_but_ticks_still_fresh(execution_env, monkeypatch):
    """
    Scenario 4: Socket disconnected but ticks still fresh
    """
    feed = FeedHealth(index_ok_age_sec=5.0, index_down_no_msg_sec=10.0)
    base_time = 100.0
    
    # Fresh tick
    feed.on_tick(token=111, symbol="NIFTY", ts_epoch=base_time, is_index=True, now_epoch=base_time)
    
    # Pretend socket was disconnected natively by Kite without calling on_ws_message again.
    # At base_time + 2.0, age is 2.0. This is < ok_age (5.0) and < down_no_msg (10.0).
    # Check the gate directly
    allowed, state, reason = feed.gate_live_entries(now_epoch=base_time + 2.0)
    
    # The gap is verified: It allows execution because age is < 5.0.
    assert allowed is True
    assert state == "ok"

def test_scenario_5_partial_feed_freshness(execution_env, monkeypatch):
    """
    Scenario 5: Partial feed freshness
    index fresh, option stale, depth stale or missing
    """
    feed = FeedHealth(index_ok_age_sec=3.0, option_ok_age_sec=2.0)
    base_time = 100.0
    
    # Index is fresh
    feed.on_tick(token=111, symbol="NIFTY", ts_epoch=base_time, is_index=True, now_epoch=base_time)
    
    # Option is stale (arrived 4 seconds ago)
    feed.on_tick(token=222, symbol="NIFTY2026CE", ts_epoch=base_time - 4.0, is_index=False, now_epoch=base_time - 4.0)
    
    trade = _trade("T-S5")
    hash_val = OrderIntent.from_trade(trade, mode="LIVE").order_intent_hash()
    approve_order_intent(hash_val, approver_id="tester", ttl_sec=600)
    
    router = ExecutionRouter(feed_health=feed)
    monkeypatch.setattr(time, "time", lambda: base_time)
    import core.market_data_monitor as mdm
    monkeypatch.setattr(mdm, "now_utc_epoch", lambda: base_time)
    
    # Check the gate directly
    allowed, state, reason = feed.gate_live_entries(now_epoch=base_time)
    
    # Option is stale (4.0 > 2.0) -> should be DEGRADED
    assert allowed is False
    assert state.startswith("degraded:") or state.startswith("down:")

def test_scenario_6_recovery_completes_without_resubscription_proof(execution_env, monkeypatch):
    """
    Scenario 6: Recovery completes without resubscription proof
    """
    feed = FeedHealth(index_ok_age_sec=3.0, index_down_no_msg_sec=5.0)
    coordinator = get_feed_recovery_coordinator()
    coordinator.clear_recovery(source="test", reason="reset")
    base_time = 100.0
    
    feed.on_tick(token=111, symbol="NIFTY", ts_epoch=base_time, is_index=True, now_epoch=base_time)
    
    # Socket disconnects
    monkeypatch.setattr(coordinator, "_now_epoch", lambda: base_time + 1.0)
    coordinator.request_recovery(source="on_close", code=1006, reason="drop")
    
    # Socket reconnects, clears recovery
    monkeypatch.setattr(coordinator, "_now_epoch", lambda: base_time + 1.5)
    coordinator.clear_recovery(source="on_open", reason="reconnected")
    
    # But no NEW ticks have arrived yet!
    # Wait until base_time + 4.0 (ticks are now 4.0s old, which is > index_ok_age_sec of 3.0s)
    
    trade = _trade("T-S6")
    hash_val = OrderIntent.from_trade(trade, mode="LIVE").order_intent_hash()
    approve_order_intent(hash_val, approver_id="tester", ttl_sec=600)
    
    router = ExecutionRouter(feed_health=feed)
    monkeypatch.setattr(time, "time", lambda: base_time + 4.0)
    import core.market_data_monitor as mdm
    monkeypatch.setattr(mdm, "now_utc_epoch", lambda: base_time + 4.0)
    
    # Check the gate directly
    allowed, state, reason = feed.gate_live_entries(now_epoch=base_time + 4.0)
    
    # The tick is stale (4.0 > 3.0), so execution SHOULD be blocked (DEGRADED).
    # This shows it behaves correctly on the other side (stale ticks block execution, 
    # regardless of socket being connected and recovery being cleared).
    assert allowed is False
    assert state.startswith("degraded:")

def test_feed_gate_parity(execution_env, monkeypatch):
    from core.feed_recovery_coordinator import get_feed_recovery_coordinator
    from core.market_data_monitor import FeedHealth
    from core.feed.gate import check_execution_allowed
    from core.feed.runtime import FeedHealthMachine, FeedGroupMetrics, FeedGroupThreshold
    import time
    
    coordinator = get_feed_recovery_coordinator()
    
    cases = [
        ("fully_healthy", "OK", True, "ok", "ok", 0.0),
        ("disconnected_but_ticks_fresh", "RECONNECTING", False, "feed_state_DOWN", "down:FEED_RECOVERY_IN_PROGRESS", 0.0),
        ("recovery_in_progress", "RECOVERY_IN_PROGRESS", False, "feed_state_DOWN", "down:FEED_RECOVERY_IN_PROGRESS", 0.0),
        ("terminal_failure", "TERMINAL_FAILURE", False, "feed_state_DOWN", "down:FEED_RECOVERY_TERMINAL_FAILURE", 0.0),
        ("recovery_blocked", "RECOVERY_BLOCKED", False, "feed_state_DOWN", "down:FEED_RECOVERY_BLOCKED", 0.0),
        ("authentication_required", "AUTH_REQUIRED", False, "feed_state_DOWN", "down:FEED_AUTH_REQUIRED", 0.0),
        ("connected_but_index_stale", "OK", False, "feed_state_DEGRADED", "degraded:index_stale_tokens=1", 4.0),
        ("index_fresh_but_option_stale", "OK", False, "feed_state_DEGRADED", "degraded:option_stale_tokens=1", 4.0),
        # Unimplemented cases marked explicitly
        ("subscriptions_unconfirmed", "OK", True, "ok", "ok", 0.0), # SUBSCRIPTION_RESTORATION_PROOF: NOT IMPLEMENTED
        ("no_post_reconnect_message", "OK", True, "ok", "ok", 0.0), # POST_RECONNECT_MESSAGE_PROOF: NOT IMPLEMENTED
        ("old_pre_disconnect_tick_still_fresh", "OK", True, "ok", "ok", 0.0), # PRE_DISCONNECT_TICK_INVALIDATION: NOT IMPLEMENTED
        ("contradictory_input_state", "OK", True, "ok", "ok", 0.0), # Handled identically by lack of strict enforcement
    ]
    
    for case_name, state_setup, exp_allowed, exp_gate_reason, exp_mdm_reason, tick_age in cases:
        feed = FeedHealth(index_ok_age_sec=3.0, option_ok_age_sec=3.0, index_down_no_msg_sec=5.0)
        machine = FeedHealthMachine(thresholds_by_group={"INDEX:NIFTY": FeedGroupThreshold(ok_age_sec=3.0, down_no_msg_sec=5.0)})
        coordinator.reset()
        base_time = 100.0
        monkeypatch.setattr(time, "time", lambda: base_time)
        import core.market_data_monitor as mdm
        monkeypatch.setattr(mdm, "now_utc_epoch", lambda: base_time)
        metrics_map = {"INDEX:NIFTY": FeedGroupMetrics(group_key="INDEX:NIFTY", now_fn=lambda: base_time)}
        
        # Freshness setup
        feed.on_tick(token=111, symbol="NIFTY", ts_epoch=base_time - tick_age, is_index=True, now_epoch=base_time)
        if case_name == "index_fresh_but_option_stale":
            feed.on_tick(token=111, symbol="NIFTY", ts_epoch=base_time, is_index=True, now_epoch=base_time)
            feed.on_tick(token=222, symbol="NIFTY2026CE", ts_epoch=base_time - tick_age, is_index=False, now_epoch=base_time)
            
        monkeypatch.setattr(coordinator, "_now_epoch", lambda: base_time)
        
        # Recovery setup
        if state_setup == "RECONNECTING" or state_setup == "RECOVERY_IN_PROGRESS":
            coordinator.request_recovery(source="on_close", code=1006, reason="peer dropped")
        elif state_setup == "TERMINAL_FAILURE":
            coordinator._terminal_decision(source="test", reason="term")
        elif state_setup == "RECOVERY_BLOCKED":
            coordinator._blocked_decision(source="test", reason="blocked", recovery_blocked=True)
        elif state_setup == "AUTH_REQUIRED":
            coordinator._auth_required_decision(source="test", reason="auth")
            
        # Path 1: Market Data Monitor
        mdm_allowed, mdm_state, mdm_snap = feed.gate_live_entries(now_epoch=base_time)
        
        # Path 2: Gate.py
        metrics_map["INDEX:NIFTY"].observe_tick(111, base_time - tick_age)
        if case_name == "index_fresh_but_option_stale":
            metrics_map["INDEX:NIFTY"].observe_tick(111, base_time)
            metrics_map["INDEX:NIFTY"].observe_tick(222, base_time - tick_age)
            
        gate_allowed, gate_reason, gate_state_name, gate_details = check_execution_allowed(
            symbol="NIFTY", machine=machine, metrics_map=metrics_map
        )
        
        # Assert parity
        assert mdm_allowed == gate_allowed, f"{case_name}: {mdm_allowed} != {gate_allowed}"
        
        # Gate path block reason matching
        if not gate_allowed:
            assert gate_reason == exp_gate_reason, f"{case_name}: gate reason {gate_reason} != {exp_gate_reason}"
        
        # MDM path block reason matching (prefix logic)
        if not mdm_allowed:
            assert mdm_state.startswith(exp_mdm_reason.split(":")[0]), f"{case_name}: mdm state {mdm_state} != {exp_mdm_reason}"
            if ":" in exp_mdm_reason:
                assert exp_mdm_reason.split(":")[1] in mdm_state, f"{case_name}: mdm state {mdm_state} missing {exp_mdm_reason}"
