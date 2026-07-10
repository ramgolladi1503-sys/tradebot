from core.feed.recovery_evaluator import evaluate_recovery_block
from core.feed_recovery_coordinator import FeedRecoveryState
from core.market_data_monitor import FeedState
from core.feed.gate import check_execution_allowed
from core.market_data_monitor import FeedHealth
import pytest

def test_gate_recovery_parity(monkeypatch):
    states = [
        ("healthy", FeedRecoveryState()),
        ("auth required", FeedRecoveryState(auth_required=True)),
        ("terminal failure", FeedRecoveryState(terminal_failure=True)),
        ("recovery blocked", FeedRecoveryState(recovery_blocked=True)),
        ("recovery in progress", FeedRecoveryState(recovery_in_progress=True)),
    ]

    for state_name, recovery_state in states:
        class DummyCoordinator:
            def get_state_snapshot(self):
                print(f"DummyCoordinator called for {state_name}")
                return recovery_state
                
        monkeypatch.setattr("core.feed_recovery_coordinator.get_feed_recovery_coordinator", lambda: DummyCoordinator())
        monkeypatch.setattr("core.market_data_monitor.get_feed_recovery_coordinator", lambda: DummyCoordinator())

        # Test check_execution_allowed (from gate.py)
        monkeypatch.setattr("core.feed.gate.classify_group", lambda x: "NIFTY")
        from core.feed.runtime import FeedHealthState
        class MockMachine:
            state = FeedHealthState.OK
            def update_group(self, group, snapshot):
                return {
                    "is_executable": True,
                    "state": FeedHealthState.OK,
                    "reason": "ok"
                }
        class MockMetrics:
            def snapshot(self):
                class Snap:
                    pass
                return Snap()
        is_allowed, primary_blocker, blocker_code, details = check_execution_allowed(
            symbol="NIFTY", machine=MockMachine(), metrics_map={"NIFTY": MockMetrics()}
        )

        # Test FeedHealth.snapshot() (from market_data_monitor.py)
        import time
        now = time.time()
        health = FeedHealth()
        health.on_tick(token=123, symbol="NIFTY", ts_epoch=now, has_depth=True, is_index=True, now_epoch=now)
        snapshot = health.snapshot(now_epoch=now)

        if state_name == "healthy":
            print(f"is_allowed: {is_allowed}, primary_blocker: {primary_blocker}, blocker_code: {blocker_code}")
            assert is_allowed is True
            # gate.py might not return a blocker for healthy, FeedHealth might return DOWN due to age, but we only care about recovery parity
        else:
            print(f"[{state_name}] is_allowed: {is_allowed}, primary_blocker: {primary_blocker}, blocker_code: {blocker_code}")
            assert is_allowed is False
            assert primary_blocker == "feed_state_DOWN"
            assert snapshot.state == FeedState.DOWN
            assert snapshot.reason == details.get("reason")
