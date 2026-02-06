import json
import time
from pathlib import Path
from config import config as cfg
from core.execution_engine import ExecutionEngine
from core.trade_store import insert_execution_stat

class ExecutionRouter:
    """
    Routes trades to SIM/PAPER/LIVE modes.
    LIVE mode is a stub until order placement is enabled.
    """
    def __init__(self):
        self.engine = ExecutionEngine()

    def execute(self, trade, bid, ask, volume, depth=None):
        if cfg.EXECUTION_MODE == "SIM":
            # record intent even in SIM mode
            self._record_intent(trade, bid, ask, volume, depth=depth, note="sim intent")
            filled, price = self.engine.simulate_order_slicing(trade, bid, ask, volume, depth=depth)
            try:
                insert_execution_stat({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "instrument": trade.instrument,
                    "slippage_bps": self.engine.slippage_bps,
                    "latency_ms": 0,
                    "fill_ratio": 1.0 if filled else 0.0
                })
            except Exception:
                pass
            return filled, price
        if cfg.EXECUTION_MODE == "PAPER":
            self._record_intent(trade, bid, ask, volume, depth=depth, note="paper intent")
            filled, price = self.engine.simulate_order_slicing(trade, bid, ask, volume, depth=depth)
            try:
                insert_execution_stat({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "instrument": trade.instrument,
                    "slippage_bps": self.engine.slippage_bps,
                    "latency_ms": 0,
                    "fill_ratio": 1.0 if filled else 0.0
                })
            except Exception:
                pass
            return filled, price
        if cfg.EXECUTION_MODE == "LIVE":
            # Live placement guarded by config (manual approval / safety)
            if not getattr(cfg, "ALLOW_LIVE_PLACEMENT", False):
                self._record_intent(trade, bid, ask, volume, depth=depth)
                return False, None
            # TODO: integrate actual broker order placement
            self._record_intent(trade, bid, ask, volume, depth=depth, note="live placement requested")
            return False, None
        return False, None

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
                "note": note,
            }
            path.parent.mkdir(exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass
