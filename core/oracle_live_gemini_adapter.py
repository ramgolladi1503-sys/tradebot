"""
ORACLE Gemini Live Market Copilot Adapter
=========================================
A completely decoupled, autonomous AI market reasoning engine for NIFTY & Options.
Distinct from Sentinel:
- Prefix: [ORACLE_GEMINI_LIVE]
- Independent log: logs/oracle_gemini_live_{YYYYMMDD}.log
- Independent WAL: .runtime/oracle_gemini_wal/

Architecture:
1. Stateful Trade State Machine (Flat Cash -> Pending Confirmation -> In Trade -> Breakeven -> Exit)
   - Prevents BUY <-> WAIT tick flapping via hysteresis and cooldown timers.
2. Structured Pydantic Outputs:
   - Returns concrete option limit prices: entry_price, stop_loss_price, breakeven_trigger, target_price.
3. RBFN & Option Ladder Grounding:
   - Grounded in exact option premiums (e.g. low-premium ladder 38, 48, 58, 68, 88, 128).
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Literal
from dataclasses import dataclass, asdict

from pydantic import BaseModel, Field
from google import genai
from google.genai import types

logger = logging.getLogger("oracle_gemini_live")


class OracleAdviceSchema(BaseModel):
    """Deterministic Pydantic schema for Gemini structured output."""
    action: Literal[
        "BUY_CE",
        "BUY_PE",
        "WAIT_IN_CASH",
        "HOLD_POSITION",
        "MOVE_SL_BREAKEVEN",
        "EXIT_PROFIT_TARGET",
        "EXIT_STOP_LOSS",
    ] = Field(description="Immediate trade execution action")
    strike: str = Field(description="Contract identifier (e.g. 'NIFTY 23200 PE' or 'NONE')")
    entry_limit_price: float = Field(description="Exact option entry limit price in INR (0.0 if WAIT/HOLD)")
    stop_loss_price: float = Field(description="Exact stop loss option price in INR (0.0 if WAIT)")
    breakeven_trigger_price: float = Field(description="Option price at which SL must move to entry (0.0 if WAIT)")
    target_price: float = Field(description="Primary profit target option price in INR (0.0 if WAIT)")
    spot_reference: float = Field(description="Underlying NIFTY Spot reference level triggering the trade")
    rationale: str = Field(description="1-2 sentences on microstructure, RBFN boundary, or price action")


@dataclass
class OracleActivePosition:
    strike: str
    entry_price: float
    current_ltp: float
    stop_loss_price: float
    breakeven_price: float
    target_price: float
    entry_time: float
    is_breakeven_locked: bool = False

    def update_ltp(self, ltp: float) -> None:
        self.current_ltp = ltp


SYSTEM_INSTRUCTION = """
You are ORACLE, an elite institutional intraday options execution copilot for Indian Markets (NIFTY).
You are completely separate from rule-based algorithms. Your job is to give decisive, human-like execution advice.

Trading Mandates:
1. EXACT PRICES REQUIRED:
   - Never say just "at spot" or relative points like "+15 pts" alone.
   - You MUST compute exact Option Limit Prices (e.g., Entry: 38.00, Stop Loss: 30.00, Breakeven Trigger: 50.00, Target: 68.00 or 100.00).
   - If targeting low-premium contracts, align with the established ladder tiers: 38, 48, 58, 68, 88, 128.

2. ASYMMETRIC RISK/REWARD:
   - Target Payoff: At least +15 to +30 option points (or next ladder tier).
   - Hard Stop Loss: -8 to -10 option points strictly below entry limit.
   - Breakeven Trigger: When option advances +12 option points above entry, signal MOVE_SL_BREAKEVEN.

3. STATEFUL DISCIPLINE:
   - If FLAT_CASH and market is within chop zone (between OR High and OR Low or inside Trend Decider dead-zone), action MUST be WAIT_IN_CASH.
   - If FLAT_CASH and spot tests Upper Reversal or OR Low with rejection wick, select the corresponding CE/PE contract near the 38-68 ladder and issue BUY.
   - If IN_TRADE: evaluate ONLY HOLD_POSITION, MOVE_SL_BREAKEVEN, EXIT_PROFIT_TARGET, or EXIT_STOP_LOSS based on current option LTP vs entry. DO NOT flip to WAIT_IN_CASH while holding!
"""


class OracleGeminiLiveAdapter:
    def __init__(
        self,
        api_key: Optional[str] = None,
        poll_interval_sec: float = 30.0,
        signal_cooldown_sec: float = 120.0,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment or .env")

        self.client = genai.Client(api_key=self.api_key)
        self.model_name = "gemini-3.5-flash-lite"
        self.poll_interval_sec = poll_interval_sec
        self.signal_cooldown_sec = signal_cooldown_sec
        self.last_eval_time = 0.0
        self.last_signal_time = 0.0

        # State tracking
        self.current_spot = 0.0
        self.active_position: Optional[OracleActivePosition] = None
        self.last_advice: Optional[OracleAdviceSchema] = None

        # Logging setup
        today_str = datetime.now().strftime("%Y%m%d")
        log_dir = Path("/Users/madhuram/tradebot/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = log_dir / f"oracle_gemini_live_{today_str}.log"

        # File logger
        fh = logging.FileHandler(self.log_file)
        fh.setFormatter(logging.Formatter("%(asctime)s [ORACLE] %(message)s"))
        logger.addHandler(fh)
        logger.setLevel(logging.INFO)

    def evaluate_market_snapshot(
        self,
        spot: float,
        or_high: float,
        or_low: float,
        trend_decider: float = 0.0,
        upper_reversal: float = 0.0,
        lower_reversal: float = 0.0,
        futures_basis: float = 0.0,
        candidate_ce_symbol: str = "NONE",
        candidate_ce_ltp: float = 0.0,
        candidate_pe_symbol: str = "NONE",
        candidate_pe_ltp: float = 0.0,
    ) -> Optional[OracleAdviceSchema]:
        """Throttled, state-aware evaluation outputting concrete option limit prices."""
        now = time.time()
        if (now - self.last_eval_time) < self.poll_interval_sec:
            return None

        self.last_eval_time = now
        self.current_spot = spot

        # If currently holding a position, update its current LTP before prompt
        if self.active_position:
            if "CE" in self.active_position.strike and candidate_ce_ltp > 0:
                self.active_position.update_ltp(candidate_ce_ltp)
            elif "PE" in self.active_position.strike and candidate_pe_ltp > 0:
                self.active_position.update_ltp(candidate_pe_ltp)

        # Build comprehensive structured state payload for Gemini
        position_payload: Any = "FLAT_CASH"
        if self.active_position:
            position_payload = asdict(self.active_position)
            position_payload["unrealized_pts"] = round(
                self.active_position.current_ltp - self.active_position.entry_price, 2
            )

        payload = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "nifty_spot": round(spot, 2),
            "opening_range": {
                "high": round(or_high, 2),
                "low": round(or_low, 2),
                "range_pts": round(or_high - or_low, 1),
            },
            "rbfn_levels": {
                "upper_reversal": round(upper_reversal, 2) if upper_reversal > 0 else "N/A",
                "trend_decider": round(trend_decider, 2) if trend_decider > 0 else "N/A",
                "lower_reversal": round(lower_reversal, 2) if lower_reversal > 0 else "N/A",
            },
            "futures_basis_pts": round(futures_basis, 2),
            "candidate_options": {
                "ce": {"symbol": candidate_ce_symbol, "ltp": round(candidate_ce_ltp, 2)},
                "pe": {"symbol": candidate_pe_symbol, "ltp": round(candidate_pe_ltp, 2)},
            },
            "active_trade_state": position_payload,
        }

        # Prompt with clear instruction to provide exact limit prices
        prompt = (
            "Evaluate this real-time institutional NIFTY snapshot. "
            "If signaling an entry, compute EXACT option limit prices for entry, stop_loss, breakeven, and target. "
            "If in an active trade, advise only on management (HOLD, MOVE_SL_BREAKEVEN, or EXIT):\n"
            f"{json.dumps(payload, indent=2)}"
        )

        try:
            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.1,  # Low temperature for stable, non-flapping decisions
                    response_mime_type="application/json",
                    response_schema=OracleAdviceSchema,
                ),
            )

            advice: OracleAdviceSchema = resp.parsed
            
            # Distinct Oracle attribution log
            log_msg = (
                f"[ORACLE_GEMINI_LIVE] Spot: {spot:.1f} | Action: {advice.action} | Strike: {advice.strike} | "
                f"Entry: ₹{advice.entry_limit_price:.2f} | SL: ₹{advice.stop_loss_price:.2f} | "
                f"Tgt: ₹{advice.target_price:.2f} | Reason: {advice.rationale}"
            )
            logger.info(log_msg)
            print(f"\n🔮 {log_msg}\n")

            # --- State Machine Transitions & Anti-Flapping Hysteresis ---
            if self.active_position is not None:
                # While in an active trade, ignore conflicting BUY signals or premature WAIT
                if advice.action in ("BUY_CE", "BUY_PE", "WAIT_IN_CASH"):
                    logger.info(f"Ignoring {advice.action} while holding active position {self.active_position.strike}.")
                    return None
                elif advice.action == "MOVE_SL_BREAKEVEN":
                    self.active_position.stop_loss_price = self.active_position.entry_price
                    self.active_position.is_breakeven_locked = True
                elif advice.action in ("EXIT_PROFIT_TARGET", "EXIT_STOP_LOSS"):
                    logger.info(f"Closing position {self.active_position.strike} on {advice.action}.")
                    self.active_position = None
                    self.last_signal_time = now
            else:
                # Flat Cash -> Entry transition
                if advice.action in ("BUY_CE", "BUY_PE"):
                    # Cooldown check: prevent rapid re-entry churn
                    if (now - self.last_signal_time) < self.signal_cooldown_sec:
                        logger.info(f"Signal {advice.action} suppressed by cooldown ({self.signal_cooldown_sec}s). Waiting for setup confirmation.")
                        return advice

                    # Establish active position
                    entry_px = advice.entry_limit_price if advice.entry_limit_price > 0 else (
                        candidate_ce_ltp if "CE" in advice.strike else candidate_pe_ltp
                    )
                    sl_px = advice.stop_loss_price if advice.stop_loss_price > 0 else round(entry_px - 8.0, 2)
                    be_px = advice.breakeven_trigger_price if advice.breakeven_trigger_price > 0 else round(entry_px + 12.0, 2)
                    tgt_px = advice.target_price if advice.target_price > 0 else round(entry_px + 20.0, 2)

                    self.active_position = OracleActivePosition(
                        strike=advice.strike,
                        entry_price=entry_px,
                        current_ltp=entry_px,
                        stop_loss_price=sl_px,
                        breakeven_price=be_px,
                        target_price=tgt_px,
                        entry_time=now,
                    )
                    self.last_signal_time = now

            self.last_advice = advice
            return advice

        except Exception as e:
            err_msg = f"Gemini evaluation failed: {e}"
            logger.error(err_msg)
            return None
