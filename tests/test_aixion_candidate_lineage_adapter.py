from __future__ import annotations

from datetime import datetime, timezone

from aixion_trade_intelligence.adapters.candidate_lineage import (
    adapt_candidate_lineage_row,
    candidate_lineage_event_type,
)


def test_candidate_lineage_event_mapping():
    assert candidate_lineage_event_type({"stage": "generated", "stage_status": "generated"}) == "SIGNAL_GENERATED"
    assert candidate_lineage_event_type({"stage": "phase2", "stage_status": "blocked"}) == "CANDIDATE_BLOCKED"
    assert candidate_lineage_event_type({"stage": "phase2", "stage_status": "selected"}) == "CANDIDATE_RANKED"


def test_candidate_lineage_adapter_preserves_block_truth():
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    event = adapt_candidate_lineage_row(
        {
            "timestamp": now.isoformat(),
            "cycle_id": "cycle-1",
            "candidate_id": "cand-1",
            "strategy_name": "trend_pullback",
            "stage": "phase2",
            "stage_status": "blocked",
            "block_reason": "STALE_OPTION_TICK",
            "stale_quote": True,
            "executable": False,
        },
        session_id="session-1",
        producer_sequence=1,
        observed_at=now,
    )
    assert event.event_type == "CANDIDATE_BLOCKED"
    assert event.data_quality_state == "DEGRADED"
    assert event.payload["reason"] == "STALE_OPTION_TICK"
    assert event.payload["stale_quote"] is True
