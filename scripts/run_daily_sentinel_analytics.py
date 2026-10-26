"""Daily Sentinel Quant Analytics Runner.

Implements Gate 5 (Pillar 1: scripts/run_daily_sentinel_analytics.py):
- Executes at 15:40 IST (or on demand) post market close.
- Ingestion of multi-WALs (NIFTY, SENSEX, BANKNIFTY).
- Applies 15:15 RMS auto-square-off cap on counterfactual holding periods:
  Retail brokers forcibly liquidate open MIS intraday options between 15:15 and 15:20 IST.
  Trades with exit_time > 15:15:00 or MARKET_CLOSE_AUTO_SQUAREOFF are capped at 15:15 IST.
- Tracks rolling 100 trades performance pooled and per-index.
- Generates executive daily report in Markdown and structured JSON.
- Enforces calendar validation (rejects weekends and exchange holidays).

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.analytics.multi_session_aggregator import MultiSessionAggregator, NormalizedTrade
from core.analytics.quant_metrics_engine import QuantMetricsEngine, SummaryQuantKPIs, TradeAccounting
from core.market_calendar import _is_nse_fno_holiday

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_daily_sentinel_analytics")

DEFAULT_REPORT_MD_PATH = Path("docs/reports/SENTINEL_DAILY_TRADE_REPORT_LATEST.md")
DEFAULT_REPORT_JSON_PATH = Path("reports/research/sentinel_daily_analytics_latest.json")


def is_market_trading_day(target_date: date) -> Tuple[bool, str]:
    """Validate trading day according to NSE calendar."""
    if target_date.weekday() >= 5:
        return False, "MARKET_CLOSED_WEEKEND"
    if _is_nse_fno_holiday(target_date):
        return False, "MARKET_CLOSED_HOLIDAY"
    return True, "TRADING_SESSION"


def apply_1515_rms_square_off_cap(trades: Sequence[NormalizedTrade]) -> List[NormalizedTrade]:
    """Invariant 5.2 (Broker RMS 15:15 Auto-Square-Off Realism):
    
    Caps counterfactual holding periods and exit times at 15:15:00 IST.
    If a trade exited post-15:15:00 or via MARKET_CLOSE_AUTO_SQUAREOFF,
    adjusts exit_time to 15:15:00 and annotates root_cause / exit_reason.
    """
    adjusted_trades: List[NormalizedTrade] = []
    for t in trades:
        exit_t_str = t.exit_time or ""
        # Check if exit is post 15:15:00
        time_part = exit_t_str
        if "T" in exit_t_str:
            time_part = exit_t_str.split("T", 1)[1][:8]
        elif len(exit_t_str) >= 8:
            time_part = exit_t_str[:8]

        is_post_1515 = False
        if time_part and len(time_part) >= 5:
            try:
                parts = [int(p) for p in time_part.split(":")[:2]]
                if (parts[0] > 15) or (parts[0] == 15 and parts[1] > 15):
                    is_post_1515 = True
            except Exception:
                pass

        if is_post_1515 or t.exit_reason == "MARKET_CLOSE_AUTO_SQUAREOFF":
            # Cap exit time at 15:15:00
            new_exit_time = "15:15:00" if "T" not in exit_t_str else (exit_t_str.split("T")[0] + "T15:15:00")
            adj = NormalizedTrade(
                position_id=t.position_id,
                symbol=t.symbol,
                underlying=t.underlying,
                direction=t.direction,
                strike_contract=t.strike_contract,
                entry_time=t.entry_time,
                exit_time=new_exit_time,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                pnl_pts=t.pnl_pts,
                opt_entry_ltp=t.opt_entry_ltp,
                opt_exit_ltp=t.opt_exit_ltp,
                opt_pnl_pts=t.opt_pnl_pts,
                opt_peak_hwm=t.opt_peak_hwm,
                exit_reason="BROKER_1515_RMS_SQUAREOFF",
                session_gear=t.session_gear,
                is_in_flight=t.is_in_flight,
                opt_bid=t.opt_bid,
                opt_ask=t.opt_ask,
                raw_payload=t.raw_payload,
            )
            adjusted_trades.append(adj)
        else:
            adjusted_trades.append(t)
    return adjusted_trades


def compute_rolling_metrics(
    accountings: Sequence[TradeAccounting],
    window: int = 100
) -> Dict[str, Any]:
    """Invariant 5.3: Compute rolling trailing performance across rolling window trades.
    
    Includes:
    - Pooled portfolio-level (All indices combined)
    - Per-index isolated slices (NIFTY, BANKNIFTY, SENSEX)
    """
    engine = QuantMetricsEngine()
    
    # Trailing window trades (sorted by entry_time)
    sorted_accs = sorted(accountings, key=lambda a: a.trade.entry_time or "")
    rolling_pooled = sorted_accs[-window:] if len(sorted_accs) > window else sorted_accs
    pooled_kpis = engine.compute_summary_kpis(rolling_pooled)

    # Per index slices
    by_index: Dict[str, List[TradeAccounting]] = defaultdict(list)
    for a in sorted_accs:
        by_index[a.trade.underlying].append(a)

    index_slices: Dict[str, Any] = {}
    for idx_name in ("NIFTY", "BANKNIFTY", "SENSEX"):
        idx_trades = by_index.get(idx_name, [])
        idx_rolling = idx_trades[-window:] if len(idx_trades) > window else idx_trades
        index_slices[idx_name] = {
            "window_size": len(idx_rolling),
            "kpis": engine.compute_summary_kpis(idx_rolling).to_dict(),
        }

    return {
        "window_target": window,
        "pooled": {
            "sample_size": len(rolling_pooled),
            "kpis": pooled_kpis.to_dict(),
        },
        "per_index": index_slices,
    }


def generate_executive_markdown(
    target_date: str,
    today_kpis: SummaryQuantKPIs,
    rolling_100: Dict[str, Any],
    today_trades: Sequence[TradeAccounting],
) -> str:
    """Formats executive daily summary in GitHub Markdown."""
    lines = [
        f"# Sentinel Daily Trade Summary & EOD Ledger: {target_date}",
        "",
        f"**Session Date**: {target_date}  ",
        "**Execution Status**: COMPLETED (15:40 IST Daily Analytics)  ",
        f"**Daily Executed Trades**: {today_kpis.total_trades}  ",
        f"**Daily Win Rate**: {today_kpis.win_rate_pct:.1f}%  ",
        f"**Daily Net PnL**: ₹{today_kpis.net_pnl_rupees:+,.2f}  ",
        f"**Total Frictional Costs**: ₹{today_kpis.total_frictional_costs:,.2f}  ",
        "",
        "---",
        "",
        "## 1. Today's Trade Execution Log (15:15 RMS Realism Cap Applied)",
        "",
        "| # | Position ID | Index | Strike Contract | Dir | Entry Time | Entry LTP | Exit Time | Exit LTP | Opt PnL | Net PnL (₹) | Exit Reason |",
        "|:---:|:---|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|",
    ]

    for i, a in enumerate(today_trades, 1):
        t = a.trade
        opt_pnl_str = f"{a.trade.opt_pnl_pts:+.2f} pts" if a.trade.opt_pnl_pts is not None else "N/A"
        entry_ltp_str = f"₹{t.opt_entry_ltp:.2f}" if t.opt_entry_ltp else "N/A"
        exit_ltp_str = f"₹{t.opt_exit_ltp:.2f}" if t.opt_exit_ltp else "N/A"
        entry_t_str = t.entry_time[11:19] if "T" in t.entry_time else t.entry_time
        exit_t_str = str(t.exit_time)[11:19] if "T" in str(t.exit_time) else str(t.exit_time or "N/A")

        lines.append(
            f"| **{i}** | `{t.position_id}` | {t.underlying} | {t.strike_contract} | **{t.direction}** | "
            f"{entry_t_str} | {entry_ltp_str} | {exit_t_str} | {exit_ltp_str} | "
            f"**{opt_pnl_str}** | **₹{a.net_pnl_rupees:+,.2f}** | `{t.exit_reason}` |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Rolling 100 Trades Performance Tracking (Pillar 1)",
        "",
        f"- **Pooled Trades Analyzed**: {rolling_100['pooled']['sample_size']}",
        f"- **Pooled Win Rate**: {rolling_100['pooled']['kpis']['win_rate_pct']:.1f}%",
        f"- **Pooled Profit Factor**: {rolling_100['pooled']['kpis']['profit_factor']:.2f}",
        f"- **Pooled Net PnL**: ₹{rolling_100['pooled']['kpis']['net_pnl_rupees']:+,.2f}",
        f"- **Pooled Expectancy / Trade**: ₹{rolling_100['pooled']['kpis']['expectancy_rupees']:+,.2f}",
        f"- **Pooled Max Drawdown**: ₹{rolling_100['pooled']['kpis']['max_drawdown_rupees']:,.2f}",
        "",
        "### Per-Index Rolling 100 Breakdown",
        "",
        "| Index | Trades In Window | Win Rate (%) | Net PnL (₹) | Profit Factor | Expectancy (₹) |",
        "|:---|:---:|:---:|:---:|:---:|:---:|",
    ])

    for idx, data in rolling_100["per_index"].items():
        k = data["kpis"]
        lines.append(
            f"| **{idx}** | {data['window_size']} | {k['win_rate_pct']:.1f}% | "
            f"₹{k['net_pnl_rupees']:+,.2f} | {k['profit_factor']:.2f} | ₹{k['expectancy_rupees']:+,.2f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Production Safety Attestations",
        "- `read_only = true`",
        "- `is_order_action = false`",
        "- `broker_api_called = false`",
        "- `allowed_for_live_execution = false`",
        "- `broker_1515_rms_capped = true`",
    ])
    return "\n".join(lines)


def run_daily_sentinel_analytics(
    target_date: Optional[str] = None,
    audit_dir: str = "runtime/audit",
    wal_path: Any = None,
    output_md: Optional[Path] = None,
    output_json: Optional[Path] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Execute daily sentinel analytics routine."""
    target_d = (
        datetime.strptime(target_date, "%Y-%m-%d").date()
        if target_date
        else date.today()
    )
    target_date_str = target_d.isoformat()

    # Calendar validation gate
    is_trading, cal_reason = is_market_trading_day(target_d)
    if not is_trading and not force:
        logger.warning("Session %s is not an active trading day: %s. Exiting cleanly.", target_date_str, cal_reason)
        return {
            "status": cal_reason,
            "session_date": target_date_str,
            "is_trading_day": False,
        }

    logger.info("Executing Daily Sentinel Analytics for session %s...", target_date_str)

    aggregator = MultiSessionAggregator(
        audit_dir=audit_dir,
        wal_path=wal_path,
        start_date="2026-10-07",
        end_date=target_date_str,
    )

    raw_trades = aggregator.extract_trades()
    logger.info("Extracted %d total raw trades across multi-WALs.", len(raw_trades))

    # Apply 15:15 RMS auto-square-off cap
    capped_trades = apply_1515_rms_square_off_cap(raw_trades)

    engine = QuantMetricsEngine()
    all_accountings = engine.process_trades(capped_trades)

    # Filter trades belonging to target_date
    today_accountings = [
        a for a in all_accountings
        if (a.trade.entry_time and a.trade.entry_time.startswith(target_date_str))
    ]
    today_kpis = engine.compute_summary_kpis(today_accountings)

    # Compute rolling 100 trades metrics (pooled and per-index)
    rolling_100 = compute_rolling_metrics(all_accountings, window=100)

    # Generate executive reports
    md_content = generate_executive_markdown(
        target_date=target_date_str,
        today_kpis=today_kpis,
        rolling_100=rolling_100,
        today_trades=today_accountings,
    )

    json_report = {
        "metadata": {
            "session_date": target_date_str,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "calendar_status": cal_reason,
            "safety": {
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
                "broker_1515_rms_capped": True,
            },
        },
        "daily_summary": {
            "total_trades": today_kpis.total_trades,
            "win_rate_pct": today_kpis.win_rate_pct,
            "net_pnl_rupees": today_kpis.net_pnl_rupees,
            "total_frictional_costs": today_kpis.total_frictional_costs,
            "profit_factor": today_kpis.profit_factor,
            "trades": [a.to_dict() for a in today_accountings],
        },
        "rolling_100_trades": rolling_100,
    }

    # Persist reports
    md_path = output_md or DEFAULT_REPORT_MD_PATH
    json_path = output_json or DEFAULT_REPORT_JSON_PATH

    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info("Saved Daily Markdown Report to: %s", md_path)

    # Also persist session-dated report (e.g. docs/reports/SENTINEL_DAILY_TRADE_REPORT_YYYYMMDD.md)
    dated_md = md_path.parent / f"SENTINEL_DAILY_TRADE_REPORT_{target_date_str.replace('-', '')}.md"
    with open(dated_md, "w", encoding="utf-8") as f:
        f.write(md_content)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, indent=2)
    logger.info("Saved Daily JSON Report to: %s", json_path)

    return json_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Sentinel Quant Analytics Runner")
    parser.add_argument("--date", default=None, help="Session date YYYY-MM-DD (defaults to today)")
    parser.add_argument("--audit-dir", default="runtime/audit", help="Audit directory")
    parser.add_argument("--wal-path", default=None, help="WAL path (or None for multi-WALs)")
    parser.add_argument("--force", action="store_true", help="Force run even on weekends/holidays")
    args = parser.parse_args()

    run_daily_sentinel_analytics(
        target_date=args.date,
        audit_dir=args.audit_dir,
        wal_path=args.wal_path,
        force=args.force,
    )


if __name__ == "__main__":
    main()
