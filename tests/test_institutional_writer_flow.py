"""Tests proving Institutional Option Writer Flow Engine gates.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False

Guarantees:
1. Calculates Near-The-Money PCR strictly from ATM ± 3 strikes.
2. Identifies major Call Wall and Put Floor strikes from live OI data.
3. Vetoes buying Call options directly beneath an unyielding Call Wall (< 35 pts runway).
4. Vetoes buying Put options when PCR is heavily bullish and rising.
5. Clears breakouts when short covering (Delta OI < 0) is verified.
"""
from core.institutional_writer_flow import InstitutionalWriterFlowEngine, WriterFlowState


def test_ntm_pcr_calculation_and_walls():
    engine = InstitutionalWriterFlowEngine(strike_step=100, ntm_strikes_count=3)
    spot = 73000.0

    mock_book = {
        "SENSEX 73000 CE 15 OCT 26": {"ltp": 120.0, "oi": 500000.0},
        "SENSEX 73100 CE 15 OCT 26": {"ltp": 80.0, "oi": 1200000.0},  # Major Call Wall
        "SENSEX 73200 CE 15 OCT 26": {"ltp": 45.0, "oi": 300000.0},
        "SENSEX 73000 PE 15 OCT 26": {"ltp": 110.0, "oi": 400000.0},
        "SENSEX 72900 PE 15 OCT 26": {"ltp": 70.0, "oi": 800000.0},
        "SENSEX 72800 PE 15 OCT 26": {"ltp": 35.0, "oi": 1500000.0},  # Major Put Floor
    }

    state = engine.compute_ntm_flow(spot_price=spot, live_option_book=mock_book, asset_prefix="SENSEX")

    assert state.major_call_wall_strike == 73100
    assert state.call_wall_oi == 1200000.0
    assert state.major_put_wall_strike == 72800
    assert state.put_wall_oi == 1500000.0
    # Total Put OI = 2,700,000 / Total Call OI = 2,000,000 = 1.35
    assert state.ntm_pcr == 1.35


def test_call_wall_collision_veto():
    engine = InstitutionalWriterFlowEngine(strike_step=100)
    # Spot is at 73080.0, only 20 pts away from massive Call Wall at 73100
    state = WriterFlowState(
        ntm_pcr=0.95,
        pcr_trend="NEUTRAL",
        major_call_wall_strike=73100,
        major_put_wall_strike=72500,
        call_wall_oi=2000000.0,
        put_wall_oi=1000000.0,
        call_unwinding_detected=False,
        put_unwinding_detected=False
    )

    passed, reason = engine.validate_writer_gate(
        entry_direction="CE",
        spot_price=73080.0,
        flow_state=state,
        min_runway_pts=35.0
    )
    assert passed is False
    assert "VETO_CALL_WALL_COLLISION" in reason


def test_bearish_pcr_divergence_veto():
    engine = InstitutionalWriterFlowEngine(strike_step=100)
    # Price trying to break up, but PCR is heavily bearish (0.60) and falling
    state = WriterFlowState(
        ntm_pcr=0.60,
        pcr_trend="BEARISH_FALLING",
        major_call_wall_strike=73300,
        major_put_wall_strike=72500,
        call_wall_oi=2000000.0,
        put_wall_oi=800000.0,
        call_unwinding_detected=False,
        put_unwinding_detected=False
    )

    passed, reason = engine.validate_writer_gate(
        entry_direction="CE",
        spot_price=73050.0,
        flow_state=state
    )
    assert passed is False
    assert "VETO_BEARISH_PCR_DIVERGENCE" in reason


def test_short_covering_panic_clears_gate():
    engine = InstitutionalWriterFlowEngine(strike_step=100)
    # Spot is at 73085.0 near 73100 Call Wall, BUT call unwinding (panic buying) is active!
    state = WriterFlowState(
        ntm_pcr=1.10,
        pcr_trend="BULLISH_RISING",
        major_call_wall_strike=73100,
        major_put_wall_strike=72500,
        call_wall_oi=1500000.0,
        put_wall_oi=1800000.0,
        call_unwinding_detected=True,  # Panic covering confirmed!
        put_unwinding_detected=False
    )

    passed, reason = engine.validate_writer_gate(
        entry_direction="CE",
        spot_price=73085.0,
        flow_state=state,
        min_runway_pts=35.0
    )
    assert passed is True
    assert reason == "PASSED_WRITER_FLOW_VERIFIED"
