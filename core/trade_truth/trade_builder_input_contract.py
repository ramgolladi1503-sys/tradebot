"""Authoritative input builder for TradeBuilder in canonical observer runtime.

Guarantees:
- Zero synthetic defaults (no hardcoded 'NIFTY', no 0.0 price fallback).
- Fail-closed validation on mandatory symbol and market state.
- Real feed truth, regime, and session lineage preservation.
- Deterministic hashing of input payload.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from core.trade_truth.decision_hash import compute_deterministic_hash


def parse_iso_or_epoch_seconds(value: Any) -> float | None:
    """Parse an authoritative event timestamp into UTC epoch seconds.

    Returns ``None`` for missing, malformed, non-finite, or timezone-naive
    timestamps. Epoch milliseconds are normalized to seconds. The caller must
    decide whether ``None`` means BLOCKED/UNKNOWN; it must never be converted
    to a causal PASS.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed != parsed or parsed in (float("inf"), float("-inf")):
            return None
        if abs(parsed) >= 1_000_000_000_000:
            parsed /= 1000.0
        return parsed

    text = str(value or "").strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        numeric = None
    if numeric is not None:
        if numeric != numeric or numeric in (float("inf"), float("-inf")):
            return None
        if abs(numeric) >= 1_000_000_000_000:
            numeric /= 1000.0
        return numeric

    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        dt = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).timestamp()


def build_canonical_tradebuilder_input(
    market_data: Mapping[str, Any] | None = None,
    *,
    symbol: str | None = None,
    ltp: float | None = None,
    regime: Mapping[str, Any] | None = None,
    cycle_id: str | None = None,
    session_id: str | None = None,
    source_sha: str | None = None,
    market_open: bool | None = None,
    execution_mode: str | None = None,
    feed_truth: Mapping[str, Any] | None = None,
    option_chain: list[dict[str, Any]] | None = None,
    extra_market_data: Mapping[str, Any] | None = None,
    read_only: bool = True,
    event_timestamp: str | float | None = None,
) -> dict[str, Any]:
    """Validate and build authoritative market_data dictionary for TradeBuilder.

    Shared by both production orchestrator and canonical observer runtime.
    Fails closed (raises ValueError) if symbol, price, regime, cycle_id,
    session_id, or source_sha are missing or invalid.
    """
    base_data = dict(market_data) if isinstance(market_data, Mapping) else {}

    raw_sym = symbol if symbol is not None else base_data.get("symbol")
    sym = str(raw_sym or "").strip().upper()
    if not sym:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_SYMBOL")

    raw_ltp = ltp if ltp is not None else base_data.get("ltp", base_data.get("close", base_data.get("entry")))
    try:
        price = float(raw_ltp)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ValueError("TRADEBUILDER_INPUT_INVALID_LTP") from None

    if price <= 0.0:
        raise ValueError("TRADEBUILDER_INPUT_NON_POSITIVE_LTP")

    raw_regime = regime if regime is not None else base_data.get("regime")
    if not isinstance(raw_regime, Mapping) or not raw_regime:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_REGIME")

    raw_cid = cycle_id if cycle_id is not None else base_data.get("cycle_id", base_data.get("run_id"))
    cid = str(raw_cid or "").strip()
    if not cid:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_CYCLE_ID")

    raw_sid = session_id if session_id is not None else base_data.get("session_id")
    sid = str(raw_sid or "").strip()
    if not sid:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_SESSION_ID")

    raw_sha = source_sha if source_sha is not None else base_data.get("source_sha")
    sha = str(raw_sha or "").strip()
    if not sha:
        raise ValueError("TRADEBUILDER_INPUT_MISSING_SOURCE_SHA")

    payload: dict[str, Any] = dict(base_data)
    payload.update({
        "symbol": sym,
        "ltp": price,
        "close": price,
        "regime": dict(raw_regime),
        "cycle_id": cid,
        "run_id": cid,
        "session_id": sid,
        "source_sha": sha,
    })

    if read_only:
        payload["read_only"] = True
        payload["is_order_action"] = False
        payload["broker_write_authority"] = False
        payload["order_authority"] = False

    raw_mopen = market_open if market_open is not None else base_data.get("market_open")
    if raw_mopen is not None:
        payload["market_open"] = bool(raw_mopen)

    raw_exec_mode = execution_mode if execution_mode is not None else base_data.get("execution_mode")
    if raw_exec_mode is not None:
        payload["execution_mode"] = str(raw_exec_mode).strip().upper()

    raw_feed_truth = feed_truth if feed_truth is not None else base_data.get("feed_truth")
    if raw_feed_truth is not None and isinstance(raw_feed_truth, Mapping):
        payload["feed_truth"] = dict(raw_feed_truth)

    raw_opt_chain = option_chain if option_chain is not None else base_data.get("option_chain")
    if raw_opt_chain is not None and isinstance(raw_opt_chain, (list, tuple)):
        payload["option_chain"] = list(raw_opt_chain)

    raw_ts = event_timestamp if event_timestamp is not None else base_data.get("event_timestamp", base_data.get("timestamp"))
    if raw_ts is not None:
        payload["event_timestamp"] = raw_ts

    if extra_market_data and isinstance(extra_market_data, Mapping):
        for k, v in extra_market_data.items():
            if k not in payload:
                payload[k] = v

    return payload


def hash_tradebuilder_input(payload: Mapping[str, Any]) -> str:
    """Deterministic hash of authoritative TradeBuilder input payload."""
    return compute_deterministic_hash(payload)
