from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

import pytest

from tests.core.test_runtime_snapshot_producer import _run_cas_spot_dependency_cycle


@pytest.mark.parametrize(
    ("spot", "expected_reason"),
    [
        ({"quote_symbol": "NIFTY 50"}, "cas_required_spot_identity_mismatch"),
        ({"token": True}, "cas_required_spot_identity_mismatch"),
        ({"token": None}, "cas_required_spot_identity_mismatch"),
        ({"executable": True}, "cas_spot_quote_authority_invalid"),
        ({"fresh": 1}, "cas_required_spot_unhealthy"),
        ({"status": "healthy"}, "cas_required_spot_unhealthy"),
        ({"raw_age_override": True}, "cas_required_spot_age_invalid"),
        ({"raw_age_override": "0.2"}, "cas_required_spot_age_invalid"),
        ({"raw_age_override": -0.1}, "cas_required_spot_age_invalid"),
        ({"raw_age_override": math.nan}, "cas_required_spot_age_invalid"),
        ({"raw_age_override": math.inf}, "cas_required_spot_age_invalid"),
        ({"age": 3.0}, "cas_required_spot_stale"),
        ({"remove_quote_truth": True}, "cas_required_spot_health_missing"),
        ({"remove_nifty": True}, "cas_required_spot_snapshot_missing"),
        ({"transport": False}, "cas_shared_feed_unhealthy_or_unknown"),
        (
            {"transport": True, "effective_transport": False},
            "cas_shared_feed_unhealthy_or_unknown",
        ),
        (
            {"snapshot_timestamp_override": "2026-10-02T15:14:00"},
            "cas_spot_snapshot_timezone_missing",
        ),
        (
            {
                "snapshot_timestamp_override": (
                    datetime(2026, 10, 2, 15, 14, tzinfo=timezone.utc)
                    + timedelta(seconds=1)
                ).isoformat()
            },
            "cas_spot_snapshot_from_future",
        ),
        (
            {
                "snapshot_timestamp_override": datetime(
                    2026, 10, 2, 15, 13, 56, tzinfo=timezone.utc
                ).isoformat()
            },
            "cas_spot_snapshot_stale",
        ),
        ({"snapshot_timestamp_override": "not-a-timestamp"}, "cas_spot_snapshot_timestamp_invalid"),
        ({"snapshot_timestamp_override": ""}, "cas_spot_snapshot_timestamp_missing"),
    ],
)
def test_cas_bridge_fails_closed_for_adversarial_dependency_evidence(
    tmp_path, monkeypatch, spot, expected_reason
):
    from core.read_only_consumer_cycle import _evaluate_cas

    outputs, eval_time, source_sha = _run_cas_spot_dependency_cycle(
        tmp_path, monkeypatch, spot=spot
    )

    assert outputs["cas_input_gate"]["state"] == "BLOCKED"
    assert outputs["cas_input_gate"]["reason_code"] == expected_reason
    assert "cas_short_horizon_inputs" not in outputs
    result = _evaluate_cas(
        runtime_outputs=outputs,
        output_root=tmp_path / "consumer",
        session_id="cas-spot-dependency-test",
        source_sha=source_sha,
        now=eval_time,
    )
    assert result["verdict"] == "PENDING"
    assert result["reason"] == "short_horizon_inputs_missing"
    assert not (tmp_path / "consumer" / "cas_v2_artifact.json").exists()


def test_cas_bridge_accepts_legacy_transport_only_when_effective_field_absent(
    tmp_path, monkeypatch
):
    from core.read_only_consumer_cycle import _evaluate_cas

    outputs, eval_time, source_sha = _run_cas_spot_dependency_cycle(
        tmp_path, monkeypatch, spot={"transport": True, "omit_effective_transport": True}
    )
    assert outputs["cas_input_gate"]["state"] == "READY"
    result = _evaluate_cas(
        runtime_outputs=outputs,
        output_root=tmp_path / "consumer",
        session_id="cas-spot-dependency-test",
        source_sha=source_sha,
        now=eval_time,
    )
    assert result["verdict"] == "PASS"
