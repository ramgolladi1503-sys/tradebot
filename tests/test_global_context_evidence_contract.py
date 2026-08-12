from datetime import datetime, timezone, timedelta
import pytest

from core.global_context_evidence_contract import GlobalObservation, build_causal_snapshot


def test_snapshot_preserves_missingness_and_sha_lineage():
    cutoff = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    snapshot = build_causal_snapshot({"DXY": GlobalObservation("provider", cutoff, None, "a" * 64)}, cutoff=cutoff)
    assert snapshot["observations"]["DXY"]["value"] is None
    assert len(snapshot["snapshot_sha256"]) == 64


def test_future_observation_is_rejected():
    cutoff = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="FUTURE"):
        build_causal_snapshot({"SPX": GlobalObservation("provider", cutoff + timedelta(seconds=1), 1.0, "b" * 64)}, cutoff=cutoff)


def test_missing_provenance_is_rejected():
    cutoff = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="PROVENANCE"):
        build_causal_snapshot({"VIX": GlobalObservation("", cutoff, 1.0, "short")}, cutoff=cutoff)
