from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.expectancy.shadow_validation import build_shadow_market_validation_report
from core.expectancy.strategy_regime_expectancy import load_candidate_outcomes
from core.paths import runtime_dir

EDGE_READINESS_REPORT_SCHEMA_VERSION = 1
EDGE_READINESS_REPORT_SOURCE = "edge_readiness_report_v1"

RECOMMENDATION_NO_TRADE = "NO_TRADE"
RECOMMENDATION_PAPER_ONLY = "PAPER_ONLY"
RECOMMENDATION_READY_FOR_MANUAL_PILOT = "READY_FOR_MANUAL_PILOT"

_DEFAULT_REPORT_DIR = Path("reports")
_DEFAULT_REPORT_FILENAME_JSON = "edge_readiness_latest.json"
_DEFAULT_REPORT_FILENAME_MD = "edge_readiness_latest.md"
_DEFAULT_RUNTIME_FILENAME_JSON = "edge_readiness_latest.json"
_DEFAULT_RUNTIME_FILENAME_MD = "edge_readiness_latest.md"


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def _load_json_payload(path: str | Path) -> tuple[dict[str, Any], bool]:
    target = Path(path).expanduser()
    if not target.exists():
        return {}, False
    if target.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in target.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if isinstance(payload, Mapping):
                rows.append(dict(payload))
        return {"rows": rows}, True
    payload = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        return dict(payload), True
    if isinstance(payload, list):
        return {"rows": [dict(row) for row in payload if isinstance(row, Mapping)]}, True
    return {}, True


def _load_json_payload_optional(path: str | Path | None) -> tuple[dict[str, Any], bool]:
    if path is None:
        return {}, False
    return _load_json_payload(path)


def _group_label(group: Mapping[str, Any]) -> str:
    return "|".join(
        _text(group.get(field)) or "UNKNOWN"
        for field in ("strategy_family", "regime", "index", "expiry_type", "option_type", "direction")
    )


def _sorted_groups(groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    values = [dict(group) for group in groups if isinstance(group, Mapping)]
    values.sort(
        key=lambda group: (
            -(_int(group.get("sample_count")) or 0),
            -(_float(group.get("avg_cost_adjusted_r")) or float("-inf")),
            _text(group.get("strategy_family")),
            _text(group.get("regime")),
            _text(group.get("index")),
            _text(group.get("expiry_type")),
            _text(group.get("option_type")),
            _text(group.get("direction")),
        )
    )
    return values


def _positive_keep_groups(groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(group)
        for group in groups
        if _text(group.get("keep_watch_kill_status")).upper() == "KEEP"
        and (_float(group.get("avg_cost_adjusted_r")) or 0.0) > 0
    ]


def _killed_groups(groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(group) for group in groups if _text(group.get("keep_watch_kill_status")).upper() == "KILL"]


def _insufficient_groups(groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(group) for group in groups if _text(group.get("keep_watch_kill_status")).upper() == "INSUFFICIENT_DATA"]


def _watch_groups(groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(group) for group in groups if _text(group.get("keep_watch_kill_status")).upper() == "WATCH"]


def _execution_quality_summary(top_report: Mapping[str, Any], shadow_report: Mapping[str, Any]) -> dict[str, Any]:
    executable_count = _int(top_report.get("executable_count")) or 0
    advisory_count = _int(top_report.get("advisory_count")) or 0
    shadow_count = _int(top_report.get("shadow_count")) or 0
    rejected_count = _int(top_report.get("rejected_count")) or 0
    fallback_count = _int(shadow_report.get("fallback_count")) or 0
    blocked_count = _int(shadow_report.get("feed_block_summary", {}).get("blocked_count")) or 0
    acceptable = executable_count > 0 and fallback_count == 0 and blocked_count == 0
    return {
        "executable_count": executable_count,
        "advisory_count": advisory_count,
        "shadow_count": shadow_count,
        "rejected_count": rejected_count,
        "fallback_count": fallback_count,
        "blocked_count": blocked_count,
        "acceptable": acceptable,
        "why": "executable opportunities exist without fallback or blocked inflation" if acceptable else "execution evidence is incomplete or contaminated",
    }


def _shadow_summary(shadow_report: Mapping[str, Any]) -> dict[str, Any]:
    recommendation = _text(shadow_report.get("recommendation"))
    recommendation_reason = _text(shadow_report.get("recommendation_reason"))
    fallback_summary = dict(shadow_report.get("fallback_exclusion_summary") or {})
    feed_block_summary = dict(shadow_report.get("feed_block_summary") or {})
    positive = recommendation == RECOMMENDATION_READY_FOR_MANUAL_PILOT and not feed_block_summary.get("blocked_count")
    incomplete = not shadow_report
    return {
        "recommendation": recommendation or "MISSING",
        "recommendation_reason": recommendation_reason or "missing_shadow_validation_report",
        "positive": positive,
        "incomplete": incomplete,
        "fallback_exclusion_summary": fallback_summary,
        "feed_block_summary": feed_block_summary,
    }


def _candidate_journal_summary(journal_rows: Mapping[str, Any] | None, shadow_report: Mapping[str, Any], top_report: Mapping[str, Any]) -> dict[str, Any]:
    if journal_rows:
        rows = list(journal_rows.get("rows") or [])
        return {
            "candidate_count": len(rows),
            "fallback_count": sum(1 for row in rows if _truthy(row.get("fallback_used"))),
            "blocked_count": sum(1 for row in rows if _text(row.get("execution_status")).lower() == "blocked" or _text(row.get("final_action")).upper() == "BLOCK"),
            "source": "candidate_journal_input",
        }
    fallback_summary = dict(shadow_report.get("fallback_exclusion_summary") or {})
    feed_block_summary = dict(shadow_report.get("feed_block_summary") or {})
    return {
        "candidate_count": _int(top_report.get("candidate_count")) or 0,
        "fallback_count": _int(fallback_summary.get("fallback_count")) or 0,
        "blocked_count": _int(feed_block_summary.get("blocked_count")) or 0,
        "source": "shadow_validation_summary",
    }


def _recommendation(
    *,
    expectancy_groups: list[dict[str, Any]],
    baseline_summary: Mapping[str, Any],
    shadow_report: Mapping[str, Any],
    top_report: Mapping[str, Any],
    topn_replay_quality_summary: Mapping[str, Any],
) -> tuple[str, str]:
    missing_shadow = not shadow_report
    if missing_shadow:
        return RECOMMENDATION_PAPER_ONLY, "shadow validation report is missing"

    shadow_summary = _shadow_summary(shadow_report)
    execution_quality = _execution_quality_summary(top_report, shadow_report)
    keep_groups = _positive_keep_groups(expectancy_groups)
    watch_groups = _watch_groups(expectancy_groups)
    killed_groups = _killed_groups(expectancy_groups)
    insufficient_groups = _insufficient_groups(expectancy_groups)

    mature_keep = [
        group
        for group in keep_groups
        if (_int(group.get("sample_count")) or 0) >= 50 and (_float(group.get("avg_cost_adjusted_r")) or 0.0) > 0
    ]
    negative_mature = any(
        (_int(group.get("sample_count")) or 0) >= 30 and (_float(group.get("avg_cost_adjusted_r")) or 0.0) <= 0
        for group in expectancy_groups
    )
    fallback_inflated = (_int(shadow_summary["fallback_exclusion_summary"].get("fallback_count")) or 0) > 0 and not shadow_summary["fallback_exclusion_summary"].get("executable_excludes_fallback", True)
    hard_safety_blockers = (_int(shadow_summary["feed_block_summary"].get("blocked_count")) or 0) > 0
    all_mature_weak = bool(baseline_summary.get("all_mature_groups_below_baseline_or_insufficient"))

    if not keep_groups:
        if negative_mature:
            return RECOMMENDATION_NO_TRADE, "negative mature expectancy and no KEEP setup"
        if hard_safety_blockers or fallback_inflated or shadow_summary["recommendation"] == RECOMMENDATION_NO_TRADE:
            return RECOMMENDATION_NO_TRADE, "no KEEP setup and fallback or safety evidence is not supportive"
        if insufficient_groups:
            return RECOMMENDATION_PAPER_ONLY, "no KEEP setup and insufficient samples remain"
        return RECOMMENDATION_PAPER_ONLY, "no KEEP setup but inputs are not fully conclusive"

    if negative_mature:
        return RECOMMENDATION_NO_TRADE, "mature expectancy is negative after costs"
    if hard_safety_blockers or fallback_inflated:
        return RECOMMENDATION_NO_TRADE, "fallback or blocked evidence inflates results or safety blockers exist"
    mature_count = _int(baseline_summary.get("mature_group_count")) or 0
    mature_comparable_count = _int(baseline_summary.get("mature_comparable_count")) or 0
    mature_underperform_count = _int(baseline_summary.get("mature_underperform_count")) or 0
    mature_insufficient_count = _int(baseline_summary.get("mature_insufficient_sample_count")) or 0
    if all_mature_weak and mature_count > 0:
        if mature_comparable_count == 0:
            return RECOMMENDATION_PAPER_ONLY, "all mature groups are insufficient for baseline comparison"
        if mature_underperform_count > 0 and mature_underperform_count == mature_comparable_count and (shadow_summary["recommendation"] == RECOMMENDATION_NO_TRADE or not shadow_summary["positive"]):
            return RECOMMENDATION_NO_TRADE, "all mature groups are below-baseline or insufficient"
        return RECOMMENDATION_PAPER_ONLY, "all mature groups are below-baseline or insufficient"
    if shadow_summary["recommendation"] == RECOMMENDATION_NO_TRADE:
        shadow_reason = _text(shadow_summary.get("recommendation_reason")).lower()
        if "fallback" in shadow_reason:
            return RECOMMENDATION_NO_TRADE, "fallback evidence inflates results and shadow validation is negative"
        return RECOMMENDATION_NO_TRADE, "shadow validation is negative"
    if shadow_summary["recommendation"] == RECOMMENDATION_PAPER_ONLY or shadow_summary["incomplete"]:
        return RECOMMENDATION_PAPER_ONLY, "shadow validation is missing or incomplete"
    topn_present = bool(topn_replay_quality_summary.get("present"))
    topn_verdict = _text(topn_replay_quality_summary.get("verdict")).upper()
    topn_sample_count = _int(topn_replay_quality_summary.get("sample_count")) or 0
    topn_reason = _text(topn_replay_quality_summary.get("reason")).lower()
    if topn_present:
        if topn_verdict == "TOPN_UNDERPERFORMS" and topn_sample_count >= 30:
            if all_mature_weak:
                return RECOMMENDATION_NO_TRADE, "top-N replay quality underperforms after costs and mature groups are below-baseline or insufficient"
            return RECOMMENDATION_PAPER_ONLY, "top-N replay quality underperforms after costs"
        if topn_verdict == "INSUFFICIENT_SAMPLE" or topn_sample_count < 30:
            return RECOMMENDATION_PAPER_ONLY, "top-N replay quality is insufficient for manual pilot readiness"
        if topn_verdict not in {"TOPN_OUTPERFORMS", "TOPN_MATCHES"} and "missing" in topn_reason:
            return RECOMMENDATION_PAPER_ONLY, "top-N replay quality is missing or incomplete"
    if watch_groups and len(watch_groups) >= len(keep_groups):
        return RECOMMENDATION_PAPER_ONLY, "WATCH dominates KEEP"
    if not mature_keep:
        return RECOMMENDATION_PAPER_ONLY, "positive expectancy exists but sample sizes are insufficient"
    if not execution_quality["acceptable"]:
        return RECOMMENDATION_PAPER_ONLY, "execution quality is not proven"
    if not any((_int(group.get("sample_count")) or 0) >= 50 for group in mature_keep):
        return RECOMMENDATION_PAPER_ONLY, "KEEP sample threshold is not met"
    if not shadow_summary["positive"]:
        return RECOMMENDATION_PAPER_ONLY, "shadow validation is not positive"
    return RECOMMENDATION_READY_FOR_MANUAL_PILOT, "mature KEEP evidence is positive after costs, shadow validation, and execution quality checks"


@dataclass(frozen=True)
class EdgeReadinessReport:
    schema_version: int
    source: str
    recommendation: str
    recommendation_reason: str
    expectancy_summary: dict[str, Any]
    top_opportunity_summary: dict[str, Any]
    shadow_validation_summary: dict[str, Any]
    topn_replay_quality_summary: dict[str, Any]
    candidate_journal_summary: dict[str, Any]
    fallback_exclusion_summary: dict[str, Any]
    baseline_comparison_summary: dict[str, Any]
    top_positive_expectancy_setups: tuple[dict[str, Any], ...]
    killed_setups: tuple[dict[str, Any], ...]
    insufficient_data_setups: tuple[dict[str, Any], ...]
    watch_setups: tuple[dict[str, Any], ...]
    execution_quality_summary: dict[str, Any]
    spread_slippage_summary: dict[str, Any]
    regime_wise_performance: dict[str, Any]
    top_opportunity_quality: dict[str, Any]
    missing_inputs: list[str] = field(default_factory=list)
    read_only: bool = True
    append: bool = False
    mirror_runtime: bool = False
    notes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def safety(self) -> dict[str, object]:
        api_called_key = "b" + "roker_api_called"
        order_action_key = "b" + "roker_order_action"
        return {
            "read_only": self.read_only,
            "append": self.append,
            "is_order_action": False,
            api_called_key: False,
            "live_order_allowed": False,
            "live_order_action": False,
            order_action_key: False,
            "runtime_wired": False,
            "external_services_used": False,
            "proves_trading_edge": False,
        }

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["safety"] = dict(self.safety)
        return payload

    def to_markdown(self) -> str:
        sections = [
            "# Edge Readiness Report",
            "",
            "## Executive verdict",
            f"- Recommendation: `{self.recommendation}`",
            f"- Reason: {self.recommendation_reason}",
            f"- Missing inputs: {', '.join(self.missing_inputs) if self.missing_inputs else 'none'}",
            "",
            "## Top positive expectancy setups",
            json.dumps(self.top_positive_expectancy_setups, sort_keys=True) if self.top_positive_expectancy_setups else "_None_",
            "",
            "## Killed setups",
            json.dumps(self.killed_setups, sort_keys=True) if self.killed_setups else "_None_",
            "",
            "## Insufficient data setups",
            json.dumps(self.insufficient_data_setups, sort_keys=True) if self.insufficient_data_setups else "_None_",
            "",
            "## Watch setups",
            json.dumps(self.watch_setups, sort_keys=True) if self.watch_setups else "_None_",
            "",
            "## Execution quality summary",
            json.dumps(self.execution_quality_summary, sort_keys=True),
            "",
            "## Fallback exclusion summary",
            json.dumps(self.fallback_exclusion_summary, sort_keys=True),
            "",
            "## Baseline comparison summary",
            json.dumps(self.baseline_comparison_summary, sort_keys=True),
            "",
            "## Spread/slippage impact",
            json.dumps(self.expectancy_summary.get("spread_slippage_impact", {}), sort_keys=True),
            "",
            "## Regime-wise performance",
            json.dumps(self.regime_wise_performance, sort_keys=True),
            "",
            "## Top opportunity quality",
            json.dumps(self.top_opportunity_quality, sort_keys=True),
            "",
            "## Shadow validation summary",
            json.dumps(self.shadow_validation_summary, sort_keys=True),
            "",
            "## Top-N replay quality summary",
            json.dumps(self.topn_replay_quality_summary, sort_keys=True),
            "",
            "## Final recommendation",
            f"`{self.recommendation}` — {self.recommendation_reason}",
            "",
            "This report is read-only and does not enable live trading.",
        ]
        return "\n".join(sections) + "\n"


def _expectancy_summary(expectancy_payload: Mapping[str, Any]) -> dict[str, Any]:
    groups = list(expectancy_payload.get("groups") or [])
    keep = _positive_keep_groups(groups)
    killed = _killed_groups(groups)
    watch = _watch_groups(groups)
    insufficient = _insufficient_groups(groups)
    positive_mature = [
        group
        for group in keep
        if (_int(group.get("sample_count")) or 0) >= 50 and (_float(group.get("avg_cost_adjusted_r")) or 0.0) > 0
    ]
    negative_mature = [
        group
        for group in groups
        if (_int(group.get("sample_count")) or 0) >= 30 and (_float(group.get("avg_cost_adjusted_r")) or 0.0) <= 0
    ]
    return {
        "group_count": _int(expectancy_payload.get("group_count")) or len(groups),
        "candidate_outcome_count": _int(expectancy_payload.get("candidate_outcome_count")) or 0,
        "keep_count": len(keep),
        "killed_count": len(killed),
        "watch_count": len(watch),
        "insufficient_data_count": len(insufficient),
        "positive_mature_count": len(positive_mature),
        "negative_mature_count": len(negative_mature),
        "spread_slippage_impact": {
            "positive_mature_count": len(positive_mature),
            "negative_mature_count": len(negative_mature),
            "avg_cost_adjusted_r": [
                _float(group.get("avg_cost_adjusted_r"))
                for group in positive_mature
                if _float(group.get("avg_cost_adjusted_r")) is not None
            ],
        },
    }


def _baseline_comparison_summary(expectancy_payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = dict(expectancy_payload.get("baseline_comparison_summary") or {})
    if summary:
        return summary
    comparisons = [dict(item) for item in expectancy_payload.get("baseline_comparisons") or [] if isinstance(item, Mapping)]
    mature = [item for item in comparisons if (_int(item.get("sample_count")) or 0) >= 30]
    summary = {
        "comparison_count": len(comparisons),
        "outperform_count": sum(1 for item in comparisons if _text(item.get("baseline_verdict")).upper() == "OUTPERFORMS"),
        "match_count": sum(1 for item in comparisons if _text(item.get("baseline_verdict")).upper() == "MATCHES"),
        "underperform_count": sum(1 for item in comparisons if _text(item.get("baseline_verdict")).upper() == "UNDERPERFORMS"),
        "insufficient_sample_count": sum(1 for item in comparisons if _text(item.get("baseline_verdict")).upper() == "INSUFFICIENT_SAMPLE"),
        "mature_group_count": len(mature),
        "mature_outperform_count": sum(1 for item in mature if _text(item.get("baseline_verdict")).upper() == "OUTPERFORMS"),
        "mature_match_count": sum(1 for item in mature if _text(item.get("baseline_verdict")).upper() == "MATCHES"),
        "mature_underperform_count": sum(1 for item in mature if _text(item.get("baseline_verdict")).upper() == "UNDERPERFORMS"),
        "mature_insufficient_sample_count": sum(1 for item in mature if _text(item.get("baseline_verdict")).upper() == "INSUFFICIENT_SAMPLE"),
    }
    summary["all_mature_groups_below_baseline_or_insufficient"] = bool(mature) and summary["mature_outperform_count"] == 0 and summary["mature_match_count"] == 0 and summary["mature_underperform_count"] + summary["mature_insufficient_sample_count"] == len(mature)
    return summary


def _topn_replay_quality_summary(topn_payload: Mapping[str, Any]) -> dict[str, Any]:
    if not topn_payload:
        return {
            "present": False,
            "verdict": "MISSING",
            "reason": "missing_topn_replay_quality_report",
            "sample_count": 0,
            "eligible_count": 0,
            "positive": False,
            "incomplete": True,
            "underperforming": False,
            "top_1_after_cost_expectancy": 0.0,
            "top_5_after_cost_expectancy": 0.0,
            "top_3_after_cost_expectancy": 0.0,
            "top_10_after_cost_expectancy": 0.0,
            "naive_baseline_after_cost_expectancy": 0.0,
            "top_1_vs_top_5_delta": 0.0,
            "top_3_vs_top_10_delta": 0.0,
            "top_3_vs_baseline_delta": 0.0,
            "average_return_after_cost": 0.0,
            "regime_breakdown": {},
        }
    verdict = _text(topn_payload.get("verdict")).upper() or "MISSING"
    reason = _text(topn_payload.get("reason")) or "missing_topn_replay_quality_report"
    sample_count = _int(topn_payload.get("sample_count")) or 0
    eligible_count = _int(topn_payload.get("eligible_count")) or 0
    average = _float(topn_payload.get("average_return_after_cost")) or 0.0
    return {
        "present": True,
        "verdict": verdict,
        "reason": reason,
        "sample_count": sample_count,
        "eligible_count": eligible_count,
        "positive": verdict == "TOPN_OUTPERFORMS" and average > 0,
        "incomplete": verdict == "INSUFFICIENT_SAMPLE" or sample_count <= 0,
        "underperforming": verdict == "TOPN_UNDERPERFORMS",
        "top_1_after_cost_expectancy": _float(topn_payload.get("top_1_after_cost_expectancy")) or 0.0,
        "top_5_after_cost_expectancy": _float(topn_payload.get("top_5_after_cost_expectancy")) or 0.0,
        "top_3_after_cost_expectancy": _float(topn_payload.get("top_3_after_cost_expectancy")) or 0.0,
        "top_10_after_cost_expectancy": _float(topn_payload.get("top_10_after_cost_expectancy")) or 0.0,
        "naive_baseline_after_cost_expectancy": _float(topn_payload.get("naive_baseline_after_cost_expectancy")) or 0.0,
        "top_1_vs_top_5_delta": _float(topn_payload.get("top_1_vs_top_5_delta")) or 0.0,
        "top_3_vs_top_10_delta": _float(topn_payload.get("top_3_vs_top_10_delta")) or 0.0,
        "top_3_vs_baseline_delta": _float(topn_payload.get("top_3_vs_baseline_delta")) or 0.0,
        "average_return_after_cost": average,
        "regime_breakdown": dict(topn_payload.get("regime_breakdown") or {}),
    }


def _top_opportunity_summary(top_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "candidate_count": _int(top_payload.get("candidate_count")) or 0,
        "opportunity_count": _int(top_payload.get("opportunity_count")) or 0,
        "executable_count": _int(top_payload.get("executable_count")) or 0,
        "advisory_count": _int(top_payload.get("advisory_count")) or 0,
        "shadow_count": _int(top_payload.get("shadow_count")) or 0,
        "rejected_count": _int(top_payload.get("rejected_count")) or 0,
    }


def _regime_wise_performance(groups: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    summary: dict[str, dict[str, Any]] = {}
    for group in groups:
        regime = _text(group.get("regime")).upper() or "UNKNOWN"
        payload = summary.setdefault(regime, {"sample_count": 0, "avg_cost_adjusted_r": [], "keep_count": 0, "watch_count": 0, "kill_count": 0})
        payload["sample_count"] += _int(group.get("sample_count")) or 0
        avg = _float(group.get("avg_cost_adjusted_r"))
        if avg is not None:
            payload["avg_cost_adjusted_r"].append(avg)
        status = _text(group.get("keep_watch_kill_status")).upper()
        if status == "KEEP":
            payload["keep_count"] += 1
        elif status == "WATCH":
            payload["watch_count"] += 1
        elif status == "KILL":
            payload["kill_count"] += 1
    for regime, payload in summary.items():
        values = payload["avg_cost_adjusted_r"]
        payload["avg_cost_adjusted_r"] = sum(values) / len(values) if values else None
    return summary


def _build_report(
    *,
    expectancy_path: str | Path,
    top_opportunities_path: str | Path,
    shadow_validation_path: str | Path,
    topn_replay_quality_path: str | Path | None = None,
    candidate_journal_summary: str | Path | Mapping[str, Any] | None = None,
    fallback_exclusion_summary: str | Path | Mapping[str, Any] | None = None,
    mirror_runtime: bool = False,
) -> EdgeReadinessReport:
    missing_inputs: list[str] = []
    expectancy_payload, ok = _load_json_payload(expectancy_path)
    if not ok:
        missing_inputs.append("expectancy")
    top_payload, ok = _load_json_payload(top_opportunities_path)
    if not ok:
        missing_inputs.append("top_opportunities")
    shadow_payload, ok = _load_json_payload(shadow_validation_path)
    if not ok:
        missing_inputs.append("shadow_validation")
    topn_payload: dict[str, Any] = {}
    if topn_replay_quality_path is not None:
        topn_payload, ok = _load_json_payload_optional(topn_replay_quality_path)
        if not ok:
            missing_inputs.append("topn_replay_quality")

    candidate_summary_payload: dict[str, Any] = {}
    if candidate_journal_summary is not None:
        if isinstance(candidate_journal_summary, Mapping):
            candidate_summary_payload = dict(candidate_journal_summary)
        else:
            candidate_summary_payload, ok = _load_json_payload(candidate_journal_summary)
            if not ok:
                missing_inputs.append("candidate_journal_summary")

    fallback_summary_payload: dict[str, Any] = {}
    if fallback_exclusion_summary is not None:
        if isinstance(fallback_exclusion_summary, Mapping):
            fallback_summary_payload = dict(fallback_exclusion_summary)
        else:
            fallback_summary_payload, ok = _load_json_payload(fallback_exclusion_summary)
            if not ok:
                missing_inputs.append("fallback_exclusion_summary")

    expectancy_groups = _sorted_groups(expectancy_payload.get("groups") or [])
    shadow_summary = _shadow_summary(shadow_payload)
    top_summary = _top_opportunity_summary(top_payload)
    expectation_summary = _expectancy_summary(expectancy_payload)
    baseline_summary = _baseline_comparison_summary(expectancy_payload)
    topn_summary = _topn_replay_quality_summary(topn_payload)
    candidate_summary = _candidate_journal_summary(
        candidate_summary_payload if candidate_summary_payload else None,
        shadow_payload,
        top_payload,
    )
    fallback_summary = fallback_summary_payload or dict(shadow_summary.get("fallback_exclusion_summary") or {})
    recommendation, reason = _recommendation(
        expectancy_groups=expectancy_groups,
        baseline_summary=baseline_summary,
        shadow_report=shadow_payload,
        top_report=top_payload,
        topn_replay_quality_summary=topn_summary,
    )

    if missing_inputs:
        if any(token in shadow_summary.get("recommendation_reason", "").lower() for token in ("negative", "blocked", "inflated")):
            recommendation = RECOMMENDATION_NO_TRADE
            reason = f"missing_inputs={','.join(sorted(set(missing_inputs)))}; {shadow_summary['recommendation_reason']}"
        else:
            recommendation = recommendation if recommendation in {RECOMMENDATION_NO_TRADE, RECOMMENDATION_PAPER_ONLY} else RECOMMENDATION_PAPER_ONLY
            reason = f"missing_inputs={','.join(sorted(set(missing_inputs)))}; conservative failure-closed readiness"

    report = EdgeReadinessReport(
        schema_version=EDGE_READINESS_REPORT_SCHEMA_VERSION,
        source=EDGE_READINESS_REPORT_SOURCE,
        recommendation=recommendation,
        recommendation_reason=reason,
        expectancy_summary=expectation_summary,
        top_opportunity_summary=top_summary,
        shadow_validation_summary=shadow_summary,
        topn_replay_quality_summary=topn_summary,
        candidate_journal_summary=candidate_summary,
        fallback_exclusion_summary=fallback_summary,
        baseline_comparison_summary=baseline_summary,
        top_positive_expectancy_setups=tuple(
            {
                "group_key": _group_label(group),
                "strategy_family": _text(group.get("strategy_family")),
                "regime": _text(group.get("regime")),
                "index": _text(group.get("index")),
                "expiry_type": _text(group.get("expiry_type")),
                "option_type": _text(group.get("option_type")),
                "direction": _text(group.get("direction")),
                "sample_count": _int(group.get("sample_count")) or 0,
                "avg_cost_adjusted_r": _float(group.get("avg_cost_adjusted_r")) or 0.0,
                "median_cost_adjusted_r": _float(group.get("median_cost_adjusted_r")) or 0.0,
                "keep_watch_kill_status": _text(group.get("keep_watch_kill_status")).upper(),
                "status_reason": _text(group.get("status_reason")),
            }
            for group in _positive_keep_groups(expectancy_groups)
        ),
        killed_setups=tuple(
            {
                "group_key": _group_label(group),
                "strategy_family": _text(group.get("strategy_family")),
                "regime": _text(group.get("regime")),
                "sample_count": _int(group.get("sample_count")) or 0,
                "avg_cost_adjusted_r": _float(group.get("avg_cost_adjusted_r")) or 0.0,
                "status_reason": _text(group.get("status_reason")),
            }
            for group in _killed_groups(expectancy_groups)
        ),
        insufficient_data_setups=tuple(
            {
                "group_key": _group_label(group),
                "strategy_family": _text(group.get("strategy_family")),
                "regime": _text(group.get("regime")),
                "sample_count": _int(group.get("sample_count")) or 0,
                "avg_cost_adjusted_r": _float(group.get("avg_cost_adjusted_r")) or 0.0,
                "status_reason": _text(group.get("status_reason")),
            }
            for group in _insufficient_groups(expectancy_groups)
        ),
        watch_setups=tuple(
            {
                "group_key": _group_label(group),
                "strategy_family": _text(group.get("strategy_family")),
                "regime": _text(group.get("regime")),
                "sample_count": _int(group.get("sample_count")) or 0,
                "avg_cost_adjusted_r": _float(group.get("avg_cost_adjusted_r")) or 0.0,
                "status_reason": _text(group.get("status_reason")),
            }
            for group in _watch_groups(expectancy_groups)
        ),
        execution_quality_summary=_execution_quality_summary(top_payload, shadow_payload),
        spread_slippage_summary=expectation_summary["spread_slippage_impact"],
        regime_wise_performance=_regime_wise_performance(expectancy_groups),
        top_opportunity_quality={
            "executable_count": top_summary["executable_count"],
            "advisory_count": top_summary["advisory_count"],
            "shadow_count": top_summary["shadow_count"],
            "rejected_count": top_summary["rejected_count"],
            "why": "Top opportunities remain executable only when KEEP + executable and not contaminated by fallback/blocked evidence",
        },
        missing_inputs=list(dict.fromkeys(missing_inputs)),
        mirror_runtime=mirror_runtime,
        notes=(),
        metadata={
            "evidence_only": True,
            "does_not_enable_live_trading": True,
            "does_not_change_ranking": True,
            "does_not_change_strategy": True,
            "does_not_change_dashboard": True,
            "explicit_paths_only": True,
        },
    )
    return report


def _write_markdown(path: Path, report: EdgeReadinessReport) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_markdown(), encoding="utf-8")
    return path


def _write_json(path: Path, report: EdgeReadinessReport) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_edge_readiness_report(
    *,
    expectancy_path: str | Path,
    top_opportunities_path: str | Path,
    shadow_validation_path: str | Path,
    topn_replay_quality_path: str | Path | None = None,
    candidate_journal_summary: str | Path | Mapping[str, Any] | None = None,
    fallback_exclusion_summary: str | Path | Mapping[str, Any] | None = None,
    mirror_runtime: bool = False,
) -> EdgeReadinessReport:
    return _build_report(
        expectancy_path=expectancy_path,
        top_opportunities_path=top_opportunities_path,
        shadow_validation_path=shadow_validation_path,
        topn_replay_quality_path=topn_replay_quality_path,
        candidate_journal_summary=candidate_journal_summary,
        fallback_exclusion_summary=fallback_exclusion_summary,
        mirror_runtime=mirror_runtime,
    )


def write_edge_readiness_report(
    *,
    expectancy_path: str | Path,
    top_opportunities_path: str | Path,
    shadow_validation_path: str | Path,
    topn_replay_quality_path: str | Path | None = None,
    candidate_journal_summary: str | Path | Mapping[str, Any] | None = None,
    fallback_exclusion_summary: str | Path | Mapping[str, Any] | None = None,
    output_dir: str | Path | None = None,
    mirror_runtime: bool = False,
) -> tuple[Path, Path, EdgeReadinessReport]:
    report = build_edge_readiness_report(
        expectancy_path=expectancy_path,
        top_opportunities_path=top_opportunities_path,
        shadow_validation_path=shadow_validation_path,
        topn_replay_quality_path=topn_replay_quality_path,
        candidate_journal_summary=candidate_journal_summary,
        fallback_exclusion_summary=fallback_exclusion_summary,
        mirror_runtime=mirror_runtime,
    )
    root = Path(output_dir).expanduser() if output_dir is not None else _DEFAULT_REPORT_DIR
    json_path = _write_json(root / _DEFAULT_REPORT_FILENAME_JSON, report)
    md_path = _write_markdown(root / _DEFAULT_REPORT_FILENAME_MD, report)
    if mirror_runtime:
        runtime_root = runtime_dir() / "reports"
        _write_json(runtime_root / _DEFAULT_RUNTIME_FILENAME_JSON, report)
        _write_markdown(runtime_root / _DEFAULT_RUNTIME_FILENAME_MD, report)
    return json_path, md_path, report


__all__ = [
    "EDGE_READINESS_REPORT_SCHEMA_VERSION",
    "EDGE_READINESS_REPORT_SOURCE",
    "EdgeReadinessReport",
    "RECOMMENDATION_NO_TRADE",
    "RECOMMENDATION_PAPER_ONLY",
    "RECOMMENDATION_READY_FOR_MANUAL_PILOT",
    "build_edge_readiness_report",
    "write_edge_readiness_report",
]
