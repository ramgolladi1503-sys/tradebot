from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from research.setup_expectancy import (
    _iter_jsonl,
    _json_dict,
    _metric_table,
    _safe_float,
    _trade_id,
    _write_report,
    calculate_expectancy,
    load_trade_quality_rows,
)


COMPONENT_ALIASES: dict[str, list[str]] = {
    "trend_alignment_score": ["trend_alignment_score", "trade_alignment"],
    "momentum_score": ["momentum_score"],
    "liquidity_score": ["liquidity_score", "liquidity_quality"],
    "spread_score": ["spread_score", "spread_quality"],
    "regime_fit_score": ["regime_fit_score", "regime_alignment"],
    "freshness_score": ["freshness_score", "freshness_quality"],
    "reward_risk_score": ["reward_risk_score", "risk_adjusted_quality"],
    "allocation_priority_score": ["allocation_priority_score", "strategy_priority", "allocation_score"],
}


def _nested_maps(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    detail = row.get("trade_score_detail")
    detail_map = detail if isinstance(detail, dict) else _json_dict(detail)
    features = row.get("features_snapshot")
    features_map = features if isinstance(features, dict) else _json_dict(features)
    source_flags = row.get("source_flags")
    source_flags_map = source_flags if isinstance(source_flags, dict) else {}
    if not source_flags_map:
        source_flags_map = _json_dict(row.get("source_flags_json"))
    nested_from_features = features_map.get("trade_score_detail") if isinstance(features_map.get("trade_score_detail"), dict) else {}
    nested_from_source_flags = (
        source_flags_map.get("trade_score_detail") if isinstance(source_flags_map.get("trade_score_detail"), dict) else {}
    )
    return [
        dict(row),
        detail_map,
        nested_from_features,
        features_map,
        nested_from_source_flags,
        source_flags_map,
    ]


def _extract_component(row: Mapping[str, Any], component: str) -> float | None:
    for payload in _nested_maps(row):
        for alias in COMPONENT_ALIASES.get(component, [component]):
            value = _safe_float(payload.get(alias))
            if value is not None:
                return value
    return None


def _extract_penalty_codes(row: Mapping[str, Any]) -> list[str]:
    codes: list[str] = []
    for field in ("soft_penalties", "confidence_penalty_reasons", "confidence_penalty_soft_veto_reasons"):
        raw = row.get(field)
        if isinstance(raw, str):
            maybe = _json_dict(raw)
            if maybe:
                raw = maybe
        if isinstance(raw, dict):
            raw = list(raw.keys())
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                text = str(item or "").strip().upper()
                if text and text not in codes:
                    codes.append(text)
    return codes


def _merge_prefer_existing(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if value in (None, "", [], {}):
            continue
        if target.get(key) in (None, "", [], {}):
            target[key] = value


def load_feature_attribution_rows(
    *,
    suggestions_path: Path | None = None,
    trade_log_path: Path | None = None,
    trade_updates_path: Path | None = None,
) -> list[dict[str, Any]]:
    base_rows = load_trade_quality_rows(
        suggestions_path=suggestions_path,
        trade_log_path=trade_log_path,
        trade_updates_path=trade_updates_path,
    )
    raw_by_trade: dict[str, dict[str, Any]] = {}
    for row in _iter_jsonl(suggestions_path) + _iter_jsonl(trade_log_path) + _iter_jsonl(trade_updates_path):
        trade_id = _trade_id(row)
        if not trade_id:
            continue
        current = raw_by_trade.setdefault(trade_id, {})
        _merge_prefer_existing(current, dict(row))

    enriched_rows: list[dict[str, Any]] = []
    for row in base_rows:
        trade_id = str(row.get("trade_id") or "")
        raw = raw_by_trade.get(trade_id, {})
        enriched = dict(row)
        for component in COMPONENT_ALIASES:
            enriched[component] = _extract_component(raw, component)
        enriched["penalty_codes"] = _extract_penalty_codes(raw)
        enriched_rows.append(enriched)
    return enriched_rows


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    denom_y = sum((y - mean_y) ** 2 for y in ys)
    if denom_x <= 0.0 or denom_y <= 0.0:
        return 0.0
    return float(numerator / ((denom_x ** 0.5) * (denom_y ** 0.5)))


def _component_summary(rows: list[Mapping[str, Any]], component: str) -> dict[str, Any]:
    available = [row for row in rows if _safe_float(row.get(component)) is not None and _safe_float(row.get("realized_pnl")) is not None]
    if not available:
        return {
            "component": component,
            "available_trade_count": 0,
            "usefulness_score": 0.0,
            "correlation_pnl": 0.0,
            "correlation_win": 0.0,
            "mean_component_win": 0.0,
            "mean_component_loss": 0.0,
            "expectancy_high_component": 0.0,
            "expectancy_low_component": 0.0,
        }

    values = [float(row[component]) for row in available]
    pnls = [float(row["realized_pnl"]) for row in available]
    wins = [1.0 if pnl > 0 else 0.0 for pnl in pnls]
    sorted_values = sorted(values)
    median = sorted_values[len(sorted_values) // 2]
    high_rows = [row for row in available if float(row[component]) >= median]
    low_rows = [row for row in available if float(row[component]) < median]
    win_values = [float(row[component]) for row in available if float(row["realized_pnl"]) > 0]
    loss_values = [float(row[component]) for row in available if float(row["realized_pnl"]) <= 0]
    corr_pnl = _pearson(values, pnls)
    corr_win = _pearson(values, wins)
    usefulness_score = max(abs(corr_pnl), abs(corr_win))
    return {
        "component": component,
        "available_trade_count": int(len(available)),
        "usefulness_score": round(float(usefulness_score), 6),
        "correlation_pnl": round(float(corr_pnl), 6),
        "correlation_win": round(float(corr_win), 6),
        "mean_component_win": round(float(sum(win_values) / len(win_values)), 6) if win_values else 0.0,
        "mean_component_loss": round(float(sum(loss_values) / len(loss_values)), 6) if loss_values else 0.0,
        "expectancy_high_component": round(float(calculate_expectancy(high_rows)["expectancy"]), 6) if high_rows else 0.0,
        "expectancy_low_component": round(float(calculate_expectancy(low_rows)["expectancy"]), 6) if low_rows else 0.0,
    }


def _penalty_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        for code in list(row.get("penalty_codes") or []):
            grouped.setdefault(str(code).upper(), []).append(row)
    table_rows = []
    for bucket in sorted(grouped):
        metrics = calculate_expectancy(grouped[bucket])
        table_rows.append(
            {
                "bucket": bucket,
                "trade_count": metrics["trade_count"],
                "expectancy": metrics["expectancy"],
                "win_rate": metrics["win_rate"],
                "avg_win": metrics["avg_win"],
                "avg_loss": metrics["avg_loss"],
            }
        )
    return {
        "label": "penalty_code",
        "columns": ["bucket", "trade_count", "expectancy", "win_rate", "avg_win", "avg_loss"],
        "rows": table_rows,
    }


def build_feature_attribution_report(
    *,
    suggestions_path: Path | None = None,
    trade_log_path: Path | None = None,
    trade_updates_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    rows = load_feature_attribution_rows(
        suggestions_path=suggestions_path,
        trade_log_path=trade_log_path,
        trade_updates_path=trade_updates_path,
    )
    evaluated = [row for row in rows if _safe_float(row.get("realized_pnl")) is not None]
    component_rows = [_component_summary(evaluated, component) for component in COMPONENT_ALIASES]
    ranked_rows = sorted(
        component_rows,
        key=lambda row: (-float(row.get("usefulness_score") or 0.0), str(row.get("component") or "")),
    )
    missing_components = [row["component"] for row in component_rows if int(row.get("available_trade_count") or 0) == 0]
    report = {
        "source_trade_count": int(len(rows)),
        "evaluated_trade_count": int(len(evaluated)),
        **calculate_expectancy(evaluated),
        "performance_by_strategy": _metric_table(evaluated, "strategy", label="strategy"),
        "performance_by_setup_type": _metric_table(evaluated, "setup_type", label="setup_type"),
        "performance_by_regime": _metric_table(evaluated, "regime", label="regime"),
        "performance_by_time_bucket": _metric_table(evaluated, "time_bucket", label="time_bucket"),
        "performance_by_allocation_bucket": _metric_table(evaluated, "allocation_bucket", label="allocation_bucket"),
        "component_attribution_summary": {
            "label": "component",
            "columns": [
                "component",
                "available_trade_count",
                "usefulness_score",
                "correlation_pnl",
                "correlation_win",
                "mean_component_win",
                "mean_component_loss",
                "expectancy_high_component",
                "expectancy_low_component",
            ],
            "rows": component_rows,
        },
        "component_usefulness_ranked": {
            "label": "component_usefulness",
            "columns": [
                "component",
                "available_trade_count",
                "usefulness_score",
                "correlation_pnl",
                "correlation_win",
                "mean_component_win",
                "mean_component_loss",
                "expectancy_high_component",
                "expectancy_low_component",
            ],
            "rows": ranked_rows,
        },
        "penalty_attribution_summary": _penalty_summary(evaluated),
        "notes": [],
    }
    if not evaluated:
        report["notes"].append("no_realized_trade_rows")
    if missing_components:
        report["notes"].append("missing_components:" + ",".join(sorted(missing_components)))
    _write_report(output_path, report)
    return report
