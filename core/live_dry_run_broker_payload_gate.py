"""Live dry-run broker payload gate.

This module validates a broker-order-shaped payload in dry-run mode and returns a
read-only gate report. It does not submit, modify, cancel, or place orders. It
also does not call brokers, write files, mutate ledgers, or wire runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

LIVE_DRY_RUN_BROKER_PAYLOAD_GATE_SCHEMA_VERSION = 1

BROKER_PAYLOAD_DRY_RUN_APPROVED = "BROKER_PAYLOAD_DRY_RUN_APPROVED"
BROKER_PAYLOAD_DRY_RUN_BLOCKED = "BROKER_PAYLOAD_DRY_RUN_BLOCKED"

ALLOWED_EXCHANGES: frozenset[str] = frozenset({"NFO", "BFO"})
ALLOWED_TRANSACTION_TYPES: frozenset[str] = frozenset({"BUY", "SELL"})
ALLOWED_ORDER_TYPES: frozenset[str] = frozenset({"MARKET", "LIMIT", "SL", "SL-M"})
ALLOWED_PRODUCTS: frozenset[str] = frozenset({"MIS", "NRML"})
ALLOWED_VARIETIES: frozenset[str] = frozenset({"regular", "amo"})
ALLOWED_VALIDITIES: frozenset[str] = frozenset({"DAY", "IOC"})


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return None


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _upper(value: Any) -> str | None:
    text = _text(value)
    return text.upper() if text else None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if out == out else None


def _list_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


@dataclass(frozen=True)
class LiveDryRunBrokerPayloadGateReport:
    schema_version: int
    state: str
    read_only: bool
    dry_run: bool
    is_order_action: bool
    append: bool
    broker_order_action: bool
    live_order_action: bool
    payload_id: str | None
    exchange: str | None
    tradingsymbol: str | None
    transaction_type: str | None
    order_type: str | None
    product: str | None
    variety: str | None
    validity: str | None
    quantity: int | None
    price: float | None
    trigger_price: float | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    normalized_payload: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["normalized_payload"] = dict(self.normalized_payload)
        payload["metadata"] = dict(self.metadata)
        return payload


def build_live_dry_run_broker_payload_gate_report(payload: Any) -> LiveDryRunBrokerPayloadGateReport:
    """Validate a dry-run broker payload without taking broker/order action."""

    data = _to_mapping(payload)
    blockers: list[str] = []
    warnings: list[str] = []

    if data is None:
        blockers.append("BROKER_PAYLOAD_MISSING")
        data = {}

    blockers.extend(_list_of_strings(data.get("blockers")))
    warnings.extend(_list_of_strings(data.get("warnings")))

    if _bool(data.get("broker_order_action"), default=False):
        blockers.append("BROKER_ORDER_ACTION_REJECTED")
    if _bool(data.get("live_order_action"), default=False):
        blockers.append("LIVE_ORDER_ACTION_REJECTED")
    if _bool(data.get("is_order_action"), default=False):
        blockers.append("ORDER_ACTION_REJECTED")
    if _bool(data.get("append"), default=False):
        blockers.append("APPEND_TRUE_REJECTED")

    dry_run = _bool(data.get("dry_run"), default=False)
    if not dry_run:
        blockers.append("DRY_RUN_REQUIRED")

    payload_id = _text(data.get("payload_id"))
    if payload_id is None:
        blockers.append("PAYLOAD_ID_MISSING")

    exchange = _upper(data.get("exchange"))
    if exchange is None:
        blockers.append("EXCHANGE_MISSING")
    elif exchange not in ALLOWED_EXCHANGES:
        blockers.append("EXCHANGE_UNSUPPORTED")

    tradingsymbol = _text(data.get("tradingsymbol"))
    if tradingsymbol is None:
        blockers.append("TRADINGSYMBOL_MISSING")

    transaction_type = _upper(data.get("transaction_type"))
    if transaction_type is None:
        blockers.append("TRANSACTION_TYPE_MISSING")
    elif transaction_type not in ALLOWED_TRANSACTION_TYPES:
        blockers.append("TRANSACTION_TYPE_UNSUPPORTED")

    order_type = _upper(data.get("order_type"))
    if order_type is None:
        blockers.append("ORDER_TYPE_MISSING")
    elif order_type not in ALLOWED_ORDER_TYPES:
        blockers.append("ORDER_TYPE_UNSUPPORTED")

    product = _upper(data.get("product"))
    if product is None:
        blockers.append("PRODUCT_MISSING")
    elif product not in ALLOWED_PRODUCTS:
        blockers.append("PRODUCT_UNSUPPORTED")

    variety = _text(data.get("variety"))
    if variety is None:
        blockers.append("VARIETY_MISSING")
    elif variety not in ALLOWED_VARIETIES:
        blockers.append("VARIETY_UNSUPPORTED")

    validity = _upper(data.get("validity"))
    if validity is None:
        blockers.append("VALIDITY_MISSING")
    elif validity not in ALLOWED_VALIDITIES:
        blockers.append("VALIDITY_UNSUPPORTED")

    quantity = _as_int(data.get("quantity"))
    if quantity is None:
        blockers.append("QUANTITY_MISSING")
    elif quantity <= 0:
        blockers.append("QUANTITY_NON_POSITIVE")

    price = _as_float(data.get("price"))
    trigger_price = _as_float(data.get("trigger_price"))

    if order_type == "LIMIT" and (price is None or price <= 0.0):
        blockers.append("LIMIT_PRICE_REQUIRED")
    if order_type == "MARKET" and price not in (None, 0.0):
        blockers.append("MARKET_PRICE_MUST_BE_EMPTY_OR_ZERO")
    if order_type in {"SL", "SL-M"} and (trigger_price is None or trigger_price <= 0.0):
        blockers.append("STOPLOSS_TRIGGER_PRICE_REQUIRED")
    if price is not None and price < 0.0:
        blockers.append("PRICE_NEGATIVE")
    if trigger_price is not None and trigger_price < 0.0:
        blockers.append("TRIGGER_PRICE_NEGATIVE")

    normalized_payload = {
        "payload_id": payload_id,
        "dry_run": dry_run,
        "exchange": exchange,
        "tradingsymbol": tradingsymbol,
        "transaction_type": transaction_type,
        "order_type": order_type,
        "product": product,
        "variety": variety,
        "validity": validity,
        "quantity": quantity,
        "price": price,
        "trigger_price": trigger_price,
        "broker_order_action": False,
        "live_order_action": False,
        "is_order_action": False,
        "append": False,
    }

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    approved = not normalized_blockers

    return LiveDryRunBrokerPayloadGateReport(
        schema_version=LIVE_DRY_RUN_BROKER_PAYLOAD_GATE_SCHEMA_VERSION,
        state=BROKER_PAYLOAD_DRY_RUN_APPROVED if approved else BROKER_PAYLOAD_DRY_RUN_BLOCKED,
        read_only=True,
        dry_run=dry_run,
        is_order_action=False,
        append=False,
        broker_order_action=False,
        live_order_action=False,
        payload_id=payload_id,
        exchange=exchange,
        tradingsymbol=tradingsymbol,
        transaction_type=transaction_type,
        order_type=order_type,
        product=product,
        variety=variety,
        validity=validity,
        quantity=quantity,
        price=price,
        trigger_price=trigger_price,
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        normalized_payload=normalized_payload,
        metadata={
            "gate": "live_dry_run_broker_payload_gate_v1",
            "scope": "read_only_no_broker_calls_no_order_submission_no_runtime_wiring",
            "schema_version": LIVE_DRY_RUN_BROKER_PAYLOAD_GATE_SCHEMA_VERSION,
        },
    )


__all__ = [
    "BROKER_PAYLOAD_DRY_RUN_APPROVED",
    "BROKER_PAYLOAD_DRY_RUN_BLOCKED",
    "LIVE_DRY_RUN_BROKER_PAYLOAD_GATE_SCHEMA_VERSION",
    "LiveDryRunBrokerPayloadGateReport",
    "build_live_dry_run_broker_payload_gate_report",
]
