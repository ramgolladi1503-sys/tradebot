from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.expectancy.strategy_regime_expectancy import load_candidate_outcomes
from core.expectancy.top_opportunity_selector import select_top_opportunities
from core.paths import runtime_dir

TOPN_REPLAY_QUALITY_SCHEMA_VERSION = 1
TOPN_VERDICT_OUTPERFORMS = "TOPN_OUTPERFORMS"
TOPN_VERDICT_MATCHES = "TOPN_MATCHES"
TOPN_VERDICT_UNDERPERFORMS = "TOPN_UNDERPERFORMS"
TOPN_VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

_MIN_SAMPLE_SIZE = 30
_MATCH_DELTA_THRESHOLD = 0.03
_DEFAULT_TOPN_REPLAY_QUALITY_SUBDIR = "replay_quality"
_DEFAULT_TOPN_REPLAY_QUALITY_FILENAME_JSON = "topn_replay_quality_latest.json"
_DEFAULT_TOPN_REPLAY_QUALITY_FILENAME_MD = "topn_replay_quality_latest.md"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _lower(value: Any) -> str:
    return _text(value).lower()


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
            rows = payload.get("rows") or payload.get("items") or payload.get("opportunities") or payload.get("candidates") or payload.get("results")
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)], diagnostics
            return [dict(payload)], diagnostics
        return [], diagnostics
    return [dict(row) for row in source if isinstance(row, Mapping)], diagnostics


def _load_top_opportunities(source: str | Path | Iterable[Mapping[str, Any]] | Mapping[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    rows, diagnostics = _load_json_or_jsonl(source)
    if not rows:
        return {}, diagnostics
    if len(rows) == 1 and {"executable_opportunities", "advisory_opportunities", "shadow_opportunities", "rejected_opportunities"} & set(rows[0]):
        return dict(rows[0]), diagnostics
    report = select_top_opportunities(rows)
    return report.to_payload(), diagnostics


def _all_top_rows(top_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("executable_opportunities", "advisory_opportunities", "shadow_opportunities", "rejected_opportunities"):
        value = top_report.get(key)
        if isinstance(value, list):
            for row in value:
                if isinstance(row, Mapping):
                    rows.append(dict(row))
    rows.sort(
        key=lambda item: (
            _int(item.get("rank")) or 0,
            -float(_float(item.get("edge_rank_score")) or -1.0),
            -float(_float(item.get("rank_score")) or -1.0),
            _text(item.get("symbol")),
            _text(item.get("trade_id")),
        )
    )
    return rows


def _candidate_key(row: Mapping[str, Any]) -> str:
    candidate_id = _text(row.get("candidate_id"))
    if candidate_id:
        return candidate_id
    return _text(row.get("trade_id"))


def _is_fallback(row: Mapping[str, Any]) -> bool:
    if _truthy(row.get("fallback_used")):
        return True
    if _lower(row.get("candidate_class")) == "fallback":
        return True
    if _lower(row.get("row_kind")) in {"fallback", "recovered_fallback"}:
        return True
    candidate_type = _lower(row.get("candidate_type"))
    if "fallback" in candidate_type:
        return True
    candidate_origin = _lower(row.get("candidate_origin"))
    if "fallback" in candidate_origin:
        return True
    trade_id = _text(row.get("trade_id")).lower()
    if trade_id.startswith("softrej_"):
        return True
    if _upper(row.get("quote_source")) in {"REST_FALLBACK", "SYNTHETIC_OFFHOURS", "SUBSCRIPTION_FAILED"}:
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
    if execution_truth_state in {"BLOCKED", "DEAD", "RECOVERY_BLOCKED"}:
        return True
    if _upper(row.get("permission")) == "BLOCK":
        return True
    if _upper(row.get("final_action")) == "BLOCK":
        return True
    if _lower(row.get("execution_status")) == "blocked":
        return True
    blockers = list(row.get("blockers") or []) + list(row.get("execution_truth_blockers") or [])
    for blocker in blockers:
        text = _upper(blocker)
        if any(token in text for token in ("STALE", "LTP_STALE", "WS_DISCONNECTED", "GLOBAL_FEED_UNHEALTHY", "RECOVERY_BLOCKED", "WS1006", "PROCESS_RESTART_REQUIRED")):
            return True
    return False


def _candidate_outcome_map(candidate_outcomes: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
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


def _after_cost_return(outcome: Mapping[str, Any]) -> float | None:
    value = _float(outcome.get("cost_adjusted_r"))
    if value is not None:
        return value
    gross = _float(outcome.get("gross_r"))
    estimated_cost = _float(outcome.get("estimated_cost_r"))
    if gross is not None and estimated_cost is not None:
        return round(gross - estimated_cost, 6)
    return None


def _eligible_rows(top_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in top_rows:
        if _is_fallback(row) or _is_blocked(row):
            continue
        if _upper(row.get("expectancy_status") or row.get("keep_watch_kill_status")) != "KEEP":
            continue
        if _upper(row.get("permission")) != "EXECUTE":
            continue
        if _upper(row.get("final_action")) != "EXECUTE":
            continue
        if not _truthy(row.get("reportable_executable")):
            continue
        if not _truthy(row.get("execution_allowed")):
            continue
        rows.append(dict(row))
    return rows


def _ranked_after_cost_values(rows: Sequence[Mapping[str, Any]], primary_outcomes: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, float, str]]:
    ranked: list[tuple[str, float, str]] = []
    for row in rows:
        key = _candidate_key(row)
        if not key:
            continue
        outcome = primary_outcomes.get(key)
        if outcome is None:
            continue
        after_cost = _after_cost_return(outcome)
        if after_cost is None:
            continue
        ranked.append((key, float(after_cost), _text(row.get("regime")) or "UNKNOWN"))
    return ranked


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def _verdict(
    *,
    sample_count: int,
    top_1_after_cost_expectancy: float,
    top_5_after_cost_expectancy: float,
    top_3_after_cost_expectancy: float,
    top_10_after_cost_expectancy: float,
    naive_baseline_after_cost_expectancy: float,
    average_return_after_cost: float,
) -> tuple[str, str]:
    if sample_count < _MIN_SAMPLE_SIZE:
        return TOPN_VERDICT_INSUFFICIENT_SAMPLE, "sample_count_below_threshold"
    if average_return_after_cost <= 0:
        return TOPN_VERDICT_UNDERPERFORMS, "after_cost_average_non_positive"
    top_1_vs_top_5_delta = round(top_1_after_cost_expectancy - top_5_after_cost_expectancy, 6)
    top_3_vs_top_10_delta = round(top_3_after_cost_expectancy - top_10_after_cost_expectancy, 6)
    top_3_vs_baseline_delta = round(top_3_after_cost_expectancy - naive_baseline_after_cost_expectancy, 6)
    if (
        abs(top_1_vs_top_5_delta) <= _MATCH_DELTA_THRESHOLD
        and abs(top_3_vs_top_10_delta) <= _MATCH_DELTA_THRESHOLD
        and abs(top_3_vs_baseline_delta) <= _MATCH_DELTA_THRESHOLD
    ):
        return TOPN_VERDICT_MATCHES, "top_n_matches_naive_baseline_after_cost"
    if (
        top_1_vs_top_5_delta > _MATCH_DELTA_THRESHOLD
        and top_3_vs_top_10_delta > _MATCH_DELTA_THRESHOLD
        and top_3_vs_baseline_delta > _MATCH_DELTA_THRESHOLD
    ):
        return TOPN_VERDICT_OUTPERFORMS, "top_n_outperforms_lower_ranks_and_baseline_after_cost"
    return TOPN_VERDICT_UNDERPERFORMS, "top_n_underperforms_lower_ranks_or_baseline_after_cost"


def _regime_breakdown(rows: Sequence[Mapping[str, Any]], primary_outcomes: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        regime = _upper(row.get("regime")) or "UNKNOWN"
        groups.setdefault(regime, []).append(dict(row))
    breakdown: dict[str, dict[str, Any]] = {}
    for regime in sorted(groups):
        eligible = _eligible_rows(groups[regime])
        ranked = _ranked_after_cost_values(eligible, primary_outcomes)
        values = [item[1] for item in ranked]
        if not values:
            breakdown[regime] = {
                "sample_count": 0,
                "eligible_count": 0,
                "top_1_after_cost_expectancy": 0.0,
                "top_5_after_cost_expectancy": 0.0,
                "top_3_after_cost_expectancy": 0.0,
                "top_10_after_cost_expectancy": 0.0,
                "naive_baseline_after_cost_expectancy": 0.0,
                "top_1_vs_top_5_delta": 0.0,
                "top_3_vs_top_10_delta": 0.0,
                "top_3_vs_baseline_delta": 0.0,
                "average_return_after_cost": 0.0,
                "verdict": TOPN_VERDICT_INSUFFICIENT_SAMPLE,
                "reason": "missing_regime_or_outcome_data",
            }
            continue
        top_1 = ranked[0][1]
        top_5 = _average(values[:5])
        top_3 = _average(values[:3])
        top_10 = _average(values[:10])
        baseline = _average(values)
        verdict, reason = _verdict(
            sample_count=len(values),
            top_1_after_cost_expectancy=top_1,
            top_5_after_cost_expectancy=top_5,
            top_3_after_cost_expectancy=top_3,
            top_10_after_cost_expectancy=top_10,
            naive_baseline_after_cost_expectancy=baseline,
            average_return_after_cost=baseline,
        )
        breakdown[regime] = {
            "sample_count": len(values),
            "eligible_count": len(eligible),
            "top_1_after_cost_expectancy": top_1,
            "top_5_after_cost_expectancy": top_5,
            "top_3_after_cost_expectancy": top_3,
            "top_10_after_cost_expectancy": top_10,
            "naive_baseline_after_cost_expectancy": baseline,
            "top_1_vs_top_5_delta": round(top_1 - top_5, 6),
            "top_3_vs_top_10_delta": round(top_3 - top_10, 6),
            "top_3_vs_baseline_delta": round(top_3 - baseline, 6),
            "average_return_after_cost": baseline,
            "verdict": verdict,
            "reason": reason,
        }
    return breakdown


@dataclass(frozen=True)
class TopNReplayQualityReport:
    schema_version: int
    generated_by: str
    source: str
    sample_count: int
    eligible_count: int
    fallback_count: int
    blocked_count: int
    top_1_after_cost_expectancy: float
    top_5_after_cost_expectancy: float
    top_3_after_cost_expectancy: float
    top_10_after_cost_expectancy: float
    naive_baseline_after_cost_expectancy: float
    top_1_vs_top_5_delta: float
    top_1_vs_top_10_delta: float
    top_3_vs_top_10_delta: float
    top_3_vs_baseline_delta: float
    win_rate_after_cost: float
    average_return_after_cost: float
    max_loss_after_cost: float
    regime_breakdown: dict[str, dict[str, Any]]
    verdict: str
    reason: str
    missing_inputs: list[str] = field(default_factory=list)
    read_only: bool = True
    append: bool = False

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
            "# Top-N Replay Quality Report",
            "",
            f"- Schema version: {self.schema_version}",
            f"- Generated by: {self.generated_by}",
            f"- Source: {self.source}",
            f"- Sample count: {self.sample_count}",
            f"- Eligible count: {self.eligible_count}",
            f"- Fallback count: {self.fallback_count}",
            f"- Blocked count: {self.blocked_count}",
            f"- Top 1 after-cost expectancy: {self.top_1_after_cost_expectancy}",
            f"- Top 5 after-cost expectancy: {self.top_5_after_cost_expectancy}",
            f"- Top 3 after-cost expectancy: {self.top_3_after_cost_expectancy}",
            f"- Top 10 after-cost expectancy: {self.top_10_after_cost_expectancy}",
            f"- Naive baseline after-cost expectancy: {self.naive_baseline_after_cost_expectancy}",
            f"- Top 1 vs Top 5 delta: {self.top_1_vs_top_5_delta}",
            f"- Top 1 vs Top 10 delta: {self.top_1_vs_top_10_delta}",
            f"- Top 3 vs Top 10 delta: {self.top_3_vs_top_10_delta}",
            f"- Top 3 vs baseline delta: {self.top_3_vs_baseline_delta}",
            f"- Win rate after cost: {self.win_rate_after_cost}",
            f"- Average return after cost: {self.average_return_after_cost}",
            f"- Max loss after cost: {self.max_loss_after_cost}",
            f"- Verdict: {self.verdict}",
            f"- Reason: {self.reason}",
            f"- Missing inputs: {', '.join(self.missing_inputs) if self.missing_inputs else 'none'}",
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
            "## Regime Breakdown",
            json.dumps(self.regime_breakdown, sort_keys=True),
            "",
            "This report is read-only and does not enable live trading.",
        ]
        return "\n".join(lines) + "\n"


def build_topn_replay_quality_report(
    *,
    candidate_outcomes: str | Path | Iterable[Mapping[str, Any]] | None,
    top_opportunities: str | Path | Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
    session_rows: str | Path | Iterable[Mapping[str, Any]] | None = None,
) -> TopNReplayQualityReport:
    missing_inputs: list[str] = []
    outcome_rows = load_candidate_outcomes(candidate_outcomes)
    outcome_diag: list[str] = []
    if isinstance(candidate_outcomes, (str, Path)) and not Path(candidate_outcomes).expanduser().exists():
        missing_inputs.append("candidate_outcomes")
    top_report, top_diag = _load_top_opportunities(top_opportunities)
    if isinstance(top_opportunities, (str, Path)) and not Path(top_opportunities).expanduser().exists():
        missing_inputs.append("top_opportunities")

    session_rows_loaded, session_diag = _load_json_or_jsonl(session_rows)
    if session_rows is not None and isinstance(session_rows, (str, Path)) and not Path(session_rows).expanduser().exists():
        missing_inputs.append("session_rows")
    primary_outcomes = _candidate_outcome_map(outcome_rows)
    top_rows = _all_top_rows(top_report)
    eligible_rows = _eligible_rows(top_rows)
    ranked = _ranked_after_cost_values(eligible_rows, primary_outcomes)
    fallback_count = sum(1 for row in top_rows if _is_fallback(row))
    blocked_count = sum(1 for row in top_rows if _is_blocked(row) and not _is_fallback(row))
    eligible_count = len(eligible_rows)
    sample_count = len(ranked)

    if not ranked:
        top_1 = top_5 = top_3 = top_10 = baseline = average = 0.0
        max_loss = 0.0
        win_rate = 0.0
        verdict, reason = TOPN_VERDICT_INSUFFICIENT_SAMPLE, "no eligible executable candidates with outcome truth"
    else:
        values = [item[1] for item in ranked]
        top_1 = ranked[0][1]
        top_5 = _average(values[:5])
        top_3 = _average(values[:3])
        top_10 = _average(values[:10])
        baseline = _average(values)
        average = baseline
        max_loss = min(values)
        win_rate = round(sum(1 for value in values if value > 0) / len(values), 6)
        verdict, reason = _verdict(
            sample_count=sample_count,
            top_1_after_cost_expectancy=top_1,
            top_5_after_cost_expectancy=top_5,
            top_3_after_cost_expectancy=top_3,
            top_10_after_cost_expectancy=top_10,
            naive_baseline_after_cost_expectancy=baseline,
            average_return_after_cost=average,
        )

    if session_rows_loaded:
        session_diag.append(f"session_rows={len(session_rows_loaded)}")
    diagnostics = {
        "candidate_outcome_diagnostics": outcome_diag,
        "top_opportunity_diagnostics": top_diag,
        "session_diagnostics": session_diag,
        "top_rows": len(top_rows),
        "eligible_rows": eligible_count,
        "ranked_ids": [item[0] for item in ranked],
        "top_row_ids": [_candidate_key(row) for row in top_rows[:10]],
    }

    report = TopNReplayQualityReport(
        schema_version=TOPN_REPLAY_QUALITY_SCHEMA_VERSION,
        generated_by="topn_replay_quality",
        source="explicit_inputs",
        sample_count=sample_count,
        eligible_count=eligible_count,
        fallback_count=fallback_count,
        blocked_count=blocked_count,
        top_1_after_cost_expectancy=top_1,
        top_5_after_cost_expectancy=top_5,
        top_3_after_cost_expectancy=top_3,
        top_10_after_cost_expectancy=top_10,
        naive_baseline_after_cost_expectancy=baseline,
        top_1_vs_top_5_delta=round(top_1 - top_5, 6),
        top_1_vs_top_10_delta=round(top_1 - top_10, 6),
        top_3_vs_top_10_delta=round(top_3 - top_10, 6),
        top_3_vs_baseline_delta=round(top_3 - baseline, 6),
        win_rate_after_cost=win_rate,
        average_return_after_cost=average,
        max_loss_after_cost=max_loss,
        regime_breakdown=_regime_breakdown(eligible_rows, primary_outcomes),
        verdict=verdict,
        reason=reason,
        missing_inputs=list(dict.fromkeys(missing_inputs)),
    )
    return report


def write_topn_replay_quality_report(
    *,
    candidate_outcomes: str | Path | Iterable[Mapping[str, Any]] | None,
    top_opportunities: str | Path | Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
    session_rows: str | Path | Iterable[Mapping[str, Any]] | None = None,
    output_dir: str | Path | None = None,
    mirror_runtime: bool = False,
) -> tuple[Path, Path, TopNReplayQualityReport]:
    report = build_topn_replay_quality_report(
        candidate_outcomes=candidate_outcomes,
        top_opportunities=top_opportunities,
        session_rows=session_rows,
    )
    root = Path(output_dir).expanduser() if output_dir is not None else runtime_dir() / _DEFAULT_TOPN_REPLAY_QUALITY_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / _DEFAULT_TOPN_REPLAY_QUALITY_FILENAME_JSON
    md_path = root / _DEFAULT_TOPN_REPLAY_QUALITY_FILENAME_MD
    json_path.write_text(json.dumps(report.to_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    if mirror_runtime:
        runtime_root = runtime_dir() / _DEFAULT_TOPN_REPLAY_QUALITY_SUBDIR
        runtime_root.mkdir(parents=True, exist_ok=True)
        (runtime_root / _DEFAULT_TOPN_REPLAY_QUALITY_FILENAME_JSON).write_text(json.dumps(report.to_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (runtime_root / _DEFAULT_TOPN_REPLAY_QUALITY_FILENAME_MD).write_text(report.to_markdown(), encoding="utf-8")
    return json_path, md_path, report


__all__ = [
    "TOPN_REPLAY_QUALITY_SCHEMA_VERSION",
    "TOPN_VERDICT_INSUFFICIENT_SAMPLE",
    "TOPN_VERDICT_MATCHES",
    "TOPN_VERDICT_OUTPERFORMS",
    "TOPN_VERDICT_UNDERPERFORMS",
    "TopNReplayQualityReport",
    "build_topn_replay_quality_report",
    "write_topn_replay_quality_report",
]
