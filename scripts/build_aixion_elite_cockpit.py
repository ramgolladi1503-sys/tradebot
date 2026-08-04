#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aixion_trade_intelligence.elite_cockpit import build_elite_analytics_cockpit
from aixion_trade_intelligence.evidence_guardian import (
    SourceContinuityCheckpoint,
    summarize_evidence_guardian,
)
from aixion_trade_intelligence.ranking_diagnostics import (
    CandidateScoreObservation,
    analyze_score_separation,
    compare_cycle_rankings,
    evaluate_empirical_score_policy,
)


def _read_json(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"json_root_must_be_object path={path}")
    return payload


def _read_jsonl(path: Path) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_jsonl path={path} line={line_number}") from exc
            if not isinstance(payload, Mapping):
                raise ValueError(f"jsonl_row_must_be_object path={path} line={line_number}")
            rows.append(payload)
    if not rows:
        raise ValueError(f"jsonl_empty path={path}")
    return rows


def _score_cycles(rows: Iterable[Mapping[str, object]]) -> tuple[list[CandidateScoreObservation], list[CandidateScoreObservation] | None]:
    grouped: dict[str, list[CandidateScoreObservation]] = {}
    cycle_order: list[str] = []
    for row in rows:
        score_value = row.get("final_score") if row.get("final_score") is not None else row.get("score")
        if score_value is None or not bool(row.get("rankable")):
            continue
        observation = CandidateScoreObservation.from_mapping(row)
        if observation.cycle_id not in grouped:
            grouped[observation.cycle_id] = []
            cycle_order.append(observation.cycle_id)
        grouped[observation.cycle_id].append(observation)
    if not cycle_order:
        raise ValueError("candidate_lineage_has_no_rankable_scored_cycle")
    current = grouped[cycle_order[-1]]
    previous = grouped[cycle_order[-2]] if len(cycle_order) > 1 else None
    return current, previous


def _checkpoint_rows(payload: Mapping[str, object]) -> list[SourceContinuityCheckpoint]:
    values = payload.get("sources")
    if not isinstance(values, list) or not values:
        raise ValueError("source_checkpoints_sources_missing")
    rows: list[SourceContinuityCheckpoint] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("source_checkpoint_row_not_object")
        rows.append(SourceContinuityCheckpoint.from_mapping(value))
    return rows


def _render_markdown(record: Mapping[str, object]) -> str:
    authorities = record.get("authorities")
    if not isinstance(authorities, Mapping):
        raise ValueError("cockpit_authorities_missing")
    lines = [
        "# Aixion Elite Analytics Cockpit",
        "",
        "## Authority matrix",
        "",
        "| Authority | Verdict | Passed | Reasons |",
        "|---|---|---:|---|",
    ]
    for name in ("observation", "diagnosis", "strategy_change", "profitability_claim"):
        gate = authorities.get(name)
        if not isinstance(gate, Mapping):
            continue
        reasons = gate.get("reasons") if isinstance(gate.get("reasons"), list) else []
        lines.append(
            f"| {name} | `{gate.get('verdict')}` | `{bool(gate.get('passed'))}` | {'; '.join(str(value) for value in reasons)} |"
        )
    lines.extend(["", "## Global blockers", ""])
    blockers = record.get("global_blockers")
    if isinstance(blockers, list) and blockers:
        lines.extend(f"- `{value}`" for value in blockers)
    else:
        lines.append("- none")
    ranking = record.get("ranking")
    if isinstance(ranking, Mapping):
        score = ranking.get("score_separation")
        if isinstance(score, Mapping):
            lines.extend(
                [
                    "",
                    "## Ranking diagnostics",
                    "",
                    f"- cycle_id: `{score.get('cycle_id')}`",
                    f"- rankable_count: `{score.get('rankable_count')}`",
                    f"- executable_rate: `{score.get('executable_rate')}`",
                    f"- score_range: `{score.get('score_range')}`",
                    f"- score_iqr: `{score.get('score_iqr')}`",
                    f"- top1_minus_top2: `{score.get('top1_minus_top2')}`",
                    f"- fallback_contamination_rate: `{score.get('fallback_contamination_rate')}`",
                    f"- stale_quote_rate: `{score.get('stale_quote_rate')}`",
                    f"- outcome_pairwise_concordance: `{score.get('outcome_pairwise_concordance')}`",
                ]
            )
    evidence = record.get("evidence")
    if isinstance(evidence, Mapping):
        lines.extend(
            [
                "",
                "## Evidence continuity",
                "",
                f"- observation_authority: `{evidence.get('observation_authority')}`",
                f"- valid_source_count: `{evidence.get('valid_source_count')}`",
                f"- invalid_source_count: `{evidence.get('invalid_source_count')}`",
                f"- stale_source_count: `{evidence.get('stale_source_count')}`",
                f"- total_sequence_gap_events: `{evidence.get('total_sequence_gap_events')}`",
                f"- total_malformed_events: `{evidence.get('total_malformed_events')}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the fail-closed Aixion elite analytics cockpit.")
    parser.add_argument("--canary-readiness", type=Path, required=True)
    parser.add_argument("--session-analysis", type=Path, required=True)
    parser.add_argument("--candidate-lineage", type=Path, required=True)
    parser.add_argument("--source-checkpoints", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--certification", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evaluation-time")
    args = parser.parse_args()

    canary = _read_json(args.canary_readiness)
    session_analysis = _read_json(args.session_analysis)
    policy = _read_json(args.policy)
    source_payload = _read_json(args.source_checkpoints)
    checkpoints = _checkpoint_rows(source_payload)
    freshness_limits = policy.get("freshness_limits_seconds")
    if not isinstance(freshness_limits, Mapping) or not freshness_limits:
        raise ValueError("policy_freshness_limits_seconds_missing")
    evaluation_time = (
        datetime.fromisoformat(args.evaluation_time.replace("Z", "+00:00"))
        if args.evaluation_time
        else datetime.now(tz=timezone.utc)
    )
    evidence_summary = summarize_evidence_guardian(
        checkpoints,
        evaluation_time=evaluation_time,
        freshness_limits_seconds={str(key): float(value) for key, value in freshness_limits.items()},
    )

    current_cycle, previous_cycle = _score_cycles(_read_jsonl(args.candidate_lineage))
    score_report = analyze_score_separation(current_cycle)
    ranking_stability = None
    if previous_cycle is not None:
        top_k = int(policy.get("ranking_stability_top_k") or 0)
        if top_k <= 0:
            raise ValueError("policy_ranking_stability_top_k_must_be_positive")
        ranking_stability = compare_cycle_rankings(previous_cycle, current_cycle, top_k=top_k)

    findings = ()
    if args.baseline is not None:
        baseline = _read_json(args.baseline)
        reference_metrics = baseline.get("ranking_metrics")
        score_policy = policy.get("score_policy")
        if not isinstance(reference_metrics, Mapping):
            raise ValueError("baseline_ranking_metrics_missing")
        if not isinstance(score_policy, Mapping):
            raise ValueError("policy_score_policy_missing")
        findings = evaluate_empirical_score_policy(
            score_report,
            reference_metrics={
                str(key): [float(value) for value in values]
                for key, values in reference_metrics.items()
                if isinstance(values, list)
            },
            policy=score_policy,
        )

    certification = _read_json(args.certification) if args.certification is not None else None
    refs = [
        args.canary_readiness.as_posix(),
        args.session_analysis.as_posix(),
        args.candidate_lineage.as_posix(),
        args.source_checkpoints.as_posix(),
        args.policy.as_posix(),
    ]
    if args.baseline is not None:
        refs.append(args.baseline.as_posix())
    if args.certification is not None:
        refs.append(args.certification.as_posix())
    cockpit = build_elite_analytics_cockpit(
        canary_readiness=canary,
        evidence_guardian=evidence_summary,
        session_analysis=session_analysis,
        score_report=score_report,
        ranking_stability=ranking_stability,
        empirical_score_findings=findings,
        certification=certification,
        evidence_refs=refs,
    )
    record = cockpit.to_record()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "elite_cockpit.json"
    markdown_path = args.output_dir / "elite_cockpit.md"
    json_path.write_text(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(record), encoding="utf-8")
    print(json.dumps({"json": json_path.as_posix(), "markdown": markdown_path.as_posix()}, sort_keys=True))
    return 0 if cockpit.observation.passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
