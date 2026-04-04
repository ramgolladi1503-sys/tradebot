from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger(__name__)


class OpenAlgoError(RuntimeError):
    """Base OpenAlgo integration error."""


class OpenAlgoConfigError(OpenAlgoError):
    """Raised when OpenAlgo configuration is incomplete or invalid."""


class OpenAlgoHttpError(OpenAlgoError):
    """Raised when OpenAlgo returns a transport or HTTP failure."""


class OpenAlgoApiError(OpenAlgoError):
    """Raised when OpenAlgo returns an application-level failure."""


@dataclass(frozen=True)
class OpenAlgoOrderRequest:
    strategy: str
    symbol: str
    action: str
    exchange: str
    price_type: str
    product: str
    quantity: int
    price: float | None = None
    trigger_price: float | None = None
    disclosed_quantity: int | None = None

    def as_payload(self, api_key: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "apikey": api_key,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "action": self.action,
            "exchange": self.exchange,
            "pricetype": self.price_type,
            "product": self.product,
            "quantity": int(self.quantity),
        }
        if self.price is not None:
            payload["price"] = float(self.price)
        if self.trigger_price is not None:
            payload["trigger_price"] = float(self.trigger_price)
        if self.disclosed_quantity is not None:
            payload["disclosed_quantity"] = int(self.disclosed_quantity)
        return payload


class OpenAlgoClient:
    """
    Small stdlib-only client for OpenAlgo V1 REST endpoints.

    Docs used for request shape and endpoint behavior:
    - /api/v1/placeorder
    - /api/v1/orderstatus
    - /api/v1/cancelorder
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        api_key: str | None = None,
        timeout_sec: float | None = None,
    ) -> None:
        resolved_host = str(host or os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")).strip().rstrip("/")
        resolved_key = str(api_key or os.getenv("OPENALGO_API_KEY", "")).strip()
        resolved_timeout = float(timeout_sec or os.getenv("OPENALGO_TIMEOUT_SEC", "8.0"))
        if not resolved_host:
            raise OpenAlgoConfigError("missing_openalgo_host")
        if not resolved_key:
            raise OpenAlgoConfigError("missing_openalgo_api_key")
        if resolved_timeout <= 0:
            raise OpenAlgoConfigError("invalid_openalgo_timeout")
        self.host = resolved_host
        self.api_key = resolved_key
        self.timeout_sec = resolved_timeout

    @staticmethod
    def enabled() -> bool:
        return str(os.getenv("OPENALGO_ENABLED", "false")).strip().lower() == "true"

    def _url(self, path: str) -> str:
        suffix = str(path or "").strip()
        if not suffix.startswith("/"):
            suffix = f"/{suffix}"
        return f"{self.host}{suffix}"

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            self._url(path),
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        started = time.time()
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                if not isinstance(parsed, dict):
                    raise OpenAlgoHttpError("openalgo_non_dict_response")
                parsed.setdefault("_http_status", getattr(resp, "status", 200))
                parsed.setdefault("_latency_ms", round((time.time() - started) * 1000.0, 2))
                return parsed
        except urllib_error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OpenAlgoHttpError(f"openalgo_http_{exc.code}:{detail}") from exc
        except urllib_error.URLError as exc:
            raise OpenAlgoHttpError(f"openalgo_transport_error:{exc}") from exc
        except TimeoutError as exc:
            raise OpenAlgoHttpError("openalgo_timeout") from exc

    @staticmethod
    def _normalize_status(value: Any) -> str:
        text = str(value or "").strip().upper()
        if text in {"SUCCESS", "COMPLETE", "COMPLETED", "FILLED", "EXECUTED"}:
            return "SUCCESS"
        if text in {"OPEN", "PENDING", "TRIGGER PENDING", "TRIGGER_PENDING", "PLACED", "SUBMITTED"}:
            return "OPEN"
        if text in {"CANCELLED", "CANCELED"}:
            return "CANCELLED"
        if text in {"REJECTED", "FAILED", "FAILURE", "ERROR"}:
            return "REJECTED"
        return text or "UNKNOWN"

    def place_order(self, order: OpenAlgoOrderRequest) -> dict[str, Any]:
        response = self._post("/api/v1/placeorder", order.as_payload(self.api_key))
        status = self._normalize_status(response.get("status"))
        order_id = response.get("orderid") or response.get("order_id")
        if status in {"REJECTED", "ERROR", "UNKNOWN"} and not order_id:
            raise OpenAlgoApiError(json.dumps(response, sort_keys=True, default=str))
        return {
            "status": status,
            "order_id": str(order_id) if order_id is not None else None,
            "raw": response,
            "latency_ms": response.get("_latency_ms"),
        }

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        payload = {"apikey": self.api_key, "orderid": str(order_id)}
        response = self._post("/api/v1/cancelorder", payload)
        return {"status": self._normalize_status(response.get("status")), "raw": response}

    def fetch_order_status(self, order_id: str) -> dict[str, Any]:
        payload = {"apikey": self.api_key, "orderid": str(order_id)}
        response = self._post("/api/v1/orderstatus", payload)
        return {"status": self._normalize_status(response.get("status") or response.get("orderstatus")), "raw": response}


def build_openalgo_order_request(trade: Any) -> OpenAlgoOrderRequest:
    side = str(getattr(trade, "side", "") or "").strip().upper()
    if side not in {"BUY", "SELL"}:
        raise OpenAlgoConfigError("invalid_trade_side_for_openalgo")

    qty_raw = getattr(trade, "qty", getattr(trade, "quantity", 0))
    try:
        qty = int(qty_raw)
    except Exception as exc:
        raise OpenAlgoConfigError("invalid_trade_qty_for_openalgo") from exc
    if qty <= 0:
        raise OpenAlgoConfigError("non_positive_trade_qty_for_openalgo")

    order_type = str(getattr(trade, "order_type", getattr(trade, "entry_type", "LIMIT")) or "LIMIT").strip().upper()
    supported_price_types = {"MARKET", "LIMIT", "SL", "SL-M"}
    if order_type not in supported_price_types:
        if order_type == "SLM":
            order_type = "SL-M"
        else:
            order_type = "LIMIT"

    symbol = str(getattr(trade, "symbol", getattr(trade, "tradingsymbol", "")) or "").strip()
    exchange = str(getattr(trade, "exchange", "NFO") or "NFO").strip().upper()
    product = str(getattr(trade, "product", "MIS") or "MIS").strip().upper()
    strategy = str(
        getattr(trade, "strategy_name", None)
        or getattr(trade, "strategy_id", None)
        or getattr(trade, "strategy", None)
        or "tradebot"
    ).strip()
    if not symbol:
        raise OpenAlgoConfigError("missing_trade_symbol_for_openalgo")

    price = getattr(trade, "entry_price", None)
    trigger_price = getattr(trade, "trigger_price", None)
    disclosed_quantity = getattr(trade, "disclosed_quantity", None)

    if order_type == "MARKET":
        price = None
    elif price is None:
        # OpenAlgo accepts 0 for optional price, but forcing a real limit price is safer.
        raise OpenAlgoConfigError("missing_limit_price_for_openalgo")

    return OpenAlgoOrderRequest(
        strategy=strategy,
        symbol=symbol,
        action=side,
        exchange=exchange,
        price_type=order_type,
        product=product,
        quantity=qty,
        price=(None if price is None else float(price)),
        trigger_price=(None if trigger_price is None else float(trigger_price)),
        disclosed_quantity=(None if disclosed_quantity is None else int(disclosed_quantity)),
    )
