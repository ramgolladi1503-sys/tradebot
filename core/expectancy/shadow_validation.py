from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.expectancy.strategy_regime_expectancy import (
    aggregate_strategy_regime_expectancy,
    load_candidate_outcomes,
)
from core.expectancy.top_opportunity_selector import select_top_opportunities
from core.paths import runtime_dir

SHADOW_VALIDATION_SCHEMA_VERSION = 1
_DEFAULT_SHADOW_VALIDATION_SUBDIR = "shadow_validation"
_DEFAULT_SHADOW_VALIDATION_SESSION_PREFIX = "session_"
_DEFAULT_SHADOW_VALIDATION_FILENAME_JSON = "shadow_validation_latest.json"
_DEFAULT_SHADOW_VALIDATION_FILENAME_MD = "shadow_validation_latest.md"

_BLOCKED_EXECUTION_STATES = {"BLOCKED", "DEAD", "RECOVERY_BLOCKED"}
_BLOCKING_TOKENS = ("STALE", "LTP_STALE", "WS_DISCONNECTED", "GLOBAL_FEED_UNHEALTHY", "RECOVERY_BLOCKED", "WS1006", "PROCESS_RESTART_REQUIRED")
_FALLBACK_REASONS = {"fallback", "fallback_used", "recovered_fallback", "softrej"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if number != number:
        return None
    return number


def _int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        return int(float(value))
    except Exception:
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_json_or_jsonl(source: str | Path | Iterable[Mapping[str, Any]] | Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    diagnostics: list[str] = []
    if source is None:
        return [], diagnostics
    if isinstance(source, Mapping):
        return [dict(source)], diagnostics
    if isinstance(source, (str, Path)):
        path = Path(source).expanduser()
        if not path.exists():
            diagnostics.append(f"missing:{path}")
            return [], diagnostics
        if path.is_dir():
            diagnostics.append(f"unsupported_directory:{path}")
            return [], diagnostics
        if path.suffix.lower() == ".jsonl":
            rows: list[dict[str, Any]] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text:
                    continue
                payload = json.loads(text)
                if isinstance(payload, Mapping):
                    rows.append(dict(payload))
            return rows, diagnostics
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [dict(row) for row in payload if isinstance(row, Mapping)], diagnostics
        if isinstance(payload, Mapping):
            rows = payload.get("rows") or payload.get("candidates") or payload.get("items") or payload.get("opportunities") or payload.get("journal_rows")
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)], diagnostics
            return [dict(payload)], diagnostics
        return [], diagnostics
    rows = [dict(row) for row in source if isinstance(row, Mapping)]
    return rows, diagnostics


def _load_top_opportunity_payload(source: str | Path | Iterable[Mapping[str, Any]] | Mapping[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    rows, diagnostics = _load_json_or_jsonl(source)
    if not rows:
        return {}, diagnostics
    if len(rows) == 1 and {"executable_opportunities", "advisory_opportunities", "shadow_opportunities", "rejected_opportunities"} & set(rows[0]):
        return dict(rows[0]), diagnostics
    report = select_top_opportunities(rows)
    return report.to_payload(), diagnostics


def _top_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("executable_opportunities", "advisory_opportunities", "shadow_opportunities", "rejected_opportunities"):
        value = payload.get(key)
        if isinstance(value, list):
            for row in value:
                if isinstance(row, Mapping):
                    rows.append(dict(row))
    return rows


def _is_fallback(row: Mapping[str, Any]) -> bool:
    if _truthy(row.get("fallback_used")):
        return True
    if _lower(row.get("candidate_class")) == "fallback":
        return True
    row_kind = _lower(row.get("row_kind"))
    if row_kind in {"fallback", "recovered_fallback"}:
        return True
    candidate_type = _lower(row.get("candidate_type"))
    if any(token in candidate_type for token in _FALLBACK_REASONS):
        return True
    candidate_origin = _lower(row.get("candidate_origin"))
    if any(token in candidate_origin for token in _FALLBACK_REASONS):
        return True
    trade_id = _text(row.get("trade_id")).lower()
    if trade_id.startswith("softrej_"):
        return True
    quote_source = _upper(row.get("quote_source"))
    if quote_source in {"REST_FALLBACK", "SYNTHETIC_OFFHOURS", "SUBSCRIPTION_FAILED"}:
        return True
    source_flags = row.get("source_flags")
    if isinstance(source_flags, Mapping) and any(
        _truthy(source_flags.get(flag))
        for flag in ("fallback_used", "recovered_fallback", "softened", "soft_reject_fallback")
    ):
        return True
    return False


def _is_blocked(row: Mapping[str, Any]) -> bool:
    execution_truth_state = _upper(row.get("execution_truth_state"))
    if execution_truth_state in _BLOCKED_EXECUTION_STATES:
        return True
    final_action = _upper(row.get("final_action"))
    permission = _upper(row.get("permission"))
    execution_status = _lower(row.get("execution_status"))
    if final_action == "BLOCK" or permission == "BLOCK" or execution_status == "blocked":
        return True
    blockers = list(row.get("blockers") or []) + list(row.get("execution_truth_blockers") or [])
    for blocker in blockers:
        text = _upper(blocker)
        if any(token in text for token in _BLOCKING_TOKENS):
            return True
    return False


def _candidate_key(row: Mapping[str, Any]) -> str:
    candidate_id = _text(row.get("candidate_id"))
    if candidate_id:
        return candidate_id
    return _text(row.get("trade_id"))


def _load_candidate_outcome_rows(source: str | Path | Iterable[Mapping[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    rows, diagnostics = _load_json_or_jsonl(source)
    if isinstance(source, (str, Path)):
        path = Path(source).expanduser()
        if path.exists() and path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, Mapping):
                rows = payload.get("rows") or payload.get("outcomes") or payload.get("results") or rows
                if isinstance(rows, list):
                    rows = [dict(row) for row in rows if isinstance(row, Mapping)]
    return rows, diagnostics


def _primary_outcome_by_candidate(candidate_outcomes: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in candidate_outcomes:
        if not isinstance(row, Mapping):
            continue
        key = _candidate_key(row)
        if not key:
            continue
        grouped.setdefault(key, []).append(dict(row))
    primary: dict[str, dict[str, Any]] = {}
    for key, rows in grouped.items():
        rows.sort(
            key=lambda item: (
                _int(item.get("window_sec")) or 0,
                _float(item.get("signal_epoch")) or float("inf"),
                _text(item.get("outcome_status")),
                _text(item.get("trade_id")),
            )
        )
        primary[key] = rows[0]
    return primary


def _selected_top_rows(top_report: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    executable = [dict(row) for row in (top_report.get("executable_opportunities") or []) if isinstance(row, Mapping)]
    advisory = [dict(row) for row in (top_report.get("advisory_opportunities") or []) if isinstance(row, Mapping)]
    shadow = [dict(row) for row in (top_report.get("shadow_opportunities") or []) if isinstance(row, Mapping)]
    rejected = [dict(row) for row in (top_report.get("rejected_opportunities") or []) if isinstance(row, Mapping)]
    return executable, advisory, shadow, rejected


def _aggregate_cost_adjusted_r(rows: Sequence[Mapping[str, Any]], primary_outcomes: Mapping[str, Mapping[str, Any]]) -> float:
    values: list[float] = []
    for row in rows:
        if _is_fallback(row) or _is_blocked(row):
            continue
        key = _candidate_key(row)
        outcome = primary_outcomes.get(key) if key else None
        if outcome is None:
            continue
        cost_adjusted_r = _float(outcome.get("cost_adjusted_r"))
        if cost_adjusted_r is not None:
            values.append(cost_adjusted_r)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _result_for_row(row: Mapping[str, Any], primary_outcomes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    key = _candidate_key(row)
    outcome = primary_outcomes.get(key) if key else None
    if outcome is None:
        return {
            "candidate_id": key,
            "trade_id": _text(row.get("trade_id")),
            "edge_rank_score": _float(row.get("edge_rank_score")),
            "rank": _int(row.get("rank")),
            "outcome_status": "NO_OUTCOME",
            "outcome_reason": "missing_candidate_outcome",
        }
    return {
        "candidate_id": _text(outcome.get("candidate_id")) or key,
        "trade_id": _text(outcome.get("trade_id")) or _text(row.get("trade_id")),
        "symbol": _text(outcome.get("symbol")) or _text(row.get("symbol")),
        "strategy_family": _text(outcome.get("strategy_family")) or _text(row.get("strategy_family")),
        "setup_id": _text(outcome.get("setup_id")) or _text(row.get("setup_id")),
        "regime": _text(outcome.get("regime")) or _text(row.get("regime")),
        "direction": _text(outcome.get("direction")) or _text(row.get("direction")),
        "edge_rank_score": _float(row.get("edge_rank_score")),
        "rank": _int(row.get("rank")),
        "outcome_status": _text(outcome.get("outcome_status")) or "UNKNOWN",
        "outcome_reason": _text(outcome.get("outcome_reason")) or "",
        "cost_adjusted_r": _float(outcome.get("cost_adjusted_r")),
        "gross_r": _float(outcome.get("gross_r")),
        "target_hit": _truthy(outcome.get("target_hit")),
        "stop_hit": _truthy(outcome.get("stop_hit")),
        "timeout_hit": _truthy(outcome.get("timeout_hit")),
        "first_hit_epoch": _float(outcome.get("first_hit_epoch")),
        "window_sec": _int(outcome.get("window_sec")),
    }


def _top_n_result(rows: Sequence[Mapping[str, Any]], primary_outcomes: Mapping[str, Mapping[str, Any]], *, limit: int) -> dict[str, Any]:
    selected = list(rows[:limit])
    candidates = [_result_for_row(row, primary_outcomes) for row in selected]
    aggregate_cost_adjusted_r = _aggregate_cost_adjusted_r(selected, primary_outcomes)
    return {
        "candidate_count": len(selected),
        "candidate_ids": [item["candidate_id"] for item in candidates],
        "candidates": candidates,
        "aggregate_cost_adjusted_r": aggregate_cost_adjusted_r,
        "summary": _summarize_outcomes(candidates),
    }


def _summarize_outcomes(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {"TARGET_HIT": 0, "STOP_HIT": 0, "TIMEOUT": 0, "NO_OUTCOME": 0, "UNKNOWN": 0}
    for candidate in candidates:
        status = _upper(candidate.get("outcome_status"))
        if status in counts:
            counts[status] += 1
        else:
            counts["UNKNOWN"] += 1
    return counts


def _group_summary(report: Any) -> dict[str, Any]:
    groups = list(getattr(report, "groups", ()) or [])
    if not groups:
        return {
            "group_count": 0,
            "best_group": None,
            "keep_count": 0,
            "watch_count": 0,
            "kill_count": 0,
            "insufficient_data_count": 0,
        }
    best_group = max(
        groups,
        key=lambda group: (
            _upper(getattr(group, "keep_watch_kill_status", "")) == "KEEP",
            _float(getattr(group, "avg_cost_adjusted_r", None)) or float("-inf"),
            _int(getattr(group, "sample_count", None)) or 0,
            -len(_text(getattr(group, "group_key", ""))),
        ),
    )
    status_counts = {"KEEP": 0, "WATCH": 0, "KILL": 0, "INSUFFICIENT_DATA": 0}
    for group in groups:
        status = _upper(getattr(group, "keep_watch_kill_status", ""))
        if status in status_counts:
            status_counts[status] += 1
    return {
        "group_count": len(groups),
        "best_group": {
            "group_key": getattr(best_group, "group_key", ""),
            "strategy_family": getattr(best_group, "strategy_family", ""),
            "regime": getattr(best_group, "regime", ""),
            "index": getattr(best_group, "index", ""),
            "expiry_type": getattr(best_group, "expiry_type", ""),
            "option_type": getattr(best_group, "option_type", ""),
            "direction": getattr(best_group, "direction", ""),
            "sample_count": getattr(best_group, "sample_count", 0),
            "avg_cost_adjusted_r": getattr(best_group, "avg_cost_adjusted_r", 0.0),
            "median_cost_adjusted_r": getattr(best_group, "median_cost_adjusted_r", 0.0),
            "keep_watch_kill_status": getattr(best_group, "keep_watch_kill_status", ""),
            "status_reason": getattr(best_group, "status_reason", ""),
        },
        "keep_count": status_counts["KEEP"],
        "watch_count": status_counts["WATCH"],
        "kill_count": status_counts["KILL"],
        "insufficient_data_count": status_counts["INSUFFICIENT_DATA"],
    }


def _fallback_exclusion_summary(top_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fallback_rows = [row for row in top_rows if _is_fallback(row)]
    blocked_rows = [row for row in top_rows if _is_blocked(row) and not _is_fallback(row)]
    executable_rows = [row for row in top_rows if row in top_rows and not _is_fallback(row) and not _is_blocked(row)]
    return {
        "fallback_count": len(fallback_rows),
        "blocked_count": len(blocked_rows),
        "excluded_from_executable_count": len(fallback_rows),
        "executable_excludes_fallback": True,
        "executable_excludes_blocked": True,
        "executable_row_count": len(executable_rows),
        "fallback_candidate_ids": [_candidate_key(row) for row in fallback_rows],
        "blocked_candidate_ids": [_candidate_key(row) for row in blocked_rows],
    }


def _feed_block_summary(top_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    blocked_rows = [row for row in top_rows if _is_blocked(row) and not _is_fallback(row)]
    reasons: dict[str, int] = {}
    for row in blocked_rows:
        blockers = list(row.get("blockers") or []) + list(row.get("execution_truth_blockers") or [])
        if not blockers:
            reasons["blocked"] = reasons.get("blocked", 0) + 1
        for blocker in blockers:
            blocker_text = _text(blocker)
            if blocker_text:
                reasons[blocker_text] = reasons.get(blocker_text, 0) + 1
    return {
        "blocked_count": len(blocked_rows),
        "blocked_candidate_ids": [_candidate_key(row) for row in blocked_rows],
        "reasons": reasons,
    }


def _recommendation(
    *,
    expectancy_report: Any,
    shadow_top_summary: Mapping[str, Any],
    fallback_summary: Mapping[str, Any],
    average_cost_adjusted_r: float,
) -> tuple[str, str]:
    keep_count = int(shadow_top_summary.get("executable_count") or 0)
    grouped = list(getattr(expectancy_report, "groups", ()) or [])
    mature_keep = [
        group
        for group in grouped
        if _upper(getattr(group, "keep_watch_kill_status", "")) == "KEEP"
        and (_int(getattr(group, "sample_count", None)) or 0) >= 50
        and (_float(getattr(group, "avg_cost_adjusted_r", None)) or 0.0) > 0
    ]
    watch_groups = [
        group
        for group in grouped
        if _upper(getattr(group, "keep_watch_kill_status", "")) == "WATCH"
    ]
    has_negative_mature = any(
        (_int(getattr(group, "sample_count", None)) or 0) >= 30
        and (_float(getattr(group, "avg_cost_adjusted_r", None)) or 0.0) <= 0
        for group in grouped
    )
    fallback_inflation = int(fallback_summary.get("fallback_count") or 0) > 0 and int(fallback_summary.get("excluded_from_executable_count") or 0) > 0
    shadow_negative = _text(shadow_top_summary.get("shadow_validation_signal")).lower() == "negative"
    if not mature_keep:
        if has_negative_mature or shadow_negative or fallback_inflation or average_cost_adjusted_r <= 0:
            return "NO_TRADE", "no mature KEEP setup with positive post-cost evidence"
        return "PAPER_ONLY", "positive signals exist but mature KEEP evidence is missing"
    if shadow_negative or fallback_inflation:
        return "NO_TRADE", "shadow validation or fallback inflation blocks readiness"
    if keep_count == 0:
        return "PAPER_ONLY", "KEEP evidence exists but executable top opportunities are absent"
    if average_cost_adjusted_r <= 0:
        return "NO_TRADE", "post-cost executable edge is not positive"
    if any((_int(getattr(group, "sample_count", None)) or 0) < 50 for group in mature_keep):
        return "PAPER_ONLY", "KEEP evidence exists but sample thresholds are incomplete"
    return "READY_FOR_MANUAL_PILOT", "mature KEEP evidence is positive after costs and shadow validation"


@dataclass(frozen=True)
class ShadowValidationReport:
    schema_version: int
    generated_by: str
    source: str
    candidate_count: int
    executable_count: int
    advisory_count: int
    blocked_count: int
    fallback_count: int
    avg_cost_adjusted_r: float
    top_1_result: dict[str, Any]
    top_3_result: dict[str, Any]
    strategy_regime_result: dict[str, Any]
    setup_result: dict[str, Any]
    fallback_exclusion_summary: dict[str, Any]
    feed_block_summary: dict[str, Any]
    recommendation: str
    recommendation_reason: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = True

    @property
    def safety(self) -> dict[str, object]:
        return {
            "read_only": self.read_only,
            "append": self.append,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_allowed": False,
            "live_order_action": False,
            "broker_order_action": False,
            "runtime_wired": False,
            "external_services_used": False,
            "proves_trading_edge": False,
        }

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["safety"] = dict(self.safety)
        return payload

    def to_markdown(self) -> str:
        lines = [
            "# Shadow Market Validation Report",
            "",
            f"- Schema version: {self.schema_version}",
            f"- Generated by: {self.generated_by}",
            f"- Source: {self.source}",
            f"- Candidate count: {self.candidate_count}",
            f"- Executable count: {self.executable_count}",
            f"- Advisory count: {self.advisory_count}",
            f"- Blocked count: {self.blocked_count}",
            f"- Fallback count: {self.fallback_count}",
            f"- Avg cost adjusted R: {self.avg_cost_adjusted_r}",
            f"- Recommendation: {self.recommendation}",
            f"- Recommendation reason: {self.recommendation_reason}",
            "",
            "## Safety",
            "- read_only: True",
            "- append: True",
            "- is_order_action: False",
            "- broker_api_called: False",
            "- live_order_allowed: False",
            "- live_order_action: False",
            "- broker_order_action: False",
            "",
            "## Top 1 Result",
            json.dumps(self.top_1_result, sort_keys=True),
            "",
            "## Top 3 Result",
            json.dumps(self.top_3_result, sort_keys=True),
            "",
            "## Strategy Regime Result",
            json.dumps(self.strategy_regime_result, sort_keys=True),
            "",
            "## Setup Result",
            json.dumps(self.setup_result, sort_keys=True),
            "",
            "## Fallback Exclusion Summary",
            json.dumps(self.fallback_exclusion_summary, sort_keys=True),
            "",
            "## Feed Block Summary",
            json.dumps(self.feed_block_summary, sort_keys=True),
            "",
            "## Diagnostics",
            json.dumps(self.diagnostics, sort_keys=True),
            "",
            "This report is read-only and does not place orders or change live behavior.",
        ]
        return "\n".join(lines) + "\n"


def _session_day(value: str | date | datetime | None = None) -> str:
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if len(text) == 8 and text.isdigit():
            return text
        return text.replace("-", "")[:8]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _write_outputs(report: ShadowValidationReport, *, output_dir: Path, session_date: str | date | datetime | None) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / _DEFAULT_SHADOW_VALIDATION_FILENAME_JSON
    md_path = output_dir / _DEFAULT_SHADOW_VALIDATION_FILENAME_MD
    session_path = output_dir / f"{_DEFAULT_SHADOW_VALIDATION_SESSION_PREFIX}{_session_day(session_date)}.jsonl"

    json_path.write_text(json.dumps(report.to_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    with session_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report.to_payload(), sort_keys=True, default=str) + "\n")
    return json_path, md_path, session_path


def build_shadow_market_validation_report(
    *,
    candidate_journal: str | Path | Iterable[Mapping[str, Any]] | None,
    candidate_outcomes: str | Path | Iterable[Mapping[str, Any]] | None,
    top_opportunities: str | Path | Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
    observations: str | Path | Iterable[Mapping[str, Any]] | None = None,
    output_dir: str | Path | None = None,
    session_date: str | date | datetime | None = None,
) -> ShadowValidationReport:
    journal_rows, journal_diagnostics = _load_json_or_jsonl(candidate_journal)
    outcome_rows, outcome_diagnostics = _load_candidate_outcome_rows(candidate_outcomes)
    top_report, top_diagnostics = _load_top_opportunity_payload(top_opportunities)
    observation_rows, observation_diagnostics = _load_json_or_jsonl(observations)
    primary_outcomes = _primary_outcome_by_candidate(outcome_rows)
    executable_rows, advisory_rows, shadow_rows, rejected_rows = _selected_top_rows(top_report)
    top_rows = executable_rows + advisory_rows + shadow_rows + rejected_rows

    average_cost_adjusted_r = _aggregate_cost_adjusted_r(executable_rows, primary_outcomes)
    top_1_result = _result_for_row(executable_rows[0], primary_outcomes) if executable_rows else {
        "candidate_id": None,
        "trade_id": None,
        "outcome_status": "NO_EXECUTABLE_CANDIDATES",
        "outcome_reason": "no_executable_candidates",
    }
    top_3_result = _top_n_result(executable_rows, primary_outcomes, limit=3)

    strategy_expectancy_report = aggregate_strategy_regime_expectancy(outcome_rows)
    setup_expectancy_report = aggregate_strategy_regime_expectancy(outcome_rows, group_by_setup_id=True)
    strategy_regime_result = _group_summary(strategy_expectancy_report)
    setup_result = _group_summary(setup_expectancy_report)

    fallback_summary = _fallback_exclusion_summary(top_rows)
    feed_block_summary = _feed_block_summary(top_rows)
    recommendation, recommendation_reason = _recommendation(
        expectancy_report=strategy_expectancy_report,
        shadow_top_summary={"executable_count": len(executable_rows), "shadow_validation_signal": "negative" if average_cost_adjusted_r <= 0 else "positive"},
        fallback_summary=fallback_summary,
        average_cost_adjusted_r=average_cost_adjusted_r,
    )

    diagnostics = {
        "missing_inputs": [
            label
            for label, values in (
                ("candidate_journal", journal_diagnostics),
                ("candidate_outcomes", outcome_diagnostics),
                ("top_opportunities", top_diagnostics),
                ("observations", observation_diagnostics),
            )
            if values
        ],
        "journal_row_count": len(journal_rows),
        "outcome_row_count": len(outcome_rows),
        "top_row_count": len(top_rows),
        "observation_row_count": len(observation_rows),
        "source_candidates": len(journal_rows),
        "source_outcomes": len(outcome_rows),
        "source_top_opportunities": len(top_rows),
    }

    report = ShadowValidationReport(
        schema_version=SHADOW_VALIDATION_SCHEMA_VERSION,
        generated_by="shadow_market_validation_runner",
        source="in_memory" if not isinstance(candidate_journal, (str, Path)) else str(Path(candidate_journal).expanduser()),
        candidate_count=len(journal_rows),
        executable_count=len(executable_rows),
        advisory_count=len(advisory_rows),
        blocked_count=len(feed_block_summary["blocked_candidate_ids"]),
        fallback_count=len(fallback_summary["fallback_candidate_ids"]),
        avg_cost_adjusted_r=average_cost_adjusted_r,
        top_1_result=top_1_result,
        top_3_result=top_3_result,
        strategy_regime_result=strategy_regime_result,
        setup_result=setup_result,
        fallback_exclusion_summary=fallback_summary,
        feed_block_summary=feed_block_summary,
        recommendation=recommendation,
        recommendation_reason=recommendation_reason,
        diagnostics=diagnostics,
    )

    if output_dir is not None:
        _write_outputs(report, output_dir=Path(output_dir).expanduser(), session_date=session_date)
    return report


def write_shadow_market_validation_report(
    *,
    candidate_journal: str | Path | Iterable[Mapping[str, Any]] | None,
    candidate_outcomes: str | Path | Iterable[Mapping[str, Any]] | None,
    top_opportunities: str | Path | Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
    observations: str | Path | Iterable[Mapping[str, Any]] | None = None,
    output_dir: str | Path | None = None,
    session_date: str | date | datetime | None = None,
) -> tuple[Path, Path, Path, ShadowValidationReport]:
    report = build_shadow_market_validation_report(
        candidate_journal=candidate_journal,
        candidate_outcomes=candidate_outcomes,
        top_opportunities=top_opportunities,
        observations=observations,
        output_dir=output_dir,
        session_date=session_date,
    )
    root = Path(output_dir).expanduser() if output_dir is not None else runtime_dir() / _DEFAULT_SHADOW_VALIDATION_SUBDIR
    json_path = root / _DEFAULT_SHADOW_VALIDATION_FILENAME_JSON
    md_path = root / _DEFAULT_SHADOW_VALIDATION_FILENAME_MD
    session_path = root / f"{_DEFAULT_SHADOW_VALIDATION_SESSION_PREFIX}{_session_day(session_date)}.jsonl"
    return json_path, md_path, session_path, report


__all__ = [
    "SHADOW_VALIDATION_SCHEMA_VERSION",
    "ShadowValidationReport",
    "build_shadow_market_validation_report",
    "write_shadow_market_validation_report",
]
