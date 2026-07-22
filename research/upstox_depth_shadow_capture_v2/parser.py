from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


PARSER_SCHEMA_VERSION = "UPSTOX_DEPTH_SHADOW_V2_1"
SUPPORTED_MODES = {"full": 5, "full_d30": 30}


class DepthParseError(ValueError):
    """Raised when an Upstox V3 market-feed message violates the frozen parser contract."""


@dataclass(frozen=True)
class ParsedMarketMessage:
    message_type: str
    records: tuple[dict[str, Any], ...]
    feed_count: int
    market_feed_count: int
    index_feed_count: int
    empty_depth_count: int
    invalid_level_count: int
    warnings: tuple[str, ...]


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _optional_float(value: Any, *, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise DepthParseError(f"{field} is not numeric") from exc
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise DepthParseError(f"{field} is non-finite")
    return parsed


def _optional_int(value: Any, *, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DepthParseError(f"{field} is not an integer") from exc


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _extract_feeds(message: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    feeds = _mapping(_first(message, "feeds"))
    if feeds is not None:
        return feeds, "OFFICIAL_V3_FEEDS"

    direct = {
        str(key): value
        for key, value in message.items()
        if isinstance(key, str) and "|" in key and isinstance(value, Mapping)
    }
    if direct and len(direct) == len(message):
        return direct, "SDK_DIRECT_FEED_MAP"
    raise DepthParseError("message contains no Upstox V3 feeds mapping")


def _extract_market_ff(feed: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, str, bool]:
    full_feed = _mapping(_first(feed, "fullFeed", "full_feed", "ff"))
    if full_feed is None:
        return None, "NO_FULL_FEED", False

    market_ff = _mapping(_first(full_feed, "marketFF", "market_ff"))
    if market_ff is not None:
        return market_ff, "FULL_FEED_MARKET_FF", False

    index_ff = _mapping(_first(full_feed, "indexFF", "index_ff"))
    if index_ff is not None:
        return None, "FULL_FEED_INDEX_FF", True

    # Some SDK versions expose the market-full-feed object directly under `ff`.
    if _mapping(_first(full_feed, "marketLevel", "market_level")) is not None:
        return full_feed, "DIRECT_MARKET_FF", False
    return None, "FULL_FEED_UNRECOGNIZED", False


def _extract_levels(
    market_ff: Mapping[str, Any],
    *,
    mode: str,
) -> tuple[list[dict[str, Any]], int, int, int, tuple[str, ...]]:
    maximum = SUPPORTED_MODES[mode]
    market_level = _mapping(_first(market_ff, "marketLevel", "market_level"))
    raw_quotes = None if market_level is None else _first(
        market_level, "bidAskQuote", "bid_ask_quote"
    )
    if raw_quotes is None:
        return [], 0, 0, 0, ("MARKET_LEVEL_MISSING",)
    if isinstance(raw_quotes, (str, bytes)) or not isinstance(raw_quotes, Sequence):
        raise DepthParseError("marketLevel.bidAskQuote is not a sequence")
    if len(raw_quotes) > maximum:
        raise DepthParseError(
            f"{mode} message contains {len(raw_quotes)} levels; maximum is {maximum}"
        )

    levels: list[dict[str, Any]] = []
    invalid_count = 0
    warnings: list[str] = []
    for index, raw in enumerate(raw_quotes, start=1):
        quote = _mapping(raw)
        if quote is None:
            invalid_count += 1
            warnings.append(f"LEVEL_{index}_NOT_MAPPING")
            continue
        try:
            bid_price = _optional_float(
                _first(quote, "bidP", "bid_p", "bp"), field=f"level[{index}].bidP"
            )
            bid_qty = _optional_int(
                _first(quote, "bidQ", "bid_q", "bq"), field=f"level[{index}].bidQ"
            )
            ask_price = _optional_float(
                _first(quote, "askP", "ask_p", "ap"), field=f"level[{index}].askP"
            )
            ask_qty = _optional_int(
                _first(quote, "askQ", "ask_q", "aq"), field=f"level[{index}].askQ"
            )
        except DepthParseError:
            invalid_count += 1
            warnings.append(f"LEVEL_{index}_INVALID_SCALAR")
            continue

        if bid_price is not None and bid_price < 0:
            invalid_count += 1
            warnings.append(f"LEVEL_{index}_NEGATIVE_BID_PRICE")
            continue
        if ask_price is not None and ask_price < 0:
            invalid_count += 1
            warnings.append(f"LEVEL_{index}_NEGATIVE_ASK_PRICE")
            continue
        if bid_qty is not None and bid_qty < 0:
            invalid_count += 1
            warnings.append(f"LEVEL_{index}_NEGATIVE_BID_QTY")
            continue
        if ask_qty is not None and ask_qty < 0:
            invalid_count += 1
            warnings.append(f"LEVEL_{index}_NEGATIVE_ASK_QTY")
            continue

        bid_present = bid_price is not None and bid_price > 0
        ask_present = ask_price is not None and ask_price > 0
        if not bid_present and not ask_present:
            continue
        levels.append(
            {
                "level": index,
                "bid_price": bid_price if bid_present else None,
                "bid_qty": bid_qty if bid_present else None,
                "ask_price": ask_price if ask_present else None,
                "ask_qty": ask_qty if ask_present else None,
            }
        )

    two_sided = sum(
        level["bid_price"] is not None and level["ask_price"] is not None
        for level in levels
    )
    return levels, len(raw_quotes), two_sided, invalid_count, tuple(warnings)


def _monotonic(values: list[float], *, descending: bool) -> bool:
    pairs = zip(values, values[1:])
    return all(left >= right if descending else left <= right for left, right in pairs)


def parse_market_message(
    message: Mapping[str, Any],
    *,
    received_at_ns: int,
    mode: str = "full",
) -> ParsedMarketMessage:
    """Parse one decoded Upstox Market Data Feed V3 callback payload.

    The parser supports the official camelCase V3 shape and explicit SDK aliases.
    It never infers order-book data from LTP or top-level placeholder fields.
    """
    if mode not in SUPPORTED_MODES:
        raise DepthParseError(f"unsupported mode: {mode}")
    if not isinstance(message, Mapping):
        raise DepthParseError("decoded market message must be a mapping")
    if received_at_ns <= 0:
        raise DepthParseError("received_at_ns must be positive")

    message_type = str(_first(message, "type") or "unknown")
    if message_type == "market_info":
        return ParsedMarketMessage(
            message_type=message_type,
            records=(),
            feed_count=0,
            market_feed_count=0,
            index_feed_count=0,
            empty_depth_count=0,
            invalid_level_count=0,
            warnings=(),
        )

    feeds, envelope_variant = _extract_feeds(message)
    current_ts_ms = _optional_int(
        _first(message, "currentTs", "current_ts"), field="currentTs"
    )
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    market_feed_count = 0
    index_feed_count = 0
    empty_depth_count = 0
    invalid_level_count = 0

    for instrument_key in sorted(feeds, key=str):
        feed = _mapping(feeds[instrument_key])
        if feed is None:
            warnings.append(f"FEED_NOT_MAPPING:{instrument_key}")
            continue
        market_ff, feed_variant, is_index = _extract_market_ff(feed)
        if is_index:
            index_feed_count += 1
            continue
        if market_ff is None:
            warnings.append(f"UNSUPPORTED_FEED:{instrument_key}:{feed_variant}")
            continue

        market_feed_count += 1
        levels, raw_level_count, two_sided_count, invalid_count, level_warnings = (
            _extract_levels(market_ff, mode=mode)
        )
        invalid_level_count += invalid_count
        warnings.extend(f"{instrument_key}:{warning}" for warning in level_warnings)
        if not levels:
            empty_depth_count += 1

        ltpc = _mapping(_first(market_ff, "ltpc")) or {}
        ltp = _optional_float(_first(ltpc, "ltp"), field=f"{instrument_key}.ltp")
        ltt_ms = _optional_int(_first(ltpc, "ltt"), field=f"{instrument_key}.ltt")
        ltq = _optional_int(_first(ltpc, "ltq"), field=f"{instrument_key}.ltq")
        close_price = _optional_float(
            _first(ltpc, "cp"), field=f"{instrument_key}.cp"
        )

        bids = [
            float(level["bid_price"])
            for level in levels
            if level["bid_price"] is not None
        ]
        asks = [
            float(level["ask_price"])
            for level in levels
            if level["ask_price"] is not None
        ]
        best_bid = max(bids) if bids else None
        best_ask = min(asks) if asks else None
        best_bid_qty = next(
            (
                level["bid_qty"]
                for level in levels
                if level["bid_price"] == best_bid
            ),
            None,
        )
        best_ask_qty = next(
            (
                level["ask_qty"]
                for level in levels
                if level["ask_price"] == best_ask
            ),
            None,
        )
        depth_json = json.dumps(
            levels, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        records.append(
            {
                "receive_ts_ns": int(received_at_ns),
                "feed_current_ts_ms": current_ts_ms,
                "instrument_key": str(instrument_key),
                "message_type": message_type,
                "mode": mode,
                "parser_variant": f"{envelope_variant}:{feed_variant}",
                "ltp": ltp,
                "ltt_ms": ltt_ms,
                "ltq": ltq,
                "close_price": close_price,
                "raw_depth_level_count": int(raw_level_count),
                "valid_depth_level_count": int(len(levels)),
                "two_sided_level_count": int(two_sided_count),
                "invalid_depth_level_count": int(invalid_count),
                "best_bid_price": best_bid,
                "best_ask_price": best_ask,
                "best_bid_qty": best_bid_qty,
                "best_ask_qty": best_ask_qty,
                "total_bid_qty": int(
                    sum(level["bid_qty"] or 0 for level in levels)
                ),
                "total_ask_qty": int(
                    sum(level["ask_qty"] or 0 for level in levels)
                ),
                "crossed_market": bool(
                    best_bid is not None
                    and best_ask is not None
                    and best_bid > best_ask
                ),
                "bid_ladder_monotonic": _monotonic(bids, descending=True),
                "ask_ladder_monotonic": _monotonic(asks, descending=False),
                "depth_json": depth_json,
                "payload_sha256": _canonical_hash(feed),
                "schema_version": PARSER_SCHEMA_VERSION,
            }
        )

    return ParsedMarketMessage(
        message_type=message_type,
        records=tuple(records),
        feed_count=len(feeds),
        market_feed_count=market_feed_count,
        index_feed_count=index_feed_count,
        empty_depth_count=empty_depth_count,
        invalid_level_count=invalid_level_count,
        warnings=tuple(sorted(warnings)),
    )
