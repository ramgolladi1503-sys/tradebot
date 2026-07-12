from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from core.replay_context_bundle_recorder import (
    build_replay_context_bundle_record,
    replay_context_bundle_path,
    write_replay_context_bundle_evidence,
)


class _MappingLike:
    def __init__(self, payload: dict):
        self._payload = dict(payload)

    def to_dict(self) -> dict:
        return dict(self._payload)


def _report() -> SimpleNamespace:
    candidate_pool = _MappingLike(
        {
            "schema_version": 1,
            "symbol": "NIFTY",
            "candidate_count": 1,
            "movement_candidate_count": 1,
            "no_trade_candidate_count": 0,
            "validated_candidate_count": 1,
            "blocked_candidate_count": 0,
            "eligible_candidate_count_before_suppression": 1,
            "report_executable_eligible_count": 1,
            "generator_count": 1,
            "failed_generator_count": 0,
        }
    )
    ranking = _MappingLike({"schema_version": 1, "ranked_report_id": "rank-1", "ranks": []})
    return SimpleNamespace(
        schema_version=1,
        symbol="NIFTY",
        read_only=True,
        append=False,
        raw_candidate_count=1,
        normalized_candidate_count=1,
        ranked_candidate_count=1,
        top_rank_strategy_id="vwap_reclaim_rejection_v1",
        top_rank_score=12.5,
        executable_rank_count=1,
        rankable_candidates=1,
        feed_blocked_candidates=0,
        fallback_blocked_candidates=0,
        stale_blocked_candidates=0,
        real_bid_ask_candidates=1,
        mocked_from_ltp_candidates=0,
        executable_fallback_violations=0,
        blockers=("ok",),
        warnings=(),
        safety_flags=(),
        generated_epoch=1_000.0,
        candidate_pool=candidate_pool,
        ranking=ranking,
    )


def test_bundle_writer_records_available_context_and_isolated_paths(tmp_path):
    source = tmp_path / "replay.jsonl"
    source.write_text(json.dumps({"event_id": "evt-001", "ts": 1_783_049_403.7, "symbol": "NIFTY26JUL58400CE"}) + "\n", encoding="utf-8")
    normalized_snapshot = {
        "schema_version": "1.0",
        "symbol": "NIFTY",
        "spot": 24550.0,
        "ltp": 24550.0,
        "ohlc": {"open": 24500.0, "high": 24600.0, "low": 24480.0, "close": 24550.0},
        "regime": {"primary_regime": "TREND_UP", "scores": {"TREND_UP": 0.71}},
        "option_chain_summary": {"ce_ltp": 112.5, "pe_ltp": 108.0, "ce_spread_pct": 0.02, "pe_spread_pct": 0.02, "ce_depth": 120, "pe_depth": 110},
        "feed_health": {"quote_source": "tick_store", "fallback_used": False, "option_ltp_age_sec": 1.2},
        "quote_truth": {"state": "LIVE"},
        "metadata": {"source": "replay"},
    }
    strategy_context = {
        "symbol": "NIFTY",
        "ts_epoch": 1_783_049_403.7,
        "spot_ltp": 24550.0,
        "open_price": 24500.0,
        "vwap": 24520.0,
        "day_high": 24600.0,
        "day_low": 24480.0,
        "regime_hint": "TREND_UP",
        "regime_scores": {"TREND_UP": 0.71},
        "option_ce_ltp": 112.5,
        "option_pe_ltp": 108.0,
        "ce_spread_pct": 0.02,
        "pe_spread_pct": 0.02,
        "ce_depth": 120,
        "pe_depth": 110,
        "option_ltp_age_sec": 1.2,
        "quote_source": "tick_store",
        "fallback_used": False,
        "metadata": {"vwap_reclaim_up_confirmed": True},
        "feature_cutoff_ts": None,
        "earliest_entry_ts": None,
        "feed_truth_state": None,
        "feed_truth_reason_code": None,
        "feed_truth_source": None,
    }

    bundle = build_replay_context_bundle_record(
        replay_bundle_id="evt-001",
        replay_event_id="evt-001",
        source_path=source,
        source_row_index=0,
        source_timestamp_epoch=1_783_049_403.7,
        raw_row={
            "event_id": "evt-001",
            "ts": 1_783_049_403.7,
            "symbol": "NIFTY26JUL58400CE",
            "quote_source": "replay_source:replay.jsonl",
            "quote_age_sec": 0.0,
            "feature_cutoff_ts": "2026-06-07T09:15:00+05:30",
            "signal_ts": "2026-06-07T09:16:00+05:30",
            "earliest_entry_ts": "2026-06-07T09:16:30+05:30",
            "is_oos": False,
            "oos_label": "IS",
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "OK",
            "feed_truth_source": "joined_feed_truth_artifact",
            "regime": "TREND_UP",
            "option_type": "CE",
            "strike": 58400,
            "expiry": "2026-07-07",
            "bid": 112.0,
            "ask": 112.5,
            "quote_source": "replay_source:replay.jsonl",
            "quote_age_sec": 0.0,
            "trade_builder_raw_count": 1,
            "top_opportunities_source_candidate_count": 1,
            "top_opportunities_executable_count": 1,
            "ranked_total_count": 1,
            "ranked_executable_count": 1,
            "phase2_input_count": 1,
        },
        normalized_snapshot=normalized_snapshot,
        strategy_context=strategy_context,
        report=_report(),
        strategy_id="vwap_reclaim_rejection_v1",
        source_file_sha256="abc123",
        source_row_sha256="def456",
    )

    assert bundle["replay_context_bundle_ready"] is True
    assert bundle["replay_context_bundle_blockers"] == []
    assert bundle["replay_context_ready"] is True
    assert bundle["replay_context_blockers"] == []
    assert bundle["normalized_snapshot"]["symbol"] == "NIFTY"
    assert bundle["strategy_context"]["vwap"] == 24520.0
    assert bundle["candidate_pool_summary"]["candidate_count"] == 1
    assert bundle["ranking_summary"]["ranked_report_id"] == "rank-1"
    assert bundle["source_file_sha256"] == "abc123"
    assert bundle["source_row_sha256"] == "def456"
    assert bundle["replay_context"]["quote_source"] == "replay_source:replay.jsonl"
    assert bundle["replay_context"]["quote_age_sec"] == 0.0
    assert bundle["replay_context"]["feed_truth_source"] == "joined_feed_truth_artifact"
    assert bundle["replay_context"]["feature_cutoff_ts"] == "2026-06-07T09:15:00+05:30"
    assert bundle["replay_context"]["earliest_entry_ts"] == "2026-06-07T09:16:30+05:30"
    assert bundle["replay_context"]["feed_truth_state"] == "LIVE"
    assert bundle["replay_context"]["feed_truth_reason_code"] == "OK"
    assert bundle["replay_context"]["field_sources"]["feature_cutoff_ts_source"] == "preserved:feature_cutoff_ts"
    assert bundle["replay_context"]["field_sources"]["earliest_entry_ts_source"] == "preserved:earliest_entry_ts"
    assert bundle["replay_context"]["field_sources"]["feed_truth_state_source"] == "preserved:feed_truth_state"
    assert bundle["replay_context"]["field_sources"]["feed_truth_reason_code_source"] == "preserved:feed_truth_reason_code"
    assert bundle["replay_context"]["field_sources"]["feed_truth_source_source"] == "preserved:feed_truth_source"

    out = write_replay_context_bundle_evidence(
        output_root=tmp_path / ".runtime" / "replay_context_bundles",
        run_id="run-001",
        bundle_id="evt-001",
        replay_event_id="evt-001",
        source_path=source,
        source_row_index=0,
        source_timestamp_epoch=1_783_049_403.7,
        raw_row={
            "event_id": "evt-001",
            "ts": 1_783_049_403.7,
            "symbol": "NIFTY26JUL58400CE",
            "feature_cutoff_ts": "2026-06-07T09:15:00+05:30",
            "signal_ts": "2026-06-07T09:16:00+05:30",
            "earliest_entry_ts": "2026-06-07T09:16:30+05:30",
            "is_oos": False,
            "oos_label": "IS",
            "feed_truth_state": "LIVE",
            "feed_truth_reason_code": "OK",
            "feed_truth_source": "joined_feed_truth_artifact",
            "regime": "TREND_UP",
            "option_type": "CE",
            "strike": 58400,
            "expiry": "2026-07-07",
            "bid": 112.0,
            "ask": 112.5,
            "quote_source": "replay_source:replay.jsonl",
            "quote_age_sec": 0.0,
            "trade_builder_raw_count": 1,
            "top_opportunities_source_candidate_count": 1,
            "top_opportunities_executable_count": 1,
            "ranked_total_count": 1,
            "ranked_executable_count": 1,
            "phase2_input_count": 1,
        },
        normalized_snapshot=normalized_snapshot,
        strategy_context=strategy_context,
        report=_report(),
        strategy_id="vwap_reclaim_rejection_v1",
        source_file_sha256="abc123",
        source_row_sha256="def456",
    )
    assert out == replay_context_bundle_path(output_root=tmp_path / ".runtime" / "replay_context_bundles", run_id="run-001", bundle_id="evt-001")
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["replay_bundle_id"] == "evt-001"
    assert saved["replay_context_bundle_ready"] is True
    assert saved["production_artifacts_written"] is False
    assert saved["read_only"] is True
    assert saved["broker_api_called"] is False


def test_bundle_writer_blocks_missing_required_context(tmp_path):
    out = write_replay_context_bundle_evidence(
        output_root=tmp_path / ".runtime" / "replay_context_bundles",
        run_id="run-002",
        bundle_id="evt-002",
        replay_event_id="evt-002",
        source_path=tmp_path / "replay.jsonl",
        source_row_index=0,
        source_timestamp_epoch=None,
        raw_row={"event_id": "evt-002"},
        normalized_snapshot={},
        strategy_context={},
        report=None,
        strategy_id=None,
    )
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["replay_context_bundle_ready"] is False
    assert "missing_normalized_snapshot" in saved["replay_context_bundle_blockers"]
    assert "missing_strategy_context" in saved["replay_context_bundle_blockers"]
    assert "missing_feature_cutoff_ts" in saved["replay_context_blockers"]
    assert "missing_signal_ts" in saved["replay_context_blockers"]
    assert "missing_earliest_entry_ts" in saved["replay_context_blockers"]
