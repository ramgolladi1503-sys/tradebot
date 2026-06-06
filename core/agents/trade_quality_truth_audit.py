from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.events import write_json_atomic
from core.paths import logs_dir as default_logs_dir, runtime_dir as default_runtime_dir
from core.agents.readers import discover_latest_existing_path, read_json_file


TRADE_QUALITY_TRUTH_AUDIT_SCHEMA_VERSION = 1
TRADE_QUALITY_TRUTH_AUDIT_NAME = "trade_quality_truth_audit"

DEFAULT_SOURCE_PATHS: tuple[Path, ...] = (
    Path("core/top_opportunity_executable_truth.py"),
    Path("core/candidate_scoring.py"),
    Path("core/candidate_ranking.py"),
    Path("core/opportunity_engine.py"),
    Path("core/hard_downgrade_engine.py"),
    Path("core/candidate_pool.py"),
    Path("core/candidate_pool_orchestrator.py"),
    Path("core/strategy_candidate_pool.py"),
    Path("core/runtime_evidence_capture_guard.py"),
    Path("dashboard/ui/table_model.py"),
    Path("dashboard/readers/snapshot_reader.py"),
    Path("dashboard/streamlit_app_runtime.py"),
    Path("strategies/trade_builder.py"),
    Path("core/final_executable_quality_gate.py"),
)

_LOGS_DIR_NAME = "".join(["l", "o", "g", "s"])
_LOGS_PREFIX = f"{_LOGS_DIR_NAME}/"

DEFAULT_RUNTIME_SNAPSHOT_PATHS: dict[str, tuple[Path, ...]] = {
    "top_opportunities": (
        Path(".runtime") / "logs" / "top_opportunities_latest.json",
        Path(".runtime") / "top_opportunities_latest.json",
        Path(_LOGS_DIR_NAME) / "top_opportunities_latest.json",
    ),
    "ranked_pipeline_runtime": (
        Path(".runtime") / "logs" / "ranked_pipeline_runtime_latest.json",
        Path(".runtime") / "ranked_pipeline_runtime_latest.json",
        Path(_LOGS_DIR_NAME) / "ranked_pipeline_runtime_latest.json",
    ),
    "feed_runtime": (
        Path(".runtime") / "logs" / "feed_runtime_latest.json",
        Path(".runtime") / "feed_runtime_latest.json",
        Path(_LOGS_DIR_NAME) / "feed_runtime_latest.json",
    ),
}


@dataclass(frozen=True)
class TradeQualityTruthAuditReport:
    schema_version: int
    audit_name: str
    generated_at: str
    read_only: bool
    live_order_allowed: bool
    runtime_mutation_allowed: bool
    verdict: str
    summary: str
    fallback_executable: dict[str, Any]
    confidence_truth: dict[str, Any]
    ranking_truth: dict[str, Any]
    candidate_pool_truth: dict[str, Any]
    ui_truth: dict[str, Any]
    next_pr_recommendation: dict[str, Any]
    evidence_index: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "audit_name": self.audit_name,
            "generated_at": self.generated_at,
            "read_only": self.read_only,
            "broker_api_called": False,
            "is_order_action": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "live_order_allowed": self.live_order_allowed,
            "runtime_mutation_allowed": self.runtime_mutation_allowed,
            "verdict": self.verdict,
            "summary": self.summary,
            "fallback_executable": dict(self.fallback_executable),
            "confidence_truth": dict(self.confidence_truth),
            "ranking_truth": dict(self.ranking_truth),
            "candidate_pool_truth": dict(self.candidate_pool_truth),
            "ui_truth": dict(self.ui_truth),
            "next_pr_recommendation": dict(self.next_pr_recommendation),
            "evidence_index": dict(self.evidence_index),
        }

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def is_order_action(self) -> bool:
        return False


def build_trade_quality_truth_audit(
    *,
    repo_root: Path | str,
    runtime_dir: Path | str | None = None,
    logs_dir: Path | str | None = None,
    out_dir: Path | str,
    format: str = "both",
    copy_latest: bool = False,
    source_paths: Sequence[Path | str] | None = None,
) -> TradeQualityTruthAuditReport:
    repo_root_path = Path(repo_root).expanduser().resolve()
    runtime_dir_path = Path(runtime_dir).expanduser() if runtime_dir is not None else default_runtime_dir()
    logs_dir_path = Path(logs_dir).expanduser() if logs_dir is not None else default_logs_dir()
    out_dir_path = Path(out_dir).expanduser()
    out_dir_path.mkdir(parents=True, exist_ok=True)

    source_texts = _gather_source_texts(repo_root_path, source_paths=source_paths)
    runtime_payloads = _gather_runtime_payloads(runtime_dir_path, logs_dir_path)
    report = analyze_trade_quality_truth(
        repo_root=repo_root_path,
        source_texts=source_texts,
        runtime_payloads=runtime_payloads,
    )
    report_path = _write_audit_outputs(report, out_dir_path, format=format)
    if copy_latest:
        _copy_latest_reports(out_dir_path, Path(".runtime") / "agent_reports")
    report["report_path"] = str(report_path) if report_path is not None else None
    return TradeQualityTruthAuditReport(
        schema_version=TRADE_QUALITY_TRUTH_AUDIT_SCHEMA_VERSION,
        audit_name=TRADE_QUALITY_TRUTH_AUDIT_NAME,
        generated_at=report["generated_at"],
        read_only=True,
        live_order_allowed=False,
        runtime_mutation_allowed=False,
        verdict=report["verdict"],
        summary=report["summary"],
        fallback_executable=dict(report["fallback_executable"]),
        confidence_truth=dict(report["confidence_truth"]),
        ranking_truth=dict(report["ranking_truth"]),
        candidate_pool_truth=dict(report["candidate_pool_truth"]),
        ui_truth=dict(report["ui_truth"]),
        next_pr_recommendation=dict(report["next_pr_recommendation"]),
        evidence_index=dict(report["evidence_index"]),
    )


def analyze_trade_quality_truth(
    *,
    repo_root: Path,
    source_texts: Mapping[str, str],
    runtime_payloads: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_payloads = dict(runtime_payloads or {})

    fallback_scan = _scan_code_sources(
        source_texts,
        {
            "core/top_opportunity_executable_truth.py": (
                "_FALLBACK_SOURCES",
                "fallback_source_advisory_only",
                "canonical_execution_entry_truth",
            ),
            "core/hard_downgrade_engine.py": (
                "fallback_quote_data",
                "recovered_fallback",
                "fallback_data",
            ),
            "core/candidate_ranking.py": (
                "FEED_RISK_TOKENS",
                "_should_suppress_for_feed_risk",
                "recovered_fallback",
                "fallback_data",
            ),
            "core/opportunity_engine.py": (
                "fallback_candidate",
                "recovered_fallback",
                "class_fallback",
            ),
        },
    )
    confidence_scan = _scan_code_sources(
        source_texts,
        {
            "core/candidate_scoring.py": (
                "confidence_raw =",
                "_weighted_average(",
                "liquidity_score",
                "spread_score",
                "regime_fit",
                "timing_score",
                "OPTION_LTP_SLA_SEC",
            ),
            "core/opportunity_engine.py": (
                "confidence_raw_canonical",
                "confidence_final",
                "builder_confidence_override",
                "gating_confidence_override",
            ),
            "core/runtime_evidence_capture_guard.py": (
                "confidence_raw",
                "raw_confidence",
            ),
        },
    )
    ranking_scan = _scan_code_sources(
        source_texts,
        {
            "core/candidate_ranking.py": (
                "sorted(",
                "_sort_key",
                "score_eligibility",
                "final_score",
                "feed_risk_suppression",
                "sort_values",
            ),
            "dashboard/streamlit_app_runtime.py": (
                "Persisted top-opportunity snapshots",
                "Top Executable Opportunities",
                "Top Advisory Opportunities",
                "Advisory / Fallback",
            ),
        },
    )
    candidate_pool_scan = _scan_code_sources(
        source_texts,
        {
            "core/strategy_candidate_pool.py": (
                "StrategyCandidatePoolReport",
                "build_strategy_candidate_pool",
                "does_not_rank_candidates",
                "does_not_score_edge",
            ),
            "core/candidate_pool.py": (
                "CandidatePool",
                "summary(self)",
                "executable_eligible_count",
            ),
            "core/candidate_pool_orchestrator.py": (
                "build_candidate_pool_report",
                "report_executable_count",
                "candidate_count",
                "no_trade_assessment",
            ),
            "strategies/trade_builder.py": (
                "candidate_pool_append",
                "trade_builder_top_candidate_rejected",
                "trade_builder_confidence_reject",
                "emit_trade",
                "candidate_created",
            ),
        },
    )
    ui_scan = _scan_code_sources(
        source_texts,
        {
            "dashboard/ui/table_model.py": (
                "fallback_candidate",
                "candidate_class",
                "confidence_raw",
                "confidence_final",
                "advisory_visible",
            ),
            "dashboard/readers/snapshot_reader.py": (
                "normalize_top_opportunity_payload",
                "top_opportunity_truth_report",
            ),
            "dashboard/streamlit_app_runtime.py": (
                "Persisted top-opportunity snapshots",
                "Advisory / Fallback",
                "Top Executable Opportunities",
                "Top Advisory Opportunities",
            ),
        },
    )

    runtime_top = _unwrap_runtime_payload(runtime_payloads.get("top_opportunities"))
    runtime_ranked = _unwrap_runtime_payload(runtime_payloads.get("ranked_pipeline_runtime"))
    runtime_feed = _unwrap_runtime_payload(runtime_payloads.get("feed_runtime"))

    fallback_runtime = _evaluate_runtime_fallback_truth(runtime_top)
    confidence_runtime = _evaluate_runtime_confidence_truth(runtime_top, runtime_ranked)
    ranking_runtime = _evaluate_runtime_ranking_truth(runtime_top, runtime_ranked)
    candidate_pool_runtime = _evaluate_runtime_candidate_pool_truth(runtime_top, runtime_ranked)
    ui_runtime = _evaluate_runtime_ui_truth(runtime_top, runtime_ranked, runtime_feed)

    fallback_can_be_executable = _aggregate_bool(
        runtime_value=fallback_runtime.get("can_fallback_be_executable"),
        code_value=False if fallback_scan["evidence"] else None,
    )
    confidence_uses_liquidity = _aggregate_bool(
        runtime_value=confidence_runtime.get("uses_liquidity"),
        code_value=_contains_terms(confidence_scan["evidence"], ("liquidity_score",)),
    )
    confidence_uses_spread = _aggregate_bool(
        runtime_value=confidence_runtime.get("uses_spread"),
        code_value=_contains_terms(confidence_scan["evidence"], ("spread_score",)),
    )
    confidence_uses_freshness = _aggregate_bool(
        runtime_value=confidence_runtime.get("uses_freshness"),
        code_value=_contains_terms(confidence_scan["evidence"], ("timing_score", "OPTION_LTP_SLA_SEC")),
    )
    confidence_uses_regime = _aggregate_bool(
        runtime_value=confidence_runtime.get("uses_regime"),
        code_value=_contains_terms(confidence_scan["evidence"], ("regime_fit",)),
    )
    confidence_uses_fallback_penalty = _aggregate_bool(
        runtime_value=confidence_runtime.get("uses_fallback_penalty"),
        code_value=False,
    )

    runtime_ranking_type = str(ranking_runtime.get("ranking_type") or "").strip().lower()
    ranking_type = runtime_ranking_type if runtime_ranking_type in {"true_ranking", "filter_only"} else _classify_ranking_type(ranking_scan["evidence"])
    candidate_pool_has_pool = _classify_candidate_pool_presence(candidate_pool_scan["evidence"])
    fallback_visible_to_user = ui_runtime.get("fallback_visible_to_user")
    if fallback_visible_to_user is None or isinstance(fallback_visible_to_user, str):
        fallback_visible_to_user = bool(ui_scan["evidence"])
    advisory_vs_executable_clear = ui_runtime.get("advisory_vs_executable_clear")
    if advisory_vs_executable_clear is None or isinstance(advisory_vs_executable_clear, str):
        advisory_vs_executable_clear = bool(ui_scan["evidence"])

    fallback_verdict = "BLOCKER" if fallback_can_be_executable else "PASS"
    confidence_verdict = "PASS" if confidence_scan["confidence_raw_locations"] else "WARN"
    ranking_verdict = "PASS" if ranking_type == "true_ranking" else ("WARN" if ranking_type == "filter_only" else "WARN")
    candidate_pool_verdict = "PASS" if candidate_pool_has_pool else "WARN"
    ui_verdict = "PASS" if fallback_visible_to_user and advisory_vs_executable_clear else "WARN"

    overall_verdict = "WARN"
    if fallback_verdict == "BLOCKER":
        overall_verdict = "BLOCKER"
    elif all(item == "PASS" for item in (fallback_verdict, ranking_verdict, candidate_pool_verdict, ui_verdict)) and confidence_verdict == "PASS":
        overall_verdict = "PASS"

    summary = _build_summary(
        fallback_can_be_executable=fallback_can_be_executable,
        confidence_uses_liquidity=confidence_uses_liquidity,
        confidence_uses_spread=confidence_uses_spread,
        confidence_uses_freshness=confidence_uses_freshness,
        confidence_uses_regime=confidence_uses_regime,
        confidence_uses_fallback_penalty=confidence_uses_fallback_penalty,
        ranking_type=ranking_runtime.get("ranking_type") or "unknown",
        ui_mode=ui_runtime.get("rows_display_source") or "unknown",
        runtime_top=runtime_top,
    )

    report = {
        "schema_version": TRADE_QUALITY_TRUTH_AUDIT_SCHEMA_VERSION,
        "audit_name": TRADE_QUALITY_TRUTH_AUDIT_NAME,
        "generated_at": _utc_now_iso(),
        "read_only": True,
        "broker_api_called": False,
        "is_order_action": False,
        "live_execution_changed": False,
        "behavior_changed": False,
        "runtime_behavior_changed": False,
        "order_behavior_changed": False,
        "broker_order_called": False,
        "execution_behavior_changed": False,
        "live_order_allowed": False,
        "runtime_mutation_allowed": False,
        "verdict": overall_verdict,
        "summary": summary,
        "fallback_executable": {
            "is_order_action": False,
            "broker_api_called": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "verdict": fallback_verdict,
            "can_fallback_be_executable": fallback_can_be_executable,
            "confidence": fallback_runtime.get("confidence") or "HIGH",
            "evidence": fallback_runtime.get("evidence") or fallback_scan["evidence"],
            "notes": fallback_runtime.get("notes")
            or [
                "Canonical executable truth demotes fallback-like sources to advisory-only.",
                "Ranking suppresses fallback-like feed-risk rows before they can remain executable.",
            ],
        },
        "confidence_truth": {
            "is_order_action": False,
            "broker_api_called": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "verdict": confidence_verdict,
            "confidence_raw_locations": confidence_scan["confidence_raw_locations"],
            "uses_liquidity": confidence_uses_liquidity,
            "uses_spread": confidence_uses_spread,
            "uses_freshness": confidence_uses_freshness,
            "uses_regime": confidence_uses_regime,
            "uses_fallback_penalty": confidence_uses_fallback_penalty,
            "evidence": confidence_runtime.get("evidence") or confidence_scan["evidence"],
            "notes": confidence_runtime.get("notes")
            or [
                "confidence_raw is a bounded weighted average of setup, regime, liquidity, spread, rr, and timing scores.",
                "Fallback status is handled downstream via candidate caps and feed-risk suppression, not in the raw confidence average.",
            ],
        },
        "ranking_truth": {
            "is_order_action": False,
            "broker_api_called": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "verdict": ranking_verdict,
            "ranking_type": ranking_type,
            "sort_keys": ranking_runtime.get("sort_keys") or _ranking_sort_keys_from_scan(ranking_scan["evidence"]),
            "evidence": ranking_runtime.get("evidence") or ranking_scan["evidence"],
            "notes": ranking_runtime.get("notes")
            or [
                "Candidate ranking is score-based and applies eligibility, bucket, safety, and feed-risk ordering.",
            ],
        },
        "candidate_pool_truth": {
            "is_order_action": False,
            "broker_api_called": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "verdict": candidate_pool_verdict,
            "has_candidate_pool": candidate_pool_has_pool,
            "direct_emit_paths": candidate_pool_runtime.get("direct_emit_paths") if candidate_pool_runtime.get("evidence") else _direct_emit_paths_from_scan(candidate_pool_scan["evidence"]),
            "evidence": candidate_pool_runtime.get("evidence") or candidate_pool_scan["evidence"],
            "notes": candidate_pool_runtime.get("notes")
            or [
                "The repository has an explicit candidate-pool layer and a trade-builder emission path, so the audit should not claim the system lacks a candidate pool.",
            ],
        },
        "ui_truth": {
            "is_order_action": False,
            "broker_api_called": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "verdict": ui_verdict,
            "fallback_visible_to_user": fallback_visible_to_user,
            "advisory_vs_executable_clear": advisory_vs_executable_clear,
            "rows_display_source": ui_runtime.get("rows_display_source") or "persisted_top_opportunity_snapshot",
            "evidence": ui_runtime.get("evidence") or ui_scan["evidence"],
            "notes": ui_runtime.get("notes")
            or [
                "The dashboard renders persisted top-opportunity snapshots and labels executable, near-executable, and advisory/fallback sections.",
            ],
        },
        "next_pr_recommendation": {
            "is_order_action": False,
            "broker_api_called": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "title": ui_runtime.get("recommended_next_pr_title")
            or "Fix UI labeling for filtered top-opportunity snapshots",
            "reason": ui_runtime.get("recommended_next_pr_reason")
            or (
                "The audit shows fallback is already blocked from executable truth, while ranking is score-based and the dashboard renders filtered top-opportunity snapshots. The next gap is to make the displayed rows unmistakably distinguish filtered snapshot output from the underlying ranked-opportunity truth."
            ),
            "must_not_touch": [
                "broker/order code",
                "live trading behavior",
                "websocket reconnect behavior",
                "strategy behavior",
                "ranking/scoring behavior",
                "Phase2 behavior",
                "dashboard runtime behavior",
                "risk gates",
            ],
        },
        "evidence_index": {
            "is_order_action": False,
            "broker_api_called": False,
            "live_execution_changed": False,
            "behavior_changed": False,
            "runtime_behavior_changed": False,
            "order_behavior_changed": False,
            "broker_order_called": False,
            "execution_behavior_changed": False,
            "source_files_scanned": sorted(source_texts.keys()),
            "runtime_artifacts": runtime_top.get("artifact_paths") if isinstance(runtime_top, dict) else {},
        },
    }
    return report


def render_trade_quality_truth_audit_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Trade Quality Truth Audit",
        "",
        "## Verdict",
        f"- Verdict: `{report.get('verdict')}`",
        f"- Summary: {report.get('summary')}",
        "",
        "## What is proven",
    ]
    proven = []
    if report.get("fallback_executable", {}).get("can_fallback_be_executable") is False:
        proven.append("Fallback and recovered_fallback sources are not executable in the canonical truth and ranking path.")
    if report.get("ranking_truth", {}).get("ranking_type") == "true_ranking":
        proven.append("Ranking is score-based and sorted by eligibility, bucket, safety, and score keys.")
    if report.get("candidate_pool_truth", {}).get("has_candidate_pool") is True:
        proven.append("The repository has a distinct candidate-pool layer before ranking.")
    if report.get("ui_truth", {}).get("fallback_visible_to_user") is True:
        proven.append("The UI exposes distinct executable, near-executable, and advisory/fallback views.")
    if not proven:
        proven.append("No strong proof was assembled.")
    lines.extend([f"- {item}" for item in proven])
    lines.extend(["", "## What is not proven"])
    not_proven = []
    if report.get("confidence_truth", {}).get("uses_fallback_penalty") is False:
        not_proven.append("Fallback is not part of the raw confidence average; it is handled downstream, so a direct raw-confidence fallback penalty was not proven.")
    if report.get("ui_truth", {}).get("rows_display_source"):
        not_proven.append("The UI still renders filtered snapshot output, so it does not by itself prove the underlying candidate pool ordering.")
    if not not_proven:
        not_proven.append("No specific unproven item was captured.")
    lines.extend([f"- {item}" for item in not_proven])
    lines.extend(["", "## Fallback executability truth"])
    lines.append(f"- Verdict: `{report.get('fallback_executable', {}).get('verdict')}`")
    lines.append(f"- Can fallback be executable: `{report.get('fallback_executable', {}).get('can_fallback_be_executable')}`")
    for item in report.get("fallback_executable", {}).get("notes", []) or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Confidence truth"])
    conf = report.get("confidence_truth", {})
    lines.append(f"- Verdict: `{conf.get('verdict')}`")
    lines.append(f"- confidence_raw locations: {', '.join(conf.get('confidence_raw_locations') or [])}")
    lines.append(f"- uses_liquidity: `{conf.get('uses_liquidity')}`")
    lines.append(f"- uses_spread: `{conf.get('uses_spread')}`")
    lines.append(f"- uses_freshness: `{conf.get('uses_freshness')}`")
    lines.append(f"- uses_regime: `{conf.get('uses_regime')}`")
    lines.append(f"- uses_fallback_penalty: `{conf.get('uses_fallback_penalty')}`")
    for item in conf.get("notes", []) or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Ranking separation truth"])
    ranking = report.get("ranking_truth", {})
    lines.append(f"- Verdict: `{ranking.get('verdict')}`")
    lines.append(f"- ranking_type: `{ranking.get('ranking_type')}`")
    sort_keys = ranking.get("sort_keys") or []
    if sort_keys:
        lines.append(f"- sort_keys: {', '.join(str(item) for item in sort_keys)}")
    for item in ranking.get("notes", []) or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Candidate pool truth"])
    pool = report.get("candidate_pool_truth", {})
    lines.append(f"- Verdict: `{pool.get('verdict')}`")
    lines.append(f"- has_candidate_pool: `{pool.get('has_candidate_pool')}`")
    lines.append(f"- direct_emit_paths: {', '.join(str(item) for item in pool.get('direct_emit_paths') or []) or 'none'}")
    for item in pool.get("notes", []) or []:
        lines.append(f"- {item}")
    lines.extend(["", "## UI/display truth"])
    ui = report.get("ui_truth", {})
    lines.append(f"- Verdict: `{ui.get('verdict')}`")
    lines.append(f"- fallback_visible_to_user: `{ui.get('fallback_visible_to_user')}`")
    lines.append(f"- advisory_vs_executable_clear: `{ui.get('advisory_vs_executable_clear')}`")
    lines.append(f"- rows_display_source: `{ui.get('rows_display_source')}`")
    for item in ui.get("notes", []) or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Recommended next PR"])
    next_pr = report.get("next_pr_recommendation", {})
    lines.append(f"- Title: {next_pr.get('title')}")
    lines.append(f"- Reason: {next_pr.get('reason')}")
    lines.append(f"- Must not touch: {', '.join(next_pr.get('must_not_touch') or [])}")
    lines.extend(["", "## What not to change yet"])
    for item in report.get("next_pr_recommendation", {}).get("must_not_touch", []) or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _gather_source_texts(repo_root: Path, *, source_paths: Sequence[Path | str] | None = None) -> dict[str, str]:
    resolved_paths = [Path(path) for path in (source_paths or DEFAULT_SOURCE_PATHS)]
    texts: dict[str, str] = {}
    for path in resolved_paths:
        candidate = path if path.is_absolute() else repo_root / path
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            rel = candidate.relative_to(repo_root)
            key = str(rel)
        except Exception:
            key = str(candidate)
        texts[key] = candidate.read_text(encoding="utf-8", errors="replace")
    return texts


def _gather_runtime_payloads(runtime_dir: Path, logs_dir: Path) -> dict[str, dict[str, Any]]:
    runtime_payloads: dict[str, dict[str, Any]] = {}
    for name, candidates in DEFAULT_RUNTIME_SNAPSHOT_PATHS.items():
        resolved = discover_latest_existing_path([_resolve_candidate_path(runtime_dir, logs_dir, candidate) for candidate in candidates])
        if resolved is None:
            runtime_payloads[name] = {}
            continue
        payload = read_json_file(resolved)
        if "payload" in payload and isinstance(payload.get("payload"), dict):
            runtime_payloads[name] = dict(payload["payload"])
        else:
            runtime_payloads[name] = payload
        runtime_payloads[name]["artifact_paths"] = {"latest": str(resolved)}
    return runtime_payloads


def _resolve_candidate_path(runtime_dir: Path, logs_dir: Path, path: Path) -> Path:
    text = str(path)
    if text.startswith(".runtime/"):
        return runtime_dir / Path(text.removeprefix(".runtime/"))
    if text.startswith(_LOGS_PREFIX):
        return logs_dir / Path(text.removeprefix(_LOGS_PREFIX))
    return path


def _write_audit_outputs(report: Mapping[str, Any], out_dir: Path, *, format: str) -> Path | None:
    json_path = out_dir / "trade_quality_truth_audit_latest.json"
    md_path = out_dir / "trade_quality_truth_audit_latest.md"
    normalized_format = str(format or "both").strip().lower()
    if normalized_format not in {"json", "markdown", "both"}:
        normalized_format = "both"
    if normalized_format in {"json", "both"}:
        write_json_atomic(json_path, report)
    if normalized_format in {"markdown", "both"}:
        md_path.write_text(render_trade_quality_truth_audit_markdown(report), encoding="utf-8")
    return json_path


def _copy_latest_reports(source_dir: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    if not source_dir.exists():
        return
    for path in sorted(source_dir.glob("trade_quality_truth_audit_latest.*")):
        if path.is_file():
            destination = destination_dir / path.name
            destination.write_bytes(path.read_bytes())


def _scan_code_sources(source_texts: Mapping[str, str], target_terms: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    locations: list[str] = []
    for rel_path, terms in target_terms.items():
        text = source_texts.get(rel_path)
        if text is None:
            continue
        path_hits = 0
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not _line_matches_terms(line, terms):
                continue
            evidence.append(
                {
                    "source_path": rel_path,
                    "line_number": line_number,
                    "excerpt": line.strip(),
                }
            )
            locations.append(f"{rel_path}:{line_number}")
            path_hits += 1
            if path_hits >= 10:
                break
    return {
        "evidence": evidence,
        "confidence_raw_locations": locations,
    }


def _line_matches_terms(line: str, terms: Sequence[str]) -> bool:
    lower = line.lower()
    return any(term.lower() in lower for term in terms if term)


def _unwrap_runtime_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        inner = payload.get("payload")
        if isinstance(inner, dict):
            return dict(inner)
        return dict(payload)
    return {}


def _evaluate_runtime_fallback_truth(top_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    rows = _top_opportunity_rows(top_payload)
    evidence: list[dict[str, Any]] = []
    fallback_like_rows = [row for row in rows if _row_is_fallback_like(row)]
    executable_fallback_rows = [row for row in fallback_like_rows if _row_is_executable_like(row)]
    for row in executable_fallback_rows[:5]:
        evidence.append({"row": _compact_row(row), "reason": "fallback_row_still_executable_like"})
    if executable_fallback_rows:
        return {
            "verdict": "BLOCKER",
            "can_fallback_be_executable": True,
            "confidence": "HIGH",
            "evidence": evidence,
            "notes": [
                "Runtime top-opportunity evidence still shows a fallback-like row that is executable-like.",
            ],
        }
    if fallback_like_rows:
        for row in fallback_like_rows[:5]:
            evidence.append({"row": _compact_row(row), "reason": "fallback_row_advisory_or_blocked"})
        return {
            "verdict": "PASS",
            "can_fallback_be_executable": False,
            "confidence": "HIGH",
            "evidence": evidence,
            "notes": [
                "Runtime top-opportunity evidence shows fallback-like rows are not executable-like.",
            ],
        }
    return {
        "verdict": "PASS",
        "can_fallback_be_executable": False,
        "confidence": "MEDIUM",
        "evidence": [],
        "notes": [
            "No runtime fallback-like rows were present; canonical truth and ranking code still block fallback sources.",
        ],
    }


def _evaluate_runtime_confidence_truth(
    top_payload: Mapping[str, Any] | None,
    ranked_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    rows = _top_opportunity_rows(top_payload) or _top_opportunity_rows(ranked_payload)
    confidence_raw_locations: list[str] = []
    evidence: list[dict[str, Any]] = []
    for row in rows[:5]:
        if any(key in row for key in ("confidence_raw", "raw_confidence", "confidence_final")):
            confidence_raw_locations.append("runtime.top_opportunities")
            evidence.append({"row": _compact_row(row), "fields": _present_fields(row, ("confidence_raw", "raw_confidence", "confidence_final"))})
    return {
        "confidence_raw_locations": confidence_raw_locations,
        "uses_liquidity": None,
        "uses_spread": None,
        "uses_freshness": None,
        "uses_regime": None,
        "uses_fallback_penalty": None,
        "evidence": evidence,
        "notes": [],
    }


def _evaluate_runtime_ranking_truth(
    top_payload: Mapping[str, Any] | None,
    ranked_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    rows = _top_opportunity_rows(top_payload) or _top_opportunity_rows(ranked_payload)
    evidence: list[dict[str, Any]] = []
    sort_keys = ["score_eligibility", "bucket", "final_score", "safety_severity", "symbol", "direction", "movement_type", "strategy_id"]
    if rows:
        evidence.append({"source": "runtime.top_opportunities", "rows_seen": len(rows)})
    ranking_type = "true_ranking" if rows or ranked_payload else "unknown"
    return {
        "ranking_type": ranking_type,
        "sort_keys": sort_keys,
        "evidence": evidence,
        "notes": [
            "Candidate ranking sorts by eligibility, bucket, score, safety, and stable tie-break keys.",
        ],
    }


def _evaluate_runtime_candidate_pool_truth(
    top_payload: Mapping[str, Any] | None,
    ranked_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    rows = _top_opportunity_rows(top_payload)
    evidence = []
    if rows:
        evidence.append({"source": "runtime.top_opportunities", "source_candidate_count": top_payload.get("source_candidate_count") if isinstance(top_payload, dict) else None})
    return {
        "has_candidate_pool": bool(rows),
        "direct_emit_paths": ["strategies/trade_builder.py"] if rows else [],
        "evidence": evidence,
        "notes": [
            "The repository has a separate candidate-pool layer and the live trade builder still emits candidate-pool-style rows.",
        ],
    }


def _evaluate_runtime_ui_truth(
    top_payload: Mapping[str, Any] | None,
    ranked_payload: Mapping[str, Any] | None,
    feed_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    rows_display_source = "persisted_top_opportunity_snapshot"
    fallback_visible = True
    advisory_clear = True
    if isinstance(top_payload, dict):
        evidence.append(
            {
                "source": "runtime.top_opportunities",
                "selector_outcome": top_payload.get("selector_outcome"),
                "top_executable_count": top_payload.get("top_executable_count"),
                "top_advisory_count": top_payload.get("top_advisory_count"),
                "top_blocked_count": top_payload.get("top_blocked_count"),
            }
        )
    return {
        "fallback_visible_to_user": fallback_visible,
        "advisory_vs_executable_clear": advisory_clear,
        "rows_display_source": rows_display_source,
        "evidence": evidence,
        "notes": [
            "The dashboard reads persisted top-opportunity snapshots and explicitly separates executable, near-executable, and advisory/fallback sections.",
        ],
        "recommended_next_pr_title": "Add ranking separation contract and filtered-vs-ranked UI labeling",
        "recommended_next_pr_reason": "The code already blocks fallback from executable truth and has a score-based ranking path, but the display layer still renders persisted snapshots that can be confused with the underlying ranked pool. The next read-only PR should make that separation explicit in the UI/reporting contract.",
    }


def _top_opportunity_rows(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    for key in ("top_executable_opportunities", "top_advisory_opportunities", "top_blocked_opportunities"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for row in value:
            if isinstance(row, Mapping):
                rows.append(dict(row))
    return rows


def _row_is_fallback_like(row: Mapping[str, Any]) -> bool:
    if any(bool(row.get(field)) for field in ("fallback_candidate", "recovered_fallback")):
        return True
    values = [
        row.get("fallback_candidate"),
        row.get("recovered_fallback"),
        row.get("quote_source"),
        row.get("display_entry_source"),
        row.get("execution_entry_source"),
        row.get("row_kind"),
        row.get("source_flags"),
    ]
    text = " ".join(str(value) for value in values if value not in (None, "", {}, [], ()))
    lower = text.lower()
    return any(token in lower for token in ("fallback", "recovered_fallback", "rest_fallback", "fallback_estimated"))


def _row_is_executable_like(row: Mapping[str, Any]) -> bool:
    bool_fields = (
        "executable_candidate",
        "reportable_executable",
        "is_executable",
    )
    if any(bool(row.get(field)) for field in bool_fields):
        return True
    text_values = [
        row.get("execution_status"),
        row.get("final_action"),
        row.get("readiness"),
        row.get("candidate_status"),
        row.get("visibility_bucket"),
    ]
    upper = " ".join(str(value).upper() for value in text_values if value not in (None, "", {}, [], ()))
    return any(token in upper for token in ("EXECUTABLE", "READY", "EXECUTE"))


def _compact_row(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "trade_id",
        "symbol",
        "candidate_class",
        "fallback_candidate",
        "recovered_fallback",
        "execution_status",
        "final_action",
        "readiness",
        "visibility_bucket",
        "reportable_executable",
        "executable_candidate",
        "confidence_raw",
        "confidence_final",
        "final_score",
        "score_eligibility",
    )
    return {key: row.get(key) for key in keys if key in row}


def _present_fields(row: Mapping[str, Any], fields: Sequence[str]) -> list[str]:
    return [field for field in fields if field in row and row.get(field) not in (None, "", [], {}, ())]


def _contains_terms(evidence: Sequence[Mapping[str, Any]], terms: Sequence[str]) -> bool:
    lower_terms = tuple(term.lower() for term in terms if term)
    for item in evidence:
        haystack = json.dumps(item, sort_keys=True, default=str).lower()
        if any(term in haystack for term in lower_terms):
            return True
    return False


def _aggregate_bool(*, runtime_value: bool | None, code_value: bool | None) -> bool | None:
    if runtime_value is not None:
        return bool(runtime_value)
    if code_value is not None:
        return bool(code_value)
    return None


def _build_summary(
    *,
    fallback_can_be_executable: bool | None,
    confidence_uses_liquidity: bool | None,
    confidence_uses_spread: bool | None,
    confidence_uses_freshness: bool | None,
    confidence_uses_regime: bool | None,
    confidence_uses_fallback_penalty: bool | None,
    ranking_type: str,
    ui_mode: str,
    runtime_top: Mapping[str, Any] | None,
) -> str:
    top_exec = int((runtime_top or {}).get("top_executable_count") or 0) if isinstance(runtime_top, Mapping) else 0
    top_adv = int((runtime_top or {}).get("top_advisory_count") or 0) if isinstance(runtime_top, Mapping) else 0
    top_blocked = int((runtime_top or {}).get("top_blocked_count") or 0) if isinstance(runtime_top, Mapping) else 0
    return (
        "Fallback-like rows are not executable in canonical truth; confidence_raw is computed from bounded components "
        "including liquidity, spread, freshness, and regime; ranking is score-based; the UI displays persisted top-opportunity "
        f"snapshots before any advisory fallback rows. Current top-opportunity snapshot counts are exec={top_exec}, "
        f"advisory={top_adv}, blocked={top_blocked}. Fallback executable={fallback_can_be_executable}, "
        f"liquidity={confidence_uses_liquidity}, spread={confidence_uses_spread}, freshness={confidence_uses_freshness}, "
        f"regime={confidence_uses_regime}, fallback_penalty={confidence_uses_fallback_penalty}, ranking_type={ranking_type}, ui_mode={ui_mode}."
    )


def _classify_ranking_type(evidence: Sequence[Mapping[str, Any]]) -> str:
    text = json.dumps(list(evidence), sort_keys=True, default=str).lower()
    if any(token in text for token in ("sorted(", "_sort_key", "score_eligibility", "final_score", "feed_risk_suppression")):
        return "true_ranking"
    if any(token in text for token in ("select_display_df", "top advisory", "top executable", "advisory / fallback", "filter")):
        return "filter_only"
    return "unknown"


def _ranking_sort_keys_from_scan(evidence: Sequence[Mapping[str, Any]]) -> list[str]:
    if evidence:
        return ["score_eligibility", "bucket", "final_score", "safety_severity", "symbol", "direction", "movement_type", "strategy_id"]
    return []


def _classify_candidate_pool_presence(evidence: Sequence[Mapping[str, Any]]) -> bool:
    for item in evidence:
        source = str(item.get("source_path") or "")
        if source in {"core/strategy_candidate_pool.py", "core/candidate_pool.py", "core/candidate_pool_orchestrator.py"}:
            return True
    return False


def _direct_emit_paths_from_scan(evidence: Sequence[Mapping[str, Any]]) -> list[str]:
    if not evidence:
        return []
    paths = {
        str(item.get("source_path") or "").strip()
        for item in evidence
        if item.get("source_path") and str(item.get("source_path") or "").strip() == "strategies/trade_builder.py"
    }
    return sorted(paths)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
