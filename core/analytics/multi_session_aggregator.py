"""Sentinel Multi-Session Aggregator.

Ingests historical audit traces, parquet archives, and Sentinel APM WAL records
across multi-session periods (e.g. 2026-10-07 to 2026-10-19) for NIFTY and SENSEX.
Implements fail-closed SessionContinuityAudit detecting missing days, data gaps,
and corrupted files.

Trading Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
- status = "NO_CERTIFIED_EDGE"
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)

# Expected calendar trading days between 2026-10-07 and 2026-10-19 (excluding weekends)
# 2026-10-07: Wednesday
# 2026-10-08: Thursday
# 2026-10-09: Friday
# 2026-10-10: Saturday (Weekend)
# 2026-10-11: Sunday (Weekend)
# 2026-10-12: Monday
# 2026-10-13: Tuesday
# 2026-10-14: Wednesday
# 2026-10-15: Thursday
# 2026-10-16: Friday
# 2026-10-17: Saturday (Weekend)
# 2026-10-18: Sunday (Weekend)
# 2026-10-19: Monday

STANDARD_TRADING_HOURS_START = "09:15:00"
STANDARD_TRADING_HOURS_END = "15:30:00"
MAX_INTER_BAR_GAP_SECONDS = 300  # 5 minutes gap threshold during active session


@dataclass(frozen=True)
class SessionContinuityIssue:
    issue_type: str  # "MISSING_SESSION_DAY", "INTRADAY_DATA_GAP", "CORRUPTED_RECORD", "UNRESOLVED_RECONCILIATION"
    date_str: str
    description: str
    severity: str  # "BLOCKER", "WARNING"


@dataclass
class SessionContinuityAudit:
    expected_dates: List[str]
    present_dates: List[str]
    missing_dates: List[str]
    issues: List[SessionContinuityIssue] = field(default_factory=list)
    is_continuous: bool = True
    gap_count: int = 0
    corrupt_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expected_dates": self.expected_dates,
            "present_dates": self.present_dates,
            "missing_dates": self.missing_dates,
            "issues": [asdict(i) for i in self.issues],
            "is_continuous": self.is_continuous,
            "gap_count": self.gap_count,
            "corrupt_count": self.corrupt_count,
        }


@dataclass
class NormalizedTrade:
    position_id: str
    symbol: str
    underlying: str  # "NIFTY" or "SENSEX"
    direction: str  # "CE" or "PE"
    strike_contract: str
    entry_time: str
    exit_time: Optional[str]
    entry_price: float
    exit_price: Optional[float]
    pnl_pts: Optional[float]
    opt_entry_ltp: Optional[float]
    opt_exit_ltp: Optional[float]
    opt_pnl_pts: Optional[float]
    opt_peak_hwm: Optional[float]
    exit_reason: Optional[str]
    session_gear: str  # "GEAR_1_RANGE" or "GEAR_2_TREND"
    is_in_flight: bool = False
    opt_bid: Optional[float] = None
    opt_ask: Optional[float] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MultiSessionAggregator:
    """Aggregates Sentinel execution telemetry across multiple historical sessions."""

    def __init__(
        self,
        audit_dir: str | Path = "runtime/audit",
        wal_path: str | Path = "runtime/sentinel_apm_wal.json",
        start_date: str = "2026-10-07",
        end_date: str = "2026-10-19",
    ) -> None:
        self.audit_dir = Path(audit_dir)
        self.wal_path = Path(wal_path)
        self.start_date = start_date
        self.end_date = end_date

    def get_expected_trading_days(self) -> List[str]:
        """Generate weekday date strings (YYYY-MM-DD) between start_date and end_date inclusive."""
        cur = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        stop = datetime.strptime(self.end_date, "%Y-%m-%d").date()
        expected = []
        while cur <= stop:
            # Monday=0, Sunday=6. Weekday is 0-4
            if cur.weekday() < 5:
                expected.append(cur.isoformat())
            cur += timedelta(days=1)
        return expected

    def run_continuity_audit(self) -> Tuple[SessionContinuityAudit, Dict[str, List[Dict[str, Any]]]]:
        """Audit multi-session data continuity fail-closed.
        
        Reads JSONL files, detects corrupted lines, identifies missing calendar days,
        and flags intraday timeline gaps > MAX_INTER_BAR_GAP_SECONDS.
        """
        expected_days = self.get_expected_trading_days()
        present_days_set: Set[str] = set()
        issues: List[SessionContinuityIssue] = []
        parsed_records_by_day: Dict[str, List[Dict[str, Any]]] = {}
        corrupt_count = 0
        gap_count = 0

        # Scan audit files
        audit_files = sorted(self.audit_dir.glob("sentinel_execution_paths_*.jsonl"))
        for fpath in audit_files:
            # Extract date from name e.g. sentinel_execution_paths_20261008.jsonl
            stem = fpath.stem.replace("sentinel_execution_paths_", "")
            if len(stem) == 8 and stem.isdigit():
                day_iso = f"{stem[:4]}-{stem[4:6]}-{stem[6:8]}"
            else:
                day_iso = stem

            day_records: List[Dict[str, Any]] = []
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, 1):
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            rec = json.loads(line_str)
                            day_records.append(rec)
                        except Exception as e:
                            corrupt_count += 1
                            issues.append(
                                SessionContinuityIssue(
                                    issue_type="CORRUPTED_RECORD",
                                    date_str=day_iso,
                                    description=f"Malformed JSON in {fpath.name} line {line_no}: {e}",
                                    severity="BLOCKER",
                                )
                            )
            except Exception as e:
                corrupt_count += 1
                issues.append(
                    SessionContinuityIssue(
                        issue_type="CORRUPTED_RECORD",
                        date_str=day_iso,
                        description=f"Cannot read file {fpath.name}: {e}",
                        severity="BLOCKER",
                    )
                )

            if day_records:
                present_days_set.add(day_iso)
                parsed_records_by_day[day_iso] = day_records

                # Check intraday continuity gaps
                sorted_records = []
                for r in day_records:
                    ts_str = r.get("timestamp")
                    if ts_str:
                        try:
                            dt = datetime.fromisoformat(ts_str)
                            sorted_records.append((dt, r))
                        except Exception:
                            pass
                sorted_records.sort(key=lambda x: x[0])

                for i in range(len(sorted_records) - 1):
                    dt_curr, _ = sorted_records[i]
                    dt_next, _ = sorted_records[i + 1]
                    delta_sec = (dt_next - dt_curr).total_seconds()
                    if delta_sec > MAX_INTER_BAR_GAP_SECONDS:
                        gap_count += 1
                        issues.append(
                            SessionContinuityIssue(
                                issue_type="INTRADAY_DATA_GAP",
                                date_str=day_iso,
                                description=(
                                    f"Telemetry gap of {delta_sec/60:.1f}m between "
                                    f"{dt_curr.time()} and {dt_next.time()}"
                                ),
                                severity="WARNING",
                            )
                        )

        # Check for missing calendar trading days
        missing_days = [d for d in expected_days if d not in present_days_set]
        for m_day in missing_days:
            # 2026-10-12 or 2026-10-16 might be missing or trading holiday, flag fail-closed
            issues.append(
                SessionContinuityIssue(
                    issue_type="MISSING_SESSION_DAY",
                    date_str=m_day,
                    description=f"Expected trading session date {m_day} has no execution telemetry audit archive",
                    severity="BLOCKER",
                )
            )

        # Check reconciliation records in runtime directory
        reconciliation_files = list(Path("runtime").glob("sentinel_apm_wal_reconciliation_*.json"))
        for rf in reconciliation_files:
            try:
                rec_data = json.loads(rf.read_text(encoding="utf-8"))
                if rec_data.get("trade_outcome") == "UNKNOWN_NOT_RECONSTRUCTED":
                    issues.append(
                        SessionContinuityIssue(
                            issue_type="UNRESOLVED_RECONCILIATION",
                            date_str=rf.stem.replace("sentinel_apm_wal_reconciliation_", ""),
                            description=(
                                f"Audit reconciliation file {rf.name} has UNKNOWN_NOT_RECONSTRUCTED "
                                f"disposition ({rec_data.get('reason')})"
                            ),
                            severity="WARNING",
                        )
                    )
            except Exception:
                pass

        is_continuous = len(missing_days) == 0 and corrupt_count == 0
        audit = SessionContinuityAudit(
            expected_dates=expected_days,
            present_dates=sorted(list(present_days_set)),
            missing_dates=missing_days,
            issues=issues,
            is_continuous=is_continuous,
            gap_count=gap_count,
            corrupt_count=corrupt_count,
        )
        return audit, parsed_records_by_day

    def extract_trades(self) -> List[NormalizedTrade]:
        """Extract all completed and in-flight trade lifecycles from sentinel_apm_wal.json.
        
        Handles both completed trades in 'trade_history' and in-flight positions in 'payload'.
        """
        trades: List[NormalizedTrade] = []
        if not self.wal_path.exists():
            logger.warning("WAL path does not exist: %s", self.wal_path)
            return trades

        with open(self.wal_path, "r", encoding="utf-8") as f:
            wal = json.load(f)

        wal_state = wal.get("state", "STANDBY")
        trade_history = wal.get("trade_history", [])

        for t in trade_history:
            pos_id = t.get("position_id", "UNKNOWN")
            symbol = t.get("opt_symbol") or t.get("strike_contract", "UNKNOWN")
            underlying = "SENSEX" if "SENSEX" in symbol.upper() else "NIFTY"
            direction = t.get("direction", "CE" if "CE" in symbol.upper() else "PE")

            norm = NormalizedTrade(
                position_id=pos_id,
                symbol=symbol,
                underlying=underlying,
                direction=direction,
                strike_contract=t.get("strike_contract", symbol),
                entry_time=str(t.get("entry_time", "")),
                exit_time=str(t.get("exit_time", "")) if t.get("exit_time") else None,
                entry_price=float(t.get("entry_price", 0.0) or 0.0),
                exit_price=float(t.get("exit_price", 0.0)) if t.get("exit_price") is not None else None,
                pnl_pts=float(t.get("pnl_pts")) if t.get("pnl_pts") is not None else None,
                opt_entry_ltp=float(t.get("opt_entry_ltp")) if t.get("opt_entry_ltp") is not None else None,
                opt_exit_ltp=float(t.get("opt_exit_ltp")) if t.get("opt_exit_ltp") is not None else None,
                opt_pnl_pts=float(t.get("opt_pnl_pts")) if t.get("opt_pnl_pts") is not None else None,
                opt_peak_hwm=float(t.get("opt_peak_hwm")) if t.get("opt_peak_hwm") is not None else None,
                exit_reason=t.get("exit_reason"),
                session_gear=t.get("session_gear", "GEAR_2_TREND"),
                is_in_flight=False,
                opt_bid=float(t.get("opt_bid")) if t.get("opt_bid") is not None else None,
                opt_ask=float(t.get("opt_ask")) if t.get("opt_ask") is not None else None,
                raw_payload=t,
            )
            trades.append(norm)

        # In-flight trade extraction
        if wal_state in ("IN_FLIGHT", "TRAIL_LOCK") and wal.get("payload"):
            p = wal["payload"]
            pos_id = p.get("position_id", "IN_FLIGHT")
            symbol = p.get("opt_symbol") or p.get("strike_contract", "UNKNOWN")
            underlying = "SENSEX" if "SENSEX" in symbol.upper() else "NIFTY"
            direction = p.get("direction", "CE" if "CE" in symbol.upper() else "PE")

            in_flight_norm = NormalizedTrade(
                position_id=pos_id,
                symbol=symbol,
                underlying=underlying,
                direction=direction,
                strike_contract=p.get("strike_contract", symbol),
                entry_time=str(p.get("entry_time", "")),
                exit_time=None,
                entry_price=float(p.get("entry_price", 0.0) or 0.0),
                exit_price=None,
                pnl_pts=None,
                opt_entry_ltp=float(p.get("opt_entry_ltp")) if p.get("opt_entry_ltp") is not None else None,
                opt_exit_ltp=float(p.get("opt_current_ltp")) if p.get("opt_current_ltp") is not None else None,
                opt_pnl_pts=(
                    float(p["opt_current_ltp"]) - float(p["opt_entry_ltp"])
                    if p.get("opt_current_ltp") is not None and p.get("opt_entry_ltp") is not None
                    else None
                ),
                opt_peak_hwm=float(p.get("opt_peak_hwm")) if p.get("opt_peak_hwm") is not None else None,
                exit_reason="IN_FLIGHT",
                session_gear=p.get("session_gear", "GEAR_2_TREND"),
                is_in_flight=True,
                opt_bid=float(p.get("opt_bid")) if p.get("opt_bid") is not None else None,
                opt_ask=float(p.get("opt_ask")) if p.get("opt_ask") is not None else None,
                raw_payload=p,
            )
            trades.append(in_flight_norm)

        return trades
