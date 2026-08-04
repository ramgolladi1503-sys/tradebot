from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aixion_trade_intelligence.contracts import CanonicalEvent
from aixion_trade_intelligence.elite_monitor import (
    atomic_write_json,
    build_elite_monitor_iteration,
    latest_score_cycles,
    read_complete_jsonl,
)
from aixion_trade_intelligence.publisher import FileEventPublisher
from aixion_trade_intelligence.source_checkpoint_builder import SourceFileSpec


def _event(
    event_id: str,
    event_type: str,
    *,
    event_time: datetime,
    component: str,
    sequence: int,
) -> CanonicalEvent:
    source_time = event_time - timedelta(milliseconds=20)
    receive_time = event_time - timedelta(milliseconds=10)
    return CanonicalEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version="1.0.0",
        session_id="ELITE-MONITOR-SESSION",
        run_id="ELITE-MONITOR-RUN",
        event_time=event_time,
        source_time=source_time,
        receive_time=receive_time,
        available_time=source_time,
        parse_time=receive_time,
        persist_time=event_time,
        source_provider="TRADEBOT",
        source_component=component,
        authority_class="TRADEBOT_RUNTIME_TRUTH",
        data_quality_state="VALID",
        producer_sequence=sequence,
        payload={},
    )


def _lineage_rows():
    return [
        {"candidate_id": "a", "cycle_id": "previous", "score": 0.2, "rankable": True, "executable": False, "direction": "BUY_CE", "stage": "tradebuilder"},
        {"candidate_id": "a", "cycle_id": "previous", "score": 0.6, "rankable": True, "executable": True, "direction": "BUY_CE", "stage": "ranking"},
        {"candidate_id": "b", "cycle_id": "previous", "score": 0.4, "rankable": True, "executable": False, "direction": "BUY_PE", "stage": "ranking"},
        {"candidate_id": "a", "cycle_id": "current", "score": 0.7, "rankable": True, "executable": True, "direction": "BUY_CE", "stage": "ranking"},
        {"candidate_id": "b", "cycle_id": "current", "score": 0.3, "rankable": True, "executable": False, "direction": "BUY_PE", "stage": "ranking"},
    ]


def _prepare_runtime(tmp_path: Path):
    now = datetime.now(tz=timezone.utc).replace(microsecond=0)
    evidence_root = tmp_path / "evidence"
    publisher = FileEventPublisher(evidence_root)
    publisher.publish(_event("start", "SESSION_STARTED", event_time=now - timedelta(seconds=2), component="runtime", sequence=1))
    publisher.publish(_event("feed", "FEED_TRUTH_UPDATED", event_time=now - timedelta(seconds=1), component="feed", sequence=1))
    event_log = evidence_root / "ELITE-MONITOR-SESSION" / "events.jsonl"
    with event_log.open("ab") as handle:
        handle.write(b'{"event_id":"partial"')
    lineage = tmp_path / "candidate_lineage.jsonl"
    lineage.write_bytes(
        ("".join(json.dumps(row) + "\n" for row in _lineage_rows()) + '{"candidate_id":"partial"').encode("utf-8")
    )
    source_spec = SourceFileSpec(
        source_name="feed_component",
        path=event_log,
        identity_fields=("event_id",),
        event_type_field="event_type",
        source_time_field="source_time",
        receive_time_field="receive_time",
        persist_time_field="persist_time",
        required_event_types=("FEED_TRUTH_UPDATED",),
        filters=(("source_component", ("feed",)),),
    )
    policy = {
        "freshness_limits_seconds": {"feed_component": 5.0},
        "ranking_stability_top_k": 1,
        "score_policy": {
            "minimum_reference_sessions": 3,
            "metrics": {"score_range": {"lower_quantile": 0.0, "upper_quantile": 1.0}},
        },
    }
    baseline = {"ranking_metrics": {"score_range": [0.2, 0.4, 0.6]}}
    return now, event_log, lineage, source_spec, policy, baseline


def test_monitor_reads_latest_candidate_state_and_ignores_only_partial_final_line(tmp_path):
    _, _, lineage, _, _, _ = _prepare_runtime(tmp_path)
    rows, partial = read_complete_jsonl(lineage)
    current, previous = latest_score_cycles(rows)
    assert partial is True
    assert previous is not None
    previous_by_id = {row.candidate_id: row.score for row in previous}
    assert previous_by_id == {"a": 0.6, "b": 0.4}
    current_by_id = {row.candidate_id: row.score for row in current}
    assert current_by_id == {"a": 0.7, "b": 0.3}


def test_elite_monitor_iteration_keeps_observation_open_and_diagnosis_blocked_in_session(tmp_path):
    now, event_log, lineage, source_spec, policy, baseline = _prepare_runtime(tmp_path)
    iteration = build_elite_monitor_iteration(
        event_log_path=event_log,
        candidate_lineage_path=lineage,
        source_specs=[source_spec],
        canary_readiness={"ready": True, "verdict": "READY_FOR_READ_ONLY_CANARY"},
        policy=policy,
        evaluation_time=now,
        baseline=baseline,
        certification={"verdict": "INSUFFICIENT_EVIDENCE"},
    )
    assert iteration.event_log_partial_line_ignored is True
    assert iteration.candidate_lineage_partial_line_ignored is True
    assert iteration.live_snapshot.monitoring_verdict == "LIVE_MONITORING_HEALTHY"
    assert iteration.cockpit.observation.passed is True
    assert iteration.cockpit.diagnosis.passed is False
    assert "SESSION_EVIDENCE_INVALID" in iteration.cockpit.diagnosis.reasons
    assert iteration.cockpit.profitability_claim.passed is False
    assert iteration.source_checkpoints.sources[0].filtered_out_row_count == 1


def test_atomic_monitor_write_replaces_complete_json_without_tmp_residue(tmp_path):
    target = tmp_path / "latest.json"
    atomic_write_json(target, {"version": 1, "state": "first"})
    atomic_write_json(target, {"version": 2, "state": "second"})
    record = json.loads(target.read_text(encoding="utf-8"))
    assert record == {"state": "second", "version": 2}
    assert not target.with_name(target.name + ".tmp").exists()


def test_elite_monitor_cli_writes_latest_artifacts_and_history(tmp_path):
    repo_root = Path(__file__).parents[1]
    _, event_log, lineage, source_spec, policy_payload, baseline_payload = _prepare_runtime(tmp_path)
    source_config = tmp_path / "source_config.json"
    canary = tmp_path / "canary.json"
    policy = tmp_path / "policy.json"
    baseline = tmp_path / "baseline.json"
    certification = tmp_path / "certification.json"
    output = tmp_path / "monitor"
    history = tmp_path / "history" / "monitor.jsonl"
    source_config.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_name": source_spec.source_name,
                        "path": source_spec.path.as_posix(),
                        "identity_fields": list(source_spec.identity_fields),
                        "event_type_field": source_spec.event_type_field,
                        "source_time_field": source_spec.source_time_field,
                        "receive_time_field": source_spec.receive_time_field,
                        "persist_time_field": source_spec.persist_time_field,
                        "required_event_types": list(source_spec.required_event_types),
                        "filters": {"source_component": ["feed"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    canary.write_text(json.dumps({"ready": True, "verdict": "READY_FOR_READ_ONLY_CANARY"}), encoding="utf-8")
    policy.write_text(json.dumps(policy_payload), encoding="utf-8")
    baseline.write_text(json.dumps(baseline_payload), encoding="utf-8")
    certification.write_text(json.dumps({"verdict": "INSUFFICIENT_EVIDENCE"}), encoding="utf-8")
    run = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "run_aixion_elite_monitor.py"),
            "--event-log",
            str(event_log),
            "--candidate-lineage",
            str(lineage),
            "--source-config",
            str(source_config),
            "--canary-readiness",
            str(canary),
            "--policy",
            str(policy),
            "--baseline",
            str(baseline),
            "--certification",
            str(certification),
            "--output-dir",
            str(output),
            "--history-jsonl",
            str(history),
            "--interval-seconds",
            "0.01",
            "--iterations",
            "1",
            "--stop-on-error",
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    monitor = json.loads((output / "elite_monitor_latest.json").read_text(encoding="utf-8"))
    cockpit = json.loads((output / "elite_cockpit_latest.json").read_text(encoding="utf-8"))
    live = json.loads((output / "live_snapshot_latest.json").read_text(encoding="utf-8"))
    checkpoints = json.loads((output / "source_checkpoints_latest.json").read_text(encoding="utf-8"))
    assert monitor["live_snapshot"]["monitoring_verdict"] == "LIVE_MONITORING_HEALTHY"
    assert cockpit["authorities"]["observation"]["verdict"] == "READ_ONLY_OBSERVATION_ALLOWED"
    assert cockpit["authorities"]["diagnosis"]["verdict"] == "STRATEGY_DIAGNOSIS_BLOCKED"
    assert live["monitoring_only"] is True
    assert checkpoints["source_count"] == 1
    assert history.is_file() and history.stat().st_size > 0
