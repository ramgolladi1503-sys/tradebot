from __future__ import annotations

import time
import uuid
from typing import Any

from core.trade_schema import Trade
from config import config as cfg

class ShortPremiumBuilder:
    """
    Elite Algotrader Module: Short-Premium Strategy Builder
    Generates SELL_STRANGLE and IRON_CONDOR candidates during RANGE_BOUND regimes.
    """

    def __init__(self, execution_engine=None):
        self.execution = execution_engine

    def generate_candidates(self, market_data: dict[str, Any]) -> list[Trade]:
        """
        Generates short premium candidates if the regime is RANGE_BOUND.
        Returns a list of single-leg executable Trades or multi-leg wrappers (for manual review).
        """
        candidates = []
        
        regime = str(market_data.get("regime", "")).upper()
        if regime != "RANGE_BOUND":
            return candidates  # Only generate in RANGE_BOUND

        symbol = market_data.get("symbol")
        if not symbol:
            return candidates

        ltp = float(market_data.get("ltp") or 0.0)
        if ltp <= 0:
            return candidates

        chain = market_data.get("option_chain", [])
        if not chain:
            return candidates
            
        atr = float(market_data.get("atr") or 0.0)
        if atr <= 0:
            # Fallback to 0.5% of LTP if ATR is missing
            atr = ltp * 0.005
            
        strikes = sorted({c.get("strike") for c in chain if c.get("strike") is not None})
        if not strikes:
            return candidates

        def _nearest_strike(val):
            return min(strikes, key=lambda s: abs(s - val))

        from core.time_utils import to_ist, is_market_open_ist
        from datetime import datetime, timezone
        
        ts_epoch = float(market_data.get("timestamp_epoch", market_data.get("ts_epoch") or time.time()))
        dt_ist = to_ist(datetime.fromtimestamp(ts_epoch, tz=timezone.utc))
        market_open = is_market_open_ist(now=dt_ist)

        def _get_option(strike, opt_type):
            for c in chain:
                if c.get("strike") == strike and c.get("type") == opt_type:
                    return c
            return None

        # 1. Strangle (Sell OTM Call, Sell OTM Put)
        # Typically 1 ATR out
        call_strike = _nearest_strike(ltp + atr * 1.5)
        put_strike = _nearest_strike(ltp - atr * 1.5)
        
        # 2. Iron Condor Wings (Buy further OTM)
        # Typically 2 ATR out
        wing_call_strike = _nearest_strike(ltp + atr * 2.5)
        wing_put_strike = _nearest_strike(ltp - atr * 2.5)

        # For now, we yield intent dictionaries that the orchestrator or advisory can pick up.
        # Since this codebase primarily uses single-leg Trade dataclasses, 
        # we will generate pseudo-Trade objects representing the package.

        if not getattr(cfg, "SHORT_PREMIUM_ENABLED", False):
            return candidates

        package_id = f"SHORT-PREM-{symbol}-{int(time.time())}"
        
        exec_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
        # Ensure Short Premium is always treated as PAPER if the engine is running LIVE
        is_live_override = (exec_mode == "LIVE")
        
        # Determine if we can build a Strangle or must enforce Iron Condor
        allow_naked = getattr(cfg, "ALLOW_NAKED_STRANGLE_PAPER", False)
        
        if not allow_naked:
            # Build Iron Condor (Buy Wing PE, Sell Put PE, Sell Call CE, Buy Wing CE)
            # Ensure strikes layout is correct: wing_put < put < call < wing_call
            if not (wing_put_strike < put_strike < call_strike < wing_call_strike):
                return candidates
                
            long_put_opt = _get_option(wing_put_strike, "PE")
            short_put_opt = _get_option(put_strike, "PE")
            short_call_opt = _get_option(call_strike, "CE")
            long_call_opt = _get_option(wing_call_strike, "CE")
            
            if long_put_opt and short_put_opt and short_call_opt and long_call_opt:
                expiry = short_call_opt.get("expiry")
                t = Trade(
                    trade_id=f"{package_id}-IC",
                    timestamp=market_data.get("timestamp_epoch", time.time()),
                    symbol=symbol,
                    instrument="OPT",
                    instrument_type="CE",
                    right="CALL",
                    instrument_id=short_call_opt.get("instrument_token"),
                    instrument_token=short_call_opt.get("instrument_token"),
                    strike=call_strike,
                    expiry=expiry,
                    expiry_date=expiry,
                    side="SELL",  # Short Premium
                    entry_price=short_call_opt.get("last_price", 0.0),
                    stop_loss=short_call_opt.get("last_price", 0.0) * 2.0,  
                    target=short_call_opt.get("last_price", 0.0) * 0.1,     
                    qty=1,
                    capital_at_risk=5000.0,
                    expected_slippage=0.01,
                    confidence=1.0,
                    strategy="RANGE_BOUND_IC",
                    regime=regime,
                    strategy_family="IRON_CONDOR",
                    qty_lots=1,
                )
                
                legs = [
                    {
                        "instrument_token": long_put_opt.get("instrument_token"),
                        "symbol": symbol,
                        "strike": wing_put_strike,
                        "type": "PE",
                        "side": "BUY",
                        "qty": 1,
                        "entry_price": long_put_opt.get("last_price", 0.0),
                    },
                    {
                        "instrument_token": short_put_opt.get("instrument_token"),
                        "symbol": symbol,
                        "strike": put_strike,
                        "type": "PE",
                        "side": "SELL",
                        "qty": 1,
                        "entry_price": short_put_opt.get("last_price", 0.0),
                    },
                    {
                        "instrument_token": short_call_opt.get("instrument_token"),
                        "symbol": symbol,
                        "strike": call_strike,
                        "type": "CE",
                        "side": "SELL",
                        "qty": 1,
                        "entry_price": short_call_opt.get("last_price", 0.0),
                    },
                    {
                        "instrument_token": long_call_opt.get("instrument_token"),
                        "symbol": symbol,
                        "strike": wing_call_strike,
                        "type": "CE",
                        "side": "BUY",
                        "qty": 1,
                        "entry_price": long_call_opt.get("last_price", 0.0),
                    },
                ]
                
                net_premium = (
                    short_put_opt.get("last_price", 0.0) + short_call_opt.get("last_price", 0.0)
                ) - (
                    long_put_opt.get("last_price", 0.0) + long_call_opt.get("last_price", 0.0)
                )
                put_width = abs(put_strike - wing_put_strike)
                call_width = abs(wing_call_strike - call_strike)
                max_width = max(put_width, call_width)
                max_loss = max(0.0, max_width - net_premium)
                
                object.__setattr__(t, "legs", legs)
                object.__setattr__(t, "max_loss", max_loss)
                object.__setattr__(t, "rank_score", 100.0)
                
                from core.strategy_requirements import validate_strategy_requirements
                valid, vetoes = validate_strategy_requirements(
                    strategy_family="IRON_CONDOR",
                    snapshot=market_data,
                    trade=t,
                    now_epoch=time.time()
                )
                
                if not market_open:
                    if "MARKET_CLOSED" not in vetoes:
                        vetoes.append("MARKET_CLOSED")
                    if "SESSION_CLOSED" not in vetoes:
                        vetoes.append("SESSION_CLOSED")
                    valid = False
                    
                if is_live_override:
                    if "LIVE_MODE_SHORT_PREMIUM_BLOCKED" not in vetoes:
                        vetoes.append("LIVE_MODE_SHORT_PREMIUM_BLOCKED")
                    valid = False

                if valid:
                    object.__setattr__(t, "candidate_status", "near_executable")
                    object.__setattr__(t, "execution_allowed", True)
                    object.__setattr__(t, "broker_route_allowed", True)
                    object.__setattr__(t, "live_order_allowed", False)
                    object.__setattr__(t, "veto_codes", [])
                    object.__setattr__(t, "veto_stage", None)
                else:
                    object.__setattr__(t, "candidate_status", "structurally_valid")
                    object.__setattr__(t, "execution_allowed", False)
                    object.__setattr__(t, "broker_route_allowed", False)
                    object.__setattr__(t, "live_order_allowed", False)
                    object.__setattr__(t, "veto_codes", vetoes)
                    object.__setattr__(t, "veto_stage", "STRATEGY_VAL")
                    if vetoes:
                        object.__setattr__(t, "veto_reason", vetoes[0])
                        object.__setattr__(t, "veto_reasons", vetoes)
                
                candidates.append(t)
        else:
            # Build Strangle (Sell Put, Sell Call)
            if not (put_strike < call_strike):
                return candidates
                
            short_put_opt = _get_option(put_strike, "PE")
            short_call_opt = _get_option(call_strike, "CE")
            
            if short_put_opt and short_call_opt:
                expiry = short_call_opt.get("expiry")
                t = Trade(
                    trade_id=f"{package_id}-STRANGLE",
                    timestamp=market_data.get("timestamp_epoch", time.time()),
                    symbol=symbol,
                    instrument="OPT",
                    instrument_type="CE",
                    right="CALL",
                    instrument_id=short_call_opt.get("instrument_token"),
                    instrument_token=short_call_opt.get("instrument_token"),
                    strike=call_strike,
                    expiry=expiry,
                    expiry_date=expiry,
                    side="SELL",  # Short Premium
                    entry_price=short_call_opt.get("last_price", 0.0),
                    stop_loss=short_call_opt.get("last_price", 0.0) * 2.0,  
                    target=short_call_opt.get("last_price", 0.0) * 0.1,     
                    qty=1,
                    capital_at_risk=5000.0,
                    expected_slippage=0.01,
                    confidence=1.0,
                    strategy="RANGE_BOUND_STRANGLE",
                    regime=regime,
                    strategy_family="SELL_STRANGLE",
                    qty_lots=1,
                )
                
                legs = [
                    {
                        "instrument_token": short_put_opt.get("instrument_token"),
                        "symbol": symbol,
                        "strike": put_strike,
                        "type": "PE",
                        "side": "SELL",
                        "qty": 1,
                        "entry_price": short_put_opt.get("last_price", 0.0),
                    },
                    {
                        "instrument_token": short_call_opt.get("instrument_token"),
                        "symbol": symbol,
                        "strike": call_strike,
                        "type": "CE",
                        "side": "SELL",
                        "qty": 1,
                        "entry_price": short_call_opt.get("last_price", 0.0),
                    },
                ]
                
                object.__setattr__(t, "legs", legs)
                object.__setattr__(t, "max_loss", float("inf"))
                object.__setattr__(t, "rank_score", 100.0)
                
                from core.strategy_requirements import validate_strategy_requirements
                valid, vetoes = validate_strategy_requirements(
                    strategy_family="SELL_STRANGLE",
                    snapshot=market_data,
                    trade=t,
                    now_epoch=time.time()
                )
                
                # If paper-only research flag is enabled, bypass the uncapped risk veto
                if allow_naked and not is_live_override:
                    vetoes = [v for v in vetoes if v != "UNCAPPED_RISK_STRUCTURE"]
                    valid = (len(vetoes) == 0)
                    
                if not market_open:
                    if "MARKET_CLOSED" not in vetoes:
                        vetoes.append("MARKET_CLOSED")
                    if "SESSION_CLOSED" not in vetoes:
                        vetoes.append("SESSION_CLOSED")
                    valid = False
                    
                if is_live_override:
                    if "LIVE_MODE_SHORT_PREMIUM_BLOCKED" not in vetoes:
                        vetoes.append("LIVE_MODE_SHORT_PREMIUM_BLOCKED")
                    valid = False

                if valid:
                    object.__setattr__(t, "candidate_status", "near_executable")
                    object.__setattr__(t, "execution_allowed", True)
                    object.__setattr__(t, "broker_route_allowed", True)
                    object.__setattr__(t, "live_order_allowed", False)
                    object.__setattr__(t, "veto_codes", [])
                    object.__setattr__(t, "veto_stage", None)
                else:
                    object.__setattr__(t, "candidate_status", "structurally_valid")
                    object.__setattr__(t, "execution_allowed", False)
                    object.__setattr__(t, "broker_route_allowed", False)
                    object.__setattr__(t, "live_order_allowed", False)
                    object.__setattr__(t, "veto_codes", vetoes)
                    object.__setattr__(t, "veto_stage", "STRATEGY_VAL")
                    if vetoes:
                        object.__setattr__(t, "veto_reason", vetoes[0])
                        object.__setattr__(t, "veto_reasons", vetoes)
                
                candidates.append(t)

        return candidates
