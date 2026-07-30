from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .agent import ReliabilityAgent, ScriptedReasoner, ToolRegistry
from .analytics import analyze_candidates, derive_session_verdict
from .contracts import AgentAction, AgentActionType, AgentMode, CertificationLevel
from .evidence import EvidenceLedger, canonical_json, redact
from .openai_reasoner import OpenAIReasoner


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    out: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                out.append({"_invalid_json": True, "line_number": line_number})
                continue
            if isinstance(row, Mapping):
                out.append(dict(row))
    return out


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_session_manifest(
    *, session_id: str, mode: AgentMode, repo_root: str | Path, config: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    config_payload = redact(dict(config or {}))
    return {
        "schema_version": 1,
        "session_id": str(session_id),
        "mode": mode.value,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "repo_root": str(root),
        "config_sha256": hashlib.sha256(canonical_json(config_payload).encode("utf-8")).hexdigest(),
        "config": config_payload,
        "read_only": mode == AgentMode.LIVE_OBSERVE,
        "order_authority": False,
        "broker_write_authority": False,
    }


def default_artifact_paths(repo_root: str | Path, session_date: str | None = None) -> dict[str, Path]:
    root = Path(repo_root)
    date_key = session_date or datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    runtime = root / ".runtime"
    return {
        "events": runtime / "logs" / "events.jsonl",
        "candidate_lineage": runtime / "candidate_lineage" / f"candidate_funnel_{date_key}.jsonl",
        "candidate_summary": runtime / "candidate_lineage" / f"candidate_funnel_summary_{date_key}.jsonl",
        "trade_log": runtime / "logs" / "trade_log.jsonl",
    }


def _row_identifiers(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Return stable identifiers that may join a lineage row to a trade-log row."""
    values: list[str] = []
    for key in ("candidate_id", "trade_id", "instrument_id", "order_id", "trade_key", "id"):
        value = str(row.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    return tuple(values)


def merge_trade_outcomes(
    lineage_rows: Iterable[Mapping[str, Any]],
    trade_rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Merge actual trade lifecycle rows without converting rejected candidates into trades.

    A trade row joins only when it shares a stable identifier with an existing lineage
    candidate. Unmatched trade rows are retained under their own stable identifier so the
    report can surface execution evidence that lacks candidate lineage.
    """
    lineage_materialized = [dict(row) for row in lineage_rows if isinstance(row, Mapping)]
    trade_materialized = [dict(row) for row in trade_rows if isinstance(row, Mapping)]
    merged = list(lineage_materialized)
    identifier_to_candidate: dict[str, str] = {}
    for row in merged:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            identifiers = _row_identifiers(row)
            candidate_id = identifiers[0] if identifiers else ""
        for identifier in _row_identifiers(row):
            if candidate_id:
                identifier_to_candidate.setdefault(identifier, candidate_id)

    matched = 0
    unmatched = 0
    invalid = 0
    for raw in trade_materialized:
        if not isinstance(raw, Mapping):
            continue
        row = dict(raw)
        if row.get("_invalid_json"):
            invalid += 1
            merged.append(row)
            continue
        candidate_id = ""
        for identifier in _row_identifiers(row):
            if identifier in identifier_to_candidate:
                candidate_id = identifier_to_candidate[identifier]
                break
        lineage_match = bool(candidate_id)
        if lineage_match:
            matched += 1
        else:
            identifiers = _row_identifiers(row)
            candidate_id = identifiers[0] if identifiers else ""
            unmatched += 1
        if candidate_id:
            row["candidate_id"] = candidate_id
        row.setdefault("stage", "trade_log")
        execution_status = str(row.get("execution_status") or row.get("status") or "").strip().lower()
        if not row.get("stage_status"):
            if execution_status in {"filled", "executed", "closed", "complete", "completed"}:
                row["stage_status"] = execution_status
            else:
                row["stage_status"] = "recorded"
        row["evidence_source"] = "trade_log"
        row["lineage_match"] = lineage_match
        row["outcome_scope"] = "ACTUAL"
        merged.append(row)
    return merged, {
        "lineage_rows": len(lineage_materialized),
        "trade_rows": len(trade_materialized),
        "matched_trade_rows": matched,
        "unmatched_trade_rows": unmatched,
        "invalid_trade_rows": invalid,
    }


def load_session_rows(paths: Mapping[str, Path]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    lineage_rows = read_jsonl(paths["candidate_lineage"])
    trade_rows = read_jsonl(paths["trade_log"])
    return merge_trade_outcomes(lineage_rows, trade_rows)


def assess_session_evidence(
    *,
    paths: Mapping[str, Path],
    rows: Iterable[Mapping[str, Any]],
    analytics: Mapping[str, Any],
) -> dict[str, Any]:
    materialized = [dict(row) for row in rows if isinstance(row, Mapping)]
    invalid_rows = sum(1 for row in materialized if row.get("_invalid_json"))
    blocked_without_reason = sum(
        1
        for row in materialized
        if str(row.get("stage_status") or row.get("status") or "").strip().lower() in {"blocked", "rejected"}
        and not str(row.get("block_reason") or row.get("block_reason_code") or row.get("reject_reason") or "").strip()
    )
    missing_candidate_ids = sum(
        1
        for row in materialized
        if str(row.get("stage_status") or row.get("status") or "").strip().lower() in {"selected", "approved", "executed", "filled"}
        and not str(row.get("candidate_id") or row.get("trade_id") or row.get("instrument_id") or "").strip()
    )
    unmatched_trade_rows = sum(
        1 for row in materialized
        if row.get("evidence_source") == "trade_log" and row.get("lineage_match") is False
    )
    terminal_outcomes = {"TARGET", "STOP", "TIME_EXIT", "MANUAL_EXIT"}
    approved_without_terminal = sum(
        1
        for item in analytics.get("autopsies") or []
        if item.get("approved") and str(item.get("outcome") or "") not in terminal_outcomes
    )
    summary_rows = read_jsonl(paths["candidate_summary"])
    latest_summary = next((row for row in reversed(summary_rows) if not row.get("_invalid_json")), {})
    generated_total = int(latest_summary.get("generated_total") or 0) if latest_summary else 0
    lineage_candidate_ids = {
        str(row.get("candidate_id") or row.get("trade_id") or row.get("instrument_id") or "").strip()
        for row in materialized
        if row.get("evidence_source") != "trade_log"
        and str(row.get("candidate_id") or row.get("trade_id") or row.get("instrument_id") or "").strip()
    }
    distinct_candidates = len(lineage_candidate_ids)
    unexplained_disappearances = max(0, generated_total - distinct_candidates) if generated_total else 0
    observability_gaps = (
        blocked_without_reason
        + missing_candidate_ids
        + approved_without_terminal
        + unmatched_trade_rows
        + (1 if not materialized else 0)
    )
    return {
        "candidate_lineage_exists": paths["candidate_lineage"].exists(),
        "trade_log_exists": paths["trade_log"].exists(),
        "candidate_summary_exists": paths["candidate_summary"].exists(),
        "invalid_rows": invalid_rows,
        "blocked_without_reason": blocked_without_reason,
        "missing_candidate_ids": missing_candidate_ids,
        "approved_without_terminal_outcome": approved_without_terminal,
        "unmatched_trade_rows": unmatched_trade_rows,
        "generated_total_from_latest_summary": generated_total,
        "distinct_candidates": distinct_candidates,
        "unexplained_disappearances": unexplained_disappearances,
        "observability_gaps": observability_gaps,
        "session_data_valid": bool(paths["candidate_lineage"].exists() and invalid_rows == 0),
    }


def build_tools(repo_root: str | Path, *, session_date: str | None = None) -> ToolRegistry:
    paths = default_artifact_paths(repo_root, session_date=session_date)
    registry = ToolRegistry()

    def artifact_health(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            name: {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "sha256": sha256_file(path) if path.exists() and path.is_file() else None,
            }
            for name, path in paths.items()
        }

    def candidate_analytics(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        rows, merge_stats = load_session_rows(paths)
        analytics = analyze_candidates(rows)
        evidence_quality = assess_session_evidence(paths=paths, rows=rows, analytics=analytics)
        return {**analytics, "merge_stats": merge_stats, "evidence_quality": evidence_quality}

    def query_candidate(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        candidate_id = str(arguments.get("candidate_id") or "")
        all_rows, merge_stats = load_session_rows(paths)
        rows = [row for row in all_rows if str(row.get("candidate_id") or "") == candidate_id]
        return {"candidate_id": candidate_id, "row_count": len(rows), "rows": rows, "merge_stats": merge_stats}

    def query_events(arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        event_type = str(arguments.get("event_type") or "")
        limit = max(1, min(500, int(arguments.get("limit") or 100)))
        rows = read_jsonl(paths["events"])
        if event_type:
            rows = [row for row in rows if str(row.get("type") or row.get("event_type") or "") == event_type]
        return {"event_type": event_type, "row_count": len(rows), "rows": rows[-limit:]}

    registry.register("get_artifact_health", artifact_health, description="Check required runtime evidence artifacts and hashes.")
    registry.register("analyze_candidate_lineage", candidate_analytics, description="Build deterministic funnel, rejection and candidate autopsy analytics.")
    registry.register("query_candidate_lineage", query_candidate, description="Return all lifecycle rows for one candidate ID.")
    registry.register("query_runtime_events", query_events, description="Return bounded runtime events by event type.")
    return registry


def finalize_session(
    *,
    session_id: str,
    repo_root: str | Path,
    output_dir: str | Path,
    session_date: str | None = None,
) -> dict[str, Any]:
    paths = default_artifact_paths(repo_root, session_date=session_date)
    rows, merge_stats = load_session_rows(paths)
    analytics = analyze_candidates(rows)
    evidence_quality = assess_session_evidence(paths=paths, rows=rows, analytics=analytics)
    untrustworthy = sum(
        1
        for item in analytics["autopsies"]
        if item["approved"] and (
            item["facts"].get("fallback_used")
            or item["facts"].get("recovered_fallback")
            or item["facts"].get("stale_quote")
        )
    )
    missed = int(analytics["rejection_verdicts"].get("MISSED_OPPORTUNITY", 0))
    verdict = derive_session_verdict(
        session_data_valid=bool(evidence_quality["session_data_valid"]),
        emitted_untrustworthy=untrustworthy,
        unexplained_disappearances=int(evidence_quality["unexplained_disappearances"]),
        observability_gaps=int(evidence_quality["observability_gaps"]),
        materially_missed_candidates=missed,
    )
    report = {
        "schema_version": 1,
        "session_id": session_id,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "session_verdict": verdict.value,
        "certification_level": CertificationLevel.LIVE_CERTIFICATION_PENDING.value,
        "limitations": [
            "One session cannot certify strategy profitability or structural edge.",
            "Observed contributors are not asserted as unique market causes.",
            "LIVE_CERTIFIED requires a real session with complete artifacts and explicit acceptance gates.",
        ],
        "artifact_paths": {key: str(value) for key, value in paths.items()},
        "merge_stats": merge_stats,
        "evidence_quality": evidence_quality,
        "analytics": analytics,
    }
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / f"{session_id}_post_market_report.json"
    md_path = target / f"{session_id}_post_market_report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {**report, "json_path": str(json_path), "markdown_path": str(md_path)}


def render_markdown(report: Mapping[str, Any]) -> str:
    analytics = dict(report.get("analytics") or {})
    lines = [
        "# TradeBot AI Reliability Agent — Post-Market Report",
        "",
        f"- Session: `{report.get('session_id')}`",
        f"- Verdict: `{report.get('session_verdict')}`",
        f"- Certification: `{report.get('certification_level')}`",
        f"- Candidates: `{analytics.get('candidate_count', 0)}`",
        "",
        "## Evidence quality",
        "",
    ]
    for key, value in sorted(dict(report.get("evidence_quality") or {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend([
        "",
        "## Pipeline funnel",
        "",
    ])
    for key, value in sorted(dict(analytics.get("pipeline_funnel") or {}).items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Rejections", ""])
    for key, value in dict(analytics.get("rejection_breakdown") or {}).items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Candidate autopsies", ""])
    for item in analytics.get("autopsies") or []:
        lines.extend([
            f"### {item.get('candidate_id')}",
            f"- Strategy: `{item.get('strategy_name') or 'unknown'}`",
            f"- Approved: `{item.get('approved')}`; executed: `{item.get('executed')}`",
            f"- Outcome: `{item.get('outcome')}` (`{item.get('outcome_scope')}`)",
            f"- Decision/outcome class: `{item.get('decision_outcome_class')}`",
            f"- Rejection verdict: `{item.get('rejection_verdict')}`",
        ])
        for contributor in item.get("observed_contributors") or []:
            lines.append(
                f"- Contributor `{contributor.get('factor')}` ({contributor.get('claim_kind')}, "
                f"confidence={contributor.get('confidence')}): {contributor.get('explanation')}"
            )
        lines.append("")
    lines.extend(["## Limitations", ""])
    for limitation in report.get("limitations") or []:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


def run_live_agent(
    *,
    session_id: str,
    repo_root: str | Path,
    evidence_path: str | Path,
    objective: str,
    model: str | None = None,
) -> dict[str, Any]:
    tools = build_tools(repo_root)
    ledger = EvidenceLedger(evidence_path)
    manifest = build_session_manifest(session_id=session_id, mode=AgentMode.LIVE_OBSERVE, repo_root=repo_root)
    ledger.append("session_manifest", manifest, session_id=session_id)
    reasoner = OpenAIReasoner(model=model)
    agent = ReliabilityAgent(
        session_id=session_id,
        mode=AgentMode.LIVE_OBSERVE,
        reasoner=reasoner,
        tools=tools,
        ledger=ledger,
        max_steps=12,
        max_tool_calls=8,
    )
    return agent.run(objective, initial_observations={"manifest": manifest})


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TradeBot bounded AI reliability and post-market analytics agent")
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("live-observe")
    live.add_argument("--session-id", required=True)
    live.add_argument("--repo-root", default=".")
    live.add_argument("--evidence-path", required=True)
    live.add_argument("--objective", default="Identify the highest-impact evidence-backed reliability issue, or prove no material issue was observed.")
    live.add_argument("--model", default=None)
    watch = sub.add_parser("live-watch")
    watch.add_argument("--session-id", required=True)
    watch.add_argument("--repo-root", default=".")
    watch.add_argument("--evidence-path", required=True)
    watch.add_argument("--session-date", default=None)
    watch.add_argument("--interval-sec", type=float, default=15.0)
    watch.add_argument("--max-iterations", type=int, default=None)
    watch.add_argument("--stop-file", default=None)
    certify = sub.add_parser("certify")
    certify.add_argument("--output-dir", required=True)
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--session-id", required=True)
    finalize.add_argument("--repo-root", default=".")
    finalize.add_argument("--output-dir", required=True)
    finalize.add_argument("--session-date", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "live-observe":
        result = run_live_agent(
            session_id=args.session_id,
            repo_root=args.repo_root,
            evidence_path=args.evidence_path,
            objective=args.objective,
            model=args.model,
        )
    elif args.command == "live-watch":
        from .supervisor import LiveAgentSupervisor
        result = LiveAgentSupervisor(
            session_id=args.session_id,
            repo_root=args.repo_root,
            evidence_path=args.evidence_path,
            interval_sec=args.interval_sec,
            session_date=args.session_date,
        ).run(max_iterations=args.max_iterations, stop_file=args.stop_file)
    elif args.command == "certify":
        from .certification import run_component_certification
        result = run_component_certification(args.output_dir)
    else:
        result = finalize_session(
            session_id=args.session_id,
            repo_root=args.repo_root,
            output_dir=args.output_dir,
            session_date=args.session_date,
        )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0
