import pytest

from core.live_ranking_contract import rank_advisory_candidates


def _row(candidate_id, confidence):
    return {
        "candidate_id": candidate_id, "strategy_id": "s1", "spec_sha": "b" * 40,
        "timestamp": "2026-08-24T15:14:00+05:30", "underlying": "NIFTY", "direction": "UP",
        "candidate_type": "option", "confidence_raw": confidence, "regime": "trend",
        "reason": "measured", "data_cutoff": "2026-08-24T15:13:59+05:30",
    }


def test_ranking_compares_only_supplied_confidence_and_preserves_status():
    rows = rank_advisory_candidates([_row("b", 0.4), {**_row("a", 0.8), "candidate_status": "eligible"}])
    assert [row["candidate_id"] for row in rows] == ["a", "b"]
    assert rows[0]["candidate_status"] == "eligible"
    assert rows[0]["ranking_basis"] == "supplied_confidence_only"
    assert rows[0]["execution_status"] == "advisory_only"


def test_ranking_rejects_unknown_candidate_status():
    with pytest.raises(ValueError, match="status_invalid"):
        rank_advisory_candidates([{**_row("a", 0.8), "candidate_status": "execute"}])
