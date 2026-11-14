from __future__ import annotations
import json
from datetime import datetime, timedelta
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
        rows = self._bars5.setdefault(bar.symbol, [])
        if any(existing.start == bar.start and existing.session_id == bar.session_id for existing in rows):
            return
        rows.append(bar)
        rows.sort(key=lambda item: item.start)
        self._advance_pending(bar)
        self._evaluate_new_signal(bar.symbol, bar)

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
        valid_rsi = [float(value) for value in rsi if value is not None]
        if len(valid_rsi) < 3 or not rsi or rsi[-1] is None or rsi_wma[-1] is None:
            return None
        rsi_ema = ema(valid_rsi, 3)[-1]
        if rsi_ema is None:
            return None
        if rsi[-1] > 50 and rsi[-1] > rsi_wma[-1] and rsi_ema > rsi_wma[-1]:
            return "LONG"
        if rsi[-1] < 50 and rsi[-1] < rsi_wma[-1] and rsi_ema < rsi_wma[-1]:
            return "SHORT"
        return None

    def _advance_pending(self, bar: Bar) -> None:
        key = f"{bar.session_id}:{bar.symbol}"
        pending = self.state["pending"].get(key)
        if not pending:
            return
        stage = pending["stage"]
        direction = pending["direction"]
        if stage == "WAIT_CONFIRMATION":
            expected_start = datetime.fromisoformat(pending["decision_time"])
            if bar.start < expected_start:
                return
            if bar.start > expected_start:
                self._emit("KELTNER_HM_CONFIRMATION_FAILED", {**pending,
                    "confirmation_time": bar.completion.isoformat(), "reason": "MISSING_EXPECTED_CONFIRMATION_BAR"})
                self.state["pending"].pop(key, None)
                self.store.save(self.state)
                return
            passed = bar.close > pending["signal_high"] if direction == "LONG" else bar.close < pending["signal_low"]
            if not passed:
                self._emit("KELTNER_HM_CONFIRMATION_FAILED", {**pending,
                    "confirmation_time": bar.completion.isoformat(), "reason": "EXTREME_NOT_CLEARED"})
                self.state["pending"].pop(key, None)
                self.store.save(self.state)
                return
            self._emit("KELTNER_HM_CONFIRMATION_PASSED", {**pending,
                "confirmation_time": bar.completion.isoformat()})
            pending.update({"stage": "WAIT_ENTRY", "confirmation_time": bar.completion.isoformat()})
            self.store.save(self.state)
            return
        if stage == "WAIT_ENTRY":
            expected_start = datetime.fromisoformat(pending["confirmation_time"])
            if bar.start < expected_start:
                return
            if bar.start > expected_start:
                self._emit("KELTNER_HM_ENTRY_REJECTED", {**pending,
                    "observed_bar_start": bar.start.isoformat(), "reason": "MISSING_EXPECTED_ENTRY_BAR"})
                self.state["pending"].pop(key, None)
                self.store.save(self.state)
                return
            shadow_id = self._emit("KELTNER_HM_SHADOW_ENTRY", {**pending,
                "entry_time": bar.start.isoformat(), "entry_price": bar.open,
                "primary_horizon_minutes": 60})
            pending.update({"stage": "ACTIVE", "entry_time": bar.start.isoformat(),
                "entry_price": bar.open, "shadow_id": shadow_id})
            self.store.save(self.state)
            return
        if stage == "ACTIVE":
            entry_time = datetime.fromisoformat(pending["entry_time"])
            if bar.completion < entry_time + timedelta(minutes=60):
                return
            multiplier = 1 if direction == "LONG" else -1
            signed = ((bar.close / float(pending["entry_price"])) - 1) * 10000 * multiplier
            self._emit("KELTNER_HM_SHADOW_OUTCOME", {**pending,
                "exit_time": bar.completion.isoformat(), "exit_price": bar.close,
                "gross_return_bps": signed, "net_5bps_return_bps": signed - 5.0})
            self.state["pending"].pop(key, None)
            self.store.save(self.state)

    def _evaluate_new_signal(self, symbol: str, latest_bar: Bar) -> None:
        bars5 = self._bars5[symbol]
        bars15 = aggregate_complete(bars5, 3)
        if not bars15 or bars15[-1].completion != latest_bar.completion:
            return
        bars75 = aggregate_complete(bars15, 5)
        if len(bars15) < 22 or len(bars75) < 22:
            return
        signal = bars15[-1]
        key = f"{signal.session_id}:{symbol}"
        if key in self.state["pending"]:
            return
        closes = [bar.close for bar in bars15]
        highs = [bar.high for bar in bars15]
        lows = [bar.low for bar in bars15]
        middle = ema(closes, 20)
        atr = atr_wilder(highs, lows, closes, 10)
        idx = len(bars15) - 1
        if any(value is None for value in (middle[idx], middle[idx - 1], atr[idx], atr[idx - 1])):
            return
        hm = self._hm_state([bar for bar in bars75 if bar.completion <= signal.completion])
        if hm is None:
            return
        previous = bars15[-2]
        upper_prev = float(middle[idx - 1]) + 2 * float(atr[idx - 1])
        lower_prev = float(middle[idx - 1]) - 2 * float(atr[idx - 1])
        upper = float(middle[idx]) + 2 * float(atr[idx])
        lower = float(middle[idx]) - 2 * float(atr[idx])
        candle_range = max(signal.high - signal.low, 1e-9)
        body = abs(signal.close - signal.open)
        long_signal = (previous.close <= upper_prev and signal.close > upper and float(middle[idx]) > float(middle[idx - 1])
            and hm == "LONG" and body / float(atr[idx]) >= 0.35 and (signal.close - signal.low) / candle_range >= 0.75)
        short_signal = (previous.close >= lower_prev and signal.close < lower and float(middle[idx]) < float(middle[idx - 1])
            and hm == "SHORT" and body / float(atr[idx]) >= 0.35 and (signal.close - signal.low) / candle_range <= 0.25)
        if not (long_signal or short_signal):
            return
        direction = "LONG" if long_signal else "SHORT"
        session_rows = [bar for bar in bars5 if bar.session_id == signal.session_id]
        session_open = session_rows[0].open
        extension = ((signal.close - session_open) if long_signal else (session_open - signal.close)) / float(atr[idx])
        if extension > 1.5:
            self._emit("KELTNER_HM_EVENT_REJECTED", {"symbol": symbol, "session_id": signal.session_id,
                "decision_time": signal.completion.isoformat(), "direction": direction,
                "reason": "EXTENSION_GT_1_5_ATR", "extension_atr": extension})
            return
        pending = {"symbol": symbol, "session_id": signal.session_id, "direction": direction,
            "decision_time": signal.completion.isoformat(), "signal_high": signal.high,
            "signal_low": signal.low, "atr": atr[idx], "extension_atr": extension,
            "stage": "WAIT_CONFIRMATION"}
        self.state["pending"][key] = pending
        self.store.save(self.state)
        self._emit("KELTNER_HM_EVENT_DETECTED", pending)
