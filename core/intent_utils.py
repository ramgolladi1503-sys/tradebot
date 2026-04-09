from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from typing import Any

BLOCK_ENTRY = {"", "missing", "non_exec", "adv_only", "queue_only", "blocked"}
BLOCK_ACTION = {"ADV_ONLY", "QUEUE_ONLY", "BLOCK", "BLOCKED", "NO_TRADE"}
BLOCK_PERMISSION = {"ADV_ONLY", "QUEUE_ONLY", "BLOCK", "BLOCKED"}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _set(obj: Any, key: str, value: Any) -> Any:
    if isinstance(obj, dict):
        out = dict(obj)
        out[key] = value
        return out
    if is_dataclass(obj):
        return replace(obj, **{key: value})
    setattr(obj, key, value)
    return obj


def build_intent(candidate: Any) -> dict[str, Any] | None:
    permission = str(_get(candidate, "permission") or "").upper()
    action = str(_get(candidate, "final_action") or "").upper()
    status = str(_get(candidate, "execution_entry_status") or "").lower()

    if permission in BLOCK_PERMISSION or action in BLOCK_ACTION or status in BLOCK_ENTRY:
        return None

    token = _get(candidate, "instrument_token")
    symbol = _get(candidate, "tradingsymbol")
    entry = _get(candidate, "entry_price") or _get(candidate, "entry")

    if not token or not symbol or entry is None:
        return None

    return {"symbol": _get(candidate, "symbol"), "token": token, "entry": entry}


def attach_intent(candidate: Any) -> Any:
    intent = build_intent(candidate)
    candidate = _set(candidate, "intent", intent)
    return candidate


def finalize(symbol: str, candidate: Any | None) -> dict[str, Any]:
    if not candidate:
        return {"symbol": symbol, "status": "NO_TRADE"}
    if _get(candidate, "intent"):
        return {"symbol": symbol, "status": "EXECUTABLE", "intent": _get(candidate, "intent")}
    return {"symbol": symbol, "status": "ADVISORY"}
