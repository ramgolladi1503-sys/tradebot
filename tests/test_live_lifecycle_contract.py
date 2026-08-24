import pytest

from core.live_artifact_contract import write_immutable_json
from core.live_lifecycle_contract import LifecycleEvidence, LiveState, seal_session, validate_read_only_snapshot


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


def test_session_seal_requires_close_gates_and_binds_artifacts(tmp_path):
    evidence = LifecycleEvidence(facts={
        "broker_write_authority": False, "order_authority": False,
        "paper_authorized": False, "live_execution_authorized": False,
        "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0,
    })
    for state in (LiveState.MARKET_CLOSE_STOP, LiveState.PERSISTENCE_FLUSH, LiveState.NO_RESPAWN_PROOF):
        evidence.record(state, "PASS")
    artifact = write_immutable_json(
        tmp_path / "input.json", {"x": 1}, artifact_type="evidence",
        session_id="s1", source_sha="a" * 40,
    )
    seal = seal_session(
        evidence, manifest={"session_id": "s1", "source_sha": "a" * 40},
        artifacts=(artifact,), output_path=str(tmp_path / "SESSION_SEALED.json"),
    )
    assert seal.artifact_type == "session_close_seal"
    assert evidence.states[LiveState.SESSION_SEALED.value] == "PASS"


def test_session_seal_fails_closed_before_close_gates(tmp_path):
    evidence = LifecycleEvidence()
    with pytest.raises(RuntimeError, match="SESSION_SEALED"):
        seal_session(
            evidence, manifest={"session_id": "s1", "source_sha": "a" * 40},
            artifacts=(), output_path=str(tmp_path / "SESSION_SEALED.json"),
        )
