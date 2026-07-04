import argparse
import json
try:
    import yaml
except ImportError:
    yaml = None
from pathlib import Path
from datetime import datetime, UTC

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--shadow-trades-path", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    trades_path = Path(args.shadow_trades_path)
    trades = []
    if trades_path.exists():
        with open(trades_path, "r") as f:
            for line in f:
                if line.strip():
                    trades.append(json.loads(line))

    days = set(t["signal_ts"][:10] for t in trades)
    trading_days_observed = len(days)

    stale_count = sum(1 for t in trades if t.get("rejection_reason") == "STALE_QUOTE")
    missing_count = sum(1 for t in trades if t.get("rejection_reason") == "MISSING_QUOTE")
    spread_count = sum(1 for t in trades if t.get("rejection_reason") == "WIDE_SPREAD")
    fallback_count = sum(1 for t in trades if t.get("rejection_reason") == "FALLBACK_CANDIDATE")

    exec_count = sum(1 for t in trades if t.get("rejection_reason") is None and t.get("fillable_pnl") is not None)

    violations = []
    if any(t.get("evidence_mode") == "fixture" for t in trades):
        violations.append("FIXTURE_EVIDENCE_NOT_ALLOWED")
    if any(t.get("execution_model") != "live_shadow_paper" for t in trades):
        violations.append("INVALID_EXECUTION_MODEL")
    if any(t.get("real_order_sent", True) for t in trades):
        violations.append("REAL_ORDER_SENT_IS_TRUE")

    # Gate violations for executable trades
    for t in trades:
        if t.get("rejection_reason") is None:
            if t.get("entry_quote_age_sec", 0) > 5.0:
                violations.append("EXECUTED_STALE_QUOTE")
            if t.get("spread_pct_of_premium", 0) > 0.01:
                violations.append("EXECUTED_WIDE_SPREAD")

    data_quality_score = 1.0 - ((stale_count + missing_count) / max(1, len(trades)))

    lifecycle_state = "PHASE_6_OBSERVING"

    if violations:
        lifecycle_state = "PHASE_6_FAILED_VIOLATION"
    elif data_quality_score < 0.5:
        lifecycle_state = "PHASE_6_DATA_BLOCKED"
    elif trading_days_observed >= 5:
        lifecycle_state = "PHASE_6_PASSED"

    report = {
        "strategy_id": args.strategy_id,
        "passed": lifecycle_state == "PHASE_6_PASSED",
        "shadow_start": min(days) if days else None,
        "shadow_end": max(days) if days else None,
        "trading_days_observed": trading_days_observed,
        "signal_count": len(trades),
        "executable_shadow_trade_count": exec_count,
        "rejected_signal_count": stale_count + missing_count + spread_count + fallback_count,
        "stale_quote_rejection_count": stale_count,
        "missing_quote_rejection_count": missing_count,
        "spread_rejection_count": spread_count,
        "fallback_rejection_count": fallback_count,
        "theoretical_net_pnl": sum(t.get("theoretical_pnl", 0) for t in trades),
        "fillable_net_pnl": sum(t.get("fillable_pnl", 0) for t in trades),
        "slippage_total": sum(t.get("theoretical_pnl", 0) - t.get("fillable_pnl", 0) for t in trades if t.get("rejection_reason") is None),
        "avg_quote_age_sec": sum(t.get("entry_quote_age_sec", 0) for t in trades) / max(1, len(trades)),
        "max_quote_age_sec": max([t.get("entry_quote_age_sec", 0) for t in trades] + [0]),
        "max_drawdown": 0,
        "data_quality_score": data_quality_score,
        "violations": violations,
        "lifecycle_recommendation": lifecycle_state,
        "generated_at": datetime.now(UTC).isoformat(),
        "schema_version": "1.0",
        "validator_version": "1.0"
    }

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=4)

    lifecycle_path = Path(f"runtime/strategy_validation/{args.strategy_id}/strategy_lifecycle_state.yaml")
    if lifecycle_path.exists() and yaml is not None:
        with open(lifecycle_path, "r") as f:
            state = yaml.safe_load(f)

        state["lifecycle_state"] = lifecycle_state
        state["paper_live_allowed"] = lifecycle_state == "PHASE_6_PASSED"
        state["live_allowed"] = False

        with open(lifecycle_path, "w") as f:
            yaml.dump(state, f, sort_keys=False)

if __name__ == "__main__":
    main()
