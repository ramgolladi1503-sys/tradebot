"""Pairs Execution Coordinator for atomic leg routing and margin validation."""

import time
import logging
from config import config as cfg
from core.candidate_intent import CandidateIntent
from core.pretrade_risk_engine import PreTradeRiskEngine, PreTradeRiskRequest

logger = logging.getLogger(__name__)

class PairsExecutionCoordinator:
    def __init__(self, execution_router, risk_engine: PreTradeRiskEngine = None):
        self.execution_router = execution_router
        self.risk_engine = risk_engine
        self.pairs_cfg = getattr(cfg, "PAIRS_TRADING_UNIVERSE", {})

    def _get_combined_margin(self, intent: CandidateIntent, price_a: float, price_b: float) -> float:
        """Estimate combined margin for both legs. In a real system, this queries the broker API."""
        # This is a naive estimation for demonstration. True margin requires SPAN margin calculation.
        pair_info = self.pairs_cfg.get(intent.instrument, {})
        beta = intent.metadata.get("beta", pair_info.get("hedge_ratio", 1.0))
        
        # Assume 15% margin requirement for indices
        margin_a = price_a * 0.15
        margin_b = (price_b * beta) * 0.15
        
        # True pairs get margin benefit (hedged), let's assume a 50% margin offset
        combined_margin = (margin_a + margin_b) * 0.5
        return combined_margin

    def route_pair(self, intent: CandidateIntent, current_prices: dict):
        """Atomically routes Leg A and Leg B and handles Unwind if leg-in fails."""
        if intent.intent_type != "ENTRY":
            return {"status": "IGNORED", "reason": "not_an_entry"}
            
        pair_info = self.pairs_cfg.get(intent.instrument)
        if not pair_info:
            return {"status": "FAILED", "reason": "unknown_pair"}
            
        leg_a = pair_info.get("leg_a")
        leg_b = pair_info.get("leg_b")
        beta = intent.metadata.get("beta", pair_info.get("hedge_ratio", 1.0))
        
        price_a = current_prices.get(leg_a)
        price_b = current_prices.get(leg_b)
        
        if not price_a or not price_b:
            return {"status": "FAILED", "reason": "missing_prices_for_execution"}

        # Combined Pre-trade Margin Validation
        combined_margin = self._get_combined_margin(intent, price_a, price_b)
        
        margin_request = PreTradeRiskRequest(
            signal_id=intent.candidate_intent_id,
            instrument=intent.instrument,
            side=intent.direction,
            quantity=1.0,
            timestamp=time.time(),
            exposure=combined_margin,
            margin_required=combined_margin
        )
        
        if self.risk_engine:
            risk_report = self.risk_engine.evaluate(margin_request)
            if not getattr(risk_report, 'allowed', True):
                logger.warning(f"Pairs execution blocked by pre-trade risk: {getattr(risk_report, 'reason', 'failed')}")
                return {"status": "REJECTED", "reason": getattr(risk_report, 'reason', 'failed')}

        # Determine leg directions
        dir_a = "SELL" if intent.direction == "SHORT" else "BUY"
        dir_b = "BUY" if intent.direction == "SHORT" else "SELL"
        
        # Route Leg A
        leg_a_trade = {
            "instrument": leg_a,
            "direction": dir_a,
            "quantity": 1,
            "strategy_id": intent.strategy_id
        }
        res_a = self.execution_router.execute(leg_a_trade, price_a, price_a, 1)
        
        if res_a.get("status") in ("REJECTED", "FAILED"):
            return {"status": "FAILED", "reason": "leg_a_failed"}

        # Route Leg B
        leg_b_trade = {
            "instrument": leg_b,
            "direction": dir_b,
            "quantity": beta,
            "strategy_id": intent.strategy_id
        }
        res_b = self.execution_router.execute(leg_b_trade, price_b, price_b, beta)
        
        # Unwind Logic (Leg-in Risk Mitigation)
        if res_b.get("status") in ("REJECTED", "FAILED"):
            logger.critical(f"Leg B failed for {intent.instrument}. Triggering UNWIND for Leg A.")
            unwind_dir = "BUY" if dir_a == "SELL" else "SELL"
            unwind_trade = {
                "instrument": leg_a,
                "direction": unwind_dir,
                "quantity": 1,
                "strategy_id": intent.strategy_id,
                "order_type": "MARKET"
            }
            # Execute unwind immediately at market
            self.execution_router.execute(unwind_trade, price_a, price_a, 1)
            return {"status": "UNWOUND", "reason": "leg_b_failed_unwind_triggered"}

        return {"status": "FILLED", "leg_a": res_a, "leg_b": res_b}
