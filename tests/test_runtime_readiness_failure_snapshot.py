from __future__ import annotations

import json

from core.runtime_readiness_failure_snapshot import build_runtime_readiness_failure_snapshot


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_snapshot_reports_latency_halt_when_no_paper_outcomes(tmp_path):
    runtime_health = _write_json(tmp_path / "runtime_health_latest.json", {"mode": "PAPER", "market_open": True})
    feed_runtime = _write_json(tmp_path / "feed_runtime_latest.json", {"feed_ok": False, "ws_connected": False})
    engine_status = _write_json(
        tmp_path / "engine_cycle_status.json",
        {
            "mode": "PAPER",
            "auth_ok": True,
            "auth_state": "READY",
            "feed_ok": True,
            "market_open": True,
            "visible_executable_count": 0,
            "visible_queue_only_count": 0,
            "visible_advisory_count": 2,
            "primary_blocker": "NO_CANDIDATES",
        },
    )
    paper_log = tmp_path / "paper_market.log"
    paper_log.write_text(
        "\n".join(
            [
                "DECISION_FEED_EVIDENCE veto_reasons=['latency_breach']",
                "GATE_REJECT_EMIT reason='latency_guard_halt_all'",
                "PHASE2: No input candidates for phase2 raw_count=0",
            ]
        ),
        encoding="utf-8",
    )
    family = tmp_path / "family_outcomes.jsonl"

    report = build_runtime_readiness_failure_snapshot(
        runtime_health_path=runtime_health,
        feed_runtime_path=feed_runtime,
        engine_status_path=engine_status,
        family_outcomes_path=family,
        paper_log_path=paper_log,
    )

    assert report["mode"] == "PAPER"
    assert report["read_only"] is True
    assert report["evidence_status"]["family_outcomes_exists"] is False
    assert report["evidence_status"]["family_outcome_records"] == 0
    assert report["evidence_status"]["edge_evidence_available"] is False
    assert report["runtime_status"]["primary_blocker"] == "latency_guard_halt_all"
    assert report["blocker_counts"]["latency_guard_halt_all"] == 1
    assert report["blocker_counts"]["latency_breach"] == 1
    assert report["decision"]["safe_to_claim_edge"] is False
    assert report["decision"]["should_restart_without_fix"] is False
    assert report["decision"]["recommended_next_action"] == "capture_latency_feed_diagnostics_before_next_paper_run"


def test_snapshot_prefers_auth_required_before_latency_when_auth_failed(tmp_path):
    runtime_health = _write_json(tmp_path / "runtime_health_latest.json", {"mode": "PAPER"})
    feed_runtime = _write_json(tmp_path / "feed_runtime_latest.json", {"feed_ok": True})
    engine_status = _write_json(
        tmp_path / "engine_cycle_status.json",
        {"mode": "PAPER", "auth_state": "AUTH_REQUIRED", "feed_ok": True},
    )
    paper_log = tmp_path / "paper_market.log"
    paper_log.write_text("GATE_REJECT_EMIT reason='latency_guard_halt_all'\n", encoding="utf-8")

    report = build_runtime_readiness_failure_snapshot(
        runtime_health_path=runtime_health,
        feed_runtime_path=feed_runtime,
        engine_status_path=engine_status,
        family_outcomes_path=tmp_path / "missing_family_outcomes.jsonl",
        paper_log_path=paper_log,
    )

    assert report["runtime_status"]["primary_blocker"] == "auth_required"
    assert report["decision"]["recommended_next_action"] == "refresh_and_validate_auth_before_restart"


def test_snapshot_marks_edge_available_when_family_outcomes_exist(tmp_path):
    runtime_health = _write_json(tmp_path / "runtime_health_latest.json", {"mode": "PAPER"})
    feed_runtime = _write_json(tmp_path / "feed_runtime_latest.json", {"feed_ok": True})
    engine_status = _write_json(tmp_path / "engine_cycle_status.json", {"mode": "PAPER", "feed_ok": True})
    family = tmp_path / "family_outcomes.jsonl"
    family.write_text('{"candidate_id":"c1","terminal_status":"executed"}\n', encoding="utf-8")
    paper_log = tmp_path / "paper_market.log"
    paper_log.write_text("", encoding="utf-8")

    report = build_runtime_readiness_failure_snapshot(
        runtime_health_path=runtime_health,
        feed_runtime_path=feed_runtime,
        engine_status_path=engine_status,
        family_outcomes_path=family,
        paper_log_path=paper_log,
    )

    assert report["evidence_status"]["family_outcome_records"] == 1
    assert report["evidence_status"]["edge_evidence_available"] is True
    assert report["runtime_status"]["primary_blocker"] == "paper_outcomes_available"
    assert report["decision"]["safe_to_claim_edge"] is True
    assert report["decision"]["recommended_next_action"] == "run_edge_baseline_audit"
