from __future__ import annotations

from core.replay_context_recorder import build_replay_context_record
from core.runtime_candidate_handoff import build_runtime_candidate_handoff_payload


def test_replay_context_record_preserves_available_runtime_fields():
    payload = {
        "snapshot_ts_epoch": 1_783_049_403.7,
        "signal_ts": "2026-07-02T10:52:40Z",
        "entry_ts": "2026-07-02T10:53:00Z",
        "feed_truth_state": "LIVE",
        "feed_health_reason_code": "OK",
        "regime": "TREND_UP",
        "is_oos": False,
        "oos_label": "IS",
        "bid": 112.0,
        "ask": 112.5,
        "quote_source": "tick_store",
        "quote_age_sec": 1.25,
        "option_type": "CE",
        "strike": 58400,
        "expiry": "2026-07-07",
    }

    record = build_replay_context_record(payload, source="unit_test", require_candidate_pool_inputs=False)

    assert record["replay_context_ready"] is True
    assert record["replay_context_blockers"] == []
    assert record["feature_cutoff_ts_source"] == "derived:snapshot_ts_epoch"
    assert record["signal_ts_source"] == "preserved:signal_ts"
    assert record["earliest_entry_ts_source"] == "preserved:entry_ts"
    assert record["feed_truth_state_source"] == "preserved:feed_truth_state"
    assert record["feed_truth_reason_code_source"] == "preserved:feed_health_reason_code"
    assert record["quote_source_source"] == "preserved:quote_source"
    assert record["quote_age_sec_source"] == "preserved:quote_age_sec"
    assert record["replay_context"]["feature_cutoff_ts"] == "2026-07-03T03:30:03.700000Z"
    assert record["replay_context"]["signal_ts"] == "2026-07-02T10:52:40Z"
    assert record["replay_context"]["earliest_entry_ts"] == "2026-07-02T10:53:00Z"
    assert record["replay_context"]["feed_truth_state"] == "LIVE"
    assert record["replay_context"]["feed_truth_reason_code"] == "OK"
    assert record["replay_context"]["quote_source"] == "tick_store"
    assert record["replay_context"]["quote_age_sec"] == 1.25


def test_replay_context_record_blocks_unavailable_runtime_fields_and_does_not_guess():
    record = build_replay_context_record(
        {
            "generated_epoch": 1_783_049_403.7,
            "regime": "TREND_UP",
            "bid": 112.0,
            "ask": 112.5,
            "quote_source": "tick_store",
            "quote_age_sec": 1.25,
        },
        source="unit_test",
        require_candidate_pool_inputs=False,
    )

    assert record["replay_context_ready"] is False
    assert "missing_feature_cutoff_ts" in record["replay_context_blockers"]
    assert "missing_earliest_entry_ts" in record["replay_context_blockers"]
    assert "missing_is_oos" in record["replay_context_blockers"]
    assert "missing_oos_label" in record["replay_context_blockers"]
    assert record["replay_context"]["feature_cutoff_ts"] is None
    assert record["replay_context"]["earliest_entry_ts"] is None
    assert record["replay_context"]["is_oos"] is None
    assert record["replay_context"]["oos_label"] is None
    assert record["signal_ts_source"] == "derived:generated_epoch"


def test_runtime_candidate_handoff_preserves_available_feed_and_quote_truth():
    payload = build_runtime_candidate_handoff_payload(
        symbol="NIFTY",
        ranked_executable_count=1,
        phase2_input_count=1,
        top_reportable_executable={
            "trade_id": "NIFTY-1",
            "feature_cutoff_ts": "2026-07-02T09:15:00Z",
            "signal_ts": "2026-07-02T09:16:00Z",
            "earliest_entry_ts": "2026-07-02T09:16:30Z",
            "is_oos": False,
            "oos_label": "IS",
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "OK",
            "regime": "TREND_UP",
            "bid": 112.0,
            "ask": 112.5,
            "quote_source": "tick_store",
            "quote_age_sec": 1.0,
            "option_type": "CE",
            "strike": 58500,
            "expiry": "2026-07-07",
        },
        top_opportunities_payload={"source_candidate_count": 1, "top_executable_count": 1},
        generated_epoch=1_000.0,
    )

    assert payload["replay_context_ready"] is True
    assert payload["replay_context_blockers"] == []
    assert payload["replay_context"]["feed_truth_state"] == "LIVE"
    assert payload["replay_context"]["feed_truth_reason_code"] == "OK"
    assert payload["replay_context"]["quote_source"] == "tick_store"
    assert payload["replay_context"]["quote_age_sec"] == 1.0
    assert payload["replay_context"]["feature_cutoff_ts"] == "2026-07-02T09:15:00Z"
    assert payload["replay_context"]["earliest_entry_ts"] == "2026-07-02T09:16:30Z"
    assert payload["replay_context"]["is_oos"] is False
    assert payload["replay_context"]["oos_label"] == "IS"
