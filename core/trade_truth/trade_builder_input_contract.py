"""Authoritative input builder for TradeBuilder in canonical observer runtime.

Guarantees:
- Zero synthetic defaults (no hardcoded 'NIFTY', no 0.0 price fallback).
- Fail-closed validation on mandatory symbol and market state.
- Real feed truth, regime, and session lineage preservation.
- Deterministic hashing of input payload.
"""

from __future__ import annotations

from typing import Any, Mapping
from core.trade_truth.decision_hash import compute_deterministic_hash


def build_canonical_tradebuilder_input(
    *,
    symbol: str,
    ltp: float,
    regime: Mapping[str, Any],
    cycle_id: str,
    session_id: str,
    source_sha: str,
    market_open: bool | None = None,
    execution_mode: str | None = None,
    feed_truth: Mapping[str, Any] | None = None,
    option_chain: list[dict[str, Any]] | None = None,
    extra_market_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and build authoritative market_data dictionary for TradeBuilder.

    Fails closed (raises ValueError) if symbol, price, regime, cycle_id,
    session_id, or source_sha are missing or invalid.
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_SYMBOL")

    try:
        price = float(ltp)
    except (TypeError, ValueError):
        raise ValueError("TRADEBUILDER_INPUT_INVALID_LTP") from None

    if price <= 0.0:
        raise ValueError("TRADEBUILDER_INPUT_NON_POSITIVE_LTP")

    if not isinstance(regime, Mapping) or not regime:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_REGIME")

    cid = str(cycle_id or "").strip()
    if not cid:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_CYCLE_ID")

    sid = str(session_id or "").strip()
    if not sid:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_SESSION_ID")

    sha = str(source_sha or "").strip()
    if not sha:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_SOURCE_SHA")

    payload: dict[str, Any] = {
        "symbol": sym,
        "ltp": price,
        "close": price,
        "regime": dict(regime),
        "cycle_id": cid,
        "run_id": cid,
        "session_id": sid,
        "source_sha": sha,
        "read_only": True,
        "is_order_action": False,
        "broker_write_authority": False,
        "order_authority": False,
    }

    if market_open is not None:
        payload["market_open"] = bool(market_open)

    if execution_mode is not None:
        payload["execution_mode"] = str(execution_mode).strip().upper()

    if feed_truth is not None:
        payload["feed_truth"] = dict(feed_truth)

    if option_chain is not None:
        payload["option_chain"] = list(option_chain)

    if extra_market_data:
        for k, v in extra_market_data.items():
            if k not in payload:
                payload[k] = v

    return payload


def hash_tradebuilder_input(payload: Mapping[str, Any]) -> str:
    """Deterministic hash of authoritative TradeBuilder input payload."""
    return compute_deterministic_hash(payload)
