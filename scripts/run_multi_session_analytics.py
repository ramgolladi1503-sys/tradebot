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
    end_date: str = "2026-10-19",
    audit_dir: str = "runtime/audit",
    wal_path: str = "runtime/sentinel_apm_wal.json",
    bootstrap_resamples: int = 2000,
) -> Dict[str, Any]:
    aggregator = MultiSessionAggregator(
        audit_dir=audit_dir,
        wal_path=wal_path,
        start_date=start_date,
        end_date=end_date,
    )

    logger.info("Running Session Continuity Audit (%s to %s)...", start_date, end_date)
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

    # 1. Index-level breakdowns (NIFTY vs SENSEX)
    nifty_trades = [a for a in accountings if a.trade.underlying == "NIFTY"]
    sensex_trades = [a for a in accountings if a.trade.underlying == "SENSEX"]
    nifty_kpis = engine.compute_summary_kpis(nifty_trades)
    sensex_kpis = engine.compute_summary_kpis(sensex_trades)

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

    report = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "period_start": start_date,
            "period_end": end_date,
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
        "index_comparison": {
            "NIFTY": nifty_kpis.to_dict(),
            "SENSEX": sensex_kpis.to_dict(),
        },
        "regime_attribution": regime_attribution,
        "root_cause_taxonomy": root_cause_summary,
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
    parser.add_argument("--end-date", default="2026-10-19", help="End date YYYY-MM-DD")
    parser.add_argument("--audit-dir", default="runtime/audit", help="Audit directory")
    parser.add_argument("--wal-path", default="runtime/sentinel_apm_wal.json", help="WAL path")
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
