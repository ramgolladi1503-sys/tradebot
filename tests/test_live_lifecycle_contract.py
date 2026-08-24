import pytest

from core.live_lifecycle_contract import LifecycleEvidence, LiveState, validate_read_only_snapshot


def test_running_or_socket_connected_cannot_promote_live_verified():
    evidence = LifecycleEvidence(states={"FEED_HEALTH": "PASS"}, facts={"fresh_ticks": False, "feed_owner_count": 1, "broker_write_authority": False, "order_authority": False})
    with pytest.raises(RuntimeError, match="LIFECYCLE_PROMOTION_BLOCKED"):
        evidence.promote(LiveState.LIVE_VERIFIED)


def test_no_trade_is_valid_but_still_requires_all_live_facts():
    evidence = LifecycleEvidence(facts={"fresh_ticks": True, "feed_owner_count": 1, "broker_write_authority": False, "order_authority": False})
    for state in (LiveState.READ_AUTH, LiveState.INSTRUMENT_AUTHORITY, LiveState.FEED_HEALTH, LiveState.PERSISTENCE_HEALTH, LiveState.MARKET_PRIMITIVES, LiveState.REGIME_PIPELINE, LiveState.STRATEGY_EMISSION, LiveState.OPTION_SURFACE, LiveState.ELIGIBILITY, LiveState.RANKING_PIPELINE, LiveState.ADVISORY_QUEUE):
        evidence.record(state, "NO_TRADE" if state is LiveState.STRATEGY_EMISSION else "PASS")
    evidence.promote(LiveState.LIVE_VERIFIED)


def test_seal_requires_stop_flush_and_no_respawn():
    evidence = LifecycleEvidence()
    with pytest.raises(RuntimeError):
        evidence.promote(LiveState.SESSION_SEALED)
    for state in (LiveState.MARKET_CLOSE_STOP, LiveState.PERSISTENCE_FLUSH, LiveState.NO_RESPAWN_PROOF):
        evidence.record(state, "PASS")
    evidence.promote(LiveState.SESSION_SEALED)


def test_read_only_snapshot_rejects_order_counts_or_authority():
    with pytest.raises(ValueError):
        validate_read_only_snapshot({"broker_write_authority": False, "order_authority": False, "paper_authorized": False, "live_execution_authorized": False, "orders_placed": 1})
