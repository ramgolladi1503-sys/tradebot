from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


_FO_SEGMENTS = frozenset({"NSE_FO", "BSE_FO", "NCD_FO", "BCD_FO", "MCX_FO"})


class UpstoxV3ParseError(ValueError):
    """Raised when a purported live-feed payload cannot be parsed safely."""


@dataclass(frozen=True)
class CaptureQuality:
    classification: str
    research_depth_eligible: bool
    reasons: tuple[str, ...]
    subscribed_instruments: int
    instruments_with_records: int
    active_fo_instruments: int
    fo_instruments_with_valid_depth: int
    active_fo_depth_coverage_ratio: float
    valid_depth_records: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "research_depth_eligible": self.research_depth_eligible,
            "reasons": list(self.reasons),
            "subscribed_instruments": self.subscribed_instruments,
            "instruments_with_records": self.instruments_with_records,
            "active_fo_instruments": self.active_fo_instruments,
            "fo_instruments_with_valid_depth": self.fo_instruments_with_valid_depth,
            "active_fo_depth_coverage_ratio": self.active_fo_depth_coverage_ratio,
            "valid_depth_records": self.valid_depth_records,
        }


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _first(mapping: Mapping[str, Any] | None, *keys: str) -> Any:
    if mapping is None:
        return None
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _finite_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _nonnegative_int(value: Any) -> int | None:
    parsed = _finite_float(value)
    if parsed is None or parsed < 0:
        return None
    return int(parsed)


def _epoch_ms(value: Any) -> int | None:
    parsed = _finite_float(value)
    if parsed is None or parsed <= 0:
        return None
    if parsed < 10_000_000_000:
        parsed *= 1000.0
    return int(parsed)


def _normalize_depth_levels(raw_quotes: Any) -> list[dict[str, Any]]:
    """Normalize only explicit two-sided V3 depth fields; never infer a side."""
    if raw_quotes is None:
        return []
    if isinstance(raw_quotes, Mapping):
        quotes: Sequence[Any] = [raw_quotes]
    elif isinstance(raw_quotes, Sequence) and not isinstance(
        raw_quotes, (str, bytes, bytearray)
    ):
        quotes = raw_quotes
    else:
        raise UpstoxV3ParseError(
            "market depth quote container is not a mapping or sequence"
        )

    levels: list[dict[str, Any]] = []
    for raw in quotes:
        quote = _mapping(raw)
        if quote is None:
            raise UpstoxV3ParseError("market depth level is not a mapping")
        bid_price = _finite_float(
            _first(quote, "bidP", "bp", "bid_p", "bidPrice", "bid_price")
        )
        ask_price = _finite_float(
            _first(quote, "askP", "ap", "ask_p", "askPrice", "ask_price")
        )
        bid_quantity = _nonnegative_int(
            _first(quote, "bidQ", "bq", "bid_q", "bidQuantity", "bid_quantity")
        )
        ask_quantity = _nonnegative_int(
            _first(quote, "askQ", "aq", "ask_q", "askQuantity", "ask_quantity")
        )
        if (
            bid_price is None
            and ask_price is None
            and bid_quantity is None
            and ask_quantity is None
        ):
            continue
        if bid_price is None or ask_price is None:
            raise UpstoxV3ParseError(
                "market depth level does not contain explicit bid and ask prices"
            )
        levels.append(
            {
                "bid_price": bid_price,
                "bid_quantity": bid_quantity,
                "ask_price": ask_price,
                "ask_quantity": ask_quantity,
            }
        )
    return levels


def _extract_full_feed(
    payload: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, str | None]:
    full_feed = _mapping(_first(payload, "fullFeed", "full_feed", "ff"))
    if full_feed is None:
        return None, None
    market = _mapping(_first(full_feed, "marketFF", "market_ff"))
    if market is not None:
        return market, "MARKET_FF"
    index = _mapping(_first(full_feed, "indexFF", "index_ff"))
    if index is not None:
        return index, "INDEX_FF"
    return full_feed, "FULL_FEED"


def _parse_instrument_feed(
    instrument_key: str,
    payload: Mapping[str, Any],
    *,
    source_ts_epoch_ms: int | None,
    received_ts_epoch: float,
    message_type: str | None,
) -> dict[str, Any]:
    body, feed_kind = _extract_full_feed(payload)
    first_level = _mapping(
        _first(payload, "firstLevelWithGreeks", "first_level_with_greeks")
    )

    depth_levels: list[dict[str, Any]] = []
    ltpc: Mapping[str, Any] | None = None
    greeks: Mapping[str, Any] | None = None
    details: Mapping[str, Any] | None = None
    volume: int | None = None
    oi: float | None = None
    iv: float | None = None

    if body is not None:
        ltpc = _mapping(_first(body, "ltpc"))
        market_level = _mapping(_first(body, "marketLevel", "market_level"))
        raw_quotes = _first(market_level, "bidAskQuote", "bid_ask_quote")
        depth_levels = _normalize_depth_levels(raw_quotes)
        greeks = _mapping(_first(body, "optionGreeks", "option_greeks"))
        details = _mapping(_first(body, "eFeedDetails", "e_feed_details"))
        volume = _nonnegative_int(_first(details, "vtt", "volume"))
        oi = _finite_float(_first(details, "oi"))
    elif first_level is not None:
        feed_kind = "FIRST_LEVEL_WITH_GREEKS"
        ltpc = _mapping(_first(first_level, "ltpc"))
        first_depth = _mapping(_first(first_level, "firstDepth", "first_depth"))
        depth_levels = _normalize_depth_levels(first_depth)
        greeks = _mapping(_first(first_level, "optionGreeks", "option_greeks"))
        volume = _nonnegative_int(_first(first_level, "vtt", "volume"))
        oi = _finite_float(_first(first_level, "oi"))
        iv = _finite_float(_first(first_level, "iv"))
    else:
        if "depth" in payload:
            raise UpstoxV3ParseError(
                "REST-style depth.buy/depth.sell payload is not a valid V3 live-feed shape"
            )
        ltpc = _mapping(_first(payload, "ltpc"))
        if ltpc is not None:
            feed_kind = "LTPC"
        else:
            raise UpstoxV3ParseError(
                f"unrecognized Upstox V3 feed payload for {instrument_key}"
            )

    ltp = _finite_float(_first(ltpc, "ltp"))
    if source_ts_epoch_ms is None:
        source_ts_epoch_ms = _epoch_ms(_first(ltpc, "ltt"))

    best = depth_levels[0] if depth_levels else {}
    bid_price = _finite_float(best.get("bid_price"))
    ask_price = _finite_float(best.get("ask_price"))
    bid_quantity = _nonnegative_int(best.get("bid_quantity"))
    ask_quantity = _nonnegative_int(best.get("ask_quantity"))
    depth_valid = bool(
        bid_price is not None
        and bid_price > 0
        and ask_price is not None
        and ask_price > 0
        and bid_quantity is not None
        and ask_quantity is not None
    )

    if iv is None:
        iv = _finite_float(_first(greeks, "iv"))

    return {
        "ts": float(received_ts_epoch),
        "source_ts_epoch_ms": source_ts_epoch_ms,
        "instrument_key": str(instrument_key),
        "message_type": str(message_type or "live_feed"),
        "feed_kind": str(feed_kind or "UNKNOWN"),
        "ltp": ltp,
        "bid_price": bid_price,
        "ask_price": ask_price,
        "bid_quantity": bid_quantity,
        "ask_quantity": ask_quantity,
        "depth": depth_levels,
        "depth_level_count": len(depth_levels),
        "depth_valid": depth_valid,
        "delta": _finite_float(_first(greeks, "delta")),
        "theta": _finite_float(_first(greeks, "theta")),
        "gamma": _finite_float(_first(greeks, "gamma")),
        "vega": _finite_float(_first(greeks, "vega")),
        "rho": _finite_float(_first(greeks, "rho")),
        "iv": iv,
        "volume": volume,
        "oi": oi,
    }


def parse_upstox_v3_message(
    message: Any,
    *,
    received_ts_epoch: float | None = None,
) -> list[dict[str, Any]]:
    """Parse one official Upstox MarketDataStreamerV3 callback payload.

    Control messages such as ``market_info`` produce no records. Live-feed payloads
    must expose either the official top-level ``feeds`` mapping or a legacy SDK
    mapping keyed directly by instrument key.
    """

    if isinstance(message, (str, bytes, bytearray)):
        try:
            message = json.loads(message)
        except (TypeError, json.JSONDecodeError) as exc:
            raise UpstoxV3ParseError("message is not valid JSON") from exc
    root = _mapping(message)
    if root is None:
        raise UpstoxV3ParseError("message is not a mapping")

    message_type_raw = _first(root, "type")
    message_type = str(message_type_raw) if message_type_raw is not None else None
    feeds = _mapping(_first(root, "feeds"))
    if feeds is None:
        feeds = {
            str(key): value
            for key, value in root.items()
            if "|" in str(key) and isinstance(value, Mapping)
        }
    if not feeds:
        if message_type in {"market_info", "initial_feed", "ping", "pong"}:
            return []
        if "marketInfo" in root or "market_info" in root:
            return []
        raise UpstoxV3ParseError("live-feed message contains no instrument feeds")

    received = float(
        received_ts_epoch if received_ts_epoch is not None else time.time()
    )
    source_ts = _epoch_ms(_first(root, "currentTs", "current_ts"))
    records: list[dict[str, Any]] = []
    for instrument_key in sorted(feeds):
        payload = _mapping(feeds[instrument_key])
        if payload is None:
            raise UpstoxV3ParseError(
                f"instrument payload is not a mapping: {instrument_key}"
            )
        records.append(
            _parse_instrument_feed(
                instrument_key,
                payload,
                source_ts_epoch_ms=source_ts,
                received_ts_epoch=received,
                message_type=message_type,
            )
        )
    return records


def assess_capture_quality(
    *,
    subscribed_instrument_keys: Sequence[str],
    record_counts: Mapping[str, int],
    valid_depth_counts: Mapping[str, int],
    minimum_active_fo_depth_coverage_ratio: float = 0.50,
    minimum_valid_depth_records_per_instrument: int = 1,
) -> CaptureQuality:
    if not 0.0 <= float(minimum_active_fo_depth_coverage_ratio) <= 1.0:
        raise ValueError(
            "minimum_active_fo_depth_coverage_ratio must be between 0 and 1"
        )
    if int(minimum_valid_depth_records_per_instrument) <= 0:
        raise ValueError(
            "minimum_valid_depth_records_per_instrument must be positive"
        )

    subscribed = sorted({str(key) for key in subscribed_instrument_keys})
    with_records = {
        key for key in subscribed if int(record_counts.get(key, 0)) > 0
    }
    active_fo = {
        key
        for key in with_records
        if key.split("|", 1)[0].upper() in _FO_SEGMENTS
    }
    fo_with_depth = {
        key
        for key in active_fo
        if int(valid_depth_counts.get(key, 0))
        >= int(minimum_valid_depth_records_per_instrument)
    }
    coverage = float(len(fo_with_depth) / len(active_fo)) if active_fo else 0.0
    total_valid_depth_records = sum(
        max(0, int(value)) for value in valid_depth_counts.values()
    )

    reasons: list[str] = []
    if not with_records:
        reasons.append("NO_INSTRUMENT_RECORDS")
    if not active_fo:
        reasons.append("NO_ACTIVE_FO_INSTRUMENTS")
    if total_valid_depth_records <= 0:
        reasons.append("NO_VALID_DEPTH_RECORDS")
    if active_fo and coverage < float(minimum_active_fo_depth_coverage_ratio):
        reasons.append(
            "ACTIVE_FO_DEPTH_COVERAGE_BELOW_MINIMUM:"
            f"{coverage:.6f}<{float(minimum_active_fo_depth_coverage_ratio):.6f}"
        )

    valid = not reasons
    return CaptureQuality(
        classification=(
            "UPSTOX_V3_DEPTH_CAPTURE_VALID"
            if valid
            else "UPSTOX_V3_DEPTH_CAPTURE_INVALID"
        ),
        research_depth_eligible=valid,
        reasons=tuple(reasons),
        subscribed_instruments=len(subscribed),
        instruments_with_records=len(with_records),
        active_fo_instruments=len(active_fo),
        fo_instruments_with_valid_depth=len(fo_with_depth),
        active_fo_depth_coverage_ratio=coverage,
        valid_depth_records=total_valid_depth_records,
    )
