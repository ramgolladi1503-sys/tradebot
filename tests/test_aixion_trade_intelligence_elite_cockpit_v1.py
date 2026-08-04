from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aixion_trade_intelligence.elite_cockpit import build_elite_analytics_cockpit
from aixion_trade_intelligence.evidence_guardian import (
    SourceContinuityCheckpoint,
    build_source_continuity_report,
    summarize_evidence_guardian,
)
from aixion_trade_intelligence.ranking_diagnostics import (
    CandidateScoreObservation,
    EmpiricalMetricFinding,
    analyze_score_separation,
    compare_cycle_rankings,
    evaluate_empirical_score_policy,
)


BASE = datetime(2026, 8, 5, 4, 30, tzinfo=timezone.utc)


def _score(
    candidate_id: str,
    cycle_id: str,
    score: float,
    *,
    executable: bool = False,
    fallback: bool = False,
    outcome: float | None = None,
) -> CandidateScoreObservation:
    return CandidateScoreObservation(
        candidate_id=candidate_id,
        cycle_id=cycle_id,
        score=score,
        rankable=True,
        executable=executable,
        direction="BUY_CE" if candidate_id != "c" else "BUY_PE",
        fallback_used=fallback,
        outcome_value=outcome,
    )


def test_score_separation_exposes_compression_contamination_and_outcome_ordering():
    report = analyze_score_separation(
        [
            _score("a", "cycle-1", 0.4, fallback=True, outcome=0.0),
            _score("b", "cycle-1", 0.4, outcome=-1.0),
            _score("c", "cycle-1", 0.8, executable=True, outcome=2.0),
        ]
    )
    assert report.rankable_count == 3
    assert report.executable_count == 1
    assert report.unique_score_count == 2
    assert report.score_range == pytest.approx(0.4)
    assert report.score_iqr == pytest.approx(0.2)
    assert report.top1_minus_top2 == pytest.approx(0.4)
    assert report.tie_rate == pytest.approx(1.0 / 3.0)
    assert report.fallback_contamination_rate == pytest.approx(1.0 / 3.0)
    assert report.outcome_pairwise_concordance == pytest.approx(1.0)
    assert report.outcome_pairs_evaluated == 2
    assert report.direction_counts == {"BUY_CE": 2, "BUY_PE": 1}


def test_degraded_candidate_cannot_be_marked_executable():
    with pytest.raises(ValueError, match="degraded_score_observation_must_not_be_executable"):
        _score("a", "cycle-1", 0.5, executable=True, fallback=True)


def test_ranking_stability_detects_complete_rank_reversal():
    previous = [_score("a", "previous", 0.8), _score("b", "previous", 0.6), _score("c", "previous", 0.4)]
    current = [_score("a", "current", 0.4), _score("b", "current", 0.6), _score("c", "current", 0.8)]
    report = compare_cycle_rankings(previous, current, top_k=2)
    assert report.common_candidates == 3
    assert report.candidate_retention_rate == pytest.approx(1.0)
    assert report.top_k_overlap_rate == pytest.approx(0.5)
    assert report.kendall_tau_b == pytest.approx(-1.0)
    assert report.rank_pairs_evaluated == 3


def test_empirical_policy_fails_closed_for_insufficient_and_outside_reference():
    report = analyze_score_separation([_score("a", "cycle", 0.4), _score("b", "cycle", 0.8)])
    insufficient = evaluate_empirical_score_policy(
        report,
        reference_metrics={"score_range": [0.1, 0.2]},
        policy={
            "minimum_reference_sessions": 3,
            "metrics": {"score_range": {"lower_quantile": 0.0, "upper_quantile": 1.0}},
        },
    )
    assert insufficient[0].verdict == "INSUFFICIENT_REFERENCE_EVIDENCE"
    assert insufficient[0].upper_bound is None
    outside = evaluate_empirical_score_policy(
        report,
        reference_metrics={"score_range": [0.1, 0.2, 0.3]},
        policy={
            "minimum_reference_sessions": 3,
            "metrics": {"score_range": {"lower_quantile": 0.0, "upper_quantile": 1.0}},
        },
    )
    assert outside[0].verdict == "OUTSIDE_EMPIRICAL_BASELINE"
    assert outside[0].upper_bound == pytest.approx(0.3)


def test_evidence_guardian_blocks_sequence_loss_and_stale_source():
    valid = SourceContinuityCheckpoint(
        source_name="candidate_lineage",
        observed_events=10,
        first_sequence=1,
        last_sequence=10,
        sequence_gap_events=0,
        duplicate_events=0,
        malformed_events=0,
        latest_source_time=BASE,
        latest_receive_time=BASE + timedelta(milliseconds=10),
        latest_persist_time=BASE + timedelta(milliseconds=20),
        observed_event_types=("CANDIDATE_CREATED",),
        required_event_types=("CANDIDATE_CREATED",),
    )
    valid_report = build_source_continuity_report(valid, evaluation_time=BASE + timedelta(seconds=1))
    assert valid_report.integrity_valid is True
    assert valid_report.coverage_ratio == pytest.approx(1.0)
    assert valid_report.source_to_receive_ms == pytest.approx(10.0)
    invalid = SourceContinuityCheckpoint(
        source_name="feed_truth",
        observed_events=8,
        first_sequence=1,
        last_sequence=10,
        sequence_gap_events=2,
        duplicate_events=1,
        malformed_events=0,
        latest_source_time=BASE - timedelta(seconds=30),
        latest_receive_time=BASE - timedelta(seconds=29),
        latest_persist_time=BASE - timedelta(seconds=28),
        observed_event_types=("FEED_TRUTH_UPDATED",),
        required_event_types=("FEED_TRUTH_UPDATED", "SESSION_STARTED"),
    )
    summary = summarize_evidence_guardian(
        [valid, invalid],
        evaluation_time=BASE + timedelta(seconds=1),
        freshness_limits_seconds={"candidate_lineage": 5.0, "feed_truth": 5.0},
    )
    assert summary.observation_authority == "READ_ONLY_OBSERVATION_BLOCKED"
    assert summary.invalid_source_count == 1
    assert summary.stale_source_count == 1
    assert summary.total_sequence_gap_events == 2
    assert any(reason.startswith("SOURCE_INTEGRITY_INVALID:") for reason in summary.blockers)
    assert any(reason.startswith("SOURCE_STALE:") for reason in summary.blockers)


def _valid_guardian():
    checkpoint = SourceContinuityCheckpoint(
        source_name="candidate_lineage",
        observed_events=5,
        first_sequence=1,
        last_sequence=5,
        sequence_gap_events=0,
        duplicate_events=0,
        malformed_events=0,
        latest_source_time=BASE,
        latest_receive_time=BASE,
        latest_persist_time=BASE,
        observed_event_types=("CANDIDATE_CREATED",),
        required_event_types=("CANDIDATE_CREATED",),
    )
    return summarize_evidence_guardian(
        [checkpoint],
        evaluation_time=BASE + timedelta(seconds=1),
        freshness_limits_seconds={"candidate_lineage": 5.0},
    )


def _session_analysis(*, profitability_ready: bool = False):
    return {
        "manifest": {
            "session_id": "session-1",
            "run_id": "run-1",
            "verdict": "VALID_OFFLINE_SESSION_EVIDENCE",
            "valid": True,
        },
        "outcome_readiness": {
            "ready_for_strategy_diagnosis": True,
            "ready_for_profitability_claim": profitability_ready,
            "reason": "complete" if profitability_ready else "profitability_not_certified",
        },
    }


def test_cockpit_separates_observation_diagnosis_and_profitability_authority():
    score_report = analyze_score_separation([_score("a", "cycle", 0.4), _score("b", "cycle", 0.8)])
    findings = (
        EmpiricalMetricFinding("score_range", 0.4, 20, 0.2, 0.6, "WITHIN_EMPIRICAL_BASELINE"),
    )
    cockpit = build_elite_analytics_cockpit(
        canary_readiness={"ready": True, "verdict": "READY_FOR_READ_ONLY_CANARY"},
        evidence_guardian=_valid_guardian(),
        session_analysis=_session_analysis(),
        score_report=score_report,
        empirical_score_findings=findings,
        certification={"verdict": "INSUFFICIENT_EVIDENCE"},
        evidence_refs=("session.json", "lineage.jsonl"),
    )
    assert cockpit.observation.passed is True
    assert cockpit.diagnosis.passed is True
    assert cockpit.strategy_change.passed is True
    assert cockpit.strategy_change.verdict == "HUMAN_STRATEGY_CHANGE_REVIEW_ALLOWED"
    assert cockpit.profitability_claim.passed is False
    assert "SESSION_NOT_READY_FOR_PROFITABILITY_CLAIM" in cockpit.profitability_claim.reasons
    assert "CERTIFICATION_VERDICT=INSUFFICIENT_EVIDENCE" in cockpit.profitability_claim.reasons


def test_cockpit_blocks_diagnosis_without_empirical_ranking_policy():
    score_report = analyze_score_separation([_score("a", "cycle", 0.4), _score("b", "cycle", 0.8)])
    cockpit = build_elite_analytics_cockpit(
        canary_readiness={"ready": True},
        evidence_guardian=_valid_guardian(),
        session_analysis=_session_analysis(),
        score_report=score_report,
    )
    assert cockpit.observation.passed is True
    assert cockpit.diagnosis.passed is False
    assert "RANKING_EMPIRICAL_POLICY_NOT_EVALUATED" in cockpit.diagnosis.reasons
    assert cockpit.strategy_change.passed is False


def test_elite_cockpit_cli_builds_json_and_markdown_artifacts(tmp_path):
    repo_root = Path(__file__).parents[1]
    canary = tmp_path / "canary.json"
    session = tmp_path / "session.json"
    lineage = tmp_path / "lineage.jsonl"
    checkpoints = tmp_path / "checkpoints.json"
    policy = tmp_path / "policy.json"
    baseline = tmp_path / "baseline.json"
    certification = tmp_path / "certification.json"
    output = tmp_path / "output"
    canary.write_text(json.dumps({"ready": True, "verdict": "READY_FOR_READ_ONLY_CANARY"}), encoding="utf-8")
    session.write_text(json.dumps(_session_analysis()), encoding="utf-8")
    lineage_rows = [
        {"candidate_id": "a", "cycle_id": "previous", "score": 0.6, "rankable": True, "executable": True, "direction": "BUY_CE"},
        {"candidate_id": "b", "cycle_id": "previous", "score": 0.4, "rankable": True, "executable": False, "direction": "BUY_PE"},
        {"candidate_id": "a", "cycle_id": "current", "score": 0.7, "rankable": True, "executable": True, "direction": "BUY_CE"},
        {"candidate_id": "b", "cycle_id": "current", "score": 0.4, "rankable": True, "executable": False, "direction": "BUY_PE"},
    ]
    lineage.write_text("".join(json.dumps(row) + "\n" for row in lineage_rows), encoding="utf-8")
    checkpoints.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_name": "candidate_lineage",
                        "observed_events": 4,
                        "first_sequence": 1,
                        "last_sequence": 4,
                        "sequence_gap_events": 0,
                        "duplicate_events": 0,
                        "malformed_events": 0,
                        "latest_source_time": "2026-08-05T04:30:00+00:00",
                        "latest_receive_time": "2026-08-05T04:30:00.010000+00:00",
                        "latest_persist_time": "2026-08-05T04:30:00.020000+00:00",
                        "observed_event_types": ["CANDIDATE_CREATED"],
                        "required_event_types": ["CANDIDATE_CREATED"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    policy.write_text(
        json.dumps(
            {
                "freshness_limits_seconds": {"candidate_lineage": 5.0},
                "ranking_stability_top_k": 1,
                "score_policy": {
                    "minimum_reference_sessions": 3,
                    "metrics": {
                        "score_range": {"lower_quantile": 0.0, "upper_quantile": 1.0},
                        "fallback_contamination_rate": {"upper_quantile": 1.0},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps(
            {
                "ranking_metrics": {
                    "score_range": [0.2, 0.3, 0.4],
                    "fallback_contamination_rate": [0.0, 0.0, 0.0],
                }
            }
        ),
        encoding="utf-8",
    )
    certification.write_text(json.dumps({"verdict": "INSUFFICIENT_EVIDENCE"}), encoding="utf-8")
    run = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_aixion_elite_cockpit.py"),
            "--canary-readiness",
            str(canary),
            "--session-analysis",
            str(session),
            "--candidate-lineage",
            str(lineage),
            "--source-checkpoints",
            str(checkpoints),
            "--policy",
            str(policy),
            "--baseline",
            str(baseline),
            "--certification",
            str(certification),
            "--output-dir",
            str(output),
            "--evaluation-time",
            "2026-08-05T04:30:01+00:00",
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    json_path = output / "elite_cockpit.json"
    markdown_path = output / "elite_cockpit.md"
    assert json_path.is_file() and json_path.stat().st_size > 0
    assert markdown_path.is_file() and markdown_path.stat().st_size > 0
    record = json.loads(json_path.read_text(encoding="utf-8"))
    assert record["authorities"]["observation"]["verdict"] == "READ_ONLY_OBSERVATION_ALLOWED"
    assert record["authorities"]["diagnosis"]["verdict"] == "STRATEGY_DIAGNOSIS_ALLOWED"
    assert record["authorities"]["profitability_claim"]["verdict"] == "PROFITABILITY_CLAIM_BLOCKED"
    assert record["ranking"]["score_separation"]["cycle_id"] == "current"
    assert "# Aixion Elite Analytics Cockpit" in markdown_path.read_text(encoding="utf-8")
