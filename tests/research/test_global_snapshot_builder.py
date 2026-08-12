from datetime import datetime, timedelta, timezone
import pytest

from core.global_context_evidence_contract import GlobalObservation
from research.global_v1.snapshot_builder import SnapshotPolicy, build_target_session_snapshot, verify_snapshot


def observations(at):
    return {name: GlobalObservation("offline_fixture", at, 1.0, f"{name.lower():0<64}"[:64]) for name in ("DXY", "SPX", "NASDAQ", "VIX")}


def test_snapshot_is_deterministic_and_tamper_detecting():
    cutoff = datetime(2026, 8, 12, 9, tzinfo=timezone.utc)
    policy = SnapshotPolicy(timedelta(hours=1))
    first = build_target_session_snapshot(observations(cutoff - timedelta(minutes=5)), cutoff=cutoff, policy=policy)
    second = build_target_session_snapshot(observations(cutoff - timedelta(minutes=5)), cutoff=cutoff, policy=policy)
    assert first == second
    verify_snapshot(first)
    tampered = dict(first)
    tampered["observations"] = dict(first["observations"])
    tampered["observations"]["DXY"] = dict(tampered["observations"]["DXY"], value=99.0)
    with pytest.raises(ValueError, match="TAMPERED"):
        verify_snapshot(tampered)


def test_missing_and_future_inputs_fail_closed():
    cutoff = datetime(2026, 8, 12, 9, tzinfo=timezone.utc)
    policy = SnapshotPolicy(timedelta(hours=1))
    blocked = build_target_session_snapshot({"DXY": observations(cutoff)["DXY"]}, cutoff=cutoff, policy=policy)
    assert blocked["status"] == "BLOCKED_DATA"
    with pytest.raises(ValueError, match="FUTURE"):
        build_target_session_snapshot(observations(cutoff + timedelta(seconds=1)), cutoff=cutoff, policy=policy)


def test_stale_input_is_distinguished_from_missing():
    cutoff = datetime(2026, 8, 12, 9, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="STALE"):
        build_target_session_snapshot(observations(cutoff - timedelta(days=1)), cutoff=cutoff, policy=SnapshotPolicy(timedelta(hours=1)))
