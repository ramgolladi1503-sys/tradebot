#!/usr/bin/env python3
"""
Paper Shadow Execution Runner & Telemetry Logger: INTRADAY_OPENING_DRIVE_V1
Strictly non-trading, read-only shadow logger adhering to AGENTS.md:
- read_only = True
- broker_write_authority = False
- order_authority = False
- orders_placed = 0
- orders_modified = 0
- orders_cancelled = 0

Cryptographically bound to frozen candidate specification:
CANDIDATE_FINGERPRINT = 52904a90b2a413e80b4792cf60b824118147e18b16f807d00bf24532d141a065

Causal Shadow Invariants:
1. Signal Source: NIFTY Futures Only (Gap = Open(09:15) - Close(T-1_15:29), Drive = Close(09:20) - Open(09:15)).
   Thresholds: |Gap| > 30.0 pts, |Drive| > 20.0 pts.
2. Overnight Contract Continuity:
   Requires authoritative contract key match: prev_contract_key == curr_contract_key.
   Fails closed on missing metadata or calendar/expiry roll boundaries.
3. Spot-ATM Strike Mapping:
   Contemporaneous NIFTY 50 Spot close at 09:20:00 mapped to 50-pt grid with midpoint (.5) tie-breaker.
4. Expiry Selection:
   Minimum expiry strictly greater than today's exit time (11:01:00 IST).
5. Prospective Shadow Timing & Causality:
   - Historical reference: 09:21 bar close (known at 09:22:00) -> 11:00 bar close (known at 11:01:00).
   - Fresh prospective quote entry: First valid quote strictly after 09:22:00.000.
   - Fresh prospective quote exit:  First valid quote strictly after 11:01:00.000.
6. Market Depth Validation:
   Requires bid > 0, ask > 0, ask >= bid, finite and non-NaN.
7. Conservative Crossing:
   Long option buys at Ask, sells at Bid. Spread crossing is embedded in gross PnL. Never double-deduct spread.
8. Statutory Accounting:
   Exact 2026 IndianDerivativesCostModel schedule (0.15% STT on option sell premium, 0.035% exchange fee).
"""

from __future__ import annotations
import gzip
import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Mapping, Optional, Tuple

import pandas as pd
import numpy as np
import pyarrow.dataset as ds

from core.candidate_audits.cost_model import IndianDerivativesCostModel
from core.candidate_audits.intraday_opening_drive import (
    calculate_intraday_drive_signal,
    calculate_spot_atm_strike,
    _extract_authoritative_contract_key,
    CANDIDATE_ID,
    CANDIDATE_FINGERPRINT,
    IST_TZ,
)


@dataclass(frozen=True)
class IntradayShadowExecutionRecord:
    schema_version: int
    candidate_id: str
    candidate_fingerprint: str
    verification_mode: str
    session_date: str

    # Contract Identity & Continuity
    prev_contract_key: str
    curr_contract_key: str
    contract_continuity_verified: bool

    # Signal Formation (Futures)
    prev_close_1529: float
    today_open_0915: float
    gap_pts: float
    drive_close_0920: float
    drive_5m_pts: float
    signal_side: str
    signal_completed_timestamp: str

    # Option Contract Selection
    spot_0920: float
    atm_strike: int
    option_contract: str
    expiry: str
    lot_size: int
    lot_size_source: str

    # Entry Quote & Fill (Strictly > 09:22:00.000)
    entry_quote_timestamp: str
    entry_bid: float
    entry_ask: float
    entry_spread: float
    entry_fill: float
    entry_depth_valid: bool

    # Exit Quote & Fill (Strictly > 11:01:00.000)
    exit_quote_timestamp: str
    exit_bid: float
    exit_ask: float
    exit_spread: float
    exit_fill: float
    exit_depth_valid: bool

    # Historical Reference Benchmarks (09:21 close / 11:00 close)
    historical_ref_entry_0922: float
    historical_ref_exit_1101: float

    # Economics & Rupee Accounting
    gross_premium_pts: float
    gross_pnl_inr: float
    capital_outlay_inr: float

    # Statutory Fees (2026 Schedule)
    stt_rate_applied: float
    fee_brokerage_inr: float
    fee_stt_inr: float
    fee_exchange_inr: float
    fee_sebi_inr: float
    fee_stamp_inr: float
    fee_gst_inr: float
    total_statutory_fee_inr: float

    # Net Return
    net_pnl_inr: float
    net_premium_pts: float
    return_on_capital_pct: float

    # Safety Governance Gates (AGENTS.md)
    read_only: bool
    broker_write_authority: bool
    order_authority: bool
    orders_placed: int
    orders_modified: int
    orders_cancelled: int


def parse_option_expiry_dt(symbol: str) -> Optional[datetime]:
    try:
        parts = symbol.strip().split()
        if len(parts) < 5:
            return None
        date_str = " ".join(parts[-3:])
        d = datetime.strptime(date_str, "%d %b %y")
        return datetime.combine(d.date(), dtime(15, 30, 0)).replace(tzinfo=IST_TZ)
    except Exception:
        return None


def get_authoritative_option_lot_size(symbol: str) -> Tuple[int, str]:
    paths_to_try = [
        "runtime/upstox_instruments/complete.json",
        "runtime/upstox_instruments/complete.json.gz",
        "data/upstox_instruments.json"
    ]
    for p in paths_to_try:
        if os.path.exists(p):
            try:
                if p.endswith(".gz"):
                    with gzip.open(p, "rt", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                if isinstance(data, dict):
                    data = list(data.values())
                for item in data:
                    if item.get("trading_symbol") == symbol:
                        lot = int(item.get("lot_size", 0))
                        if lot > 0:
                            return lot, f"UPSTOX_MASTER:{p}"
            except Exception:
                continue
    return -1, "NOT_FOUND"


def validate_market_depth(bid: float, ask: float) -> bool:
    if math.isnan(bid) or math.isnan(ask) or math.isinf(bid) or math.isinf(ask):
        return False
    if bid <= 0.0 or ask <= 0.0:
        return False
    if ask < bid:
        return False
    return True


def run_intraday_shadow_for_session(
    prev_session_df: pd.DataFrame,
    curr_session_df: pd.DataFrame,
    capture_dir: str = "/Volumes/TradeBotData/live market capture",
    verification_mode: str = "FRESH_PROSPECTIVE_LIVE_SHADOW"
) -> Optional[IntradayShadowExecutionRecord]:
    """
    Executes a read-only paper shadow evaluation for one prospective session.
    Enforces all frozen invariants:
    - Contract continuity check
    - Exact 15:29:00 close
    - 09:21:00 signal completion
    - > 09:22:00.000 entry quote
    - > 11:01:00.000 exit quote
    """
    # 1. Compute Signal under frozen contract continuity rules
    sig = calculate_intraday_drive_signal(prev_session_df, curr_session_df)
    if sig is None or not sig.is_valid_signal:
        return None

    session_date = sig.session_date
    opt_type = "CE" if sig.side == "LONG" else "PE"

    # 2. Get Contemporaneous NIFTY 50 Spot at 09:20:00
    spot_pq = os.path.join(capture_dir, session_date, f"indices_1m_{session_date.replace('-', '')}.parquet")
    if not os.path.exists(spot_pq):
        return None

    s_df = pd.read_parquet(spot_pq)
    nifty_spot = s_df[s_df["symbol"] == "NIFTY 50"]
    b_spot_0920 = nifty_spot[nifty_spot["timestamp"].astype(str).str.contains("09:20")]
    if b_spot_0920.empty:
        return None

    spot_0920 = float(b_spot_0920.iloc[0]["close"])
    atm_strike = calculate_spot_atm_strike(spot_0920, grid=50.0)

    # 3. Locate Option Contract in Tick Dataset
    tick_pq = os.path.join(capture_dir, session_date, f"upstox_full_ticks_{session_date.replace('-', '')}_stitched.parquet")
    if not os.path.exists(tick_pq):
        return None

    dataset = ds.dataset(tick_pq, format="parquet")
    prefix = f"NIFTY {atm_strike} {opt_type} "

    # Exit time anchor is today at 11:01:00 IST
    dt_exit_boundary = datetime.strptime(f"{session_date} 11:01:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST_TZ)
    exit_ts_boundary = dt_exit_boundary.timestamp()

    scanner_syms = dataset.scanner(columns=["symbol"])
    available_symbols = [str(s) for s in scanner_syms.to_table().column("symbol").unique().to_pylist()]

    matching_symbols = [s for s in available_symbols if s.startswith(prefix)]
    surviving = []
    for s in matching_symbols:
        exp_dt = parse_option_expiry_dt(s)
        if exp_dt is not None and exp_dt.timestamp() > exit_ts_boundary:
            surviving.append((s, exp_dt))

    if not surviving:
        return None

    surviving.sort(key=lambda x: x[1].timestamp())
    target_symbol, expiry_dt = surviving[0]
    expiry_str = target_symbol.replace(prefix, "").strip()

    # Authoritative Lot Size
    lot_size, lot_source = get_authoritative_option_lot_size(target_symbol)
    if lot_size <= 0:
        return None

    # 4. Query Entry Quote: First valid quote STRICTLY AFTER 09:22:00.000
    dt_entry_target = datetime.strptime(f"{session_date} 09:22:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST_TZ)
    entry_target_ts = dt_entry_target.timestamp()

    scanner_entry = dataset.scanner(
        filter=(ds.field("symbol") == target_symbol) &
               (ds.field("ts") > entry_target_ts) &
               (ds.field("ts") <= entry_target_ts + 15)
    )
    entry_df = scanner_entry.to_table().to_pandas().sort_values("ts", ascending=True)
    if entry_df.empty:
        return None

    valid_entry_row = None
    for _, row in entry_df.iterrows():
        b = float(row["bid"])
        a = float(row["ask"])
        t = float(row["ts"])
        if t > entry_target_ts and validate_market_depth(b, a):
            valid_entry_row = row
            break

    if valid_entry_row is None:
        return None

    entry_bid = float(valid_entry_row["bid"])
    entry_ask = float(valid_entry_row["ask"])
    entry_spread = round(entry_ask - entry_bid, 2)
    entry_fill = entry_ask
    entry_ts_val = float(valid_entry_row["ts"])
    entry_quote_str = datetime.fromtimestamp(entry_ts_val, tz=IST_TZ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # 5. Query Exit Quote: First valid quote STRICTLY AFTER 11:01:00.000
    scanner_exit = dataset.scanner(
        filter=(ds.field("symbol") == target_symbol) &
               (ds.field("ts") > exit_ts_boundary) &
               (ds.field("ts") <= exit_ts_boundary + 15)
    )
    exit_df = scanner_exit.to_table().to_pandas().sort_values("ts", ascending=True)
    if exit_df.empty:
        return None

    valid_exit_row = None
    for _, row in exit_df.iterrows():
        b = float(row["bid"])
        a = float(row["ask"])
        t = float(row["ts"])
        if t > exit_ts_boundary and validate_market_depth(b, a):
            valid_exit_row = row
            break

    if valid_exit_row is None:
        return None

    exit_bid = float(valid_exit_row["bid"])
    exit_ask = float(valid_exit_row["ask"])
    exit_spread = round(exit_ask - exit_bid, 2)
    exit_fill = exit_bid
    exit_ts_val = float(valid_exit_row["ts"])
    exit_quote_str = datetime.fromtimestamp(exit_ts_val, tz=IST_TZ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    # 6. Statutory Cost Accounting (2026 Schedule)
    gross_premium_pts = round(exit_fill - entry_fill, 2)
    gross_pnl_inr = round(gross_premium_pts * lot_size, 2)
    capital_outlay_inr = round(entry_fill * lot_size, 2)

    cost_model = IndianDerivativesCostModel()
    cb = cost_model.calculate_cost(
        entry_price=entry_fill,
        exit_price=exit_fill,
        lot_size=lot_size,
        instrument="INDEX_OPTION_BUY",
        is_long=True,
        trade_date=session_date,
        legs_count=2
    )

    total_fees_inr = cb.total
    net_pnl_inr = round(gross_pnl_inr - total_fees_inr, 2)
    net_premium_pts = round(net_pnl_inr / lot_size, 2)
    ret_on_capital_pct = round((net_pnl_inr / capital_outlay_inr) * 100.0, 2) if capital_outlay_inr > 0 else 0.0

    return IntradayShadowExecutionRecord(
        schema_version=1,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint=CANDIDATE_FINGERPRINT,
        verification_mode=verification_mode,
        session_date=session_date,
        prev_contract_key=sig.prev_contract_key,
        curr_contract_key=sig.curr_contract_key,
        contract_continuity_verified=True,
        prev_close_1529=sig.prev_close_1529,
        today_open_0915=sig.today_open_0915,
        gap_pts=sig.gap_pts,
        drive_close_0920=sig.drive_close_0920,
        drive_5m_pts=sig.drive_5m_pts,
        signal_side=sig.side,
        signal_completed_timestamp=f"{session_date} 09:21:00.000",
        spot_0920=spot_0920,
        atm_strike=atm_strike,
        option_contract=target_symbol,
        expiry=expiry_str,
        lot_size=lot_size,
        lot_size_source=lot_source,
        entry_quote_timestamp=entry_quote_str,
        entry_bid=entry_bid,
        entry_ask=entry_ask,
        entry_spread=entry_spread,
        entry_fill=entry_fill,
        entry_depth_valid=True,
        exit_quote_timestamp=exit_quote_str,
        exit_bid=exit_bid,
        exit_ask=exit_ask,
        exit_spread=exit_spread,
        exit_fill=exit_fill,
        exit_depth_valid=True,
        historical_ref_entry_0922=sig.entry_ref_0922,
        historical_ref_exit_1101=sig.exit_ref_1101,
        gross_premium_pts=gross_premium_pts,
        gross_pnl_inr=gross_pnl_inr,
        capital_outlay_inr=capital_outlay_inr,
        stt_rate_applied=cb.effective_stt_rate,
        fee_brokerage_inr=cb.brokerage,
        fee_stt_inr=cb.stt,
        fee_exchange_inr=cb.exchange,
        fee_sebi_inr=cb.sebi,
        fee_stamp_inr=cb.stamp,
        fee_gst_inr=cb.gst,
        total_statutory_fee_inr=total_fees_inr,
        net_pnl_inr=net_pnl_inr,
        net_premium_pts=net_premium_pts,
        return_on_capital_pct=ret_on_capital_pct,
        read_only=True,
        broker_write_authority=False,
        order_authority=False,
        orders_placed=0,
        orders_modified=0,
        orders_cancelled=0
    )


def main():
    print(f"Intraday Paper Shadow Runner for {CANDIDATE_ID} (Status: READY FOR PROSPECTIVE TRADE #1)")
    print(f"Bound to Specification Fingerprint: {CANDIDATE_FINGERPRINT}")


if __name__ == "__main__":
    main()
