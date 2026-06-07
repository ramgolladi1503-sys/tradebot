from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.candidate_pool_quality import CandidatePoolQualityReport, analyze_candidate_pool, pool_quality_penalty_for_row
from core.paths import runtime_dir

TOP_OPPORTUNITY_SELECTOR_SCHEMA_VERSION = 1
_DEFAULT_TOP_OPPORTUNITY_SUBDIR = "opportunities"
_DEFAULT_TOP_OPPORTUNITY_FILENAME_JSON = "top_opportunities_latest.json"
_DEFAULT_TOP_OPPORTUNITY_FILENAME_MD = "top_opportunities_latest.md"


@dataclass(frozen=True)
class TopOpportunityRow:
    rank: int
    candidate_id: str
    trade_id: str
    symbol: str
    index: str
    strategy_family: str
    setup_id: str
    regime: str
    direction: str
    edge_rank_score: float
    rank_score: float
    confidence_final: float | None
    expectancy_status: str
    expectancy_sample_count: int
    expectancy_avg_cost_adjusted_r: float | None
    execution_truth_state: str
    reportable_executable: bool
    execution_allowed: bool
    permission: str
    final_action: str
    fallback_used: bool
    pool_quality_penalty: float
    pool_quality_reasons: tuple[str, ...]
    why_ranked: str
    why_not_ranked: str
    blockers: tuple[str, ...]
    read_only: bool = True
    append: bool = False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True)
class TopOpportunitySelectorReport:
    schema_version: int
    generated_by: str
    source: str
    candidate_count: int
    opportunity_count: int
    executable_count: int
    advisory_count: int
    shadow_count: int
    rejected_count: int
    pool_quality_state: str
    pool_quality_score: float
    pool_quality_reasons: tuple[str, ...]
    executable_opportunities: tuple[TopOpportunityRow, ...]
    advisory_opportunities: tuple[TopOpportunityRow, ...]
    shadow_opportunities: tuple[TopOpportunityRow, ...]
    rejected_opportunities: tuple[TopOpportunityRow, ...]
    read_only: bool = True
    append: bool = False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["executable_opportunities"] = [row.to_payload() for row in self.executable_opportunities]
        payload["advisory_opportunities"] = [row.to_payload() for row in self.advisory_opportunities]
        payload["shadow_opportunities"] = [row.to_payload() for row in self.shadow_opportunities]
        payload["rejected_opportunities"] = [row.to_payload() for row in self.rejected_opportunities]
        payload["safety"] = {
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
        payload["pool_quality"] = {
            "state": self.pool_quality_state,
            "score": self.pool_quality_score,
            "reasons": list(self.pool_quality_reasons),
        }
        return payload


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


def _sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    edge_rank_score = _float(row.get("edge_rank_score"))
    rank_score = _float(row.get("rank_score"))
    confidence_final = _float(row.get("confidence_final"))
    return (
        -float(edge_rank_score if edge_rank_score is not None else -1.0),
        -float(rank_score if rank_score is not None else -1.0),
        -float(confidence_final if confidence_final is not None else -1.0),
        _text(row.get("symbol")),
        _text(row.get("trade_id")),
    )


def _adjusted_edge_rank_score(row: Mapping[str, Any]) -> float:
    edge_rank_score = _float(row.get("edge_rank_score")) or 0.0
    penalty = _float(row.get("pool_quality_penalty")) or 0.0
    return max(0.0, edge_rank_score - penalty)


def _load_rows(source: str | Path | Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.is_dir():
            candidate_path = path / "candidate_outcomes.jsonl"
            if candidate_path.exists():
                source = candidate_path
            else:
                return []
        if path.suffix.lower() == ".jsonl":
            rows: list[dict[str, Any]] = []
            if not path.exists():
                return rows
            for line in path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text:
                    continue
                payload = json.loads(text)
                if isinstance(payload, Mapping):
                    rows.append(dict(payload))
            return rows
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return [dict(row) for row in payload if isinstance(row, Mapping)]
            if isinstance(payload, Mapping):
                rows = payload.get("rows") or payload.get("opportunities") or payload.get("candidates") or []
                if isinstance(rows, list):
                    return [dict(row) for row in rows if isinstance(row, Mapping)]
            return []
        raise ValueError(f"unsupported top opportunity source: {path}")
    return [dict(row) for row in source if isinstance(row, Mapping)]


def _is_fallback(row: Mapping[str, Any]) -> bool:
    if bool(row.get("fallback_used")):
        return True
    if _lower(row.get("candidate_class")) == "fallback":
        return True
    row_kind = _lower(row.get("row_kind"))
    if row_kind in {"fallback", "recovered_fallback"}:
        return True
    candidate_type = _lower(row.get("candidate_type"))
    if "fallback" in candidate_type:
        return True
    candidate_origin = _lower(row.get("candidate_origin"))
    if "fallback" in candidate_origin:
        return True
    trade_id = _text(row.get("trade_id"))
    if trade_id.startswith("softrej_"):
        return True
    quote_source = _upper(row.get("quote_source"))
    if quote_source in {"REST_FALLBACK", "SYNTHETIC_OFFHOURS", "SUBSCRIPTION_FAILED"}:
        return True
    return False


def _is_blocked(row: Mapping[str, Any]) -> bool:
    execution_truth_state = _upper(row.get("execution_truth_state"))
    if execution_truth_state in {"BLOCKED", "DEAD", "RECOVERY_BLOCKED"}:
        return True
    final_action = _upper(row.get("final_action"))
    permission = _upper(row.get("permission"))
    execution_status = _lower(row.get("execution_status"))
    if final_action == "BLOCK" or permission == "BLOCK" or execution_status == "blocked":
        return True
    blockers = list(row.get("blockers") or []) + list(row.get("execution_truth_blockers") or [])
    for blocker in blockers:
        text = _upper(blocker)
        if any(token in text for token in ("STALE", "LTP_STALE", "WS_DISCONNECTED", "GLOBAL_FEED_UNHEALTHY", "RECOVERY_BLOCKED", "WS1006", "PROCESS_RESTART_REQUIRED")):
            return True
    return False


def _row_bucket(row: Mapping[str, Any]) -> str:
    status = _upper(row.get("expectancy_status") or row.get("keep_watch_kill_status"))
    if status == "KILL":
        return "rejected"
    if _is_fallback(row) or _is_blocked(row):
        return "rejected"
    if status == "WATCH":
        return "advisory"
    if status == "INSUFFICIENT_DATA":
        return "shadow"
    if status == "KEEP":
        if _upper(row.get("permission")) == "EXECUTE" and _lower(row.get("execution_status")) == "executable":
            return "executable"
        return "rejected"
    return "rejected"


def _why_ranked(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    expectancy_status = _upper(row.get("expectancy_status") or row.get("keep_watch_kill_status"))
    if expectancy_status:
        parts.append(f"expectancy={expectancy_status.lower()}")
    expectancy_avg = _float(row.get("expectancy_avg_cost_adjusted_r"))
    if expectancy_avg is not None:
        parts.append(f"expectancy_avg_cost_adjusted_r={expectancy_avg}")
    edge_rank = _float(row.get("edge_rank_score"))
    if edge_rank is not None:
        parts.append(f"edge_rank_score={edge_rank}")
    rank_score = _float(row.get("rank_score"))
    if rank_score is not None:
        parts.append(f"rank_score={rank_score}")
    confidence_final = _float(row.get("confidence_final"))
    if confidence_final is not None:
        parts.append(f"confidence_final={confidence_final}")
    if _float(row.get("liquidity_score")) is not None:
        parts.append(f"liquidity_score={_float(row.get('liquidity_score'))}")
    if _float(row.get("spread_score")) is not None:
        parts.append(f"spread_score={_float(row.get('spread_score'))}")
    if _float(row.get("timing_score")) is not None:
        parts.append(f"timing_score={_float(row.get('timing_score'))}")
    if _float(row.get("regime_fit")) is not None:
        parts.append(f"regime_fit={_float(row.get('regime_fit'))}")
    if _float(row.get("rr_score")) is not None:
        parts.append(f"rr_score={_float(row.get('rr_score'))}")
    pool_penalty = _float(row.get("pool_quality_penalty"))
    if pool_penalty is not None and pool_penalty > 0:
        parts.append(f"pool_quality_penalty={pool_penalty}")
        pool_reasons = row.get("pool_quality_reasons") or []
        if pool_reasons:
            parts.append("pool_quality=" + ",".join(_text(reason) for reason in pool_reasons if _text(reason)))
    if row.get("execution_allowed") is True or row.get("reportable_executable") is True:
        parts.append("execution_eligible")
    return "|".join(parts) if parts else "ranked_by_edge_and_execution_quality"


def _why_not_ranked(row: Mapping[str, Any]) -> str:
    reasons: list[str] = []
    status = _upper(row.get("expectancy_status") or row.get("keep_watch_kill_status"))
    if status == "KILL":
        reasons.append("expectancy_kill")
    elif status == "INSUFFICIENT_DATA":
        reasons.append("expectancy_insufficient_data")
    elif status == "WATCH":
        reasons.append("expectancy_watch")
    if _is_fallback(row):
        reasons.append("fallback_not_rankable")
    if _is_blocked(row):
        blockers = list(row.get("blockers") or []) + list(row.get("execution_truth_blockers") or [])
        if blockers:
            reasons.append("blockers=" + ",".join(_text(blocker) for blocker in blockers if _text(blocker)))
        else:
            reasons.append("blocked")
    if not reasons and status != "KEEP":
        reasons.append("non_keep_expectancy")
    return "|".join(reasons)


def _build_opportunity_rows(rows: list[dict[str, Any]], pool_quality: CandidatePoolQualityReport | None = None) -> list[TopOpportunityRow]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        payload.setdefault("edge_rank_score", 0.0)
        payload.setdefault("rank_score", 0.0)
        payload.setdefault("confidence_final", None)
        payload.setdefault("expectancy_status", payload.get("keep_watch_kill_status") or "INSUFFICIENT_DATA")
        payload.setdefault("expectancy_sample_count", _int(payload.get("expectancy_sample_count")) or 0)
        payload.setdefault("expectancy_avg_cost_adjusted_r", _float(payload.get("expectancy_avg_cost_adjusted_r")))
        payload.setdefault("execution_truth_state", payload.get("execution_truth_state") or payload.get("feed_truth_state") or "")
        payload.setdefault("reportable_executable", bool(payload.get("reportable_executable")))
        payload.setdefault("execution_allowed", bool(payload.get("execution_allowed")))
        payload.setdefault("permission", _upper(payload.get("permission")))
        payload.setdefault("final_action", _upper(payload.get("final_action")))
        payload.setdefault("fallback_used", bool(payload.get("fallback_used")))
        payload.setdefault("blockers", list(payload.get("blockers") or []))
        pool_penalty, pool_reasons = (0.0, [])
        if pool_quality is not None:
            pool_penalty, pool_reasons = pool_quality_penalty_for_row(payload, pool_quality)
        payload["pool_quality_penalty"] = float(pool_penalty)
        payload["pool_quality_reasons"] = list(pool_reasons)
        selected.append(payload)

    selected.sort(
        key=lambda row: (
            -_adjusted_edge_rank_score(row),
            -float(_float(row.get("edge_rank_score")) or -1.0),
            -float(_float(row.get("rank_score")) or -1.0),
            -float(_float(row.get("confidence_final")) or -1.0),
            _text(row.get("symbol")),
            _text(row.get("trade_id")),
        )
    )

    rows_out: list[TopOpportunityRow] = []
    for idx, row in enumerate(selected, start=1):
        bucket = _row_bucket(row)
        if bucket == "executable":
            why_not_ranked = ""
        else:
            why_not_ranked = _why_not_ranked(row)
        rows_out.append(
            TopOpportunityRow(
                rank=idx,
                candidate_id=_text(row.get("candidate_id")),
                trade_id=_text(row.get("trade_id")),
                symbol=_text(row.get("symbol")),
                index=_text(row.get("index")),
                strategy_family=_text(row.get("strategy_family")),
                setup_id=_text(row.get("setup_id")),
                regime=_text(row.get("regime")),
                direction=_text(row.get("direction") or row.get("side")),
                edge_rank_score=float(_float(row.get("edge_rank_score")) or 0.0),
                rank_score=float(_float(row.get("rank_score")) or 0.0),
                confidence_final=_float(row.get("confidence_final")),
                expectancy_status=_upper(row.get("expectancy_status") or row.get("keep_watch_kill_status")) or "INSUFFICIENT_DATA",
                expectancy_sample_count=_int(row.get("expectancy_sample_count")) or 0,
                expectancy_avg_cost_adjusted_r=_float(row.get("expectancy_avg_cost_adjusted_r")),
                execution_truth_state=_upper(row.get("execution_truth_state") or row.get("feed_truth_state") or ""),
                reportable_executable=bool(row.get("reportable_executable")),
                execution_allowed=bool(row.get("execution_allowed")),
                permission=_upper(row.get("permission")),
                final_action=_upper(row.get("final_action")),
                fallback_used=bool(row.get("fallback_used")),
                pool_quality_penalty=float(_float(row.get("pool_quality_penalty")) or 0.0),
                pool_quality_reasons=tuple(_text(reason) for reason in (row.get("pool_quality_reasons") or [])),
                why_ranked=_why_ranked(row),
                why_not_ranked=why_not_ranked,
                blockers=tuple(_text(blocker) for blocker in (row.get("blockers") or [])),
            )
        )
    return rows_out


def select_top_opportunities(
    rows: str | Path | Iterable[Mapping[str, Any]],
) -> TopOpportunitySelectorReport:
    loaded = _load_rows(rows)
    pool_quality = analyze_candidate_pool(loaded)
    rows_out = _build_opportunity_rows(loaded, pool_quality)
    executable = tuple(
        row for row in rows_out
        if row.expectancy_status == "KEEP"
        and row.permission == "EXECUTE"
        and row.final_action == "EXECUTE"
        and row.execution_truth_state not in {"BLOCKED", "DEAD", "RECOVERY_BLOCKED"}
        and not row.fallback_used
        and row.reportable_executable
        and row.execution_allowed
    )
    advisory = tuple(
        row for row in rows_out
        if row.expectancy_status == "WATCH"
        and row.permission in {"QUEUE_ONLY", "ADVISORY_ONLY", "EXECUTE"}
        and row.execution_truth_state not in {"BLOCKED", "DEAD", "RECOVERY_BLOCKED"}
        and not row.fallback_used
    )
    shadow = tuple(
        row for row in rows_out
        if row.expectancy_status == "INSUFFICIENT_DATA"
        and not row.fallback_used
        and row.execution_truth_state not in {"BLOCKED", "DEAD", "RECOVERY_BLOCKED"}
    )
    rejected = tuple(row for row in rows_out if row not in executable and row not in advisory and row not in shadow)
    source = str(rows) if isinstance(rows, (str, Path)) else "in_memory"
    return TopOpportunitySelectorReport(
        schema_version=TOP_OPPORTUNITY_SELECTOR_SCHEMA_VERSION,
        generated_by="top_opportunity_selector",
        source=source,
        candidate_count=len(loaded),
        opportunity_count=len(rows_out),
        executable_count=len(executable),
        advisory_count=len(advisory),
        shadow_count=len(shadow),
        rejected_count=len(rejected),
        pool_quality_state=pool_quality.readiness_state,
        pool_quality_score=pool_quality.quality_score,
        pool_quality_reasons=pool_quality.reasons,
        executable_opportunities=executable,
        advisory_opportunities=advisory,
        shadow_opportunities=shadow,
        rejected_opportunities=rejected,
    )


def _markdown_table(rows: tuple[TopOpportunityRow, ...]) -> str:
    headers = [
        "rank",
        "candidate_id",
        "trade_id",
        "symbol",
        "index",
        "strategy_family",
        "setup_id",
        "regime",
        "direction",
        "edge_rank_score",
        "rank_score",
        "confidence_final",
        "expectancy_status",
        "expectancy_sample_count",
        "expectancy_avg_cost_adjusted_r",
        "execution_truth_state",
        "reportable_executable",
        "execution_allowed",
        "permission",
        "final_action",
        "fallback_used",
        "pool_quality_penalty",
        "why_ranked",
        "why_not_ranked",
        "blockers",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        payload = row.to_payload()
        lines.append("| " + " | ".join(str(payload.get(column, "")) for column in headers) + " |")
    return "\n".join(lines)


def write_top_opportunities_report(
    rows: str | Path | Iterable[Mapping[str, Any]],
    output_dir: str | Path | None = None,
) -> tuple[Path, Path, TopOpportunitySelectorReport]:
    report = select_top_opportunities(rows)
    root = Path(output_dir).expanduser() if output_dir is not None else runtime_dir() / _DEFAULT_TOP_OPPORTUNITY_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / _DEFAULT_TOP_OPPORTUNITY_FILENAME_JSON
    md_path = root / _DEFAULT_TOP_OPPORTUNITY_FILENAME_MD
    json_path.write_text(json.dumps(report.to_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_lines = [
        "# Top Opportunity Selector Report",
        "",
        f"- Schema version: {report.schema_version}",
        f"- Generated by: {report.generated_by}",
        f"- Source: {report.source}",
        f"- Candidate count: {report.candidate_count}",
        f"- Opportunity count: {report.opportunity_count}",
        f"- Executable count: {report.executable_count}",
        f"- Advisory count: {report.advisory_count}",
        f"- Shadow count: {report.shadow_count}",
        f"- Rejected count: {report.rejected_count}",
        f"- Pool quality state: {report.pool_quality_state}",
        f"- Pool quality score: {report.pool_quality_score}",
        f"- Pool quality reasons: {', '.join(report.pool_quality_reasons) if report.pool_quality_reasons else 'none'}",
        "",
        "## Safety",
        "- read_only: True",
        "- append: False",
        "- is_order_action: False",
        "- broker_api_called: False",
        "- live_order_allowed: False",
        "- live_order_action: False",
        "- broker_order_action: False",
        "",
        "## Pool Quality",
        f"- state: {report.pool_quality_state}",
        f"- score: {report.pool_quality_score}",
        f"- reasons: {', '.join(report.pool_quality_reasons) if report.pool_quality_reasons else 'none'}",
        "",
        "## Executable Opportunities",
        "",
        _markdown_table(report.executable_opportunities) if report.executable_opportunities else "_None_",
        "",
        "## Advisory Opportunities",
        "",
        _markdown_table(report.advisory_opportunities) if report.advisory_opportunities else "_None_",
        "",
        "## Shadow / Paper Opportunities",
        "",
        _markdown_table(report.shadow_opportunities) if report.shadow_opportunities else "_None_",
        "",
        "## Rejected / Debug Opportunities",
        "",
        _markdown_table(report.rejected_opportunities) if report.rejected_opportunities else "_None_",
        "",
        "This report is read-only and does not change execution behavior.",
    ]
    md_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
    return json_path, md_path, report


__all__ = [
    "TOP_OPPORTUNITY_SELECTOR_SCHEMA_VERSION",
    "TopOpportunityRow",
    "TopOpportunitySelectorReport",
    "select_top_opportunities",
    "write_top_opportunities_report",
]
