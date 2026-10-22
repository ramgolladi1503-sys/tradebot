"""Dual-Index Regime Momentum Shadow Adapter.

Safely observes the dual-index consensus gap in live or shadow session runs
without executing live broker orders. Logs candidate evaluations with read-only
audit evidence.

Safety Invariants:
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
- append = False
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

from core.movement_contract import StrategyCandidate, StrategyContext
from strategies.dual_index_regime_momentum import (
    STRATEGY_ID,
    DualIndexRegimeInput,
    calculate_gap_pct,
    evaluate_dual_index_momentum,
    generate_candidate,
)

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class ShadowEvaluationRecord:
    timestamp_ist: str
    strategy_id: str
    symbol: str
    nifty_open: float
    nifty_prev_close: float
    sensex_open: float
    sensex_prev_close: float
    nifty_gap_pct: float
    sensex_gap_pct: float
    decision: str
    direction: str
    reason: str
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False


class DualIndexShadowAdapter:
    """Shadow adapter observing live tick/snapshot streams without placing orders."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("reports/research/shadow_evaluations")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def process_snapshot(
        self,
        market_snapshot: Mapping[str, Any],
        eval_time: Optional[datetime] = None,
    ) -> StrategyCandidate:
        now = eval_time or datetime.now(IST)
        context = StrategyContext(symbol="NIFTY")
        candidate = generate_candidate(context, market_snapshot)
        return candidate

    def record_shadow_observation(
        self,
        inp: DualIndexRegimeInput,
        min_gap_pct: float = 0.20,
        consensus_gap_pct: float = 0.20,
    ) -> ShadowEvaluationRecord:
        sig = evaluate_dual_index_momentum(
            inp,
            min_gap_pct=min_gap_pct,
            consensus_gap_pct=consensus_gap_pct,
        )
        record = ShadowEvaluationRecord(
            timestamp_ist=inp.evaluation_time.astimezone(IST).isoformat(),
            strategy_id=STRATEGY_ID,
            symbol=inp.symbol,
            nifty_open=inp.nifty_open,
            nifty_prev_close=inp.nifty_prev_close,
            sensex_open=inp.sensex_open,
            sensex_prev_close=inp.sensex_prev_close,
            nifty_gap_pct=sig.nifty_gap_pct,
            sensex_gap_pct=sig.sensex_gap_pct,
            decision=sig.decision,
            direction=sig.direction,
            reason=sig.reason,
            read_only=True,
            is_order_action=False,
            broker_api_called=False,
        )

        log_file = self.output_dir / "dual_index_regime_shadow.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")

        return record
