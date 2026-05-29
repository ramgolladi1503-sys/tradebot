from __future__ import annotations

from core.latency_hotpath_evidence import (
    LATENCY_EVIDENCE_INCONSISTENT_TIMING,
    LATENCY_EVIDENCE_MISSING_TIMING,
    build_latency_hotpath_evidence,
)


def test_latency_evidence_separates_hotpath_and_background_overhead():
    payload = build_latency_hotpath_evidence(
        {
            "full_cycle_ms": 1200,
            "decision_critical_path_ms": 450,
        },
        operations=[
            {"name": "decision_dag", "duration_ms": 250, "category": "hot_path"},
            {"name": "option_expiry_scan", "duration_ms": 700, "category": "background"},
            {"name": "telemetry_flush", "duration_ms": 80, "category": "background"},
        ],
        top_n=2,
    )

    assert payload["status"] == "OK"
    assert payload["fail_closed"] is False
    assert payload["full_cycle_ms"] == 1200.0
    assert payload["decision_critical_path_ms"] == 450.0
    assert payload["background_overhead_ms"] == 750.0
    assert [item["name"] for item in payload["top_operations"]] == [
        "option_expiry_scan",
        "decision_dag",
    ]
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False


def test_latency_evidence_uses_explicit_background_overhead_when_available():
    payload = build_latency_hotpath_evidence(
        {
            "cycle_ms": "1000",
            "critical_path_ms": "300",
            "background_overhead_ms": "650",
        }
    )

    assert payload["full_cycle_ms"] == 1000.0
    assert payload["decision_critical_path_ms"] == 300.0
    assert payload["background_overhead_ms"] == 650.0
    assert payload["status"] == "OK"


def test_missing_timing_data_fails_closed_without_crashing():
    payload = build_latency_hotpath_evidence({"full_cycle_ms": 900})

    assert payload["status"] == "UNKNOWN"
    assert payload["fail_closed"] is True
    assert LATENCY_EVIDENCE_MISSING_TIMING in payload["blockers"]
    assert payload["decision_critical_path_ms"] is None
    assert payload["background_overhead_ms"] is None


def test_inconsistent_timing_data_is_flagged_but_not_normalized_into_action():
    payload = build_latency_hotpath_evidence(
        {
            "full_cycle_ms": 100,
            "decision_critical_path_ms": 250,
        }
    )

    assert payload["status"] == "UNKNOWN"
    assert payload["fail_closed"] is True
    assert LATENCY_EVIDENCE_INCONSISTENT_TIMING in payload["blockers"]
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False


def test_backward_compatible_shape_with_empty_inputs():
    payload = build_latency_hotpath_evidence(None, operations=[{"operation": "bad"}])

    assert sorted(payload.keys()) == sorted(
        [
            "source",
            "status",
            "fail_closed",
            "blockers",
            "full_cycle_ms",
            "decision_critical_path_ms",
            "background_overhead_ms",
            "top_operations",
            "raw_timing_keys",
            "read_only",
            "append",
            "is_order_action",
            "broker_api_called",
        ]
    )
    assert payload["top_operations"] == []
    assert LATENCY_EVIDENCE_MISSING_TIMING in payload["blockers"]
