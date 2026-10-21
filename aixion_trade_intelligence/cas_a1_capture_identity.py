from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence
import json


FROZEN_DEVELOPMENT_SYMBOLS = (
    "ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK","BAJAJ-AUTO",
    "BAJAJFINSV","BAJFINANCE","BEL","BHARTIARTL","CIPLA","COALINDIA","DRREDDY","EICHERMOT",
    "ETERNAL","GRASIM","HCLTECH","HDFCBANK","HDFCLIFE","HEROMOTOCO","HINDALCO","HINDUNILVR",
    "ICICIBANK","INDUSINDBK","INFY","ITC","JIOFIN","JSWSTEEL","KOTAKBANK","LT","M&M","MARUTI",
    "NESTLEIND","NTPC","ONGC","POWERGRID","RELIANCE","SBILIFE","SBIN","SHRIRAMFIN","SUNPHARMA",
    "TATACONSUM","TATASTEEL","TCS","TECHM","TITAN","TRENT","ULTRACEMCO","WIPRO",
)


class CasA1CaptureIdentityError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_symbol(value: Any) -> str:
    symbol = _text(value).upper()
    return "M&M" if symbol == "MANDM" else symbol


def _token(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    return str(number) if number > 0 else ""


def _instrument_rows(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise CasA1CaptureIdentityError("broker instrument master must be a JSON list")
    return [dict(row) for row in raw if isinstance(row, Mapping)]


def _resolve_equity(rows: Sequence[Mapping[str, Any]], symbol: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for row in rows:
        candidate = _normalize_symbol(
            row.get("tradingsymbol") or row.get("trading_symbol") or row.get("symbol") or row.get("name")
        )
        exchange = _text(row.get("exchange") or "NSE").upper()
        segment = _text(row.get("segment") or "NSE").upper()
        instrument_type = _text(row.get("instrument_type") or row.get("type") or "EQ").upper()
        if candidate != symbol:
            continue
        if exchange not in {"NSE", ""}:
            continue
        if segment not in {"NSE", "NSE_EQ", ""} and not segment.startswith("NSE"):
            continue
        if instrument_type not in {"EQ", "EQUITY", ""}:
            continue
        token = _token(row.get("instrument_token") or row.get("token"))
        if not token:
            continue
        matches.append(dict(row) | {"_resolved_token": token})
    unique = {row["_resolved_token"]: row for row in matches}
    if len(unique) != 1:
        raise CasA1CaptureIdentityError(
            f"expected exactly one NSE equity token for frozen symbol {symbol}; found {sorted(unique)}"
        )
    return next(iter(unique.values()))


def build_capture_identity_contract(
    *,
    live_universe: Mapping[str, Any],
    broker_instrument_master: Any,
    index_instrument_key: str = "NSE_INDEX|Nifty 50",
) -> dict[str, Any]:
    rows = _instrument_rows(broker_instrument_master)
    current = live_universe.get("constituents")
    if not isinstance(current, list):
        raise CasA1CaptureIdentityError("live universe constituents must be a list")

    current_map: dict[str, str] = {}
    for row in current:
        if not isinstance(row, Mapping):
            continue
        symbol = _normalize_symbol(row.get("symbol"))
        token = _token(row.get("instrument_token"))
        if not symbol or not token:
            continue
        if symbol in current_map and current_map[symbol] != token:
            raise CasA1CaptureIdentityError(f"ambiguous live-universe token for {symbol}")
        current_map[symbol] = token

    index_symbol = _normalize_symbol(live_universe.get("provider_native_index_identifier") or live_universe.get("index_symbol"))
    index_token = _token(live_universe.get("index_instrument_token"))
    if not index_symbol or not index_token:
        raise CasA1CaptureIdentityError("live universe lacks exact index symbol/token")

    constituents: list[dict[str, str]] = []
    supplemental: list[dict[str, str]] = []
    for symbol in FROZEN_DEVELOPMENT_SYMBOLS:
        token = current_map.get(symbol, "")
        source = "CURRENT_MEG_UNIVERSE"
        if not token:
            resolved = _resolve_equity(rows, symbol)
            token = resolved["_resolved_token"]
            source = "SUPPLEMENTAL_BROKER_MASTER"
            supplemental.append({"symbol": symbol, "instrument_token": token})
        constituents.append({
            "instrument_key": f"NSE_EQ|{symbol}",
            "symbol": symbol,
            "instrument_token": token,
            "capture_source": source,
        })

    frozen_set = set(FROZEN_DEVELOPMENT_SYMBOLS)
    ignored_current = sorted(symbol for symbol in current_map if symbol not in frozen_set)
    supplemental_symbols = [row["symbol"] for row in supplemental]

    semantic = {
        "index": {
            "instrument_key": index_instrument_key,
            "symbol": index_symbol,
            "instrument_token": index_token,
        },
        "constituents": constituents,
        "frozen_development_symbols": list(FROZEN_DEVELOPMENT_SYMBOLS),
        "supplemental_symbols": supplemental_symbols,
        "ignored_current_symbols": ignored_current,
        "source_universe_sha256": _text(live_universe.get("canonical_sha256")),
    }
    contract_sha = sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "contract_kind": "CAS_A1_FROZEN_CAPTURE_IDENTITY",
        **semantic,
        "identity_contract_sha256": contract_sha,
        "requires_supplemental_capture": bool(supplemental),
        "supplemental_constituents": supplemental,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }
