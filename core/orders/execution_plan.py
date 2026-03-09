from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Any


def _pick(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _fallback_snapshot_id(symbol: str, token: int, side: str, qty: int, bucket: int) -> str:
    raw = f"{symbol}|{token}|{side}|{qty}|{bucket}"
    return f"snap_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _fallback_decision_id(symbol: str, token: int, side: str, qty: int, bucket: int) -> str:
    raw = f"decision|{symbol}|{token}|{side}|{qty}|{bucket}"
    return f"dec_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _fallback_token(symbol: str) -> int:
    text = str(symbol or "").strip() or "UNKNOWN"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return int(digest, 16) % 1_000_000_000 + 1


@dataclass(frozen=True)
class ExecutionPlan:
    symbol: str
    token: int
    side: str
    qty: int
    entry_type: str
    stop_loss: float | None
    take_profit: float | None
    snapshot_id: str
    decision_id: str
    mode: str
    signal_id: str
    timestamp_epoch: float

    def validate(self) -> None:
        if not str(self.symbol or "").strip():
            raise ValueError("execution_plan_missing_symbol")
        if int(self.token) <= 0:
            raise ValueError("execution_plan_invalid_token")
        if str(self.side or "").upper() not in {"BUY", "SELL"}:
            raise ValueError("execution_plan_invalid_side")
        if int(self.qty) <= 0:
            raise ValueError("execution_plan_invalid_qty")
        if not str(self.entry_type or "").strip():
            raise ValueError("execution_plan_missing_entry_type")
        if not str(self.snapshot_id or "").strip():
            raise ValueError("execution_plan_missing_snapshot_id")
        if not str(self.decision_id or "").strip():
            raise ValueError("execution_plan_missing_decision_id")
        if float(self.timestamp_epoch) <= 0:
            raise ValueError("execution_plan_invalid_timestamp_epoch")

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "token": int(self.token),
            "side": self.side,
            "qty": int(self.qty),
            "entry_type": self.entry_type,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "snapshot_id": self.snapshot_id,
            "decision_id": self.decision_id,
            "mode": self.mode,
            "signal_id": self.signal_id,
            "timestamp_epoch": float(self.timestamp_epoch),
        }

    def canonical_json(self) -> str:
        return json.dumps(self.as_dict(), separators=(",", ":"), sort_keys=True, ensure_ascii=True)

    @classmethod
    def from_trade(cls, trade: Any, *, mode: str) -> "ExecutionPlan":
        symbol = str(_pick(trade, "symbol", "") or "").strip()
        side = str(_pick(trade, "side", "") or "").strip().upper()
        entry_type = str(_pick(trade, "order_type", "LIMIT") or "LIMIT").strip().upper()
        qty_raw = _pick(trade, "qty", _pick(trade, "quantity", 0))
        token_raw = _pick(trade, "instrument_token", _pick(trade, "token", 0))
        snapshot_id = str(_pick(trade, "snapshot_id", "") or "").strip()
        decision_id = str(
            _pick(
                trade,
                "decision_id",
                _pick(trade, "trade_id", _pick(trade, "signal_id", "")),
            )
            or ""
        ).strip()
        signal_id = str(_pick(trade, "signal_id", decision_id) or decision_id).strip()
        ts_raw = _pick(trade, "timestamp_epoch", None)
        if ts_raw is None:
            ts_raw = _pick(trade, "ts_epoch", None)
        if ts_raw is None:
            ts_raw = time.time()
        try:
            ts_epoch = float(ts_raw)
        except Exception:
            ts_epoch = float(time.time())
        try:
            qty = int(qty_raw)
        except Exception:
            qty = 0
        try:
            token = int(token_raw)
        except Exception:
            token = 0
        if token <= 0:
            token = _fallback_token(symbol)
        bucket = int(ts_epoch // 60)
        if not snapshot_id:
            snapshot_id = _fallback_snapshot_id(symbol, token, side, qty, bucket)
        if not decision_id:
            decision_id = _fallback_decision_id(symbol, token, side, qty, bucket)
        if not signal_id:
            signal_id = decision_id
        plan = cls(
            symbol=symbol,
            token=token,
            side=side,
            qty=qty,
            entry_type=entry_type,
            stop_loss=_pick(trade, "stop_loss"),
            take_profit=_pick(trade, "target", _pick(trade, "take_profit")),
            snapshot_id=snapshot_id,
            decision_id=decision_id,
            mode=str(mode or "SIM").upper(),
            signal_id=signal_id,
            timestamp_epoch=ts_epoch,
        )
        plan.validate()
        return plan
