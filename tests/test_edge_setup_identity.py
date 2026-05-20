from __future__ import annotations

import pytest

from core.edge_setup_identity import (
    EdgeSetupIdentityError,
    build_edge_setup_identity,
    enrich_record_with_edge_setup_identity,
    score_bucket_for_score,
)


def _record(**overrides):
    payload = {
        "candidate_id": "cand-1",
        "setup_id": "orb_breakout_v1",
        "strategy_family": "Breakout",
        "regime_key": "trend_morning",
        "entry_rule_id": "orb_high_break_with_volume",
        "exit_rule_id": "target_stop_or_time_exit",
        "cost_model_version": "cost_v1",
        "final_score": 0.82,
        "metadata": {"existing": True},
    }
    payload.update(overrides)
    return payload


def test_score_bucket_for_score_uses_expected_buckets():
    assert score_bucket_for_score(0.1) == "0.00-0.25"
    assert score_bucket_for_score(0.25) == "0.25-0.50"
    assert score_bucket_for_score(0.5) == "0.50-0.75"
    assert score_bucket_for_score(82.0) == "0.75-1.00"
    with pytest.raises(EdgeSetupIdentityError, match="edge_setup_score_out_of_range"):
        score_bucket_for_score(101.0)


def test_build_edge_setup_identity_normalizes_required_fields():
    identity = build_edge_setup_identity(_record())

    assert identity.candidate_id == "CAND_1"
    assert identity.setup_id == "ORB_BREAKOUT_V1"
    assert identity.strategy_family == "breakout"
    assert identity.regime_key == "TREND_MORNING"
    assert identity.entry_rule_id == "ORB_HIGH_BREAK_WITH_VOLUME"
    assert identity.exit_rule_id == "TARGET_STOP_OR_TIME_EXIT"
    assert identity.cost_model_version == "COST_V1"
    assert identity.score_bucket == "0.75-1.00"
    assert identity.final_score == 0.82


def test_build_edge_setup_identity_accepts_explicit_score_bucket():
    identity = build_edge_setup_identity(_record(final_score="", score_bucket="0.50-0.75"))

    assert identity.score_bucket == "0.50-0.75"
    assert identity.final_score is None


def test_build_edge_setup_identity_fails_closed_for_blank_identity_fields():
    for field in ("setup_id", "entry_rule_id", "exit_rule_id", "cost_model_version"):
        payload = _record(**{field: ""})
        with pytest.raises(EdgeSetupIdentityError, match=field):
            build_edge_setup_identity(payload)


def test_build_edge_setup_identity_rejects_invalid_score_bucket():
    with pytest.raises(EdgeSetupIdentityError, match="edge_setup_score_bucket_invalid"):
        build_edge_setup_identity(_record(score_bucket="0.90-1.10"))


def test_enrich_record_with_edge_setup_identity_preserves_metadata():
    enriched = enrich_record_with_edge_setup_identity(_record())

    assert enriched["setup_id"] == "ORB_BREAKOUT_V1"
    assert enriched["regime_key"] == "TREND_MORNING"
    assert enriched["score_bucket"] == "0.75-1.00"
    assert enriched["metadata"]["existing"] is True
    assert enriched["metadata"]["edge_setup_identity"]["setup_id"] == "ORB_BREAKOUT_V1"
