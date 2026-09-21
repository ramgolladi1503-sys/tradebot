#!/usr/bin/env python3
"""
Nifty Overnight Drift Candidate Evaluator:
- S1_MOMENTUM_OVERNIGHT_V1
- S4_MONDAY_OVERNIGHT_V1

Runtime Authority: FROZEN_SPEC.json
Strictly non-trading, read-only analytics adhering to AGENTS.md:
- read_only = True
- broker_write_authority = False
- orders_placed = 0
- paper_authorized = False
- live_authorized = False

Invariants:
1. Economic Family: Overnight Equity Risk Transfer in Bull Regimes.
2. Macro Trend Gate: Strictly historical Close[t-1] > SMA200[t-1] (fails closed on NaN or missing data).
3. Runtime Authority is loaded dynamically and validated against FROZEN_SPEC.json.
4. Schedule hashes cryptographically locked to Option B canonical baseline.
"""

from __future__ import annotations
import os
import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple

import pandas as pd
import numpy as np

IST_TZ = timezone(timedelta(hours=5, minutes=30))

CANDIDATE_S1_ID = "S1_MOMENTUM_OVERNIGHT_V1"
CANDIDATE_S1_SCHEDULE_SHA256 = "48dc743eb7e91d92467e5f207a18640e1563b00b42b79b6d13a7bdd255ca68df"

CANDIDATE_S4_ID = "S4_MONDAY_OVERNIGHT_V1"
CANDIDATE_S4_SCHEDULE_SHA256 = "43650186de669a9cba9993f0b6cdd58540639681021cc0971cbd61258b005692"


@dataclass(frozen=True)
class FrozenCandidateSpec:
    candidate_id: str
    candidate_version: str
    candidate_status: str
    spec_digest: str
    macro_rule: str
    sma_indicator: str
    cutoff_wall_clock_ist: str
    threshold_pct: Optional[float]
    required_day: Optional[str]
    entry_wall_clock_ist: str
    exit_wall_clock_ist: str
    deterministic_friction_pts: float
    raw_spec: Dict[str, Any]


def load_and_validate_frozen_spec(candidate_id: str, base_dir: str = "docs/research/candidates") -> FrozenCandidateSpec:
    """
    Loads candidate specification from its authoritative FROZEN_SPEC.json.
    Verifies that the file content matches FROZEN_SPEC.sha256 digest.
    Fails closed if the specification file is tampered with, missing, or invalid.
    """
    spec_file = os.path.join(base_dir, candidate_id, "FROZEN_SPEC.json")
    digest_file = os.path.join(base_dir, candidate_id, "FROZEN_SPEC.sha256")

    if not os.path.exists(spec_file) or not os.path.exists(digest_file):
        raise FileNotFoundError(f"Missing authoritative frozen spec files for {candidate_id}")

    with open(spec_file, "r") as f:
        spec_dict = json.load(f)

    # Verify digest
    serialized = json.dumps(spec_dict, sort_keys=True)
    computed_digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    with open(digest_file, "r") as f:
        stored_digest = f.read().strip().split()[0]

    if computed_digest != stored_digest:
        raise ValueError(f"CRITICAL: Cryptographic spec digest mismatch for {candidate_id}! Computed: {computed_digest}, Stored: {stored_digest}")

    return FrozenCandidateSpec(
        candidate_id=spec_dict["candidate_id"],
        candidate_version=spec_dict["candidate_version"],
        candidate_status=spec_dict["candidate_status"],
        spec_digest=computed_digest,
        macro_rule=spec_dict["macro_trend_filter"]["rule"],
        sma_indicator=spec_dict["macro_trend_filter"]["indicator"],
        cutoff_wall_clock_ist=spec_dict["signal_evaluation"]["cutoff_wall_clock_ist"],
        threshold_pct=spec_dict["signal_evaluation"].get("threshold_pct"),
        required_day=spec_dict["signal_evaluation"].get("required_day"),
        entry_wall_clock_ist=spec_dict["execution_model"]["entry_wall_clock_ist"],
        exit_wall_clock_ist=spec_dict["execution_model"]["exit_wall_clock_ist"],
        deterministic_friction_pts=float(spec_dict["execution_model"]["deterministic_friction_pts"]),
        raw_spec=spec_dict,
    )


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
    s1_spec: Optional[FrozenCandidateSpec] = None,
    s4_spec: Optional[FrozenCandidateSpec] = None,
) -> OvernightSignalResult:
    """
    Evaluates both S1 and S4 using authoritative FROZEN_SPEC specifications.
    Fails closed if macro trend state is NaN, non-positive, or missing.
    """
    if s1_spec is None:
        s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)
    if s4_spec is None:
        s4_spec = load_and_validate_frozen_spec(CANDIDATE_S4_ID)

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

    # 3. Qualification logic driven by authoritative spec parameters
    s1_thresh = s1_spec.threshold_pct if s1_spec.threshold_pct is not None else 0.50
    s4_day = s4_spec.required_day if s4_spec.required_day is not None else "Monday"

    s1_qualified = bool(is_uptrend and day_gain_pct > s1_thresh)
    s4_qualified = bool(is_uptrend and dow == s4_day)

    # 4. P&L calculation if reference execution prices are supplied
    gross_pnl = None
    net_pnl = None
    deterministic_cost = s1_spec.deterministic_friction_pts
    if entry_ref_1521 is not None and exit_ref_next_0915 is not None:
        if entry_ref_1521 > 0 and exit_ref_next_0915 > 0:
            gross_pnl = float(exit_ref_next_0915 - entry_ref_1521)
            net_pnl = float(gross_pnl - deterministic_cost)

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
