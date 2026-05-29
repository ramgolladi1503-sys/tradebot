from __future__ import annotations

import json

from core.runtime_candidate_handoff_root_cause import (
    build_candidate_handoff_root_cause_payload,
    write_candidate_handoff_root_cause_latest,
)


def _candidate(primary_blocker: str | None = None, **extra):
    row = {}
    if primary_blocker is not None:
        row["primary_blocker"] = primary_blocker
    row.update(extra)
    return row


def test_root_cause_counters_split_feed_vs_indicator(tmp_path):
    raw = [_candidate("FEED_STALE") for _ in range(8)] + [_candidate("INDICATORS_MISSING") for _ in range(2)]
    payload = build_candidate_handoff_root_cause_payload(
        cycle_ts_epoch=100.0,
        strategy_generated_count=10,
        phase2_raw_candidates=raw,
        phase2_ranked_count=0,
    )
    assert payload["strategy_generated_count"] == 10
    assert payload["phase2_raw_count"] == 10
    assert payload["phase2_ranked_count"] == 0
    assert payload["feed_blocked_count"] == 8
    assert payload["indicator_missing_count"] == 2
    assert payload["unknown_drop_reason_count"] == 0

    logs_path = tmp_path / "logs" / "candidate_handoff_latest.json"
    runtime_path = tmp_path / ".runtime" / "candidate_handoff_latest.json"
    write_candidate_handoff_root_cause_latest(payload=payload, logs_path=logs_path, runtime_path=runtime_path)
    assert json.loads(logs_path.read_text())["feed_blocked_count"] == 8
    assert json.loads(runtime_path.read_text())["indicator_missing_count"] == 2


def test_root_cause_counts_phase2_raw_and_ranked(tmp_path):
    raw = [_candidate("OK") for _ in range(4)]
    payload = build_candidate_handoff_root_cause_payload(
        cycle_ts_epoch=200.0,
        strategy_generated_count=10,
        phase2_raw_candidates=raw,
        phase2_ranked_count=2,
    )
    assert payload["strategy_generated_count"] == 10
    assert payload["phase2_raw_count"] == 4
    assert payload["phase2_ranked_count"] == 2


def test_unknown_blocker_maps_to_unknown_bucket():
    raw = [_candidate(None, gate_reasons=["SOME_NEW_REASON_CODE"])]
    payload = build_candidate_handoff_root_cause_payload(
        cycle_ts_epoch=300.0,
        strategy_generated_count=1,
        phase2_raw_candidates=raw,
        phase2_ranked_count=0,
    )
    assert payload["unknown_drop_reason_count"] == 1
    assert payload["top_drop_reasons"]
