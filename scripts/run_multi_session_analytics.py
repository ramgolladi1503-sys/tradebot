"""Multi-Session Quant Analytics Runner.

Aggregates execution telemetry, runs statutory and quantitative metrics engines,
and exports structured JSON to reports/research/sentinel_multi_session_analytics.json.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
- status = "NO_CERTIFIED_EDGE"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Add repo root to sys.path if not present
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.analytics.multi_session_aggregator import MultiSessionAggregator
from core.analytics.quant_metrics_engine import QuantMetricsEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_multi_session_analytics")

OUTPUT_PATH = Path("reports/research/sentinel_multi_session_analytics.json")


def generate_multi_session_report(
    start_date: str = "2026-10-07",
    end_date: Optional[str] = None,
    audit_dir: str = "runtime/audit",
    wal_path: Any = None,
    bootstrap_resamples: int = 2000,
) -> Dict[str, Any]:
    # Dynamic end_date defaulting to today's date if None
    effective_end_date = end_date or datetime.now().date().isoformat()

    aggregator = MultiSessionAggregator(
        audit_dir=audit_dir,
        wal_path=wal_path,
        start_date=start_date,
        end_date=effective_end_date,
    )

    logger.info("Running Session Continuity Audit (%s to %s)...", start_date, effective_end_date)
    continuity_audit, parsed_records = aggregator.run_continuity_audit()

    logger.info("Extracting trades from WAL...")
    trades = aggregator.extract_trades()
    logger.info("Extracted %d trades.", len(trades))

    engine = QuantMetricsEngine()
    accountings = engine.process_trades(trades)

    logger.info("Computing Summary KPIs...")
    kpis = engine.compute_summary_kpis(accountings)

    logger.info("Computing Bootstrap Confidence Intervals (%d resamples)...", bootstrap_resamples)
    bootstraps = engine.bootstrap_confidence_intervals(accountings, n_resamples=bootstrap_resamples)

    # 1. Index-level breakdowns (dynamically computed for all detected underlyings)
    all_underlyings = sorted(list(set(a.trade.underlying for a in accountings)))
    # Ensure standard indices are present even if 0 trades
    for standard_idx in ("NIFTY", "SENSEX", "BANKNIFTY"):
        if standard_idx not in all_underlyings:
            all_underlyings.append(standard_idx)

    index_comparison = {}
    for und in all_underlyings:
        und_trades = [a for a in accountings if a.trade.underlying == und]
        index_comparison[und] = engine.compute_summary_kpis(und_trades).to_dict()

    # 2. Daily breakdown table
    daily_groups: Dict[str, List[Any]] = defaultdict(list)
    for a in accountings:
        day_str = a.trade.entry_time[:10] if a.trade.entry_time else "UNKNOWN"
        daily_groups[day_str].append(a)

    daily_breakdown = []
    for day in sorted(daily_groups.keys()):
        day_accs = daily_groups[day]
        day_kpis = engine.compute_summary_kpis(day_accs)
        daily_breakdown.append({
            "date": day,
            "total_trades": day_kpis.total_trades,
            "completed_trades": day_kpis.completed_trades,
            "winning_trades": day_kpis.winning_trades,
            "losing_trades": day_kpis.losing_trades,
            "win_rate_pct": day_kpis.win_rate_pct,
            "gross_pnl_rupees": day_kpis.gross_pnl_rupees,
            "net_pnl_rupees": day_kpis.net_pnl_rupees,
            "total_frictional_costs": day_kpis.total_frictional_costs,
            "profit_factor": day_kpis.profit_factor,
        })

    # 3. Regime Attribution (Gear 1 Chop vs Gear 2 Trend)
    gear1_accs = [a for a in accountings if "GEAR_1" in a.point_in_time_gear]
    gear2_accs = [a for a in accountings if "GEAR_2" in a.point_in_time_gear]
    regime_attribution = {
        "gear_1_range": engine.compute_summary_kpis(gear1_accs).to_dict(),
        "gear_2_trend": engine.compute_summary_kpis(gear2_accs).to_dict(),
    }

    # 4. Root-cause taxonomy aggregation
    root_cause_counts: Dict[str, int] = defaultdict(int)
    root_cause_pnl: Dict[str, float] = defaultdict(float)
    for a in accountings:
        if not a.trade.is_in_flight:
            root_cause_counts[a.root_cause] += 1
            root_cause_pnl[a.root_cause] += a.net_pnl_rupees

    root_cause_summary = {
        rc: {
            "count": root_cause_counts[rc],
            "total_net_pnl_rupees": round(root_cause_pnl[rc], 2),
            "pct_of_trades": round(root_cause_counts[rc] / max(1, kpis.completed_trades) * 100.0, 1),
        }
        for rc in sorted(root_cause_counts.keys())
    }

    # 5. Counterfactual Analysis: Actual vs Current Logic (Anti-Chop & Wall Gate Filtered)
    clean_accountings = [a for a in accountings if a.root_cause != "Chop Drag"]
    clean_kpis = engine.compute_summary_kpis(clean_accountings)
    clean_bootstraps = engine.bootstrap_confidence_intervals(clean_accountings, n_resamples=bootstrap_resamples)

    # Counterfactual breakdowns per index
    clean_index_comparison: Dict[str, Any] = {}
    for idx in all_underlyings:
        idx_clean = [a for a in clean_accountings if a.trade.underlying == idx]
        clean_index_comparison[idx] = engine.compute_summary_kpis(idx_clean).to_dict()

    counterfactual_analysis = {
        "description": "Counterfactual evaluation simulating elimination of adverse Chop Drag entries via current anti-chop supervisory gates.",
        "actual_baseline": {
            "total_trades": kpis.total_trades,
            "win_rate_pct": kpis.win_rate_pct,
            "net_pnl_rupees": kpis.net_pnl_rupees,
            "profit_factor": kpis.profit_factor,
            "total_frictional_costs": kpis.total_frictional_costs,
        },
        "filtered_current_logic": {
            "total_trades": clean_kpis.total_trades,
            "chop_trades_eliminated": len(accountings) - len(clean_accountings),
            "win_rate_pct": clean_kpis.win_rate_pct,
            "net_pnl_rupees": clean_kpis.net_pnl_rupees,
            "profit_factor": clean_kpis.profit_factor,
            "total_frictional_costs": clean_kpis.total_frictional_costs,
            "net_pnl_improvement_rupees": round(clean_kpis.net_pnl_rupees - kpis.net_pnl_rupees, 2),
            "win_rate_improvement_pct": round(clean_kpis.win_rate_pct - kpis.win_rate_pct, 2),
        },
        "index_breakdown": clean_index_comparison,
        "bootstrap_edge_significance": {k: v.to_dict() for k, v in clean_bootstraps.items()},
    }

    report = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "period_start": start_date,
            "period_end": effective_end_date,
            "status": "NO_CERTIFIED_EDGE",
            "safety": {
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            },
        },
        "continuity_audit": continuity_audit.to_dict(),
        "summary_kpis": kpis.to_dict(),
        "bootstrap_edge_significance": {k: v.to_dict() for k, v in bootstraps.items()},
        "index_comparison": index_comparison,
        "regime_attribution": regime_attribution,
        "root_cause_taxonomy": root_cause_summary,
        "counterfactual_analysis": counterfactual_analysis,
        "daily_breakdown": daily_breakdown,
        "trades": [a.to_dict() for a in accountings],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("Saved multi-session analytics report to: %s", OUTPUT_PATH)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel Multi-Session Quant Analytics Runner")
    parser.add_argument("--start-date", default="2026-10-07", help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="End date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--audit-dir", default="runtime/audit", help="Audit directory")
    parser.add_argument("--wal-path", default=None, help="WAL path (or None for canonical multi-WALs)")
    parser.add_argument("--resamples", type=int, default=2000, help="Number of bootstrap resamples")
    args = parser.parse_args()

    generate_multi_session_report(
        start_date=args.start_date,
        end_date=args.end_date,
        audit_dir=args.audit_dir,
        wal_path=args.wal_path,
        bootstrap_resamples=args.resamples,
    )


if __name__ == "__main__":
    main()
