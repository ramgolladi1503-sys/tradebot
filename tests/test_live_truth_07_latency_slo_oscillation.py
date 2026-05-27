from __future__ import annotations

import json

from core.live_truth_latency_slo_oscillation import (
    COOLDOWN_THRASH_REASON,
    HIGH_LATENCY_REASON,
    INVALID_CONFIG_REASON,
    INVALID_SAMPLE_REASON,
    LATENCY_SLO_SOURCE,
    LOOP_MODE_THRASH_REASON,
    NO_SAMPLES_REASON,
    RECOVERY_OSCILLATION_REASON,
    SLO_STATE_FLAP_REASON,
    SLO_STATUS_BLOCKED,
    SLO_STATUS_DEGRADED,
    SLO_STATUS_OSCILLATING,
    SLO_STATUS_STABLE,
    build_latency_slo_oscillation_report,
    write_latency_slo_oscillation_evidence,
)


def test_reports_stable_when_latency_and_states_are_stable():
    payload = build_latency_slo_oscillation_report(
        [
            {"latency_ms": 100.0, "slo_state": "ok", "cooldown_active": False, "loop_mode": "normal"},
            {"latency_ms": 120.0, "slo_state": "ok", "cooldown_active": False, "loop_mode": "normal"},
            {"latency_ms": 110.0, "slo_state": "ok", "cooldown_active": False, "loop_mode": "normal"},
        ],
        latency_threshold_ms=500.0,
    ).to_payload()

    assert payload["status"] == SLO_STATUS_STABLE
    assert payload["valid_sample_count"] == 3
    assert payload["max_latency_ms"] == 120.0
    assert payload["avg_latency_ms"] == 110.0
    assert payload["slo_state_flip_count"] == 0


def test_reports_no_samples_as_stable_evidence():
    payload = build_latency_slo_oscillation_report([], latency_threshold_ms=500.0).to_payload()

    assert payload["status"] == SLO_STATUS_STABLE
    assert payload["reason_code"] == NO_SAMPLES_REASON
    assert payload["sample_count"] == 0


def test_reports_degraded_when_latency_exceeds_threshold_without_state_flaps():
    payload = build_latency_slo_oscillation_report(
        [
            {"latency_ms": 100.0, "slo_state": "ok"},
            {"latency_ms": 900.0, "slo_state": "ok"},
            {"latency_ms": 120.0, "slo_state": "ok"},
        ],
        latency_threshold_ms=500.0,
    ).to_payload()

    assert payload["status"] == SLO_STATUS_DEGRADED
    assert payload["reason_code"] == HIGH_LATENCY_REASON
    assert payload["max_latency_ms"] == 900.0


def test_reports_oscillation_when_slo_state_flaps_too_often():
    payload = build_latency_slo_oscillation_report(
        [
            {"latency_ms": 100.0, "slo_state": "ok"},
            {"latency_ms": 110.0, "slo_state": "breached"},
            {"latency_ms": 120.0, "slo_state": "ok"},
            {"latency_ms": 130.0, "slo_state": "breached"},
        ],
        latency_threshold_ms=500.0,
        max_state_flips=2,
    ).to_payload()

    assert payload["status"] == SLO_STATUS_OSCILLATING
    assert payload["reason_code"] == SLO_STATE_FLAP_REASON
    assert payload["slo_state_flip_count"] == 3


def test_reports_oscillation_for_cooldown_loop_and_recovery_flaps():
    payload = build_latency_slo_oscillation_report(
        [
            {"latency_ms": 100.0, "cooldown_active": False, "loop_mode": "normal", "recovery_state": "idle"},
            {"latency_ms": 100.0, "cooldown_active": True, "loop_mode": "hold", "recovery_state": "retry"},
            {"latency_ms": 100.0, "cooldown_active": False, "loop_mode": "normal", "recovery_state": "idle"},
            {"latency_ms": 100.0, "cooldown_active": True, "loop_mode": "hold", "recovery_state": "retry"},
        ],
        latency_threshold_ms=500.0,
        max_state_flips=2,
    ).to_payload()

    assert payload["status"] == SLO_STATUS_OSCILLATING
    assert COOLDOWN_THRASH_REASON in payload["reasons"]
    assert LOOP_MODE_THRASH_REASON in payload["reasons"]
    assert RECOVERY_OSCILLATION_REASON in payload["reasons"]


def test_blocks_invalid_sample_payload():
    payload = build_latency_slo_oscillation_report(
        [["bad", "sample"]],
        latency_threshold_ms=500.0,
    ).to_payload()

    assert payload["status"] == SLO_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_SAMPLE_REASON
    assert payload["samples"][0]["valid"] is False


def test_blocks_missing_latency_sample():
    payload = build_latency_slo_oscillation_report(
        [{"slo_state": "ok"}],
        latency_threshold_ms=500.0,
    ).to_payload()

    assert payload["status"] == SLO_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_SAMPLE_REASON


def test_blocks_invalid_config():
    payload = build_latency_slo_oscillation_report(
        [{"latency_ms": 100.0}],
        latency_threshold_ms=0,
    ).to_payload()

    assert payload["status"] == SLO_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_CONFIG_REASON


def test_extracts_samples_from_container():
    payload = build_latency_slo_oscillation_report(
        {
            "latency_samples": [
                {"latency_ms": 100.0, "slo_state": "ok"},
                {"latency_ms": 150.0, "slo_state": "ok"},
                {"latency_ms": 200.0, "slo_state": "ok"},
            ]
        },
        latency_threshold_ms=500.0,
    ).to_payload()

    assert payload["status"] == SLO_STATUS_STABLE
    assert payload["sample_count"] == 3
    assert payload["max_latency_ms"] == 200.0


def test_writes_read_only_evidence_file(tmp_path):
    target = tmp_path / "latency_slo_oscillation_latest.json"
    report = build_latency_slo_oscillation_report(
        [
            {"latency_ms": 100.0, "slo_state": "ok"},
            {"latency_ms": 110.0, "slo_state": "ok"},
            {"latency_ms": 120.0, "slo_state": "ok"},
        ],
        latency_threshold_ms=500.0,
    )

    out = write_latency_slo_oscillation_evidence(report, target)

    assert out == target
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["source"] == LATENCY_SLO_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False


def test_payload_is_json_serializable():
    payload = build_latency_slo_oscillation_report(
        [
            {"latency_ms": 100.0, "slo_state": "ok"},
            {"latency_ms": 110.0, "slo_state": "ok"},
            {"latency_ms": 120.0, "slo_state": "ok"},
        ],
        latency_threshold_ms=500.0,
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["source"] == LATENCY_SLO_SOURCE
    assert decoded["read_only"] is True
    assert decoded["append"] is False
