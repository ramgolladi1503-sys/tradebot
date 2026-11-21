"""Sentinel Option Strike Resolver & Mode 5 target-strike quote lookup.
======================================================================
Implements strike selection mechanisms for Indian Index Options (NIFTY, BANKNIFTY, SENSEX),
with dedicated support for Mode 5 OptionMate RBFN auction signals using:
1. The strategy's geometric target strike as the selected contract strike.
2. Exchange step size compliance: 50 for NIFTY, 100 for BANKNIFTY / SENSEX.
3. Matching option quotes provide premium metadata only and never replace the target strike.
4. Non-negotiable Trading Safety Invariants:
   - read_only = True
   - is_order_action = False
   - broker_api_called = False
   - allowed_for_live_execution = False
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union


@dataclass(slots=True, frozen=True)
class Mode5StrikeSelection:
    """Result of Mode 5 target strike resolution and optional matching quote lookup."""
    target_strike: float
    option_type: str  # "CE" or "PE"
    selected_premium: float
    anchor_price: float
    lower_band: float
    upper_band: float
    selection_mode: str  # "GEOMETRIC_TARGET_QUOTE" or "GEOMETRIC_SLINGSHOT_FALLBACK"
    step_size: float
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


class SentinelOptionStrikeResolver:
    """Strike resolver preserving the strategy target and exchange intervals."""

    EXCHANGE_STEP_SIZES: dict[str, float] = {
        "NIFTY": 50.0,
        "BANKNIFTY": 100.0,
        "SENSEX": 100.0,
    }

    def __init__(self) -> None:
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False
        self.allowed_for_live_execution = False

    @classmethod
    def get_step_size(cls, index_name: str) -> float:
        """Returns strict exchange step size for the given index."""
        idx = (index_name or "").strip().upper()
        return cls.EXCHANGE_STEP_SIZES.get(idx, 50.0)

    @classmethod
    def round_to_exchange_step(cls, raw_strike: float, index_name: str) -> float:
        """Rounds a strike to the nearest valid exchange strike step."""
        step = cls.get_step_size(index_name)
        if step <= 0:
            return float(raw_strike)
        return round(raw_strike / step) * step

    @classmethod
    def resolve_mode5_strike(
        cls,
        index_name: str,
        direction: str,  # "CE" or "PE"
        anchor_price: float,
        geometric_strike: float,
        live_quotes: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Mode5StrikeSelection:
        """Resolve the strategy target strike and optionally find its current premium.

        The geometric RP target determines the contract strike. Quotes can supply
        premium metadata only when they match that strike and option type; they
        cannot substitute a different strike based on premium or anchor proximity.
        """
        step = cls.get_step_size(index_name)
        dir_clean = (direction or "").strip().upper()
        if dir_clean not in {"CE", "PE"}:
            dir_clean = "CE"

        safe_anchor = max(0.0, float(anchor_price))
        lower_band = round(0.50 * safe_anchor, 2)
        upper_band = round(0.75 * safe_anchor, 2)
        selected_strike: float = cls.round_to_exchange_step(geometric_strike, index_name)
        selected_premium: float = 0.0
        selection_mode = "GEOMETRIC_SLINGSHOT_FALLBACK"

        if live_quotes:
            matching_target_quotes: list[float] = []
            for quote in live_quotes:
                q_dir = str(quote.get("direction") or quote.get("option_type") or "").upper()
                if not q_dir:
                    sym = str(quote.get("symbol") or "").upper()
                    if "CE" in sym:
                        q_dir = "CE"
                    elif "PE" in sym:
                        q_dir = "PE"

                if q_dir != dir_clean:
                    continue

                raw_stk = float(quote.get("strike") or quote.get("strike_price") or 0.0)
                if raw_stk <= 0.0:
                    # Try parsing strike from symbol
                    sym = str(quote.get("symbol") or "").upper()
                    for part in sym.split():
                        if part.isdigit() and len(part) >= 4:
                            raw_stk = float(part)
                            break
                if raw_stk <= 0.0:
                    continue

                # Ensure strike strictly aligns with exchange step size
                stk = cls.round_to_exchange_step(raw_stk, index_name)
                ltp = float(quote.get("ltp") or quote.get("price") or quote.get("last_price") or 0.0)
                if ltp <= 0.0:
                    continue

                if stk == selected_strike:
                    matching_target_quotes.append(ltp)

            if matching_target_quotes:
                # Deterministic metadata when a provider yields duplicate entries;
                # quote price does not affect the selected strike.
                selected_premium = matching_target_quotes[0]
                selection_mode = "GEOMETRIC_TARGET_QUOTE"

        return Mode5StrikeSelection(
            target_strike=float(selected_strike),
            option_type=dir_clean,
            selected_premium=round(float(selected_premium), 2),
            anchor_price=round(safe_anchor, 2),
            lower_band=lower_band,
            upper_band=upper_band,
            selection_mode=selection_mode,
            step_size=step,
            read_only=True,
            is_order_action=False,
            broker_api_called=False,
            allowed_for_live_execution=False,
        )
