from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import time
from typing import Any, Optional


_NUMERIC_QUANT = Decimal("0.00000001")


def _normalize_number(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        value = Decimal(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        value = Decimal(str(value))
    if isinstance(value, Decimal):
        try:
            normalized = value.quantize(_NUMERIC_QUANT).normalize()
            return format(normalized, "f")
        except (InvalidOperation, ValueError):
            return None
    return value


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    qty: int
    order_type: str
    limit_price: Optional[float]
    product: str
    exchange: str
    strategy_id: str
    timestamp_bucket: int
    instrument_type: str = "option"
    expiry: Optional[str] = None
    strike: Optional[float] = None
    right: Optional[str] = None
    multiplier: Optional[float] = None
    trade_id: Optional[str] = None
    intent_type: str = "PLACE_ORDER"
    client_order_id: Optional[str] = None
    status: str = "NEW"

    @staticmethod
    def compute_client_order_id(
        *,
        trade_id: str | None,
        intent_type: str | None,
        symbol: str | None,
        side: str | None,
    ) -> str:
        canonical = "|".join(
            [
                str(trade_id or "").strip(),
                str(intent_type or "PLACE_ORDER").strip().upper(),
                str(symbol or "").strip().upper(),
                str(side or "").strip().upper(),
            ]
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_canonical_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Runtime idempotency fields are intentionally excluded from legacy
        # approval hash semantics to preserve backward compatibility.
        for runtime_key in ("trade_id", "intent_type", "client_order_id", "status"):
            payload.pop(runtime_key, None)
        canonical: dict[str, Any] = {}
        for key in sorted(payload.keys()):
            value = payload.get(key)
            canonical[key] = None if value is None else _normalize_number(value)
        return canonical

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_canonical_dict(),
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=True,
        )

    def intent_hash(self) -> str:
        raw = self.canonical_json().encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def canonical_dict(self) -> dict[str, Any]:
        return self.to_canonical_dict()

    def order_intent_hash(self) -> str:
        return self.intent_hash()

    @classmethod
    def from_trade(
        cls,
        trade: Any,
        mode: str,
        *,
        default_exchange: str = "NFO",
        default_product: str = "MIS",
    ) -> "OrderIntent":
        def pick(name: str, default: Any = None) -> Any:
            if isinstance(trade, dict):
                return trade.get(name, default)
            return getattr(trade, name, default)

        limit_price = pick("entry_price")
        if limit_price is None and str(pick("order_type", "LIMIT")).upper() == "MARKET":
            limit_price = None
        timestamp_bucket = int(pick("timestamp_bucket", 0) or 0)
        if timestamp_bucket <= 0:
            timestamp_bucket = int(time.time() // 60)
        qty_raw = pick("qty", pick("quantity", 0))
        try:
            qty = int(qty_raw or 0)
        except Exception:
            qty = 0
        right = pick("right") or pick("option_type")
        instrument_type = (
            pick("instrument_type")
            or ("option" if right or pick("strike") is not None else "future" if pick("expiry") else "equity")
        )
        strategy_id = str(pick("strategy_id", pick("strategy", "UNKNOWN")) or "UNKNOWN")
        trade_id = str(pick("trade_id", pick("id", pick("signal_id", ""))) or "").strip() or None
        intent_type = str(pick("intent_type", "PLACE_ORDER") or "PLACE_ORDER").upper()
        symbol = str(pick("symbol", "") or "")
        side = str(pick("side", "") or "").upper()
        client_order_id = cls.compute_client_order_id(
            trade_id=trade_id,
            intent_type=intent_type,
            symbol=symbol,
            side=side,
        )
        return cls(
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=str(pick("order_type", "LIMIT") or "LIMIT").upper(),
            limit_price=None if limit_price is None else float(limit_price),
            product=str(pick("product", default_product) or default_product).upper(),
            exchange=str(pick("exchange", default_exchange) or default_exchange).upper(),
            strategy_id=strategy_id,
            timestamp_bucket=timestamp_bucket,
            instrument_type=str(instrument_type).lower(),
            expiry=pick("expiry"),
            strike=pick("strike"),
            right=right,
            multiplier=pick("multiplier"),
            trade_id=trade_id,
            intent_type=intent_type,
            client_order_id=client_order_id,
            status=str(pick("intent_status", "NEW") or "NEW").upper(),
        )
