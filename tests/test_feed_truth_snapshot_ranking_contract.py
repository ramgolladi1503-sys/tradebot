from __future__ import annotations

import json

import pytest

from core.feed_health_truth import classify_feed_health_truth
from core.feed_hold_gate import FEED_HOLD_BLOCKER, apply_feed_hold_to_ranking
from core.opportunity_scoring import (
    SCORE_ELIGIBLE,
    OpportunityScoreBreakdown,
    OpportunityScoreRecord,
    OpportunityScoreReport,
)
from config import feed_runtime_reliability as reliability_cfg
from core.runtime_feed_truth_snapshot import build_feed_truth_snapshot


def _score_report() -> OpportunityScoreReport:
    breakdown = OpportunityScoreBreakdown(
        component_scores={},
        component_weights={},
        weighted_component_scores={},
        base_score=0.7,
        penalties={},
        total_penalty=0.0,
        bucket_cap=1.0,
        trap_risk_penalty=0.0,
        final_score=0.7,
    )
    score = OpportunityScoreRecord(
        strategy_id="contract-test",
        symbol="NIFTY",
        direction="BUY_CALL",
        movement_type="COMPRESSION_BREAKOUT",
        bucket="EXECUTABLE_CANDIDATE",
        score_eligibility=SCORE_ELIGIBLE,
        final_score=0.7,
        executable_candidate=True,
        score_explanation="contract test",
        downgrade_reasons=(),
        safety_flags=(),
        blockers=(),
        warnings=(),
        breakdown=breakdown,
    )
    return OpportunityScoreReport(
        schema_version=1,
        read_only=True,
        is_order_action=False,
        append=False,
        score_count=1,
        score_eligible_count=1,
        needs_confirmation_count=0,
        advisory_count=0,
        suppressed_count=0,
        no_trade_count=0,
        scores=(score,),
        blockers=(),
        warnings=(),
        safety_flags=(),
        metadata={"scorer": "feed_truth_snapshot_contract_test"},
    )


def _snapshot(*, ws_connected: bool = True, tick_age: float = 0.25, option_age: float = 0.25):
    payload = build_feed_truth_snapshot(
        feed_runtime={
            "effective_ws_connected": ws_connected,
            "market_open": True,
            "last_ws_tick_age_sec": tick_age,
            "option_last_tick_age_by_symbol": {"NIFTY": option_age},
            "subscribed_tokens_count": 3,
            "subscribed_option_tokens_count": 2,
            "last_depth_age_sec": 0.25,
        },
        phase2_rejection={},
    )
    # Exercise the JSON artifact representation consumed by the cycle loader.
    return json.loads(json.dumps(payload))


def test_actual_healthy_persisted_snapshot_allows_normal_ranking():
    payload = _snapshot()

    assert payload["source"] == "runtime_feed_truth_snapshot_v1"
    assert payload["feed_fresh"] is True
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)

    assert ranking.rank_count == 1
    assert ranking.executable_count == 1
    assert FEED_HOLD_BLOCKER not in ranking.blockers
    assert ranking.is_order_action is False
    assert ranking.read_only is True
    assert ranking.append is False


def test_feed_truth_latest_file_loader_preserves_stale_hold_contract(tmp_path):
    from core.orchestrator import _load_cycle_feed_truth_payload

    artifact_path = tmp_path / "feed_truth_latest.json"
    artifact_path.write_text(json.dumps(_snapshot(tick_age=30.0)))

    loaded = _load_cycle_feed_truth_payload(artifact_path)
    ranking = apply_feed_hold_to_ranking(_score_report(), loaded)

    assert loaded["feed_fresh"] is False
    assert ranking.rank_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "persisted_feed_truth_stale" in ranking.blockers


@pytest.mark.parametrize("stale_field", ("tick_age", "option_age"))
def test_actual_stale_persisted_snapshot_holds_even_when_websocket_is_connected(stale_field):
    payload = _snapshot(**{stale_field: 30.0})

    assert payload["ws_connected"] is True
    assert payload["feed_fresh"] is False
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)

    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "persisted_feed_truth_stale" in ranking.blockers


def test_versioned_snapshot_missing_or_invalid_freshness_fails_closed():
    for invalid in (None, "true", 1):
        payload = _snapshot()
        payload["feed_fresh"] = invalid
        ranking = apply_feed_hold_to_ranking(_score_report(), payload)
        assert ranking.rank_count == 0
        assert FEED_HOLD_BLOCKER in ranking.blockers
        assert "persisted_feed_truth_freshness_unknown" in ranking.blockers

    payload = _snapshot()
    payload.pop("feed_fresh")
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)
    assert ranking.rank_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "persisted_feed_truth_freshness_unknown" in ranking.blockers


def test_freshness_flag_does_not_override_transport_or_global_blockers():
    payload = _snapshot(ws_connected=False)
    payload["feed_fresh"] = True
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)

    assert ranking.rank_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "websocket_disconnected" in ranking.blockers

    payload = _snapshot()
    payload["global_feed_blocked"] = True
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)
    assert ranking.rank_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "global_feed_unhealthy" in ranking.blockers


def test_unknown_snapshot_version_fails_closed():
    payload = _snapshot(tick_age=30.0)
    payload["source"] = "runtime_feed_truth_snapshot_v2"
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)

    assert ranking.rank_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "persisted_feed_truth_source_unsupported" in ranking.blockers


def test_mutated_or_missing_source_label_does_not_hide_snapshot_contract():
    payload = _snapshot(tick_age=30.0)
    payload["source"] = "other"
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)
    assert ranking.rank_count == 0
    assert "persisted_feed_truth_source_unsupported" in ranking.blockers


def test_empty_or_transport_only_health_payload_fails_closed():
    for payload in ({}, {"ws_connected": True}, {"effective_ws_connected": True}):
        ranking = apply_feed_hold_to_ranking(_score_report(), payload)
        assert ranking.rank_count == 0
        assert FEED_HOLD_BLOCKER in ranking.blockers
        assert "feed_health_authority_missing" in ranking.blockers

    payload = _snapshot(tick_age=30.0)
    payload.pop("source")
    payload.pop("feed_fresh")
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)
    assert ranking.rank_count == 0
    assert "persisted_feed_truth_source_unsupported" in ranking.blockers


def test_canonical_loader_origin_blocks_marker_stripping_and_legacy_feed_ok(tmp_path):
    from core.orchestrator import _load_cycle_feed_truth_payload

    artifact_path = tmp_path / "feed_truth_latest.json"
    payload = _snapshot(tick_age=30.0)
    for key in (
        "schema_version",
        "source",
        "writer",
        "run_id",
        "boot_epoch",
        "feed_epoch",
        "produced_at",
        "feed_fresh",
        "market_closed_detected",
        "underlying_tick_fresh",
        "option_tick_fresh",
        "depth_fresh",
        "selected_contract_quote_fresh",
        "generated_epoch",
    ):
        payload.pop(key, None)
    payload["feed_ok"] = True
    payload["ws_connected"] = True
    payload["last_tick_age_sec"] = 0.1
    payload["feed_truth_loader_origin"] = "payload-controlled-spoof"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = _load_cycle_feed_truth_payload(artifact_path)
    ranking = apply_feed_hold_to_ranking(_score_report(), loaded)

    assert loaded["feed_truth_loader_origin"] == "canonical_feed_truth_latest_path"
    assert "source" not in loaded
    assert ranking.rank_count == 0
    assert ranking.executable_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "persisted_feed_truth_source_unsupported" in ranking.blockers


def test_aggregate_freshness_cannot_override_contradictory_components():
    payload = _snapshot()
    payload["underlying_tick_fresh"] = False
    payload["option_tick_fresh"] = False
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)

    assert ranking.rank_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "persisted_feed_truth_components_inconsistent" in ranking.blockers


def test_missing_component_freshness_fails_closed_for_versioned_snapshot():
    payload = _snapshot()
    payload.pop("option_tick_fresh")
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)

    assert ranking.rank_count == 0
    assert FEED_HOLD_BLOCKER in ranking.blockers
    assert "persisted_feed_truth_components_unknown" in ranking.blockers


def test_stale_snapshot_write_time_freshness_expires_at_consumer(monkeypatch):
    monkeypatch.setattr(reliability_cfg, "FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC", 1.0)
    payload = _snapshot()
    payload["generated_epoch"] -= 2.0

    ranking = apply_feed_hold_to_ranking(_score_report(), payload)

    assert ranking.rank_count == 0
    assert "persisted_feed_truth_snapshot_stale" in ranking.blockers


@pytest.mark.parametrize("invalid_epoch", (None, "not-an-epoch", True))
def test_missing_or_malformed_snapshot_timestamp_fails_closed(invalid_epoch):
    payload = _snapshot()
    payload["generated_epoch"] = invalid_epoch

    ranking = apply_feed_hold_to_ranking(_score_report(), payload)

    assert ranking.rank_count == 0
    assert "persisted_feed_truth_snapshot_time_unknown" in ranking.blockers


def test_future_snapshot_timestamp_and_invalid_age_config_fail_closed(monkeypatch):
    payload = _snapshot()
    payload["generated_epoch"] += 5.0
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)
    assert ranking.rank_count == 0
    assert "persisted_feed_truth_snapshot_time_invalid" in ranking.blockers

    payload = _snapshot()
    monkeypatch.setattr(reliability_cfg, "FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC", 0.0)
    ranking = apply_feed_hold_to_ranking(_score_report(), payload)
    assert ranking.rank_count == 0
    assert "persisted_feed_truth_max_age_config_invalid" in ranking.blockers


@pytest.mark.parametrize("invalid_age", (True, -0.1, float("nan"), "1.0"))
def test_legacy_ltp_age_authority_rejects_malformed_numeric_values(invalid_age):
    decision = classify_feed_health_truth(
        {"feed_ok": True, "ws_connected": True, "last_tick_age_sec": invalid_age},
        max_ltp_age_sec=2.0,
    )

    assert decision.feed_ok is False
    assert "LTP_AGE_MISSING" in decision.reasons
