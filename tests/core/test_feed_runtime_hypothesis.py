import pytest
from hypothesis import given, strategies as st
from core.feed_runtime import build_canonical_feed_truth_state

# Define strategy for feed payload
feed_payload_strategy = st.fixed_dictionaries({
    "runtime_state": st.sampled_from([
        "BOOTING", "CONNECTING", "SUBSCRIBED", "VERIFYING_OPTION_TICKS",
        "VERIFIED_HEALTHY", "LIVE", "DEGRADED", "UNHEALTHY", "STALE",
        "RECONNECTING", "RECOVERY_BLOCKED", "RESTART_REQUIRED", None, "UNKNOWN"
    ]),
    "ws_connected": st.one_of(st.booleans(), st.none()),
    "latest_ltp_age_sec": st.one_of(st.floats(min_value=0.0, max_value=3600.0), st.none()),
    "latest_depth_age_sec": st.one_of(st.floats(min_value=0.0, max_value=3600.0), st.none()),
    "latest_option_tick_age_sec": st.one_of(st.floats(min_value=0.0, max_value=3600.0), st.none()),
    "missing_option_symbols": st.one_of(st.lists(st.text(min_size=1, max_size=5), max_size=3), st.none()),
    "verified_option_symbols": st.one_of(st.lists(st.text(min_size=1, max_size=5), max_size=3), st.none()),
    "ws_error_code": st.one_of(st.integers(min_value=1000, max_value=5000), st.none()),
})

@given(payload=feed_payload_strategy)
def test_feed_truth_state_invariants_hypothesis(payload):
    # Ensure it never crashes on weird inputs
    truth_state = build_canonical_feed_truth_state(payload)
    
    # Invariant: If ws_connected is False and not booting, state must NOT be VERIFIED_HEALTHY
    if payload.get("ws_connected") is False and payload.get("runtime_state") not in {"BOOTING", "STARTING", "INIT", "INITIALIZING"}:
        assert truth_state.state != "VERIFIED_HEALTHY"
        assert "WS_DISCONNECTED" in truth_state.blockers or "WS1006_PROCESS_RESTART_REQUIRED" in truth_state.blockers
        
    # Invariant: If missing option symbols exist, it must not be healthy
    if payload.get("missing_option_symbols"):
        assert truth_state.state != "VERIFIED_HEALTHY"
        assert "MISSING_OPTION_SYMBOLS" in truth_state.blockers

    # Invariant: If ltp age is > 15s (default), it must be stale
    if payload.get("latest_ltp_age_sec") is not None and payload.get("latest_ltp_age_sec") > 15.0:
        assert truth_state.state != "VERIFIED_HEALTHY"
        assert "LTP_STALE" in truth_state.blockers

    # The returned object should always be able to serialize to payload without error
    as_dict = truth_state.to_payload()
    assert isinstance(as_dict, dict)
    assert as_dict["state"] == truth_state.state
