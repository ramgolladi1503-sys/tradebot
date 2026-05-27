from __future__ import annotations

import json

from core.live_truth_strategy_perf_shadow_fallback import (
    ESTIMATED_RATE_HIGH_REASON,
    FALLBACK_RATE_HIGH_REASON,
    INVALID_CONFIG_REASON,
    INVALID_PERF_ROW_REASON,
    LOW_SAMPLE_SHADOW_REASON,
    MISSING_TRUST_FIELD_REASON,
    NO_PERF_ROWS_REASON,
    PERF_STATUS_BLOCKED,
    PERF_STATUS_REVIEW,
    PERF_STATUS_SHADOWED,
    PERF_STATUS_TRUSTED,
    RECOVERED_RATE_HIGH_REASON,
    SHADOW_RATE_HIGH_REASON,
    STRATEGY_PERF_SHADOW_FALLBACK_SOURCE,
    build_strategy_perf_shadow_fallback_report,
    write_strategy_perf_shadow_fallback_evidence,
)


def test_reports_trusted_strategy_perf_rows():
    payload = build_strategy_perf_shadow_fallback_report(
        [
            {"strategy": "breakout", "sample_count": 10, "source": "actual", "fallback": False},
            {"strategy": "vwap", "sample_count": 8, "source": "real", "estimated": False},
            {"strategy": "mean_reversion", "sample_count": 6, "source": "actual", "recovered": False},
        ]
    ).to_payload()

    assert payload["status"] == PERF_STATUS_TRUSTED
    assert payload["valid_row_count"] == 3
    assert payload["trusted_count"] == 3
    assert payload["fallback_rate"] == 0.0
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False


def test_blocks_when_no_strategy_perf_rows_exist():
    payload = build_strategy_perf_shadow_fallback_report([]).to_payload()

    assert payload["status"] == PERF_STATUS_BLOCKED
    assert payload["reason_code"] == NO_PERF_ROWS_REASON
    assert payload["row_count"] == 0


def test_blocks_invalid_payload():
    payload = build_strategy_perf_shadow_fallback_report([["bad", "payload"]]).to_payload()

    assert payload["status"] == PERF_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_PERF_ROW_REASON
    assert payload["valid_row_count"] == 0


def test_blocks_invalid_config():
    payload = build_strategy_perf_shadow_fallback_report(
        [{"strategy": "breakout", "sample_count": 5, "source": "actual"}],
        max_fallback_rate=1.5,
    ).to_payload()

    assert payload["status"] == PERF_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_CONFIG_REASON


def test_reports_shadowed_when_fallback_rate_is_above_limit():
    payload = build_strategy_perf_shadow_fallback_report(
        [
            {"strategy": "breakout", "sample_count": 10, "fallback": True, "source": "fallback_perf"},
            {"strategy": "vwap", "sample_count": 9, "fallback": False, "source": "actual"},
        ],
        max_fallback_rate=0.0,
        max_shadow_rate=1.0,
        max_estimated_rate=1.0,
        max_recovered_rate=1.0,
    ).to_payload()

    assert payload["status"] == PERF_STATUS_SHADOWED
    assert payload["reason_code"] == FALLBACK_RATE_HIGH_REASON
    assert payload["fallback_count"] == 1
    assert payload["fallback_rate"] == 0.5


def test_reports_shadowed_when_shadow_fallback_rate_is_above_limit():
    payload = build_strategy_perf_shadow_fallback_report(
        [
            {"strategy": "breakout", "sample_count": 10, "shadow_fallback": True},
            {"strategy": "vwap", "sample_count": 9, "source": "actual"},
        ],
        max_fallback_rate=1.0,
        max_shadow_rate=0.0,
        max_estimated_rate=1.0,
        max_recovered_rate=1.0,
    ).to_payload()

    assert payload["status"] == PERF_STATUS_SHADOWED
    assert payload["reason_code"] == SHADOW_RATE_HIGH_REASON
    assert payload["shadow_fallback_count"] == 1


def test_reports_review_when_estimated_rate_is_high():
    payload = build_strategy_perf_shadow_fallback_report(
        [
            {"strategy": "breakout", "sample_count": 10, "estimated": True},
            {"strategy": "vwap", "sample_count": 9, "source": "actual"},
        ],
        max_fallback_rate=1.0,
        max_shadow_rate=1.0,
        max_estimated_rate=0.25,
        max_recovered_rate=1.0,
    ).to_payload()

    assert payload["status"] == PERF_STATUS_REVIEW
    assert payload["reason_code"] == ESTIMATED_RATE_HIGH_REASON
    assert payload["estimated_rate"] == 0.5


def test_reports_review_when_recovered_rate_is_high():
    payload = build_strategy_perf_shadow_fallback_report(
        [
            {"strategy": "breakout", "sample_count": 10, "recovered_fallback": True},
            {"strategy": "vwap", "sample_count": 9, "source": "actual"},
        ],
        max_fallback_rate=1.0,
        max_shadow_rate=1.0,
        max_estimated_rate=1.0,
        max_recovered_rate=0.25,
    ).to_payload()

    assert payload["status"] == PERF_STATUS_REVIEW
    assert payload["reason_code"] == RECOVERED_RATE_HIGH_REASON
    assert payload["recovered_rate"] == 0.5


def test_reports_review_when_trust_fields_are_missing():
    payload = build_strategy_perf_shadow_fallback_report(
        [
            {"strategy": "breakout", "sample_count": 10},
            {"strategy": "vwap", "sample_count": 9, "source": "actual"},
        ],
        max_fallback_rate=1.0,
        max_shadow_rate=1.0,
        max_estimated_rate=1.0,
        max_recovered_rate=1.0,
    ).to_payload()

    assert payload["status"] == PERF_STATUS_REVIEW
    assert payload["reason_code"] == MISSING_TRUST_FIELD_REASON
    assert MISSING_TRUST_FIELD_REASON in payload["reasons"]


def test_low_sample_shadow_is_review_when_not_fallback_rate_blocking():
    payload = build_strategy_perf_shadow_fallback_report(
        [
            {"strategy": "breakout", "sample_count": 1, "estimated": True},
            {"strategy": "vwap", "sample_count": 9, "source": "actual"},
        ],
        max_fallback_rate=1.0,
        max_shadow_rate=1.0,
        max_estimated_rate=1.0,
        max_recovered_rate=1.0,
        min_sample_count=3,
    ).to_payload()

    assert payload["status"] == PERF_STATUS_REVIEW
    assert LOW_SAMPLE_SHADOW_REASON in payload["reasons"]
    assert payload["low_sample_shadow_count"] == 1


def test_extracts_rows_from_container_mapping():
    payload = build_strategy_perf_shadow_fallback_report(
        {
            "strategy_performance": {
                "breakout": {"strategy": "breakout", "sample_count": 10, "source": "actual"},
                "vwap": {"strategy": "vwap", "sample_count": 9, "source": "actual"},
            }
        }
    ).to_payload()

    assert payload["status"] == PERF_STATUS_TRUSTED
    assert payload["valid_row_count"] == 2


def test_writes_read_only_evidence_file(tmp_path):
    target = tmp_path / "strategy_perf_shadow_fallback_latest.json"
    report = build_strategy_perf_shadow_fallback_report(
        [
            {"strategy": "breakout", "sample_count": 10, "source": "actual"},
            {"strategy": "vwap", "sample_count": 9, "source": "actual"},
        ]
    )

    out = write_strategy_perf_shadow_fallback_evidence(report, target)

    assert out == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == STRATEGY_PERF_SHADOW_FALLBACK_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False


def test_payload_is_json_serializable():
    payload = build_strategy_perf_shadow_fallback_report(
        [
            {"strategy": "breakout", "sample_count": 10, "source": "actual"},
            {"strategy": "vwap", "sample_count": 9, "source": "actual"},
        ]
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["source"] == STRATEGY_PERF_SHADOW_FALLBACK_SOURCE
    assert decoded["read_only"] is True
    assert decoded["append"] is False
