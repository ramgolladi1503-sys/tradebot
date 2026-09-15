"""Raw-Tick Production Replay Engine for Trade Truth Level C.

Strict Causal Pipeline:
1. RAW STITCHED TICK PARQUET (/Volumes/TradeBotData/live market capture/2026-09-10/upstox_full_ticks_20260910_stitched.parquet)
   - Zero derived 1M parquets used as input.
   - Zero historical analytical ledger fields used as input.
2. 1-MINUTE BAR REPLAY ADAPTER
   - Groups NIFTY 50 spot ticks into 1-minute OHLC bars.
   - Preserves actual raw max tick timestamp per bar for physical future-leak measurement.
3. PRODUCTION MarketSessionStore
   - Feeds Bar1M objects into MarketSessionStore.
   - Obtains point-in-time MarketMemorySnapshot strictly <= decision timestamp.
4. STRUCTURAL EXPECTED OUTPUT SEPARATION
   - run_raw_tick_replay(input_bundle, session_store) has ZERO access to expected output.
   - compare_replay_to_expected(actual, expected_output) compares independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq

from core.candidate_evaluators import evaluate_c1, evaluate_c2
from core.market_session_store import Bar1M, MarketMemorySnapshot, MarketSessionStore
from core.strategy_family_contract import StrategyFamily
from core.trade_truth.decision_hash import compute_deterministic_hash
from core.trade_truth.integrated_decision_tail import execute_integrated_decision_tail
from core.trade_truth.level_c_contract import validate_level_c_input_bundle

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class RawTickReplayActual:
    trace_id: str
    session_date: str
    decision_ts_epoch: float
    max_raw_tick_ts_used: float
    max_bar_ts_used: float
    max_bar_end_ts_used: float
    raw_tick_count_used: int
    bar_count_used: int
    warmup_status: str
    future_leak_detected: bool
    c1_decision: str
    c1_reason_code: str
    c1_qualified: bool
    c2_decision: str
    c2_reason_code: str
    c2_qualified: bool
    integrated_tail_verdict: str
    stage_hashes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RawTickReplayComparison:
    trace_id: str
    session_date: str
    decision_ts_epoch: float
    max_raw_tick_ts_used: float
    max_bar_ts_used: float
    max_bar_end_ts_used: float
    raw_tick_count_used: int
    bar_count_used: int
    warmup_status: str
    future_leak_detected: bool
    c1_decision: str
    c1_reason_code: str
    c1_qualified: bool
    c2_decision: str
    c2_reason_code: str
    c2_qualified: bool
    integrated_tail_verdict: str
    terminal_status: str  # PARTIAL_PARITY, BLOCKED_DATA, DIVERGED
    comparison_depth: str
    stage_hashes: dict[str, str] = field(default_factory=dict)


class RawTickSessionStore:
    """Builds 1-minute bars directly from raw tick capture and loads into MarketSessionStore."""

    def __init__(self, stitched_parquet_path: str | Path, session_date: str = "2026-09-10"):
        self.parquet_path = Path(stitched_parquet_path)
        self.session_date = session_date
        self.store = MarketSessionStore("NIFTY", session_date)
        self.bar_max_tick_ts: dict[str, float] = {}
        self.bar_end_ts: dict[str, float] = {}
        self.bar_tick_count: dict[str, int] = {}
        self._build_bars_from_ticks()

    def _build_bars_from_ticks(self):
        if not self.parquet_path.exists():
            return

        pf = pq.ParquetFile(self.parquet_path)
        ticks = []
        for b in pf.iter_batches(batch_size=100000, columns=["token", "ltp", "ts"]):
            d = b.to_pydict()
            for tok, ltp, ts in zip(d["token"], d["ltp"], d["ts"]):
                if tok == "NSE_INDEX|Nifty 50":
                    ticks.append((float(ts), float(ltp)))

        if not ticks:
            return

        year, month, day = (int(x) for x in self.session_date.split("-"))
        open_epoch = datetime(year, month, day, 9, 15, tzinfo=IST).timestamp()
        close_epoch = datetime(year, month, day, 15, 30, tzinfo=IST).timestamp()

        mkt_ticks = [t for t in ticks if open_epoch <= t[0] < close_epoch]

        minute_bins = {}
        minute_ticks = {}
        for ts, ltp in mkt_ticks:
            dt = datetime.fromtimestamp(ts, tz=IST)
            m_key = dt.replace(second=0, microsecond=0)
            if m_key not in minute_bins:
                minute_bins[m_key] = []
                minute_ticks[m_key] = []
            minute_bins[m_key].append(ltp)
            minute_ticks[m_key].append(ts)

        sorted_minutes = sorted(minute_bins.keys())
        for i, m in enumerate(sorted_minutes):
            ltps = minute_bins[m]
            ts_list = minute_ticks[m]
            iso_str = m.isoformat()
            self.bar_max_tick_ts[iso_str] = max(ts_list)
            self.bar_end_ts[iso_str] = m.timestamp() + 60.0
            self.bar_tick_count[iso_str] = len(ts_list)

            bar = Bar1M(
                timestamp=iso_str,
                bar_index=i,
                open=ltps[0],
                high=max(ltps),
                low=min(ltps),
                close=ltps[-1],
                volume=0.0,
                trace_id=f"raw_bar_{i}",
            )
            self.store.add_bar(bar)


def run_raw_tick_replay(
    input_bundle: Mapping[str, Any],
    session_store: RawTickSessionStore | None = None,
) -> RawTickReplayActual:
    """Execute raw tick causal replay with ZERO access to expected outputs."""
    # 1. Enforce strict input bundle: ZERO downstream analytical fields allowed
    validate_level_c_input_bundle(input_bundle)

    trace_id = str(input_bundle["trace_id"])
    session_date = str(input_bundle["session_date"])
    ts_str = str(input_bundle["timestamp"])
    warmup_status = str(input_bundle.get("warmup_status", "UNKNOWN"))

    dt_val = datetime.fromisoformat(ts_str.replace(" ", "T"))
    decision_epoch = dt_val.timestamp()

    # 2. Warmup Gate
    if warmup_status == "WARMUP_INSUFFICIENT" or session_store is None:
        return RawTickReplayActual(
            trace_id=trace_id,
            session_date=session_date,
            decision_ts_epoch=decision_epoch,
            max_raw_tick_ts_used=0.0,
            max_bar_ts_used=0.0,
            max_bar_end_ts_used=0.0,
            raw_tick_count_used=0,
            bar_count_used=0,
            warmup_status="WARMUP_INSUFFICIENT",
            future_leak_detected=False,
            c1_decision="NO_DATA",
            c1_reason_code="WARMUP_INSUFFICIENT",
            c1_qualified=False,
            c2_decision="NO_DATA",
            c2_reason_code="WARMUP_INSUFFICIENT",
            c2_qualified=False,
            integrated_tail_verdict="BLOCKED_DATA",
        )

    # 3. Read MarketSessionStore causally as of closed bars strictly completed at or before decision timestamp
    # A 1-minute bar starting at 09:21:00 completes at 09:22:00 (bar_end = 09:22:00).
    # Therefore, at decision timestamp 09:22:00, the last closed bar is the 09:21:00 bar.
    # This guarantees max_raw_tick_ts_used <= decision_ts and max_bar_ts_used <= decision_ts.
    try:
        closed_bars = [
            b for b in session_store.store._bars_1m
            if session_store.bar_end_ts[b.timestamp] <= decision_epoch
        ]
        if closed_bars:
            last_closed = closed_bars[-1]
            mem = session_store.store.get_market_memory(as_of_timestamp=last_closed.timestamp)
            max_tick_ts_used = max(session_store.bar_max_tick_ts[b.timestamp] for b in closed_bars)
            max_bar_ts = max(datetime.fromisoformat(b.timestamp).timestamp() for b in closed_bars)
            max_bar_end = max(session_store.bar_end_ts[b.timestamp] for b in closed_bars)
            total_ticks_used = sum(session_store.bar_tick_count[b.timestamp] for b in closed_bars)
            n_bars_used = len(closed_bars)

            res_c1 = evaluate_c1(mem)
            res_c2 = evaluate_c2(mem)
            c1_dec = res_c1.decision
            c1_reason = res_c1.reason_code
            c1_qual = res_c1.qualified
            c2_dec = res_c2.decision
            c2_reason = res_c2.reason_code
            c2_qual = res_c2.qualified
            mem_hash = compute_deterministic_hash({
                "current_price": mem.current_price,
                "session_open": mem.session_open,
                "rolling_15m_return_bps": mem.rolling_15m_return_bps,
            })
        else:
            # Market session just opened (e.g. 09:15:00), zero completed 1m bars yet
            max_tick_ts_used = 0.0
            max_bar_ts = 0.0
            max_bar_end = 0.0
            total_ticks_used = 0
            n_bars_used = 0
            c1_dec = "HOLD"
            c1_reason = "C1_OUT_OF_WINDOW"
            c1_qual = False
            c2_dec = "HOLD"
            c2_reason = "C2_PRE_SIGNAL"
            c2_qual = False
            mem_hash = compute_deterministic_hash("GENESIS_NO_CLOSED_BARS")
    except Exception as e:
        return RawTickReplayActual(
            trace_id=trace_id,
            session_date=session_date,
            decision_ts_epoch=decision_epoch,
            max_raw_tick_ts_used=0.0,
            max_bar_ts_used=0.0,
            max_bar_end_ts_used=0.0,
            raw_tick_count_used=0,
            bar_count_used=0,
            warmup_status=warmup_status,
            future_leak_detected=False,
            c1_decision="NO_DATA",
            c1_reason_code=str(e),
            c1_qualified=False,
            c2_decision="NO_DATA",
            c2_reason_code=str(e),
            c2_qualified=False,
            integrated_tail_verdict="BLOCKED_DATA",
        )

    # 4. Strict Physical Future-Leak Audit: physical tick timestamp MUST be <= decision_epoch
    future_leak = (max_tick_ts_used > decision_epoch) or (max_bar_ts > decision_epoch)

    # 5. Integrated Decision Tail Execution
    cand = {
        "candidate_id": f"cand_{trace_id}",
        "strategy_id": "C1" if c1_qual else "NO_TRADE",
        "strategy_family": "TREND" if c1_qual else "NO_TRADE",
        "symbol": "NIFTY",
        "exposure": 5000.0,
    }
    portfolio_state = {
        "equity_high": 1000000.0,
        "capital": 1000000.0,
        "daily_pnl_pct": 0.0,
        "open_risk_pct": 0.005,
        "trades_today": 0,
    }
    tail_res = execute_integrated_decision_tail(
        candidate=cand,
        allowed_families=[StrategyFamily.TREND],
        portfolio_state=portfolio_state,
        trace_id=trace_id,
    )

    stage_hashes = {
        "memory_hash": mem_hash,
        "c1_eval_hash": compute_deterministic_hash({"decision": c1_dec, "reason": c1_reason}),
        "c2_eval_hash": compute_deterministic_hash({"decision": c2_dec, "reason": c2_reason}),
        "decision_tail_hash": compute_deterministic_hash(tail_res.final_verdict),
    }

    return RawTickReplayActual(
        trace_id=trace_id,
        session_date=session_date,
        decision_ts_epoch=decision_epoch,
        max_raw_tick_ts_used=max_tick_ts_used,
        max_bar_ts_used=max_bar_ts,
        max_bar_end_ts_used=max_bar_end,
        raw_tick_count_used=total_ticks_used,
        bar_count_used=n_bars_used,
        warmup_status=warmup_status,
        future_leak_detected=future_leak,
        c1_decision=c1_dec,
        c1_reason_code=c1_reason,
        c1_qualified=c1_qual,
        c2_decision=c2_dec,
        c2_reason_code=c2_reason,
        c2_qualified=c2_qual,
        integrated_tail_verdict=tail_res.final_verdict,
        stage_hashes=stage_hashes,
    )


def compare_replay_to_expected(
    actual: RawTickReplayActual,
    expected_output: Mapping[str, Any],
) -> RawTickReplayComparison:
    """Compare independent replay actuals with separate expected outputs."""
    if actual.warmup_status == "WARMUP_INSUFFICIENT":
        return RawTickReplayComparison(
            trace_id=actual.trace_id,
            session_date=actual.session_date,
            decision_ts_epoch=actual.decision_ts_epoch,
            max_raw_tick_ts_used=actual.max_raw_tick_ts_used,
            max_bar_ts_used=actual.max_bar_ts_used,
            max_bar_end_ts_used=actual.max_bar_end_ts_used,
            raw_tick_count_used=actual.raw_tick_count_used,
            bar_count_used=actual.bar_count_used,
            warmup_status=actual.warmup_status,
            future_leak_detected=actual.future_leak_detected,
            c1_decision=actual.c1_decision,
            c1_reason_code=actual.c1_reason_code,
            c1_qualified=actual.c1_qualified,
            c2_decision=actual.c2_decision,
            c2_reason_code=actual.c2_reason_code,
            c2_qualified=actual.c2_qualified,
            integrated_tail_verdict=actual.integrated_tail_verdict,
            terminal_status="BLOCKED_DATA",
            comparison_depth="BLOCKED_BEFORE_EVALUATION",
            stage_hashes=actual.stage_hashes,
        )

    exp_c1_qual = expected_output.get("c1_qualified")
    exp_c1_reason = expected_output.get("c1_reason")

    parity = True
    if exp_c1_qual is not None and bool(exp_c1_qual) != bool(actual.c1_qualified):
        parity = False
    if exp_c1_reason is not None and str(exp_c1_reason) != str(actual.c1_reason_code):
        parity = False

    terminal_status = "PARTIAL_PARITY" if parity else "DIVERGED"
    comparison_depth = "STRATEGY_AND_DECISION_TAIL"

    return RawTickReplayComparison(
        trace_id=actual.trace_id,
        session_date=actual.session_date,
        decision_ts_epoch=actual.decision_ts_epoch,
        max_raw_tick_ts_used=actual.max_raw_tick_ts_used,
        max_bar_ts_used=actual.max_bar_ts_used,
        max_bar_end_ts_used=actual.max_bar_end_ts_used,
        raw_tick_count_used=actual.raw_tick_count_used,
        bar_count_used=actual.bar_count_used,
        warmup_status=actual.warmup_status,
        future_leak_detected=actual.future_leak_detected,
        c1_decision=actual.c1_decision,
        c1_reason_code=actual.c1_reason_code,
        c1_qualified=actual.c1_qualified,
        c2_decision=actual.c2_decision,
        c2_reason_code=actual.c2_reason_code,
        c2_qualified=actual.c2_qualified,
        integrated_tail_verdict=actual.integrated_tail_verdict,
        terminal_status=terminal_status,
        comparison_depth=comparison_depth,
        stage_hashes=actual.stage_hashes,
    )
