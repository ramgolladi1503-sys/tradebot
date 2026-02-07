import time
import json
from pathlib import Path
from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.paper_fill_simulator import PaperFillSimulator
from core.trade_store import insert_execution_stat
from core.fill_quality import log_fill_quality
from core.execution_quality import execution_quality_score

class ExecutionRouter:
    """
    Routes trades to SIM/PAPER/LIVE modes.
    LIVE mode is a stub until order placement is enabled.
    """
    def __init__(self):
        self.engine = ExecutionEngine()
        self.paper_sim = PaperFillSimulator(
            timeout_sec=getattr(cfg, "EXEC_SIM_TIMEOUT_SEC", 3.0),
            poll_sec=getattr(cfg, "EXEC_SIM_POLL_SEC", 0.25),
        )

    def execute(self, trade, bid, ask, volume, depth=None, snapshot_fn=None):
        if cfg.EXECUTION_MODE == "SIM":
            # record intent even in SIM mode
            self._record_intent(trade, bid, ask, volume, depth=depth, note="sim intent")
            if snapshot_fn is None or not callable(snapshot_fn):
                return False, None, {
                    "decision_mid": None,
                    "decision_spread": None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": "no_quote_fn",
                }
            first = snapshot_fn()
            if not first:
                return False, None, {
                    "decision_mid": None,
                    "decision_spread": None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": "no_quote",
                }
            bid = first.get("bid", bid)
            ask = first.get("ask", ask)
            limit_price = trade.entry_price or self.engine.build_limit_price(trade.side, bid, ask)
            start_ts = time.time()
            filled, price, report = self._simulate_limit(
                trade, bid, ask, limit_price, snapshot_fn=snapshot_fn
            )
            try:
                insert_execution_stat({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "instrument": trade.instrument,
                    "slippage_bps": self.engine.slippage_bps,
                    "latency_ms": 0,
                    "fill_ratio": 1.0 if filled else 0.0,
                })
            except Exception:
                pass
            self._record_fill_quality(trade, bid, ask, limit_price, start_ts, filled, price, report)
            return filled, price, report
        if cfg.EXECUTION_MODE == "PAPER":
            self._record_intent(trade, bid, ask, volume, depth=depth, note="paper intent")
            if snapshot_fn is None or not callable(snapshot_fn):
                return False, None, {
                    "decision_mid": None,
                    "decision_spread": None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": "no_quote_fn",
                }
            first = snapshot_fn()
            if not first:
                return False, None, {
                    "decision_mid": None,
                    "decision_spread": None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": "no_quote",
                }
            bid = first.get("bid", bid)
            ask = first.get("ask", ask)
            limit_price = trade.entry_price or self.engine.build_limit_price(trade.side, bid, ask)
            start_ts = time.time()
            filled, price, report = self.paper_sim.simulate(
                trade,
                limit_price,
                snapshot_fn,
                max_replaces=getattr(cfg, "EXEC_MAX_REPLACE", 2),
                reprice_pct=getattr(cfg, "EXEC_REPRICE_PCT", 0.002),
                max_chase_pct=getattr(cfg, "EXEC_MAX_CHASE_PCT", 0.002),
                max_quote_age_sec=getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0),
                max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.015),
                spread_widen_pct=getattr(cfg, "EXEC_SPREAD_WIDEN_PCT", 0.5),
            )
            try:
                insert_execution_stat({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "instrument": trade.instrument,
                    "slippage_bps": self.engine.slippage_bps,
                    "latency_ms": 0,
                    "fill_ratio": 1.0 if filled else 0.0,
                })
            except Exception:
                pass
            self._record_fill_quality(trade, bid, ask, limit_price, start_ts, filled, price, report)
            return filled, price, report
        if cfg.EXECUTION_MODE == "LIVE":
            # Live placement guarded by config (manual approval / safety)
            if not getattr(cfg, "ALLOW_LIVE_PLACEMENT", False):
                self._record_intent(trade, bid, ask, volume, depth=depth)
                return False, None, {
                    "decision_mid": None,
                    "decision_spread": None,
                    "fill_price": None,
                    "slippage": None,
                    "reason_if_aborted": "live_placement_disabled",
                }
            # TODO: integrate actual broker order placement
            self._record_intent(trade, bid, ask, volume, depth=depth, note="live placement requested")
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "live_not_implemented",
            }
        return False, None, {
            "decision_mid": None,
            "decision_spread": None,
            "fill_price": None,
            "slippage": None,
            "reason_if_aborted": "unknown_execution_mode",
        }

    def _simulate_limit(self, trade, bid, ask, limit_price, snapshot_fn=None):
        if snapshot_fn is None or not callable(snapshot_fn):
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote_fn",
            }
        return self.paper_sim.simulate(
            trade,
            limit_price,
            snapshot_fn,
            max_replaces=getattr(cfg, "EXEC_MAX_REPLACE", 2),
            reprice_pct=getattr(cfg, "EXEC_REPRICE_PCT", 0.002),
            max_chase_pct=getattr(cfg, "EXEC_MAX_CHASE_PCT", 0.002),
            max_quote_age_sec=getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0),
            max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.015),
            spread_widen_pct=getattr(cfg, "EXEC_SPREAD_WIDEN_PCT", 0.5),
        )

    def _record_fill_quality(self, trade, bid, ask, limit_price, start_ts, filled, fill_price, report):
        decision_mid = None
        decision_spread = None
        if bid and ask:
            decision_mid = round((bid + ask) / 2.0, 2)
            decision_spread = round(max(ask - bid, 0.0), 4)
        slippage_vs_mid = None
        if fill_price is not None and decision_mid is not None:
            if trade.side == "BUY":
                slippage_vs_mid = round(fill_price - decision_mid, 4)
            else:
                slippage_vs_mid = round(decision_mid - fill_price, 4)
        time_to_fill = None
        if start_ts:
            time_to_fill = round(time.time() - start_ts, 4)
        payload = {
            "ts": time.time(),
            "trade_id": getattr(trade, "trade_id", None),
            "symbol": getattr(trade, "symbol", None),
            "instrument": getattr(trade, "instrument", None),
            "side": getattr(trade, "side", None),
            "decision_bid": bid,
            "decision_ask": ask,
            "decision_mid": decision_mid,
            "decision_spread": decision_spread,
            "limit_price": limit_price,
            "fill_price": fill_price if filled else None,
            "not_filled_reason": report.get("reason_if_aborted") if report else None,
            "time_to_fill": time_to_fill if filled else None,
            "slippage_vs_mid": slippage_vs_mid if filled else None,
        }
        if report:
            payload.update({
                "queue_position": report.get("queue_position"),
                "queue_priority": report.get("queue_priority"),
                "urgency": report.get("urgency"),
                "urgency_score": report.get("urgency_score"),
                "impact_estimate": report.get("impact_estimate"),
                "vwap": report.get("vwap"),
                "alpha_decay": report.get("alpha_decay"),
                "adverse_selection": report.get("adverse_selection"),
                "implementation_shortfall": report.get("implementation_shortfall"),
                "opportunity_cost": report.get("opportunity_cost"),
                "execution_quality_score": report.get("execution_quality_score"),
            })
        if payload.get("execution_quality_score") is None:
            payload["execution_quality_score"] = execution_quality_score(payload)
        log_fill_quality(payload)

    def _record_intent(self, trade, bid, ask, volume, depth=None, note="live placement disabled"):
        try:
            path = Path("logs/execution_intents.jsonl")
            payload = {
                "ts": time.time(),
                "trade_id": getattr(trade, "trade_id", None),
                "symbol": getattr(trade, "symbol", None),
                "instrument": getattr(trade, "instrument", None),
                "side": getattr(trade, "side", None),
                "entry": getattr(trade, "entry_price", None),
                "qty": getattr(trade, "qty", None),
                "bid": bid,
                "ask": ask,
                "volume": volume,
                "depth_top": None,
                "note": note,
            }
            try:
                if depth and isinstance(depth, dict):
                    b = depth.get("buy", [{}])[0].get("price")
                    a = depth.get("sell", [{}])[0].get("price")
                    payload["depth_top"] = {"bid": b, "ask": a}
            except Exception:
                pass
            path.parent.mkdir(exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass
