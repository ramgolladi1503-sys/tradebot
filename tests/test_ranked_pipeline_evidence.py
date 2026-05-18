from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from core.ranked_pipeline_evidence import (
    DAILY_FILENAME_PREFIX,
    LATEST_FILENAME,
    RankedPipelineEvidenceError,
    build_ranked_pipeline_evidence_payload,
    write_ranked_pipeline_evidence,
)


def _report(**overrides):
    payload = {
        "schema_version": 1,
        "symbol": "NIFTY",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "pipeline_stage_order": [
            "candidate_pool",
            "normalization",
            "classification",
            "hard_downgrade",
            "opportunity_scoring",
            "directional_balance",
            "candidate_ranking",
        ],
        "ranked_candidate_count": 1,
        "top_rank_strategy_id": "call_high",
        "blockers": [],
        "warnings": [],
        "safety_flags": [],
        "metadata": {
            "orchestrator": "ranked_opportunity_pipeline_v1",
            "scope": "read_only_no_execution_no_dashboard_no_live_wiring",
        },
    }
    payload.update(overrides)
    return payload


def test_build_evidence_payload_is_json_safe_and_does_not_mutate_source():
    report = _report(extra_tuple=("a", "b"))
    before = deepcopy(report)
    now = datetime(2026, 5, 18, 6, 30, tzinfo=timezone.utc)

    payload = build_ranked_pipeline_evidence_payload(report, now=now)

    assert report == before
    assert payload["schema_version"] == 1
    assert payload["event"] == "RANKED_PIPELINE_RUNTIME_EVIDENCE"
    assert payload["ts"] == "2026-05-18T06:30:00+00:00"
    assert payload["session_date"] == "2026-05-18"
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["report"]["extra_tuple"] == ["a", "b"]
    assert len(payload["evidence_hash"]) == 64


def test_write_ranked_pipeline_evidence_writes_latest_and_daily_jsonl(tmp_path):
    now = datetime(2026, 5, 18, 6, 30, tzinfo=timezone.utc)

    result = write_ranked_pipeline_evidence(_report(), output_dir=tmp_path, now=now)

    latest_path = tmp_path / LATEST_FILENAME
    daily_path = tmp_path / f"{DAILY_FILENAME_PREFIX}_2026-05-18.jsonl"
    assert result.latest_path == str(latest_path)
    assert result.daily_path == str(daily_path)
    assert result.latest_written is True
    assert result.daily_appended is True
    assert result.is_order_action is False
    assert result.append is False
    assert latest_path.exists()
    assert daily_path.exists()

    latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
    daily_lines = [json.loads(line) for line in daily_path.read_text(encoding="utf-8").splitlines()]
    assert len(daily_lines) == 1
    assert latest_payload == daily_lines[0]
    assert latest_payload["evidence_hash"] == result.evidence_hash
    assert latest_payload["report"]["top_rank_strategy_id"] == "call_high"


def test_write_ranked_pipeline_evidence_overwrites_latest_and_appends_daily(tmp_path):
    first_now = datetime(2026, 5, 18, 6, 30, tzinfo=timezone.utc)
    second_now = datetime(2026, 5, 18, 6, 31, tzinfo=timezone.utc)

    first = write_ranked_pipeline_evidence(_report(top_rank_strategy_id="call_high"), output_dir=tmp_path, now=first_now)
    second = write_ranked_pipeline_evidence(_report(top_rank_strategy_id="put_high"), output_dir=tmp_path, now=second_now)

    latest_payload = json.loads((tmp_path / LATEST_FILENAME).read_text(encoding="utf-8"))
    daily_path = tmp_path / f"{DAILY_FILENAME_PREFIX}_2026-05-18.jsonl"
    daily_lines = [json.loads(line) for line in daily_path.read_text(encoding="utf-8").splitlines()]

    assert first.evidence_hash != second.evidence_hash
    assert latest_payload["report"]["top_rank_strategy_id"] == "put_high"
    assert len(daily_lines) == 2
    assert daily_lines[0]["report"]["top_rank_strategy_id"] == "call_high"
    assert daily_lines[1]["report"]["top_rank_strategy_id"] == "put_high"


def test_write_accepts_report_object_with_to_dict(tmp_path):
    class _Report:
        def to_dict(self):
            return _report(top_rank_strategy_id="object_report")

    result = write_ranked_pipeline_evidence(
        _Report(),
        output_dir=tmp_path,
        now=datetime(2026, 5, 18, 6, 30, tzinfo=timezone.utc),
    )

    latest_payload = json.loads((tmp_path / LATEST_FILENAME).read_text(encoding="utf-8"))
    assert result.latest_written is True
    assert latest_payload["report"]["top_rank_strategy_id"] == "object_report"


@pytest.mark.parametrize(
    "bad_report,error_text",
    [
        (_report(read_only=False), "ranked_pipeline_report_not_read_only"),
        (_report(is_order_action=True), "ranked_pipeline_report_contains_order_action"),
        (_report(append=True), "ranked_pipeline_report_append_true"),
        (_report(metadata={}), "ranked_pipeline_non_canonical_orchestrator"),
        (_report(metadata={"orchestrator": "legacy_opportunity_engine"}), "ranked_pipeline_non_canonical_orchestrator"),
    ],
)
def test_rejects_unsafe_or_non_canonical_reports(bad_report, error_text):
    with pytest.raises(RankedPipelineEvidenceError) as exc_info:
        build_ranked_pipeline_evidence_payload(bad_report)

    assert error_text in str(exc_info.value)


def test_rejects_invalid_report_object():
    with pytest.raises(RankedPipelineEvidenceError) as exc_info:
        build_ranked_pipeline_evidence_payload(object())

    assert "ranked_pipeline_report_missing_or_invalid" in str(exc_info.value)
