from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .horizon_sweep import _select_one_position_at_a_time, resolve_trace_at_horizon
from .models import summarize_returns


def _profit_factor(values: list[float]) -> float | None:
    wins = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if losses == 0:
        return math.inf if wins > 0 else None
    return wins / losses


def enrich_resolved_trade(trace: dict[str, Any], horizon: int, *, cost_bps: float) -> dict[str, Any]:
    trade = resolve_trace_at_horizon(trace, horizon, cost_bps=cost_bps)
    entry_price = float(trace["entry_price"])
    risk_points = float(trace["risk_points"])
    risk_bps = (risk_points / entry_price) * 10000.0
    if not math.isfinite(risk_bps) or risk_bps <= 0:
        raise ValueError("invalid_risk_bps")
    return {
        **trade,
        "entry_price": entry_price,
        "risk_points": risk_points,
        "risk_bps": risk_bps,
        "gross_r_multiple": float(trade["gross_return_bps"]) / risk_bps,
        "net_r_multiple": float(trade["net_return_bps"]) / risk_bps,
    }


def summarize_risk_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    net_bps = [float(trade["net_return_bps"]) for trade in trades]
    gross_r = [float(trade["gross_r_multiple"]) for trade in trades]
    net_r = [float(trade["net_r_multiple"]) for trade in trades]
    risk_bps = [float(trade["risk_bps"]) for trade in trades]
    reasons = Counter(str(trade["exit_reason"]) for trade in trades)
    reason_stats: dict[str, Any] = {}
    for reason in ("STOP", "TARGET", "TIMEOUT"):
        subset = [trade for trade in trades if trade["exit_reason"] == reason]
        reason_stats[reason] = {
            "count": len(subset),
            "average_risk_bps": mean(float(trade["risk_bps"]) for trade in subset) if subset else None,
            "average_gross_return_bps": mean(float(trade["gross_return_bps"]) for trade in subset) if subset else None,
            "average_net_return_bps": mean(float(trade["net_return_bps"]) for trade in subset) if subset else None,
            "average_gross_r_multiple": mean(float(trade["gross_r_multiple"]) for trade in subset) if subset else None,
            "average_net_r_multiple": mean(float(trade["net_r_multiple"]) for trade in subset) if subset else None,
        }
    return {
        **summarize_returns(net_bps),
        "gross_expectancy_r": mean(gross_r) if gross_r else None,
        "net_expectancy_r": mean(net_r) if net_r else None,
        "net_r_profit_factor": _profit_factor(net_r),
        "average_risk_bps": mean(risk_bps) if risk_bps else None,
        "stop_count": reasons["STOP"],
        "target_count": reasons["TARGET"],
        "timeout_count": reasons["TIMEOUT"],
        "reason_stats": reason_stats,
    }


def _scope_table(
    traces: list[dict[str, Any]],
    sessions: Iterable[str],
    horizons: Iterable[int],
    *,
    cost_bps: float,
) -> dict[str, Any]:
    allowed = set(sessions)
    scope = [trace for trace in traces if str(trace["session_date"]) in allowed]
    table: dict[str, Any] = {}
    for horizon in horizons:
        fixed = [enrich_resolved_trade(trace, int(horizon), cost_bps=cost_bps) for trace in scope]
        operational, skipped = _select_one_position_at_a_time(fixed)
        table[str(horizon)] = {
            "fixed_signal_cohort": summarize_risk_metrics(fixed),
            "one_position_at_a_time": {
                **summarize_risk_metrics(operational),
                "overlapping_signals_skipped": skipped,
            },
        }
    return {"fixed_signal_count": len(scope), "horizons": table}


def build_risk_normalized_summary(result: dict[str, Any], traces: list[dict[str, Any]]) -> dict[str, Any]:
    horizons = [int(value) for value in result["horizons_minutes"]]
    partitions = result["partitions"]
    cost_bps = float(result["config"]["round_trip_cost_bps"])
    development_sessions = list(partitions["train"]) + list(partitions["validation"])
    holdout = _scope_table(traces, partitions["holdout"], horizons, cost_bps=cost_bps)
    development = _scope_table(traces, development_sessions, horizons, cost_bps=cost_bps)

    def best(scope: dict[str, Any], metric: str) -> dict[str, Any]:
        candidates = []
        for horizon in horizons:
            metrics = scope["horizons"][str(horizon)]["one_position_at_a_time"]
            value = metrics.get(metric)
            candidates.append((float(value) if value is not None else -math.inf, -horizon, horizon, metrics))
        _, _, horizon, metrics = max(candidates)
        return {"horizon_minutes": horizon, "metrics": metrics}

    best_notional = best(holdout, "net_expectancy_bps")
    best_equal_risk = best(holdout, "net_expectancy_r")
    holdout_15 = result["holdout"]["horizons"]["15"]
    return {
        "schema_version": 1,
        "verdict": result["verdict"],
        "diagnostic_only": True,
        "holdout_reused_across_horizons": True,
        "fresh_holdout_required": True,
        "baseline_cost_bps": cost_bps,
        "best_holdout_equal_notional": best_notional,
        "best_holdout_equal_risk": best_equal_risk,
        "equal_notional_positive_at_any_horizon": any(
            float(holdout["horizons"][str(h)]["one_position_at_a_time"]["net_expectancy_bps"] or 0.0) > 0
            for h in horizons
        ),
        "equal_risk_positive_at_any_horizon": any(
            float(holdout["horizons"][str(h)]["one_position_at_a_time"]["net_expectancy_r"] or 0.0) > 0
            for h in horizons
        ),
        "holdout_15_minute_timeout_transition_to_60": holdout_15["timeouts_then_later_outcomes"],
        "holdout": holdout,
        "development": development,
        "holdout_first_touch_distribution": result["holdout"]["first_touch_distribution"],
        "all_session_first_touch_distribution": result["all_sessions"]["first_touch_distribution"],
    }


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add risk-normalized diagnostics to a horizon sweep")
    parser.add_argument("--result", required=True)
    parser.add_argument("--traces", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    traces = load_jsonl(args.traces)
    summary = build_risk_normalized_summary(result, traces)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "horizon_risk_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    best_notional = summary["best_holdout_equal_notional"]
    best_risk = summary["best_holdout_equal_risk"]
    transition = summary["holdout_15_minute_timeout_transition_to_60"]
    lines = [
        "# TREND_PULLBACK holding-horizon and risk-normalization summary",
        "",
        f"Equal-notional positive at any horizon: **{summary['equal_notional_positive_at_any_horizon']}**",
        f"Equal-risk positive at any horizon: **{summary['equal_risk_positive_at_any_horizon']}**",
        "",
        f"Best equal-notional horizon: **{best_notional['horizon_minutes']} minutes**",
        f"Best equal-risk horizon: **{best_risk['horizon_minutes']} minutes**",
        "",
        "## Fifteen-minute timeouts followed to minute 60",
        "",
        f"- Later target: {transition['later_target_by_maximum']}",
        f"- Later stop: {transition['later_stop_by_maximum']}",
        f"- Still unresolved: {transition['still_unresolved_at_maximum']}",
        "",
        "This is diagnostic only. The historical holdout has been reused across horizons and cannot certify promotion.",
    ]
    (output / "horizon_risk_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "best_equal_notional_horizon": best_notional["horizon_minutes"],
        "best_equal_risk_horizon": best_risk["horizon_minutes"],
        "equal_notional_positive": summary["equal_notional_positive_at_any_horizon"],
        "equal_risk_positive": summary["equal_risk_positive_at_any_horizon"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
