from __future__ import annotations
import json
from datetime import timedelta
from pathlib import Path
from .aggregation import Bar, aggregate_complete
from .indicators import ema, atr_wilder, rsi_wilder, wma
from .storage import JsonlPublisher, StateStore, canonical_hash

class ShadowObserver:
    def __init__(self, contract_path: str | Path, event_path: str | Path, state_path: str | Path):
        self.contract = json.loads(Path(contract_path).read_text())
        self.publisher = JsonlPublisher(event_path)
        self.store = StateStore(state_path)
        self.state = self.store.load()
        self._bars5: dict[str, list[Bar]] = {}

    def ingest(self, bar: Bar) -> None:
        if bar.completion <= bar.start:
            raise ValueError("bar must be completed")
        self._bars5.setdefault(bar.symbol, []).append(bar)
        self._bars5[bar.symbol].sort(key=lambda item: item.start)
        self._evaluate_symbol(bar.symbol)

    def _emit(self, event_type: str, payload: dict) -> str:
        base = {"event_type": event_type, "contract_hash": self.contract["contract_hash"],
            "research_only": True, "rankable": False, "displayable": True,
            "executable": False, "execution_allowed": False, "allowed_for_live_execution": False,
            "broker_api_called": False, "is_order_action": False, **payload}
        event_id = canonical_hash(base)
        if event_id in self.state["emitted_ids"]:
            return event_id
        base["event_id"] = event_id
        self.publisher.append(base)
        self.state["emitted_ids"].append(event_id)
        self.store.save(self.state)
        return event_id

    def _hm_state(self, bars75: list[Bar]) -> str | None:
        closes = [bar.close for bar in bars75]
        rsi = rsi_wilder(closes, 9)
        rsi_wma = wma(rsi, 21)
        ema_input = [0.0 if value is None else float(value) for value in rsi]
        rsi_ema = ema(ema_input, 3)
        idx = len(closes) - 1
        if idx < 0 or rsi[idx] is None or rsi_wma[idx] is None or rsi_ema[idx] is None:
            return None
        if rsi[idx] > 50 and rsi[idx] > rsi_wma[idx] and rsi_ema[idx] > rsi_wma[idx]:
            return "LONG"
        if rsi[idx] < 50 and rsi[idx] < rsi_wma[idx] and rsi_ema[idx] < rsi_wma[idx]:
            return "SHORT"
        return None

    def _evaluate_symbol(self, symbol: str) -> None:
        bars5 = self._bars5[symbol]
        bars15 = aggregate_complete(bars5, 3)
        bars75 = aggregate_complete(bars15, 5)
        if len(bars15) < 22 or len(bars75) < 22:
            return
        closes = [bar.close for bar in bars15]
        highs = [bar.high for bar in bars15]
        lows = [bar.low for bar in bars15]
        middle = ema(closes, 20)
        atr = atr_wilder(highs, lows, closes, 10)
        idx = len(bars15) - 1
        if any(value is None for value in (middle[idx], middle[idx - 1], atr[idx], atr[idx - 1])):
            return
        hm = self._hm_state([bar for bar in bars75 if bar.completion <= bars15[idx].completion])
        if hm is None:
            return
        upper_prev = float(middle[idx - 1]) + 2 * float(atr[idx - 1])
        lower_prev = float(middle[idx - 1]) - 2 * float(atr[idx - 1])
        upper = float(middle[idx]) + 2 * float(atr[idx])
        lower = float(middle[idx]) - 2 * float(atr[idx])
        signal = bars15[idx]
        previous = bars15[idx - 1]
        candle_range = max(signal.high - signal.low, 1e-9)
        body = abs(signal.close - signal.open)
        long_signal = (previous.close <= upper_prev and signal.close > upper and float(middle[idx]) > float(middle[idx - 1])
            and hm == "LONG" and body / float(atr[idx]) >= 0.35 and (signal.close - signal.low) / candle_range >= 0.75)
        short_signal = (previous.close >= lower_prev and signal.close < lower and float(middle[idx]) < float(middle[idx - 1])
            and hm == "SHORT" and body / float(atr[idx]) >= 0.35 and (signal.close - signal.low) / candle_range <= 0.25)
        if not (long_signal or short_signal):
            return
        direction = "LONG" if long_signal else "SHORT"
        session_open = next(bar.open for bar in bars5 if bar.session_id == signal.session_id)
        extension = ((signal.close - session_open) if long_signal else (session_open - signal.close)) / float(atr[idx])
        key = f"{signal.session_id}:{symbol}"
        if extension > 1.5:
            self._emit("KELTNER_HM_EVENT_REJECTED", {"symbol": symbol, "session_id": signal.session_id,
                "decision_time": signal.completion.isoformat(), "direction": direction,
                "reason": "EXTENSION_GT_1_5_ATR"})
            return
        pending = self.state["pending"].get(key)
        if pending and pending.get("decision_time") == signal.completion.isoformat():
            return
        self.state["pending"][key] = {"symbol": symbol, "session_id": signal.session_id,
            "direction": direction, "decision_time": signal.completion.isoformat(),
            "signal_high": signal.high, "signal_low": signal.low, "atr": atr[idx],
            "extension_atr": extension, "stage": "WAIT_CONFIRMATION"}
        self.store.save(self.state)
        self._emit("KELTNER_HM_EVENT_DETECTED", self.state["pending"][key])
        future = [bar for bar in bars5 if bar.start >= signal.completion]
        if len(future) < 2:
            return
        confirm, entry = future[0], future[1]
        passed = confirm.close > signal.high if long_signal else confirm.close < signal.low
        if not passed:
            self._emit("KELTNER_HM_CONFIRMATION_FAILED", {"symbol": symbol, "session_id": signal.session_id,
                "decision_time": signal.completion.isoformat(), "confirmation_time": confirm.completion.isoformat(),
                "direction": direction})
            self.state["pending"].pop(key, None)
            self.store.save(self.state)
            return
        self._emit("KELTNER_HM_CONFIRMATION_PASSED", {"symbol": symbol, "session_id": signal.session_id,
            "decision_time": signal.completion.isoformat(), "confirmation_time": confirm.completion.isoformat(),
            "direction": direction})
        shadow_id = self._emit("KELTNER_HM_SHADOW_ENTRY", {"symbol": symbol, "session_id": signal.session_id,
            "decision_time": signal.completion.isoformat(), "confirmation_time": confirm.completion.isoformat(),
            "entry_time": entry.start.isoformat(), "entry_price": entry.open, "direction": direction,
            "primary_horizon_minutes": 60})
        self.state["pending"][key].update({"stage": "ACTIVE", "entry_time": entry.start.isoformat(),
            "entry_price": entry.open, "shadow_id": shadow_id})
        self.store.save(self.state)
        exits = [bar for bar in bars5 if bar.completion >= entry.start + timedelta(minutes=60)]
        if exits:
            exit_bar = exits[0]
            signed = ((exit_bar.close / entry.open) - 1) * 10000 * (1 if long_signal else -1)
            self._emit("KELTNER_HM_SHADOW_OUTCOME", {"symbol": symbol, "session_id": signal.session_id,
                "shadow_id": shadow_id, "entry_time": entry.start.isoformat(),
                "exit_time": exit_bar.completion.isoformat(), "entry_price": entry.open,
                "exit_price": exit_bar.close, "direction": direction,
                "gross_return_bps": signed, "net_5bps_return_bps": signed - 5.0})
            self.state["pending"].pop(key, None)
            self.store.save(self.state)
