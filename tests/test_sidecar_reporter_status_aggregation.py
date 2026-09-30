from __future__ import annotations

from core.observability.sidecar_reporter import SidecarReporter
from core.observability.token_health_model import RoleAwareHealthReport


REQUIRED = {
    "process_health": "HEALTHY",
    "raw_tick_capture": "HEALTHY",
    "runtime_metadata": "HEALTHY",
    "depth_capture": "HEALTHY",
    "ws_recovery": "HEALTHY",
    "feed_truth": "HEALTHY",
    "meg": "HEALTHY",
    "heritage": "HEALTHY",
    "candidate_pipeline": "HEALTHY",
    "broker_authority": "HEALTHY",
}


def _overall(states, token_health_report=None):
    report = SidecarReporter().generate_health_snapshot(
        token_health_report=token_health_report,
        execution_plane_state={"subsystems": states},
    )
    return report["executive_state"]["OVERALL_STATE"]


def test_overall_health_requires_explicit_healthy_truth_for_every_subsystem():
    assert _overall(REQUIRED) == "HEALTHY"
    incomplete = dict(REQUIRED)
    incomplete.pop("heritage")
    assert _overall(incomplete) == "UNKNOWN"


def test_healthy_token_report_does_not_fill_missing_feed_truth():
    states = dict(REQUIRED)
    states.pop("feed_truth")
    token_health = RoleAwareHealthReport(
        overall_health="HEALTHY",
        reason_code="OK",
        critical_underlying_healthy=True,
        role_metrics={},
        affected_strategies=(),
        unaffected_strategies=(),
        system_critical=False,
        diagnostic_details={},
    )

    report = SidecarReporter().generate_health_snapshot(
        token_health_report=token_health,
        execution_plane_state={"subsystems": states},
    )

    assert report["executive_state"]["SUBSYSTEM_STATES"]["feed_truth"] == "UNKNOWN"
    assert report["executive_state"]["OVERALL_STATE"] == "UNKNOWN"


def test_degraded_websocket_or_queue_cannot_report_healthy():
    states = dict(REQUIRED, ws_recovery="DEGRADED")
    assert _overall(states) == "OPERATIONAL_DEGRADED"
    states = dict(REQUIRED, runtime_metadata="QUEUE_DEGRADED")
    assert _overall(states) == "OPERATIONAL_DEGRADED"


def test_blocked_heritage_and_unsafe_authority_have_precedence():
    assert _overall(dict(REQUIRED, heritage="BLOCKED")) == "BLOCKED"
    assert _overall(dict(REQUIRED, heritage="BLOCKED", broker_authority="UNSAFE")) == "UNSAFE"


def test_snapshot_preserves_non_authority_safety_boundaries():
    report = SidecarReporter().generate_health_snapshot(execution_plane_state={"subsystems": REQUIRED})
    assert report["safety_boundaries"] == {
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "is_order_action": False,
    }
