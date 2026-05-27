from __future__ import annotations

import json

from core.live_truth_sensex_reject_calibration import (
    CALIBRATION_STATUS_BALANCED,
    CALIBRATION_STATUS_BLOCKED,
    CALIBRATION_STATUS_OVERFILTERED,
    CALIBRATION_STATUS_REVIEW,
    INVALID_CONFIG_REASON,
    INVALID_REJECT_REASON,
    MISSING_REJECT_REASON,
    NEAR_MISS_RATE_HIGH_REASON,
    NON_SENSEX_ONLY_REASON,
    REASON_CONCENTRATION_HIGH_REASON,
    REJECT_RATE_HIGH_REASON,
    SENSEX_REJECT_CALIBRATION_SOURCE,
    build_sensex_reject_calibration_report,
    write_sensex_reject_calibration_evidence,
)


def test_reports_balanced_sensex_rejects():
    payload = build_sensex_reject_calibration_report(
        [
            {"symbol": "SENSEX_CE", "decision": "accepted", "score": 0.81, "threshold": 0.70},
            {"symbol": "SENSEX_PE", "reject_reason": "spread_wide", "score": 0.50, "threshold": 0.70},
            {"symbol": "SENSEX_CE_2", "decision": "accepted", "score": 0.77, "threshold": 0.70},
            {"symbol": "SENSEX_PE_2", "reject_reason": "low_volume", "score": 0.45, "threshold": 0.70},
        ],
        max_reject_rate=0.75,
        max_reason_concentration=0.75,
        max_near_miss_rate=0.60,
    ).to_payload()

    assert payload["status"] == CALIBRATION_STATUS_BALANCED
    assert payload["sensex_count"] == 4
    assert payload["rejected_count"] == 2
    assert payload["accepted_count"] == 2
    assert payload["reject_rate"] == 0.5


def test_reports_no_candidates_as_balanced_evidence():
    payload = build_sensex_reject_calibration_report([]).to_payload()

    assert payload["status"] == CALIBRATION_STATUS_BALANCED
    assert payload["total_count"] == 0


def test_reports_review_when_reject_rate_is_high():
    payload = build_sensex_reject_calibration_report(
        [
            {"symbol": "SENSEX_A", "reject_reason": "spread_wide"},
            {"symbol": "SENSEX_B", "reject_reason": "low_volume"},
            {"symbol": "SENSEX_C", "reject_reason": "volatility_low"},
            {"symbol": "SENSEX_D", "decision": "accepted"},
        ],
        max_reject_rate=0.5,
        max_reason_concentration=1.0,
        max_near_miss_rate=1.0,
    ).to_payload()

    assert payload["status"] == CALIBRATION_STATUS_REVIEW
    assert payload["reason_code"] == REJECT_RATE_HIGH_REASON
    assert payload["reject_rate"] == 0.75


def test_reports_review_when_reject_reason_is_concentrated():
    payload = build_sensex_reject_calibration_report(
        [
            {"symbol": "SENSEX_A", "reject_reason": "spread_wide"},
            {"symbol": "SENSEX_B", "reject_reason": "spread_wide"},
            {"symbol": "SENSEX_C", "reject_reason": "spread_wide"},
            {"symbol": "SENSEX_D", "reject_reason": "low_volume"},
            {"symbol": "SENSEX_E", "decision": "accepted"},
        ],
        max_reject_rate=1.0,
        max_reason_concentration=0.5,
        max_near_miss_rate=1.0,
    ).to_payload()

    assert payload["status"] == CALIBRATION_STATUS_REVIEW
    assert payload["reason_code"] == REASON_CONCENTRATION_HIGH_REASON
    assert payload["dominant_reason"] == "spread_wide"
    assert payload["dominant_reason_share"] == 0.75


def test_reports_overfiltered_when_high_rejects_are_near_misses():
    payload = build_sensex_reject_calibration_report(
        [
            {"symbol": "SENSEX_A", "reject_reason": "threshold", "score": 0.66, "threshold": 0.70},
            {"symbol": "SENSEX_B", "reject_reason": "threshold", "score": 0.67, "threshold": 0.70},
            {"symbol": "SENSEX_C", "reject_reason": "threshold", "score": 0.68, "threshold": 0.70},
            {"symbol": "SENSEX_D", "decision": "accepted", "score": 0.75, "threshold": 0.70},
        ],
        max_reject_rate=0.5,
        max_reason_concentration=1.0,
        max_near_miss_rate=0.5,
        near_miss_margin=0.05,
    ).to_payload()

    assert payload["status"] == CALIBRATION_STATUS_OVERFILTERED
    assert REJECT_RATE_HIGH_REASON in payload["reasons"]
    assert NEAR_MISS_RATE_HIGH_REASON in payload["reasons"]
    assert payload["near_miss_rate"] == 1.0


def test_flags_missing_reject_reason():
    payload = build_sensex_reject_calibration_report(
        [
            {"symbol": "SENSEX_A", "decision": "rejected"},
            {"symbol": "SENSEX_B", "decision": "accepted"},
            {"symbol": "SENSEX_C", "reject_reason": "low_volume"},
        ],
        max_reject_rate=1.0,
        max_reason_concentration=1.0,
        max_near_miss_rate=1.0,
    ).to_payload()

    assert payload["status"] == CALIBRATION_STATUS_REVIEW
    assert MISSING_REJECT_REASON in payload["reasons"]


def test_blocks_invalid_payload():
    payload = build_sensex_reject_calibration_report(
        [["bad", "payload"]],
    ).to_payload()

    assert payload["status"] == CALIBRATION_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_REJECT_REASON
    assert payload["invalid_count"] == 1


def test_blocks_invalid_config():
    payload = build_sensex_reject_calibration_report(
        [{"symbol": "SENSEX_A", "reject_reason": "spread_wide"}],
        max_reject_rate=1.5,
    ).to_payload()

    assert payload["status"] == CALIBRATION_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_CONFIG_REASON


def test_non_sensex_only_is_balanced():
    payload = build_sensex_reject_calibration_report(
        [
            {"symbol": "NIFTY_A", "reject_reason": "spread_wide"},
            {"symbol": "BANKNIFTY_B", "decision": "accepted"},
        ],
    ).to_payload()

    assert payload["status"] == CALIBRATION_STATUS_BALANCED
    assert payload["reason_code"] == NON_SENSEX_ONLY_REASON
    assert payload["sensex_count"] == 0


def test_extracts_candidates_from_container():
    payload = build_sensex_reject_calibration_report(
        {
            "rejected_candidates": [
                {"symbol": "SENSEX_A", "reject_reason": "spread_wide"},
                {"symbol": "SENSEX_B", "decision": "accepted"},
                {"symbol": "SENSEX_C", "reject_reason": "low_volume"},
            ]
        },
        max_reject_rate=1.0,
        max_reason_concentration=1.0,
        max_near_miss_rate=1.0,
    ).to_payload()

    assert payload["sensex_count"] == 3
    assert payload["rejected_count"] == 2
    assert payload["accepted_count"] == 1


def test_writes_read_only_evidence_file(tmp_path):
    target = tmp_path / "sensex_reject_calibration_latest.json"
    report = build_sensex_reject_calibration_report(
        [
            {"symbol": "SENSEX_A", "reject_reason": "spread_wide"},
            {"symbol": "SENSEX_B", "decision": "accepted"},
            {"symbol": "SENSEX_C", "reject_reason": "low_volume"},
        ],
        max_reject_rate=1.0,
        max_reason_concentration=1.0,
        max_near_miss_rate=1.0,
    )

    out = write_sensex_reject_calibration_evidence(report, target)

    assert out == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == SENSEX_REJECT_CALIBRATION_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False


def test_payload_is_json_serializable():
    payload = build_sensex_reject_calibration_report(
        [
            {"symbol": "SENSEX_A", "reject_reason": "spread_wide"},
            {"symbol": "SENSEX_B", "decision": "accepted"},
            {"symbol": "SENSEX_C", "reject_reason": "low_volume"},
        ],
        max_reject_rate=1.0,
        max_reason_concentration=1.0,
        max_near_miss_rate=1.0,
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["source"] == SENSEX_REJECT_CALIBRATION_SOURCE
    assert decoded["read_only"] is True
    assert decoded["append"] is False
