from __future__ import annotations

import json

from core.live_truth_stale_candidate_hygiene import (
    CANDIDATE_TIMESTAMP_IN_FUTURE_REASON,
    EXPLICIT_STALE_MARKER_REASON,
    HYGIENE_STATUS_BLOCKED,
    HYGIENE_STATUS_CLEAN,
    HYGIENE_STATUS_STALE,
    INVALID_CANDIDATE_REASON,
    INVALID_HYGIENE_CONFIG_REASON,
    MISSING_CANDIDATE_TIMESTAMP_REASON,
    NO_CANDIDATES_REASON,
    STALE_CANDIDATE_HYGIENE_SOURCE,
    STALE_CANDIDATE_TIMESTAMP_REASON,
    STALE_FEED_REASON,
    STALE_QUOTE_REASON,
    STALE_SOURCE_ARTIFACT_REASON,
    build_stale_candidate_hygiene_report,
    write_stale_candidate_hygiene_evidence,
)


def test_reports_clean_candidates_as_rankable():
    payload = build_stale_candidate_hygiene_report(
        [
            {
                "candidate_id": "c1",
                "generated_epoch": 100.0,
                "quote_age_sec": 5.0,
                "feed_age_sec": 10.0,
                "source_artifact_age_sec": 20.0,
            }
        ],
        now_epoch=110.0,
        candidate_max_age_sec=60.0,
        quote_max_age_sec=30.0,
        feed_max_age_sec=45.0,
        source_artifact_max_age_sec=90.0,
    ).to_payload()

    assert payload["status"] == HYGIENE_STATUS_CLEAN
    assert payload["clean_count"] == 1
    assert payload["rankable_count"] == 1
    assert payload["candidates"][0]["eligible_for_ranking"] is True


def test_reports_no_candidates_as_clean_evidence():
    payload = build_stale_candidate_hygiene_report([], now_epoch=100.0).to_payload()

    assert payload["status"] == HYGIENE_STATUS_CLEAN
    assert payload["reason_code"] == NO_CANDIDATES_REASON
    assert payload["candidate_count"] == 0


def test_flags_stale_candidate_timestamp():
    payload = build_stale_candidate_hygiene_report(
        [{"candidate_id": "old", "generated_epoch": 10.0}],
        now_epoch=100.0,
        candidate_max_age_sec=30.0,
    ).to_payload()

    assert payload["status"] == HYGIENE_STATUS_STALE
    assert payload["reason_code"] == STALE_CANDIDATE_TIMESTAMP_REASON
    assert payload["stale_count"] == 1
    assert payload["rankable_count"] == 0


def test_blocks_missing_candidate_timestamp():
    payload = build_stale_candidate_hygiene_report(
        [{"candidate_id": "missing_ts", "quote_age_sec": 1.0}],
        now_epoch=100.0,
    ).to_payload()

    assert payload["status"] == HYGIENE_STATUS_BLOCKED
    assert payload["reason_code"] == MISSING_CANDIDATE_TIMESTAMP_REASON
    assert payload["blocked_count"] == 1


def test_blocks_invalid_candidate_payload():
    payload = build_stale_candidate_hygiene_report(
        [["not", "a", "mapping"]],
        now_epoch=100.0,
    ).to_payload()

    assert payload["status"] == HYGIENE_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_CANDIDATE_REASON
    assert payload["candidates"][0]["candidate_id"] == "candidate_0"


def test_blocks_future_candidate_timestamp():
    payload = build_stale_candidate_hygiene_report(
        [{"candidate_id": "future", "generated_epoch": 200.0}],
        now_epoch=100.0,
        future_skew_tolerance_sec=5.0,
    ).to_payload()

    assert payload["status"] == HYGIENE_STATUS_BLOCKED
    assert payload["reason_code"] == CANDIDATE_TIMESTAMP_IN_FUTURE_REASON
    assert payload["candidates"][0]["candidate_age_sec"] == 0.0


def test_flags_stale_quote_feed_and_source_artifact_ages():
    payload = build_stale_candidate_hygiene_report(
        [
            {
                "candidate_id": "multi_stale",
                "generated_epoch": 100.0,
                "quote_age_sec": 40.0,
                "feed_age_sec": 60.0,
                "source_artifact_age_sec": 120.0,
            }
        ],
        now_epoch=110.0,
        quote_max_age_sec=30.0,
        feed_max_age_sec=45.0,
        source_artifact_max_age_sec=90.0,
    ).to_payload()

    assert payload["status"] == HYGIENE_STATUS_STALE
    reasons = payload["candidates"][0]["reasons"]
    assert STALE_QUOTE_REASON in reasons
    assert STALE_FEED_REASON in reasons
    assert STALE_SOURCE_ARTIFACT_REASON in reasons


def test_flags_explicit_stale_marker():
    payload = build_stale_candidate_hygiene_report(
        [{"candidate_id": "marked", "generated_epoch": 100.0, "freshness_warning": "stale quote"}],
        now_epoch=101.0,
    ).to_payload()

    assert payload["status"] == HYGIENE_STATUS_STALE
    assert payload["reason_code"] == EXPLICIT_STALE_MARKER_REASON
    assert payload["candidates"][0]["eligible_for_ranking"] is False


def test_accepts_iso_candidate_timestamp():
    payload = build_stale_candidate_hygiene_report(
        [{"candidate_id": "iso", "generated_at": "2026-05-27T10:00:00Z"}],
        now_epoch=1779876030.0,
        candidate_max_age_sec=60.0,
    ).to_payload()

    assert payload["status"] == HYGIENE_STATUS_CLEAN
    assert payload["candidates"][0]["timestamp_key"] == "generated_at"
    assert payload["candidates"][0]["candidate_age_sec"] == 30.0


def test_extracts_candidates_from_top_opportunities_container():
    payload = build_stale_candidate_hygiene_report(
        {
            "top_opportunities": [
                {"candidate_id": "c1", "generated_epoch": 100.0},
                {"candidate_id": "c2", "generated_epoch": 20.0},
            ]
        },
        now_epoch=110.0,
        candidate_max_age_sec=60.0,
    ).to_payload()

    assert payload["candidate_count"] == 2
    assert payload["clean_count"] == 1
    assert payload["stale_count"] == 1


def test_blocks_invalid_config():
    payload = build_stale_candidate_hygiene_report(
        [{"candidate_id": "c1", "generated_epoch": 100.0}],
        now_epoch=100.0,
        quote_max_age_sec=0,
    ).to_payload()

    assert payload["status"] == HYGIENE_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_HYGIENE_CONFIG_REASON


def test_writes_read_only_evidence_file(tmp_path):
    target = tmp_path / "stale_candidate_hygiene_latest.json"
    report = build_stale_candidate_hygiene_report(
        [{"candidate_id": "c1", "generated_epoch": 100.0}],
        now_epoch=101.0,
    )

    out = write_stale_candidate_hygiene_evidence(report, target)

    assert out == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == STALE_CANDIDATE_HYGIENE_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False


def test_payload_is_json_serializable():
    payload = build_stale_candidate_hygiene_report(
        [{"candidate_id": "c1", "generated_epoch": 100.0}],
        now_epoch=101.0,
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["source"] == STALE_CANDIDATE_HYGIENE_SOURCE
    assert decoded["read_only"] is True
    assert decoded["append"] is False
