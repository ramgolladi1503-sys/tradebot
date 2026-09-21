#!/usr/bin/env python3
"""
Nifty Overnight Drift Candidate Evaluator:
- S1_MOMENTUM_OVERNIGHT_V1
- S4_MONDAY_OVERNIGHT_V1

Strictly non-trading, read-only analytics adhering to AGENTS.md:
- read_only = True
- broker_write_authority = False
- orders_placed = 0
- paper_authorized = False
- live_authorized = False

Terminally Frozen Architecture:
1. Economic Family: Overnight Equity Risk Transfer in Bull Regimes.
2. Macro Trend Gate: Strictly historical Close[t-1] > SMA200[t-1] (fails closed on NaN).
3. Signal Evaluation: 15:20:00 IST sealed minute close.
   - S1: Close[15:20] / Day_Open - 1 > +0.50%
   - S4: Day of Week == "Monday"
4. Conservative 1-Minute Execution Buffer:
   - Arrival price reference: First valid quote strictly after 15:20:00 cutoff (approx 15:21:00 IST).
   - Exit price reference: Next regular session official open (09:15:00 IST).
5. Immutable Schedule Digests:
   - S1: 48dc743eb7e91d92467e5f207a18640e1563b00b42b79b6d13a7bdd255ca68df
   - S4: 43650186de669a9cba9993f0b6cdd58540639681021cc0971cbd61258b005692
"""

from __future__ import annotations
import json
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np

CANDIDATE_S1_ID = "S1_MOMENTUM_OVERNIGHT_V1"
CANDIDATE_S1_SPEC_DIGEST = "3d3770a74c598ae6ac8dc5096ef748bd8bb9b73f1c3969a371b40ac88225b553"
CANDIDATE_S1_SCHEDULE_SHA256 = "48dc743eb7e91d92467e5f207a18640e1563b00b42b79b6d13a7bdd255ca68df"

CANDIDATE_S4_ID = "S4_MONDAY_OVERNIGHT_V1"
CANDIDATE_S4_SPEC_DIGEST = "079587dc8960c7e863a87f63ddd4c98cec0780c797a220e747f028fad182973d"
CANDIDATE_S4_SCHEDULE_SHA256 = "43650186de669a9cba9993f0b6cdd58540639681021cc0971cbd61258b005692"

IST_TZ = timezone(timedelta(hours=5, minutes=30))
DETERMINISTIC_COST_PTS = 14.30


@dataclass(frozen=True)
class OvernightSignalResult:
    session_date: str
    dow: str
    prev_close: float
    prev_sma200: float
    is_uptrend: bool
    day_open: float
    price_1520: float
    day_gain_pct: float
    s1_qualified: bool
    s4_qualified: bool
    entry_ref_1521: Optional[float]
    exit_ref_next_0915: Optional[float]
    gross_pnl: Optional[float]
    net_pnl: Optional[float]


def evaluate_overnight_signal(
    session_date: str,
    dow: str,
    prev_close: float,
    prev_sma200: float,
    day_open: float,
    price_1520: float,
    entry_ref_1521: Optional[float] = None,
    exit_ref_next_0915: Optional[float] = None,
) -> OvernightSignalResult:
    """
    Evaluates both S1 and S4 under frozen immutable rules.
    Fails closed if macro trend state is NaN or invalid.
    """
    # 1. Fail-closed macro trend check
    if pd.isna(prev_close) or pd.isna(prev_sma200) or prev_close <= 0 or prev_sma200 <= 0:
        is_uptrend = False
    else:
        is_uptrend = bool(prev_close > prev_sma200)

    # 2. Intraday momentum by 15:20:00 cutoff
    if pd.isna(day_open) or pd.isna(price_1520) or day_open <= 0:
        day_gain_pct = 0.0
    else:
        day_gain_pct = float((price_1520 / day_open - 1.0) * 100.0)

    # 3. Qualification logic
    s1_qualified = bool(is_uptrend and day_gain_pct > 0.50)
    s4_qualified = bool(is_uptrend and dow == "Monday")

    # 4. P&L calculation if reference execution prices are supplied
    gross_pnl = None
    net_pnl = None
    if entry_ref_1521 is not None and exit_ref_next_0915 is not None:
        if entry_ref_1521 > 0 and exit_ref_next_0915 > 0:
            gross_pnl = float(exit_ref_next_0915 - entry_ref_1521)
            net_pnl = float(gross_pnl - DETERMINISTIC_COST_PTS)

    return OvernightSignalResult(
        session_date=session_date,
        dow=dow,
        prev_close=prev_close,
        prev_sma200=prev_sma200,
        is_uptrend=is_uptrend,
        day_open=day_open,
        price_1520=price_1520,
        day_gain_pct=day_gain_pct,
        s1_qualified=s1_qualified,
        s4_qualified=s4_qualified,
        entry_ref_1521=entry_ref_1521,
        exit_ref_next_0915=exit_ref_next_0915,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
    )
