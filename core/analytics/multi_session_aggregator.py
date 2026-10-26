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

    CANONICAL_WALS = {
        "NIFTY": Path("runtime/sentinel_apm_wal.json"),
        "SENSEX": Path("runtime/sentinel_apm_wal_sensex.json"),
        "BANKNIFTY": Path("runtime/sentinel_apm_wal_banknifty.json"),
    }

    def __init__(
        self,
        audit_dir: str | Path = "runtime/audit",
        wal_path: str | Path | Sequence[str | Path] | Dict[str, str | Path] | None = None,
        start_date: str = "2026-10-07",
        end_date: Optional[str] = None,
    ) -> None:
        self.audit_dir = Path(audit_dir)

        # Normalize wal_paths to Dict[str, Path]
        self.wal_paths: Dict[str, Path] = {}
        if wal_path is None:
            # Default to all existing canonical WALs
            for idx_name, p in self.CANONICAL_WALS.items():
                if p.exists():
                    self.wal_paths[idx_name] = p
            # If none exist, keep default NIFTY path for safety
            if not self.wal_paths:
                self.wal_paths["NIFTY"] = self.CANONICAL_WALS["NIFTY"]
        elif isinstance(wal_path, dict):
            for k, v in wal_path.items():
                self.wal_paths[str(k)] = Path(v)
        elif isinstance(wal_path, (list, tuple)):
            for i, p in enumerate(wal_path):
                p_path = Path(p)
                # Infer index name from filename
                name_upper = p_path.stem.upper()
                if "BANKNIFTY" in name_upper:
                    k = "BANKNIFTY"
                elif "SENSEX" in name_upper:
                    k = "SENSEX"
                else:
                    k = f"NIFTY_{i}" if "NIFTY" in self.wal_paths else "NIFTY"
                self.wal_paths[k] = p_path
        else:
            # Single path or str
            p_path = Path(wal_path)
            name_upper = p_path.stem.upper()
            if "BANKNIFTY" in name_upper:
                k = "BANKNIFTY"
            elif "SENSEX" in name_upper:
                k = "SENSEX"
            else:
                k = "NIFTY"
            self.wal_paths[k] = p_path

        # Preserve legacy self.wal_path referencing primary NIFTY wal or first wal
        if "NIFTY" in self.wal_paths:
            self.wal_path = self.wal_paths["NIFTY"]
        elif self.wal_paths:
            self.wal_path = next(iter(self.wal_paths.values()))
        else:
            self.wal_path = Path("runtime/sentinel_apm_wal.json")

        self.start_date = start_date
        # Dynamic auto-date detection for end_date defaulting to current session date
        self.end_date = end_date or date.today().isoformat()

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

    def _detect_underlying(self, symbol: str, raw_payload: Optional[Dict[str, Any]] = None) -> str:
        """Resolve underlying index with BANKNIFTY evaluated before NIFTY."""
        # Check payload fields first if present
        if raw_payload:
            for field_name in ("underlying", "contract", "opt_symbol", "strike_contract", "symbol"):
                val = str(raw_payload.get(field_name, "")).upper()
                if "BANKNIFTY" in val:
                    return "BANKNIFTY"
                if "SENSEX" in val:
                    return "SENSEX"
                if "NIFTY" in val:
                    return "NIFTY"
            if "spot_nifty" in raw_payload:
                return "NIFTY"

        # Check symbol string directly
        s = (symbol or "").upper()
        if "BANKNIFTY" in s:
            return "BANKNIFTY"
        if "SENSEX" in s:
            return "SENSEX"
        if "NIFTY" in s:
            return "NIFTY"
        return "NIFTY"

    def run_continuity_audit(self) -> Tuple[SessionContinuityAudit, Dict[str, List[Dict[str, Any]]]]:
        """Audit multi-session data continuity fail-closed.
        
        Reads JSONL files, detects corrupted lines, identifies missing calendar days,
        and flags intraday timeline gaps > MAX_INTER_BAR_GAP_SECONDS partitioned per underlying index.
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

                # Check intraday continuity gaps partitioned per underlying index
                records_by_idx: Dict[str, List[Tuple[datetime, Dict[str, Any]]]] = {}
                for r in day_records:
                    ts_str = r.get("timestamp")
                    if ts_str:
                        try:
                            dt = datetime.fromisoformat(ts_str)
                            rec_und = self._detect_underlying(r.get("opt_symbol") or r.get("contract") or "", r)
                            records_by_idx.setdefault(rec_und, []).append((dt, r))
                        except Exception:
                            pass

                for rec_und, sorted_records in records_by_idx.items():
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
                                        f"[{rec_und}] Telemetry gap of {delta_sec/60:.1f}m between "
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
        """Extract all completed and in-flight trade lifecycles from all configured WALs.
        
        Handles both completed trades in 'trade_history' and in-flight positions in 'payload'.
        Deduplicates trades across WALs using composite key:
        (underlying, strike_contract, direction, entry_time, position_id).
        """
        trades: List[NormalizedTrade] = []
        seen_keys: Set[Tuple[str, str, str, str, str]] = set()

        for wal_label, current_wal_path in self.wal_paths.items():
            if not current_wal_path.exists():
                logger.warning("WAL path does not exist for %s: %s", wal_label, current_wal_path)
                continue

            try:
                with open(current_wal_path, "r", encoding="utf-8") as f:
                    wal = json.load(f)
            except Exception as e:
                logger.error("Failed to read WAL %s (%s): %s", wal_label, current_wal_path, e)
                continue

            wal_state = wal.get("state", "STANDBY")
            trade_history = wal.get("trade_history", [])

            for t in trade_history:
                pos_id = str(t.get("position_id") or "UNKNOWN")
                symbol = t.get("opt_symbol") or t.get("strike_contract") or "UNKNOWN"
                underlying = self._detect_underlying(symbol, t)
                direction = t.get("direction", "CE" if "CE" in symbol.upper() else "PE")
                strike_contract = t.get("strike_contract", symbol)
                entry_time = str(t.get("entry_time", ""))

                composite_key = (underlying, strike_contract, direction, entry_time, pos_id)
                if composite_key in seen_keys:
                    continue
                seen_keys.add(composite_key)

                norm = NormalizedTrade(
                    position_id=pos_id,
                    symbol=symbol,
                    underlying=underlying,
                    direction=direction,
                    strike_contract=strike_contract,
                    entry_time=entry_time,
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
                pos_id = str(p.get("position_id") or "IN_FLIGHT")
                symbol = p.get("opt_symbol") or p.get("strike_contract") or "UNKNOWN"
                underlying = self._detect_underlying(symbol, p)
                direction = p.get("direction", "CE" if "CE" in symbol.upper() else "PE")
                strike_contract = p.get("strike_contract", symbol)
                entry_time = str(p.get("entry_time", ""))

                composite_key = (underlying, strike_contract, direction, entry_time, pos_id)
                if composite_key in seen_keys:
                    continue
                seen_keys.add(composite_key)

                in_flight_norm = NormalizedTrade(
                    position_id=pos_id,
                    symbol=symbol,
                    underlying=underlying,
                    direction=direction,
                    strike_contract=strike_contract,
                    entry_time=entry_time,
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
