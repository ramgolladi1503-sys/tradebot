import pytest
from unittest.mock import patch
from core.feed_recovery_coordinator import FeedRecoveryCoordinator, FeedRecoveryState

@patch("core.feed_recovery_coordinator.time")
def test_expired_token_severs_live_feed(mock_time):
    """
    REQ-AUTH-01: Prove that an expired token immediately severs the live feed
    and prevents any reconnection loop.
    """
    mock_time.time.return_value = 1000.0
    
    coordinator = FeedRecoveryCoordinator()
    
    # Simulate an auth error during websocket validation
    decision = coordinator.request_recovery(
        source="ws_on_error",
        code=None,
        reason="TokenException"
    )
    
    # Invariant: Must transition to AUTH_REQUIRED and block reconnects.
    assert decision.action == "AUTH_REQUIRED"
    assert decision.state.auth_required is True
    assert "FEED_AUTH_REQUIRED" in decision.events_emitted

def test_ws_lifecycle_blocks_on_auth_required():
    """
    Proves that if auth_required is latched, the websocket cannot transition
    back into a CONNECT_REQUEST or CONNECTED state, effectively severing it.
    """
    from core.feed.ws_lifecycle_shell import transition_for_connect_request, WsLifecycleState
    
    state = WsLifecycleState(
        phase="DISCONNECTED",
        auth_required=True
    )
    
    transition = transition_for_connect_request(state)
    
    # Invariant: If auth is required, it must block the connection attempt
    assert transition.next_phase == "AUTH_BLOCKED"
    assert transition.should_record_error is True
