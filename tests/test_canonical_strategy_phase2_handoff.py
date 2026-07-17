from __future__ import annotations

import json
from pathlib import Path

import core.orchestrator as orchestrator
from core.canonical_ranked_ui_adapter import adapt_candidate_rank_record_to_ui
from core.runtime_snapshot_store import build_snapshot_envelope
from dashboard.readers.snapshot_reader import read_snapshot_payload


def _canonical_record(**overrides):
    base = {
        "ranked_report_id": "ranked-report-1",
        "candidate_id": "cand-1",
        "strategy_id": "opening_range_retest_v1",
        "rank": 1,
        "bucket": "EXECUTABLE_CANDIDATE",
        "score_eligibility": "SCORE_ELIGIBLE",
        "final_score": 0.71,
        "executable_candidate": True,
        "rank_reason": "unit_test",
        "blockers": [],
        "warnings": [],
        "safety_flags": [],
        "generated_epoch": 1_000.0,
    }
    base.update(overrides)
    return base


def _live_row(**overrides):
    base = {
        "trade_id": "LIVE-1",
        "symbol": "NIFTY",
        "strategy_family": "trend",
        "candidate_type": "directional",
        "candidate_status": "executable",
        "execution_status": "executable",
        "execution_entry_status": "executable",
        "execution_ok": True,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "reportable_executable": True,
        "execution_entry": 101.0,
        "execution_entry_source": "ask",
        "display_entry": 101.0,
        "display_entry_source": "ask",
        "quote_source": "tick_store",
        "is_executable": True,
        "final_score": 0.58,
        "rank_score": 0.58,
        "raw_score": 0.42,
        "phase2_score": 0.63,
        "fallback_state": "none",
        "reason": "ok",
        "blockers": [],
        "hard_blockers": [],
        "source_flags": {},
    }
    base.update(overrides)
    return base


def _write_snapshot(tmp_path: Path, payload: dict) -> Path:
    snapshot_path = tmp_path / "top_opportunities_latest.json"
    snapshot_path.write_text(
        json.dumps(
            build_snapshot_envelope(
                payload=payload,
                producer="unit-test",
            ),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return snapshot_path


def test_canonical_score_separation_preserves_rank_score_and_missing_phase2_score():
    row = adapt_candidate_rank_record_to_ui(
        _canonical_record(raw_strategy_score=0.42, phase2_score=None, final_score=0.71)
    )

    assert row["rank_score"] == 0.71
    assert row["final_score"] == 0.71
    assert row["raw_strategy_score"] == 0.42
    assert "phase2_score" not in row


def test_canonical_missing_raw_score_stays_missing():
    row = adapt_candidate_rank_record_to_ui(_canonical_record())

    assert row["rank_score"] == 0.71
    assert row["final_score"] == 0.71
    assert "raw_strategy_score" not in row
    assert "phase2_score" not in row


def test_live_phase2_payload_preserves_distinct_score_ownership(monkeypatch):
    monkeypatch.setattr(orchestrator, "_filter_invalid_cycle_candidates", lambda candidates, symbol=None: (list(candidates), []), raising=True)
    monkeypatch.setattr(orchestrator, "project_advisory_row", lambda candidate: dict(candidate), raising=True)
    monkeypatch.setattr(
        orchestrator,
        "run_engine_phase2",
        lambda candidates, **kwargs: {
            "state": "ENTER",
            "reason": "unit_test",
            "selected": _live_row(trade_id="LIVE-1"),
            "ranked": [_live_row(trade_id="LIVE-1"), _live_row(trade_id="LIVE-2", reportable_executable=False, execution_allowed=False, eligible_for_execution=False, candidate_status="advisory_only", execution_status="queue_only", execution_entry_status="non_executable", permission="QUEUE_ONLY", final_action="QUEUE_ONLY", readiness="QUEUE_ONLY", execution_entry=None, execution_entry_source="none", display_entry=101.0, display_entry_source="mark", fallback_state="none", raw_score=None, phase2_score=None, rank_score=0.44, final_score=0.44)],
            "next_active_trade": None,
        },
        raising=True,
    )

    payload = orchestrator._build_top_opportunities_payload(
        candidates=[_live_row(trade_id="LIVE-1")],
        executable_top_n=1,
        advisory_top_n=1,
        execution_truth_context=None,
        cycle_primary_reason="unit_test",
    )

    row = payload["top_executable_opportunities"][0]
    assert row["rank_score"] == 0.58
    assert row["raw_strategy_score"] == 0.42
    assert row["phase2_score"] == 0.63
    assert row["execution_eligibility"] is True


def test_execution_critical_fallback_rows_do_not_survive_executable_reader(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "_filter_invalid_cycle_candidates", lambda candidates, symbol=None: (list(candidates), []), raising=True)
    monkeypatch.setattr(orchestrator, "project_advisory_row", lambda candidate: dict(candidate), raising=True)
    monkeypatch.setattr(
        orchestrator,
        "run_engine_phase2",
        lambda candidates, **kwargs: {
            "state": "ENTER",
            "reason": "unit_test",
            "selected": _live_row(
                trade_id="FALLBACK-1",
                quote_source="rest_fallback",
                execution_entry_source="recovered_fallback",
                display_entry_source="recovered_fallback",
                fallback_state="recovered_fallback",
                reportable_executable=True,
                execution_allowed=True,
                eligible_for_execution=True,
                raw_score=None,
                phase2_score=None,
                rank_score=0.61,
                final_score=0.61,
            ),
            "ranked": [],
            "next_active_trade": None,
        },
        raising=True,
    )

    payload = orchestrator._build_top_opportunities_payload(
        candidates=[_live_row(trade_id="FALLBACK-1", quote_source="rest_fallback", execution_entry_source="recovered_fallback", display_entry_source="recovered_fallback", fallback_state="recovered_fallback")],
        executable_top_n=1,
        advisory_top_n=1,
        execution_truth_context=None,
        cycle_primary_reason="unit_test",
    )
    snapshot_path = _write_snapshot(tmp_path, payload)
    normalized = read_snapshot_payload(snapshot_path)
    normalized_payload = normalized["payload"]

    assert normalized["state"] == "ok"
    assert normalized_payload["top_executable_opportunities"] == []
    assert normalized_payload["top_advisory_opportunities"][0]["trade_id"] == "FALLBACK-1"
    assert normalized_payload["top_advisory_opportunities"][0]["top_opportunity_truth_reason"] == "fallback_source_advisory_only"


def test_canonical_alias_bucket_does_not_grant_execution_authority(tmp_path):
    payload = {
        "top_executable_opportunities": [
            {
                "trade_id": "CANON-1",
                "symbol": "NIFTY",
                "execution_entry": 101.0,
                "execution_entry_source": "ask",
                "execution_entry_status": "executable",
                "display_entry": 101.0,
                "display_entry_source": "ask",
                "entry": 101.0,
                "entry_source": "ask",
                "quote_source": "tick_store",
                "is_executable": True,
                "execution_status": "executable",
                "readiness": "READY",
                "permission": "EXECUTE",
                "final_action": "EXECUTE",
                "execution_eligibility": False,
                "execution_eligibility_authority": "CANONICAL_RANKED_SNAPSHOT",
                "pipeline_source": "CANONICAL_RANKED_SNAPSHOT",
                "status_authority": "CANONICAL_CANDIDATE_POOL",
                "rank_authority": "CANONICAL_RANKING",
                "rank_score": 0.71,
                "final_score": 0.71,
            }
        ],
        "top_advisory_opportunities": [],
    }
    snapshot_path = _write_snapshot(tmp_path, payload)
    normalized = read_snapshot_payload(snapshot_path)
    normalized_payload = normalized["payload"]

    assert normalized_payload["top_executable_opportunities"] == []
    assert normalized_payload["top_advisory_opportunities"][0]["trade_id"] == "CANON-1"
    assert normalized_payload["top_advisory_opportunities"][0]["top_opportunity_truth_reason"] == "execution_not_eligible"


def test_live_executable_rows_remain_executable_through_reader(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "_filter_invalid_cycle_candidates", lambda candidates, symbol=None: (list(candidates), []), raising=True)
    monkeypatch.setattr(orchestrator, "project_advisory_row", lambda candidate: dict(candidate), raising=True)
    monkeypatch.setattr(
        orchestrator,
        "run_engine_phase2",
        lambda candidates, **kwargs: {
            "state": "ENTER",
            "reason": "unit_test",
            "selected": _live_row(trade_id="LIVE-OK", raw_score=0.42, phase2_score=0.63, rank_score=0.58, final_score=0.58),
            "ranked": [_live_row(trade_id="LIVE-OK", raw_score=0.42, phase2_score=0.63, rank_score=0.58, final_score=0.58)],
            "next_active_trade": None,
        },
        raising=True,
    )

    payload = orchestrator._build_top_opportunities_payload(
        candidates=[_live_row(trade_id="LIVE-OK", raw_score=0.42, phase2_score=0.63, rank_score=0.58, final_score=0.58)],
        executable_top_n=1,
        advisory_top_n=1,
        execution_truth_context=None,
        cycle_primary_reason="unit_test",
    )
    snapshot_path = _write_snapshot(tmp_path, payload)
    normalized = read_snapshot_payload(snapshot_path)
    normalized_payload = normalized["payload"]

    assert normalized_payload["top_executable_opportunities"][0]["trade_id"] == "LIVE-OK"
    assert normalized_payload["top_executable_opportunities"][0]["execution_eligibility"] is True
    assert normalized_payload["top_executable_opportunities"][0]["rank_score"] == 0.58
    assert normalized_payload["top_executable_opportunities"][0]["raw_strategy_score"] == 0.42
    assert normalized_payload["top_executable_opportunities"][0]["phase2_score"] == 0.63
