from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.observability import (
    CandidateLifecycleEventEmitter,
    EVIDENCE_FILENAMES,
    FeedStateEventEmitter,
    ObservabilityContext,
    ObservabilityEvidenceBundleError,
    ObservabilityIds,
    build_observability_evidence_bundle,
    write_observability_evidence_bundle,
)


def _context(candidate_id: str | None = None) -> ObservabilityContext:
    return ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_test_20260523",
            cycle_id="cycle_test_000001",
            trace_id="trace_test_000001",
            span_id="span_runtime_cycle",
            candidate_id=candidate_id,
        ),
        stage="runtime.cycle",
        execution_mode="paper",
        attributes={"source_test": "observability_evidence_bundle"},
    )


def _sample_events() -> list[dict[str, object]]:
    timestamp = datetime(2026, 5, 23, 7, 30, tzinfo=timezone.utc)
    feed = FeedStateEventEmitter(_context())
    lifecycle = CandidateLifecycleEventEmitter(_context(), candidate_id="candidate_nifty_22500_ce")
    return [
        feed.feed_fresh(timestamp=timestamp, feed_age_ms=250, latency_ms=2).as_dict(),
        lifecycle.generated(timestamp=timestamp, latency_ms=3).as_dict(),
        lifecycle.scored(timestamp=timestamp, score=0.82, latency_ms=5).as_dict(),
        lifecycle.ranked(timestamp=timestamp, rank=1, latency_ms=7).as_dict(),
        feed.quote_fallback_used(timestamp=timestamp, candidate_id="candidate_nifty_22500_ce", latency_ms=1).as_dict(),
        feed.blocked_fallback(timestamp=timestamp, candidate_id="candidate_nifty_22500_ce", latency_ms=1).as_dict(),
    ]


def test_build_observability_evidence_bundle_creates_required_reports() -> None:
    bundle = build_observability_evidence_bundle(_sample_events())

    assert tuple(sorted(bundle.reports)) == tuple(sorted(EVIDENCE_FILENAMES))
    summary = bundle.reports["observability_summary.json"]
    assert summary["event_count"] == 6
    assert summary["candidate_count"] == 1
    assert summary["run_count"] == 1
    assert summary["broker_api_called"] is False


def test_candidate_decision_funnel_records_path_and_terminal_state() -> None:
    bundle = build_observability_evidence_bundle(_sample_events())
    funnel = bundle.reports["candidate_decision_funnel.json"]

    assert funnel["candidate_count"] == 1
    assert funnel["complete"] is True
    assert funnel["missing_terminal_state_candidates"] == []
    assert funnel["candidate_paths"][0]["candidate_id"] == "candidate_nifty_22500_ce"
    assert "ranked" in funnel["candidate_paths"][0]["decisions"]
    assert "blocked" in funnel["candidate_paths"][0]["decisions"]


def test_fallback_safety_report_proves_no_executable_fallback() -> None:
    bundle = build_observability_evidence_bundle(_sample_events())
    report = bundle.reports["fallback_safety_report.json"]

    assert report["fallback_event_count"] == 2
    assert report["fallback_candidate_count"] == 1
    assert report["fallback_executable_count"] == 0
    assert report["safe"] is True


def test_feed_freshness_and_latency_reports_are_deterministic() -> None:
    first = build_observability_evidence_bundle(reversed(_sample_events())).as_dict()
    second = build_observability_evidence_bundle(_sample_events()).as_dict()

    assert first == second
    assert second["feed_freshness_report.json"]["fresh_event_count"] == 1
    assert second["feed_freshness_report.json"]["max_feed_age_ms"] == 250.0
    latency = second["latency_breakdown.json"]
    assert latency["latency_event_count"] == 6
    assert [item["stage"] for item in latency["stages"]] == sorted(item["stage"] for item in latency["stages"])


def test_invalid_event_payload_fails_closed() -> None:
    invalid = dict(_sample_events()[0])
    invalid.pop("trace_id")

    with pytest.raises(ObservabilityEvidenceBundleError, match="required_field_missing:trace_id"):
        build_observability_evidence_bundle([invalid])


def test_write_observability_evidence_bundle_writes_all_required_json_files(tmp_path: Path) -> None:
    written = write_observability_evidence_bundle(_sample_events(), output_dir=tmp_path)

    assert tuple(sorted(written)) == tuple(sorted(EVIDENCE_FILENAMES))
    for filename in EVIDENCE_FILENAMES:
        path = tmp_path / filename
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["source"] == "tradebot.observability.evidence_bundle"
        assert payload["broker_api_called"] is False


def test_cli_script_has_no_runtime_startup_or_broker_imports() -> None:
    script = Path("scripts/build_observability_evidence.py").read_text(encoding="utf-8")

    assert "run_metrics_server" not in script
    assert "run_live" not in script
    assert "kite" not in script.lower()
    assert "broker" not in script.lower()
