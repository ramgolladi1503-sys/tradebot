from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.expectancy.strategy_regime_expectancy import aggregate_strategy_regime_expectancy, load_candidate_outcomes

STRATEGY_BASELINE_COMPARISON_SCHEMA_VERSION = 1
BASELINE_VERDICT_OUTPERFORMS = "OUTPERFORMS"
BASELINE_VERDICT_MATCHES = "MATCHES"
BASELINE_VERDICT_UNDERPERFORMS = "UNDERPERFORMS"
BASELINE_VERDICT_INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"

_MIN_SAMPLE_SIZE = 30
_MATCH_DELTA_THRESHOLD = 0.03
_BOOST_CAP = 0.08
_PENALTY_CAP = 0.12

_VALID_VERDICTS = {
    BASELINE_VERDICT_OUTPERFORMS,
    BASELINE_VERDICT_MATCHES,
    BASELINE_VERDICT_UNDERPERFORMS,
    BASELINE_VERDICT_INSUFFICIENT_SAMPLE,
}

_BULLISH_DIRECTIONS = frozenset({"BUY", "LONG", "BUY_CALL", "LONG_CALL", "CALL", "CE", "BULLISH"})
_BEARISH_DIRECTIONS = frozenset({"SELL", "SHORT", "BUY_PUT", "LONG_PUT", "PUT", "PE", "SELL_CALL", "SELL_PUT", "BEARISH"})


@dataclass(frozen=True)
class StrategyBaselineComparison:
    schema_version: int
    strategy_id: str
    setup_fingerprint: str
    setup_id: str
    strategy_family: str
    regime: str
    index: str
    expiry_type: str
    option_type: str
    direction: str
    sample_count: int
    strategy_after_cost_expectancy: float
    baseline_after_cost_expectancy: float | None
    expectancy_delta_vs_baseline: float | None
    baseline_verdict: str
    confidence_tier: str
    penalty_or_boost: float
    reason: str
    baseline_source: str
    baseline_sample_count: int
    same_regime_baseline_after_cost_expectancy: float | None
    same_direction_baseline_after_cost_expectancy: float | None
    eligible_baseline_after_cost_expectancy: float | None
    read_only: bool = True
    append: bool = False

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyBaselineComparisonReport:
    schema_version: int
    generated_by: str
    source: str
    comparison_count: int
    outperform_count: int
    match_count: int
    underperform_count: int
    insufficient_sample_count: int
    comparisons: tuple[StrategyBaselineComparison, ...]
    baseline_lookup: dict[str, dict[str, Any]]
    read_only: bool = True
    append: bool = False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["comparisons"] = [comparison.to_payload() for comparison in self.comparisons]
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
        return payload

    def to_dict(self) -> dict[str, Any]:
        return self.to_payload()


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def _int(value: Any) -> int:
    try:
        if value in (None, "", "None"):
            return 0
        return int(float(value))
    except Exception:
        return 0


def _direction_family(direction: Any) -> str:
    normalized = _text(direction).upper()
    if normalized in _BULLISH_DIRECTIONS:
        return "BULLISH"
    if normalized in _BEARISH_DIRECTIONS:
        return "BEARISH"
    return "OTHER"


def _group_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in rows]
    if rows and any("outcome_status" in row for row in rows):
        report = aggregate_strategy_regime_expectancy(rows, group_by_setup_id=True)
        return [dict(group.to_payload()) for group in report.groups]
    grouped_rows: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        setup_id = _text(payload.get("setup_id")) or _text(payload.get("group_key"))
        if not setup_id:
            setup_id = _text(payload.get("strategy_id")) or f"{_text(payload.get('strategy_family'))}__{_text(payload.get('regime'))}"
        payload.setdefault("group_key", setup_id)
        payload.setdefault("strategy_id", _text(payload.get("strategy_id")) or setup_id)
        payload.setdefault("strategy_family", _text(payload.get("strategy_family")) or _text(payload.get("group_key")).split("__")[0])
        payload.setdefault("regime", _lower(payload.get("regime")))
        payload.setdefault("index", _text(payload.get("index")))
        payload.setdefault("expiry_type", _text(payload.get("expiry_type")))
        payload.setdefault("option_type", _text(payload.get("option_type")))
        payload.setdefault("direction", _text(payload.get("direction")))
        payload.setdefault("sample_count", _int(payload.get("sample_count")))
        payload.setdefault("executable_count", _int(payload.get("executable_count")))
        payload.setdefault("not_executable_count", _int(payload.get("not_executable_count")))
        payload.setdefault("avg_cost_adjusted_r", _float(payload.get("avg_cost_adjusted_r")) or 0.0)
        payload.setdefault("median_cost_adjusted_r", _float(payload.get("median_cost_adjusted_r")) or _float(payload.get("avg_cost_adjusted_r")) or 0.0)
        payload.setdefault("keep_watch_kill_status", _text(payload.get("keep_watch_kill_status")) or BASELINE_VERDICT_INSUFFICIENT_SAMPLE)
        payload.setdefault("status_reason", _text(payload.get("status_reason")))
        grouped_rows.append(payload)
    return grouped_rows


def _group_lookup(groups: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for group in groups:
        setup_id = _text(group.get("group_key")) or _text(group.get("setup_id"))
        if not setup_id:
            continue
        lookup[setup_id] = dict(group)
    return lookup


def _peer_average(
    groups: Iterable[Mapping[str, Any]],
    *,
    exclude_setup_id: str,
    predicate,
) -> tuple[float | None, int]:
    peers = [
        group
        for group in groups
        if _text(group.get("group_key")) != exclude_setup_id and predicate(group)
    ]
    if not peers:
        return None, 0
    weights = [max(_int(group.get("executable_count")), 1) for group in peers]
    values = [_float(group.get("avg_cost_adjusted_r")) for group in peers]
    paired = [
        (value, weight)
        for value, weight in zip(values, weights, strict=False)
        if value is not None
    ]
    if not paired:
        return None, 0
    total_weight = sum(weight for _, weight in paired)
    avg = sum(value * weight for value, weight in paired) / total_weight if total_weight else None
    return round(avg, 6) if avg is not None else None, sum(weight for _, weight in paired)


def _confidence_tier(sample_count: int, baseline_sample_count: int, verdict: str) -> str:
    if verdict == BASELINE_VERDICT_INSUFFICIENT_SAMPLE or sample_count < _MIN_SAMPLE_SIZE or baseline_sample_count < _MIN_SAMPLE_SIZE:
        return "INSUFFICIENT"
    if sample_count >= 80 and baseline_sample_count >= 80:
        return "HIGH"
    if sample_count >= 50 and baseline_sample_count >= 50:
        return "MEDIUM"
    return "LOW"


def _verdict(delta: float | None, sample_count: int, baseline_sample_count: int) -> str:
    if sample_count < _MIN_SAMPLE_SIZE or baseline_sample_count < _MIN_SAMPLE_SIZE or delta is None:
        return BASELINE_VERDICT_INSUFFICIENT_SAMPLE
    if delta > _MATCH_DELTA_THRESHOLD:
        return BASELINE_VERDICT_OUTPERFORMS
    if delta < -_MATCH_DELTA_THRESHOLD:
        return BASELINE_VERDICT_UNDERPERFORMS
    return BASELINE_VERDICT_MATCHES


def _penalty_or_boost(verdict: str, delta: float | None) -> float:
    if verdict == BASELINE_VERDICT_OUTPERFORMS and delta is not None:
        return round(min(_BOOST_CAP, 0.02 + max(delta, 0.0) * 0.25), 6)
    if verdict == BASELINE_VERDICT_UNDERPERFORMS and delta is not None:
        return round(-min(_PENALTY_CAP, 0.03 + abs(delta) * 0.30), 6)
    return 0.0


def _baseline_source(group: Mapping[str, Any], comparison: Mapping[str, Any]) -> str:
    if comparison.get("same_regime_baseline_after_cost_expectancy") is not None:
        return "same_regime"
    if comparison.get("same_direction_baseline_after_cost_expectancy") is not None:
        return "same_direction"
    if comparison.get("eligible_baseline_after_cost_expectancy") is not None:
        return "eligible_candidates"
    return "missing_baseline"


def compare_strategy_to_baselines(
    candidate_outcomes: str | Path | Iterable[Mapping[str, Any]],
) -> StrategyBaselineComparisonReport:
    rows = load_candidate_outcomes(candidate_outcomes)
    groups = _group_rows(rows)
    by_setup_id = _group_lookup(groups)
    comparisons: list[StrategyBaselineComparison] = []
    counts = {
        BASELINE_VERDICT_OUTPERFORMS: 0,
        BASELINE_VERDICT_MATCHES: 0,
        BASELINE_VERDICT_UNDERPERFORMS: 0,
        BASELINE_VERDICT_INSUFFICIENT_SAMPLE: 0,
    }

    for group in sorted(groups, key=lambda item: (_text(item.get("group_key")), _text(item.get("strategy_family")), _text(item.get("regime")))):
        setup_id = _text(group.get("group_key"))
        strategy_family = _text(group.get("strategy_family"))
        regime = _text(group.get("regime"))
        index = _text(group.get("index"))
        expiry_type = _text(group.get("expiry_type"))
        option_type = _text(group.get("option_type"))
        direction = _text(group.get("direction"))
        sample_count = _int(group.get("sample_count"))
        strategy_after_cost_expectancy = float(_float(group.get("avg_cost_adjusted_r")) or 0.0)
        same_regime_baseline_after_cost_expectancy, same_regime_sample_count = _peer_average(
            groups,
            exclude_setup_id=setup_id,
            predicate=lambda item: _text(item.get("regime")) == regime,
        )
        same_direction_baseline_after_cost_expectancy, same_direction_sample_count = _peer_average(
            groups,
            exclude_setup_id=setup_id,
            predicate=lambda item: _direction_family(item.get("direction")) == _direction_family(direction),
        )
        eligible_baseline_after_cost_expectancy, eligible_sample_count = _peer_average(
            groups,
            exclude_setup_id=setup_id,
            predicate=lambda item: (_float(item.get("avg_cost_adjusted_r")) is not None) and _int(item.get("sample_count")) >= _MIN_SAMPLE_SIZE,
        )

        baseline_after_cost_expectancy = same_regime_baseline_after_cost_expectancy
        baseline_sample_count = same_regime_sample_count
        baseline_reason = "same_regime_baseline"
        if baseline_after_cost_expectancy is None or baseline_sample_count < _MIN_SAMPLE_SIZE:
            baseline_after_cost_expectancy = same_direction_baseline_after_cost_expectancy
            baseline_sample_count = same_direction_sample_count
            baseline_reason = "same_direction_baseline"
        if baseline_after_cost_expectancy is None or baseline_sample_count < _MIN_SAMPLE_SIZE:
            baseline_after_cost_expectancy = eligible_baseline_after_cost_expectancy
            baseline_sample_count = eligible_sample_count
            baseline_reason = "eligible_candidate_baseline"

        delta = None
        if baseline_after_cost_expectancy is not None:
            delta = round(strategy_after_cost_expectancy - float(baseline_after_cost_expectancy), 6)
        verdict = _verdict(delta, sample_count, baseline_sample_count)
        confidence_tier = _confidence_tier(sample_count, baseline_sample_count, verdict)
        penalty_or_boost = _penalty_or_boost(verdict, delta)
        reason = baseline_reason if verdict != BASELINE_VERDICT_INSUFFICIENT_SAMPLE else "insufficient_sample_for_baseline_comparison"
        if verdict == BASELINE_VERDICT_OUTPERFORMS:
            reason = f"{baseline_reason}; strategy_after_cost_expectancy_above_baseline"
        elif verdict == BASELINE_VERDICT_MATCHES:
            reason = f"{baseline_reason}; strategy_after_cost_expectancy_near_baseline"
        elif verdict == BASELINE_VERDICT_UNDERPERFORMS:
            reason = f"{baseline_reason}; strategy_after_cost_expectancy_below_baseline"

        comparison = StrategyBaselineComparison(
            schema_version=STRATEGY_BASELINE_COMPARISON_SCHEMA_VERSION,
            strategy_id=_text(group.get("strategy_id")) or setup_id,
            setup_fingerprint=setup_id,
            setup_id=setup_id,
            strategy_family=strategy_family,
            regime=regime,
            index=index,
            expiry_type=expiry_type,
            option_type=option_type,
            direction=direction,
            sample_count=sample_count,
            strategy_after_cost_expectancy=strategy_after_cost_expectancy,
            baseline_after_cost_expectancy=baseline_after_cost_expectancy,
            expectancy_delta_vs_baseline=delta,
            baseline_verdict=verdict,
            confidence_tier=confidence_tier,
            penalty_or_boost=penalty_or_boost,
            reason=reason,
            baseline_source=_baseline_source(group, {"same_regime_baseline_after_cost_expectancy": same_regime_baseline_after_cost_expectancy, "same_direction_baseline_after_cost_expectancy": same_direction_baseline_after_cost_expectancy, "eligible_baseline_after_cost_expectancy": eligible_baseline_after_cost_expectancy}),
            baseline_sample_count=baseline_sample_count,
            same_regime_baseline_after_cost_expectancy=same_regime_baseline_after_cost_expectancy,
            same_direction_baseline_after_cost_expectancy=same_direction_baseline_after_cost_expectancy,
            eligible_baseline_after_cost_expectancy=eligible_baseline_after_cost_expectancy,
        )
        comparisons.append(comparison)
        counts[verdict] += 1

    lookup = {
        comparison.setup_id: {
            "strategy_id": comparison.strategy_id,
            "setup_fingerprint": comparison.setup_fingerprint,
            "baseline_verdict": comparison.baseline_verdict,
            "baseline_penalty_or_boost": comparison.penalty_or_boost,
            "baseline_reason": comparison.reason,
            "baseline_source": comparison.baseline_source,
            "baseline_after_cost_expectancy": comparison.baseline_after_cost_expectancy,
            "expectancy_delta_vs_baseline": comparison.expectancy_delta_vs_baseline,
            "confidence_tier": comparison.confidence_tier,
            "sample_count": comparison.sample_count,
        }
        for comparison in comparisons
    }
    source = str(candidate_outcomes) if isinstance(candidate_outcomes, (str, Path)) else "in_memory"
    return StrategyBaselineComparisonReport(
        schema_version=STRATEGY_BASELINE_COMPARISON_SCHEMA_VERSION,
        generated_by="strategy_baseline_comparison",
        source=source,
        comparison_count=len(comparisons),
        outperform_count=counts[BASELINE_VERDICT_OUTPERFORMS],
        match_count=counts[BASELINE_VERDICT_MATCHES],
        underperform_count=counts[BASELINE_VERDICT_UNDERPERFORMS],
        insufficient_sample_count=counts[BASELINE_VERDICT_INSUFFICIENT_SAMPLE],
        comparisons=tuple(comparisons),
        baseline_lookup=lookup,
    )


def build_strategy_baseline_lookup(candidate_outcomes: str | Path | Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    return dict(compare_strategy_to_baselines(candidate_outcomes).baseline_lookup)


def write_strategy_baseline_comparison_report(
    candidate_outcomes: str | Path | Iterable[Mapping[str, Any]],
    output_dir: str | Path | None = None,
) -> tuple[Path, Path, StrategyBaselineComparisonReport]:
    report = compare_strategy_to_baselines(candidate_outcomes)
    root = Path(output_dir).expanduser() if output_dir is not None else Path("reports")
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "strategy_baseline_comparison_latest.json"
    md_path = root / "strategy_baseline_comparison_latest.md"
    json_path.write_text(json.dumps(report.to_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_lines = [
        "# Strategy Baseline Comparison Report",
        "",
        f"- Schema version: {report.schema_version}",
        f"- Generated by: {report.generated_by}",
        f"- Source: {report.source}",
        f"- Comparison count: {report.comparison_count}",
        f"- Outperform count: {report.outperform_count}",
        f"- Match count: {report.match_count}",
        f"- Underperform count: {report.underperform_count}",
        f"- Insufficient sample count: {report.insufficient_sample_count}",
        "",
        "## Comparisons",
        "",
        "| setup_id | verdict | confidence_tier | delta_vs_baseline | penalty_or_boost | reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for comparison in report.comparisons:
        markdown_lines.append(
            f"| {comparison.setup_id} | {comparison.baseline_verdict} | {comparison.confidence_tier} | {comparison.expectancy_delta_vs_baseline} | {comparison.penalty_or_boost} | {comparison.reason} |"
        )
    markdown_lines.extend(
        [
            "",
            "This report is read-only and does not enable live trading.",
        ]
    )
    md_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
    return json_path, md_path, report


__all__ = [
    "BASELINE_VERDICT_INSUFFICIENT_SAMPLE",
    "BASELINE_VERDICT_MATCHES",
    "BASELINE_VERDICT_OUTPERFORMS",
    "BASELINE_VERDICT_UNDERPERFORMS",
    "STRATEGY_BASELINE_COMPARISON_SCHEMA_VERSION",
    "StrategyBaselineComparison",
    "StrategyBaselineComparisonReport",
    "build_strategy_baseline_lookup",
    "compare_strategy_to_baselines",
    "write_strategy_baseline_comparison_report",
]
