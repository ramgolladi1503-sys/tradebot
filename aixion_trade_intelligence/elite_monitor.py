from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .elite_cockpit import EliteAnalyticsCockpit, build_elite_analytics_cockpit
from .evidence_guardian import summarize_evidence_guardian
from .live_snapshot import LiveSessionSnapshot, build_live_session_snapshot
from .ranking_diagnostics import (
    CandidateScoreObservation,
    analyze_score_separation,
    compare_cycle_rankings,
    evaluate_empirical_score_policy,
)
from .session import SessionAnalyzer
from .source_checkpoint_builder import (
    SourceCheckpointBundle,
    SourceFileSpec,
    build_source_checkpoint_bundle,
)
from .storage import iter_events, verify_event_log


def _complete_lines(raw: bytes) -> tuple[bytes, bool]:
    partial = bool(raw) and not raw.endswith(b"\n")
    if not partial:
        return raw, False
    position = raw.rfind(b"\n")
    if position < 0:
        return b"", True
    return raw[: position + 1], True


def read_complete_jsonl(path: str | Path) -> tuple[list[Mapping[str, object]], bool]:
    source = Path(path)
    raw, partial = _complete_lines(source.read_bytes())
    rows: list[Mapping[str, object]] = []
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        text = raw_line.decode("utf-8").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"monitor_invalid_jsonl path={source} line={line_number}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(f"monitor_jsonl_row_not_object path={source} line={line_number}")
        rows.append(payload)
    if not rows:
        raise ValueError(f"monitor_jsonl_has_no_complete_rows path={source}")
    return rows, partial


def latest_score_cycles(
    rows: Iterable[Mapping[str, object]],
) -> tuple[list[CandidateScoreObservation], list[CandidateScoreObservation] | None]:
    grouped: dict[str, dict[str, CandidateScoreObservation]] = {}
    cycle_order: list[str] = []
    for row in rows:
        score_value = row.get("final_score") if row.get("final_score") is not None else row.get("score")
        if score_value is None or not bool(row.get("rankable")):
            continue
        observation = CandidateScoreObservation.from_mapping(row)
        if observation.cycle_id not in grouped:
            grouped[observation.cycle_id] = {}
            cycle_order.append(observation.cycle_id)
        grouped[observation.cycle_id][observation.candidate_id] = observation
    if not cycle_order:
        raise ValueError("monitor_candidate_lineage_has_no_rankable_scored_cycle")
    current = list(grouped[cycle_order[-1]].values())
    previous = list(grouped[cycle_order[-2]].values()) if len(cycle_order) > 1 else None
    return current, previous


def _event_log_snapshot(path: Path) -> tuple[dict[str, object], list[object], bool]:
    raw, partial = _complete_lines(path.read_bytes())
    if not raw:
        raise ValueError("monitor_event_log_has_no_complete_rows")
    with tempfile.NamedTemporaryFile(prefix="aixion-event-snapshot-", suffix=".jsonl", delete=True) as handle:
        handle.write(raw)
        handle.flush()
        snapshot_path = Path(handle.name)
        verification = verify_event_log(snapshot_path)
        events = list(iter_events(snapshot_path))
    return verification, events, partial


@dataclass(frozen=True)
class EliteMonitorIteration:
    evaluated_at: str
    event_log_partial_line_ignored: bool
    candidate_lineage_partial_line_ignored: bool
    live_snapshot: LiveSessionSnapshot
    source_checkpoints: SourceCheckpointBundle
    cockpit: EliteAnalyticsCockpit

    def to_record(self) -> dict[str, object]:
        return {
            "evaluated_at": self.evaluated_at,
            "event_log_partial_line_ignored": self.event_log_partial_line_ignored,
            "candidate_lineage_partial_line_ignored": self.candidate_lineage_partial_line_ignored,
            "live_snapshot": self.live_snapshot.to_record(),
            "source_checkpoints": self.source_checkpoints.to_record(),
            "cockpit": self.cockpit.to_record(),
        }


def build_elite_monitor_iteration(
    *,
    event_log_path: str | Path,
    candidate_lineage_path: str | Path,
    source_specs: Sequence[SourceFileSpec],
    canary_readiness: Mapping[str, object],
    policy: Mapping[str, object],
    evaluation_time: datetime,
    baseline: Mapping[str, object] | None = None,
    certification: Mapping[str, object] | None = None,
    evidence_refs: Iterable[str] = (),
) -> EliteMonitorIteration:
    evaluated = evaluation_time.astimezone(timezone.utc) if evaluation_time.tzinfo else None
    if evaluated is None:
        raise ValueError("monitor_evaluation_time_must_be_timezone_aware")
    event_log = Path(event_log_path)
    candidate_lineage = Path(candidate_lineage_path)
    verification, events, event_partial = _event_log_snapshot(event_log)
    analysis = SessionAnalyzer().analyze(events)
    live_snapshot = build_live_session_snapshot(analysis, verification=verification)
    checkpoint_bundle = build_source_checkpoint_bundle(source_specs)
    freshness_limits = policy.get("freshness_limits_seconds")
    if not isinstance(freshness_limits, Mapping) or not freshness_limits:
        raise ValueError("monitor_policy_freshness_limits_missing")
    guardian = summarize_evidence_guardian(
        [result.checkpoint for result in checkpoint_bundle.sources],
        evaluation_time=evaluated,
        freshness_limits_seconds={str(key): float(value) for key, value in freshness_limits.items()},
    )
    lineage_rows, lineage_partial = read_complete_jsonl(candidate_lineage)
    current_cycle, previous_cycle = latest_score_cycles(lineage_rows)
    score_report = analyze_score_separation(current_cycle)
    stability = None
    if previous_cycle is not None:
        top_k = int(policy.get("ranking_stability_top_k") or 0)
        if top_k <= 0:
            raise ValueError("monitor_policy_ranking_stability_top_k_invalid")
        stability = compare_cycle_rankings(previous_cycle, current_cycle, top_k=top_k)
    findings = ()
    if baseline is not None:
        reference_metrics = baseline.get("ranking_metrics")
        score_policy = policy.get("score_policy")
        if not isinstance(reference_metrics, Mapping):
            raise ValueError("monitor_baseline_ranking_metrics_missing")
        if not isinstance(score_policy, Mapping):
            raise ValueError("monitor_policy_score_policy_missing")
        findings = evaluate_empirical_score_policy(
            score_report,
            reference_metrics={
                str(key): [float(value) for value in values]
                for key, values in reference_metrics.items()
                if isinstance(values, list)
            },
            policy=score_policy,
        )
    refs = tuple(
        sorted(
            {
                str(event_log),
                str(candidate_lineage),
                *(str(value).strip() for value in evidence_refs if str(value).strip()),
            }
        )
    )
    cockpit = build_elite_analytics_cockpit(
        canary_readiness=canary_readiness,
        evidence_guardian=guardian,
        session_analysis=analysis.to_record(),
        score_report=score_report,
        ranking_stability=stability,
        empirical_score_findings=findings,
        certification=certification,
        evidence_refs=refs,
    )
    return EliteMonitorIteration(
        evaluated_at=evaluated.isoformat(),
        event_log_partial_line_ignored=event_partial,
        candidate_lineage_partial_line_ignored=lineage_partial,
        live_snapshot=live_snapshot,
        source_checkpoints=checkpoint_bundle,
        cockpit=cockpit,
    )


def atomic_write_json(path: str | Path, payload: Mapping[str, object]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(target)
    return target
