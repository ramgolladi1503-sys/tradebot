from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from .patterns import classify_pattern, summarize_patterns
from .replay import classify_outcome_for_rejected_trade


IST = ZoneInfo("Asia/Kolkata")
UNDERLYINGS = ("NIFTY", "BANKNIFTY", "SENSEX")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except Exception:
        return None


def _coerce_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = _text(value)
    if not text:
        raise ValueError("day is required")
    return date.fromisoformat(text)


def _coerce_epoch_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw >= 1_000_000_000_000:
            return int(raw)
        if raw >= 1_000_000_000:
            return int(raw * 1000.0)
        return None
    text = _text(value)
    if not text:
        return None
    try:
        return _coerce_epoch_ms(float(text))
    except Exception:
        pass
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return int(dt.timestamp() * 1000.0)
    except Exception:
        return None


def _event_ts_ms(row: Mapping[str, Any]) -> int | None:
    for key in (
        "ts_epoch_ms",
        "timestamp_epoch_ms",
        "timestamp_ms",
        "ts_ms",
        "ts",
        "timestamp",
        "ts_utc",
        "time_ms",
    ):
        ts = _coerce_epoch_ms(row.get(key))
        if ts is not None:
            return ts
    return None


def _to_ist_day(ts_epoch_ms: int) -> date:
    return datetime.fromtimestamp(float(ts_epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date()


def _ist_open_ts(day: date) -> int:
    dt = datetime.combine(day, time(9, 15), tzinfo=IST)
    return int(dt.timestamp() * 1000.0)


def _percentile(values: Sequence[float], pct: float) -> float | None:
    if not values:
        return None
    arr = sorted(float(v) for v in values)
    if len(arr) == 1:
        return float(arr[0])
    pos = (len(arr) - 1) * min(max(float(pct), 0.0), 1.0)
    lo = int(pos)
    hi = min(lo + 1, len(arr) - 1)
    if lo == hi:
        return float(arr[lo])
    frac = pos - lo
    return float(arr[lo] + (arr[hi] - arr[lo]) * frac)


def _extract_symbol(row: Mapping[str, Any]) -> str:
    for key in ("tradingsymbol", "instrument", "symbol"):
        text = _text(row.get(key))
        if text:
            return text.upper()
    return ""


def _parse_underlying(symbol: str, universe: Sequence[str]) -> str | None:
    upper = symbol.upper()
    for name in universe:
        if name.upper() in upper:
            return name.upper()
    return None


def _parse_option_side(row: Mapping[str, Any], symbol: str) -> str | None:
    direct = _text(row.get("option_type") or row.get("right") or row.get("cp")).upper()
    if direct in {"CE", "CALL", "C"}:
        return "CE"
    if direct in {"PE", "PUT", "P"}:
        return "PE"
    upper = symbol.upper()
    match = re.search(r"(CE|PE)\b", upper)
    if match:
        return match.group(1)
    return None


def _parse_strike(row: Mapping[str, Any], symbol: str) -> float | None:
    direct = _safe_float(row.get("strike"))
    if direct is not None:
        return direct
    upper = symbol.upper()
    match = re.search(r"(\d{4,6})(?=[-_]?(CE|PE)\b)", upper)
    if match:
        return _safe_float(match.group(1))
    return None


def _parse_expiry(row: Mapping[str, Any], symbol: str) -> str | None:
    for key in ("expiry", "expiry_date"):
        text = _text(row.get(key))
        if text:
            return text
    upper = symbol.upper()
    match = re.search(r"(\d{2}[A-Z]{3}\d{2})", upper)
    if match:
        return match.group(1)
    return None


def _is_trade_decision_event(row: Mapping[str, Any]) -> bool:
    event_type = _text(row.get("event_type")).upper()
    intent = _text(row.get("intent")).lower()
    if event_type in {"REJECTED_TRADE", "ACCEPTED_TRADE", "ADVISORY_TRADE"}:
        return True
    if intent in {"rejected", "accepted", "advisory"}:
        return True
    return False


def _is_quote_event(row: Mapping[str, Any]) -> bool:
    if _is_trade_decision_event(row):
        return False
    event_type = _text(row.get("event_type")).upper()
    if event_type in {"TICK", "SNAPSHOT", "QUOTE"}:
        return True
    if event_type and event_type not in {"TICK", "SNAPSHOT", "QUOTE"}:
        return False
    if _extract_symbol(row) and any(k in row for k in ("ltp", "bid", "ask", "mark_price", "price")):
        return True
    return False


def _mid_price(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None:
        return None
    if bid <= 0 or ask <= 0:
        return None
    if ask < bid:
        return None
    return (bid + ask) / 2.0


def _extract_price(row: Mapping[str, Any]) -> tuple[float | None, float | None, float | None, float | None]:
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    mid = _mid_price(bid, ask)
    ltp = _safe_float(row.get("ltp"))
    if ltp is None:
        ltp = _safe_float(row.get("last_price"))
    mark = _safe_float(row.get("mark_price"))
    price = mid
    if price is None:
        price = ltp
    if price is None:
        price = mark
    if price is None:
        price = _safe_float(row.get("price"))
    return price, bid, ask, ltp


def _extract_spread_pct(row: Mapping[str, Any], bid: float | None, ask: float | None, price: float | None) -> float | None:
    direct = _safe_float(row.get("spread_pct"))
    if direct is not None:
        return direct
    if bid is not None and ask is not None and ask >= bid:
        ref = _mid_price(bid, ask)
        if ref is None:
            ref = price
        if ref is not None and ref > 0:
            return (ask - bid) / ref
    return None


def _extract_quote_age_sec(row: Mapping[str, Any]) -> float | None:
    direct = _safe_float(row.get("quote_age_sec"))
    if direct is not None:
        return direct
    feed_metrics = row.get("feed_metrics")
    if isinstance(feed_metrics, Mapping):
        nested = _safe_float(feed_metrics.get("quote_age_sec"))
        if nested is not None:
            return nested
    metrics = row.get("metrics_snapshot")
    if isinstance(metrics, Mapping):
        nested = _safe_float(metrics.get("quote_age_sec"))
        if nested is not None:
            return nested
    return None


def _extract_gate_reasons(row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    raw = row.get("gate_reasons")
    if isinstance(raw, list):
        for item in raw:
            text = _text(item)
            if text:
                reasons.append(text)
    reject_reason = _text(row.get("reject_reason"))
    if reject_reason:
        reasons.append(reject_reason)
    gate_decisions = row.get("gate_decisions")
    if isinstance(gate_decisions, list):
        for item in gate_decisions:
            if not isinstance(item, Mapping):
                continue
            if item.get("passed") is True:
                continue
            reason = _text(item.get("reason")) or _text(item.get("gate_name"))
            if reason:
                reasons.append(reason)
    seen: set[str] = set()
    out: list[str] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        out.append(reason)
    return out


def _collect_contract_series(
    events: Sequence[Mapping[str, Any]],
    day: date,
    universe: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    contract_map: dict[str, dict[str, Any]] = {}
    index_map: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in events:
        if not isinstance(row, Mapping):
            continue
        if not _is_quote_event(row):
            continue
        ts = _event_ts_ms(row)
        if ts is None:
            continue
        if _to_ist_day(ts) != day:
            continue
        symbol = _extract_symbol(row)
        if not symbol:
            continue
        underlying = _parse_underlying(symbol, universe)
        if underlying is None:
            continue

        price, bid, ask, ltp = _extract_price(row)
        if price is None:
            continue
        spread_pct = _extract_spread_pct(row, bid, ask, price)
        quote_age_sec = _extract_quote_age_sec(row)
        point = {
            "ts_epoch_ms": ts,
            "price": float(price),
            "bid": bid,
            "ask": ask,
            "ltp": ltp,
            "spread_pct": spread_pct,
            "quote_age_sec": quote_age_sec,
        }

        option_side = _parse_option_side(row, symbol)
        if option_side is None:
            # treat as index stream context
            if symbol.upper() == underlying:
                point["vwap"] = _safe_float(row.get("vwap"))
                index_map[underlying].append(point)
            continue

        entry = contract_map.get(symbol)
        if entry is None:
            entry = {
                "underlying": underlying,
                "symbol": symbol,
                "option_side": option_side,
                "strike": _parse_strike(row, symbol),
                "expiry": _parse_expiry(row, symbol),
                "points": [],
            }
            contract_map[symbol] = entry
        entry["points"].append(point)

    for entry in contract_map.values():
        entry["points"].sort(key=lambda item: int(item["ts_epoch_ms"]))
    for rows in index_map.values():
        rows.sort(key=lambda item: int(item["ts_epoch_ms"]))
    return contract_map, index_map


def _nearest_price_before(points: Sequence[Mapping[str, Any]], ts_epoch_ms: int) -> float | None:
    best: float | None = None
    for point in points:
        ts = _safe_int(point.get("ts_epoch_ms"))
        if ts is None:
            continue
        if ts <= ts_epoch_ms:
            price = _safe_float(point.get("price"))
            if price is not None:
                best = price
        else:
            break
    return best


def _nearest_price_after(points: Sequence[Mapping[str, Any]], ts_epoch_ms: int) -> float | None:
    for point in points:
        ts = _safe_int(point.get("ts_epoch_ms"))
        if ts is None:
            continue
        if ts >= ts_epoch_ms:
            price = _safe_float(point.get("price"))
            if price is not None:
                return price
    return None


def identify_extreme_movers(
    events: Sequence[Mapping[str, Any]],
    day: Any,
    universe: Sequence[str] = UNDERLYINGS,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    target_day = _coerce_date(day)
    open_ts = _ist_open_ts(target_day)
    contract_map, _ = _collect_contract_series(events, target_day, universe)

    movers: list[dict[str, Any]] = []
    for entry in contract_map.values():
        points = list(entry.get("points") or [])
        if len(points) < 30:
            continue

        open_price: float | None = None
        open_point_ts: int | None = None
        for point in points:
            ts = _safe_int(point.get("ts_epoch_ms"))
            price = _safe_float(point.get("price"))
            if ts is None or price is None:
                continue
            if ts >= open_ts:
                open_price = price
                open_point_ts = ts
                break
        if open_price is None:
            first = points[0]
            open_price = _safe_float(first.get("price"))
            open_point_ts = _safe_int(first.get("ts_epoch_ms"))

        if open_price is None or open_price <= 0:
            continue

        high_price = max(_safe_float(p.get("price")) or 0.0 for p in points)
        if high_price <= 0:
            continue
        pct_move = (high_price - open_price) / open_price

        spread_vals = [float(v) for v in (_safe_float(p.get("spread_pct")) for p in points) if v is not None]
        quote_age_vals = [float(v) for v in (_safe_float(p.get("quote_age_sec")) for p in points) if v is not None]

        spread_p95 = _percentile(spread_vals, 0.95)
        quote_age_p95 = _percentile(quote_age_vals, 0.95)

        # Hard liquidity gate: reject if spread data exists and p95 is too wide.
        if spread_p95 is not None and spread_p95 > 0.008:
            continue

        execution_unknown = spread_p95 is None or quote_age_p95 is None
        execution_ok = bool(
            spread_p95 is not None
            and spread_p95 <= 0.008
            and quote_age_p95 is not None
            and quote_age_p95 <= 5.0
        )

        movers.append(
            {
                "day": target_day.isoformat(),
                "underlying": str(entry.get("underlying")),
                "symbol": str(entry.get("symbol")),
                "option_side": str(entry.get("option_side")),
                "strike": _safe_float(entry.get("strike")),
                "expiry": entry.get("expiry"),
                "open_price": float(open_price),
                "open_ts_epoch_ms": open_point_ts,
                "high_price": float(high_price),
                "pct_move": float(pct_move),
                "obs_count": len(points),
                "spread_p95": spread_p95,
                "quote_age_p95": quote_age_p95,
                "execution_ok": execution_ok,
                "execution_unknown": execution_unknown,
                "_points": points,
            }
        )

    top_n = max(1, int(top_k))
    ce = sorted([m for m in movers if m.get("option_side") == "CE"], key=lambda row: float(row["pct_move"]), reverse=True)[:top_n]
    pe = sorted([m for m in movers if m.get("option_side") == "PE"], key=lambda row: float(row["pct_move"]), reverse=True)[:top_n]
    return ce + pe


def reconstruct_pre_move_features(
    events: Sequence[Mapping[str, Any]],
    mover: Mapping[str, Any],
    lookback_min: int = 30,
    trigger_pct: float = 0.30,
) -> dict[str, Any]:
    target_day = _coerce_date(mover.get("day") or datetime.now(tz=IST).date())
    symbol = _text(mover.get("symbol"))
    underlying = _text(mover.get("underlying"))

    points = list(mover.get("_points") or [])
    if not points:
        # fallback for externally supplied mover rows
        contract_map, _ = _collect_contract_series(events, target_day, UNDERLYINGS)
        entry = contract_map.get(symbol)
        points = list(entry.get("points") or []) if entry else []

    if not points:
        return {
            "t0_ts_epoch_ms": None,
            "t0_price": None,
            "trigger_price": None,
            "pre_return_5m": None,
            "pre_return_15m": None,
            "compression_score": None,
            "volume_burst_ratio": None,
            "spread_p95_pre": None,
            "quote_age_p95_pre": None,
            "index_return_5m": None,
            "index_return_15m": None,
            "index_position_vs_vwap": None,
            "post_t0_jump_5m": None,
            "data_quality": {"has_points": False},
        }

    open_price = _safe_float(mover.get("open_price"))
    if open_price is None or open_price <= 0:
        open_price = _safe_float(points[0].get("price"))
    if open_price is None or open_price <= 0:
        return {
            "t0_ts_epoch_ms": None,
            "t0_price": None,
            "trigger_price": None,
            "pre_return_5m": None,
            "pre_return_15m": None,
            "compression_score": None,
            "volume_burst_ratio": None,
            "spread_p95_pre": None,
            "quote_age_p95_pre": None,
            "index_return_5m": None,
            "index_return_15m": None,
            "index_position_vs_vwap": None,
            "post_t0_jump_5m": None,
            "data_quality": {"has_points": True, "has_open": False},
        }

    trigger_price = float(open_price * (1.0 + float(trigger_pct)))
    t0_ts: int | None = None
    t0_price: float | None = None
    for point in points:
        price = _safe_float(point.get("price"))
        ts = _safe_int(point.get("ts_epoch_ms"))
        if price is None or ts is None:
            continue
        if price >= trigger_price:
            t0_ts = ts
            t0_price = price
            break

    if t0_ts is None:
        return {
            "t0_ts_epoch_ms": None,
            "t0_price": None,
            "trigger_price": trigger_price,
            "pre_return_5m": None,
            "pre_return_15m": None,
            "compression_score": None,
            "volume_burst_ratio": None,
            "spread_p95_pre": None,
            "quote_age_p95_pre": None,
            "index_return_5m": None,
            "index_return_15m": None,
            "index_position_vs_vwap": None,
            "post_t0_jump_5m": None,
            "data_quality": {"has_points": True, "has_open": True, "crossed_trigger": False},
        }

    lookback_ms = max(1, int(lookback_min)) * 60_000
    pre_start = int(t0_ts - lookback_ms)
    pre_points = [
        point
        for point in points
        if (_safe_int(point.get("ts_epoch_ms")) or 0) >= pre_start and (_safe_int(point.get("ts_epoch_ms")) or 0) <= t0_ts
    ]
    pre_prices = [float(v) for v in (_safe_float(p.get("price")) for p in pre_points) if v is not None]
    pre_spreads = [float(v) for v in (_safe_float(p.get("spread_pct")) for p in pre_points) if v is not None]
    pre_quote_ages = [float(v) for v in (_safe_float(p.get("quote_age_sec")) for p in pre_points) if v is not None]

    pre_5_base = _nearest_price_before(points, int(t0_ts - 5 * 60_000))
    pre_15_base = _nearest_price_before(points, int(t0_ts - 15 * 60_000))
    pre_return_5m = ((t0_price - pre_5_base) / pre_5_base) if pre_5_base and pre_5_base > 0 else None
    pre_return_15m = ((t0_price - pre_15_base) / pre_15_base) if pre_15_base and pre_15_base > 0 else None

    range_15_start = int(t0_ts - 15 * 60_000)
    range_60_start = int(t0_ts - 60 * 60_000)
    prices_last_15 = [
        float(v)
        for v in (
            _safe_float(p.get("price"))
            for p in points
            if (_safe_int(p.get("ts_epoch_ms")) or 0) >= range_15_start and (_safe_int(p.get("ts_epoch_ms")) or 0) <= t0_ts
        )
        if v is not None
    ]
    prices_last_60 = [
        float(v)
        for v in (
            _safe_float(p.get("price"))
            for p in points
            if (_safe_int(p.get("ts_epoch_ms")) or 0) >= range_60_start and (_safe_int(p.get("ts_epoch_ms")) or 0) <= t0_ts
        )
        if v is not None
    ]
    compression_score: float | None = None
    if len(prices_last_15) >= 3 and len(prices_last_60) >= 6:
        range_15 = max(prices_last_15) - min(prices_last_15)
        range_60 = max(prices_last_60) - min(prices_last_60)
        if range_60 > 0:
            compression_score = range_15 / range_60

    ticks_5 = sum(1 for p in points if range_15_start <= (_safe_int(p.get("ts_epoch_ms")) or 0) <= t0_ts)
    ticks_60 = sum(1 for p in points if range_60_start <= (_safe_int(p.get("ts_epoch_ms")) or 0) <= t0_ts)
    volume_burst_ratio: float | None = None
    baseline = ticks_60 / 12.0 if ticks_60 > 0 else None
    if baseline and baseline > 0:
        volume_burst_ratio = ticks_5 / baseline

    post_5_price = _nearest_price_before(points, int(t0_ts + 5 * 60_000))
    post_t0_jump_5m = ((post_5_price - t0_price) / t0_price) if post_5_price and t0_price and t0_price > 0 else None

    # index context
    _, index_map = _collect_contract_series(events, target_day, UNDERLYINGS)
    index_points = list(index_map.get(underlying, []))
    idx_t0 = _nearest_price_before(index_points, t0_ts)
    idx_5_base = _nearest_price_before(index_points, int(t0_ts - 5 * 60_000))
    idx_15_base = _nearest_price_before(index_points, int(t0_ts - 15 * 60_000))
    index_return_5m = ((idx_t0 - idx_5_base) / idx_5_base) if idx_t0 and idx_5_base and idx_5_base > 0 else None
    index_return_15m = ((idx_t0 - idx_15_base) / idx_15_base) if idx_t0 and idx_15_base and idx_15_base > 0 else None
    index_position_vs_vwap: float | None = None
    if idx_t0 is not None:
        vwap_value = None
        for point in reversed(index_points):
            ts = _safe_int(point.get("ts_epoch_ms"))
            if ts is None or ts > t0_ts:
                continue
            vwap_value = _safe_float(point.get("vwap"))
            if vwap_value is not None:
                break
        if vwap_value and vwap_value > 0:
            index_position_vs_vwap = (idx_t0 - vwap_value) / vwap_value

    return {
        "t0_ts_epoch_ms": t0_ts,
        "t0_price": t0_price,
        "trigger_price": trigger_price,
        "pre_return_5m": pre_return_5m,
        "pre_return_15m": pre_return_15m,
        "compression_score": compression_score,
        "volume_burst_ratio": volume_burst_ratio,
        "spread_p95_pre": _percentile(pre_spreads, 0.95),
        "quote_age_p95_pre": _percentile(pre_quote_ages, 0.95),
        "index_return_5m": index_return_5m,
        "index_return_15m": index_return_15m,
        "index_position_vs_vwap": index_position_vs_vwap,
        "post_t0_jump_5m": post_t0_jump_5m,
        "data_quality": {
            "has_points": True,
            "has_open": True,
            "crossed_trigger": True,
            "pre_window_points": len(pre_points),
            "index_points": len(index_points),
            "spread_available": bool(pre_spreads),
            "quote_age_available": bool(pre_quote_ages),
        },
    }


def bot_visibility_and_rejects(events: Sequence[Mapping[str, Any]], mover: Mapping[str, Any]) -> dict[str, Any]:
    symbol = _text(mover.get("symbol")).upper()
    t0_ts = _safe_int(mover.get("t0_ts_epoch_ms"))
    low_ts = int(t0_ts - 15 * 60_000) if t0_ts is not None else None
    high_ts = int(t0_ts + 15 * 60_000) if t0_ts is not None else None

    saw_candidate = False
    saw_quote = False
    rejected_rows: list[Mapping[str, Any]] = []

    for row in events:
        if not isinstance(row, Mapping):
            continue
        row_symbol = _extract_symbol(row).upper()
        if row_symbol != symbol:
            continue

        if _is_quote_event(row):
            saw_quote = True

        event_type = _text(row.get("event_type")).upper()
        if "CANDIDATE" in event_type or "SCAN" in event_type or "SUBSCRIB" in event_type:
            saw_candidate = True
        if row.get("candidate_id") or row.get("scan_id") or row.get("subscription") is not None:
            saw_candidate = True

        is_reject = event_type == "REJECTED_TRADE" or _text(row.get("intent")).lower() == "rejected"
        if not is_reject:
            continue
        if low_ts is not None and high_ts is not None:
            ts = _event_ts_ms(row)
            if ts is None or ts < low_ts or ts > high_ts:
                continue
        rejected_rows.append(row)

    bot_saw = saw_candidate or saw_quote
    unknown_visibility = (not saw_candidate) and (not saw_quote)

    reasons: Counter[str] = Counter()
    feed_states: Counter[str] = Counter()
    for row in rejected_rows:
        for reason in _extract_gate_reasons(row):
            reasons[reason] += 1
        feed_state = _text(row.get("feed_state")).upper()
        if not feed_state:
            metrics = row.get("metrics_snapshot")
            if isinstance(metrics, Mapping):
                feed_state = _text(metrics.get("feed_state")).upper()
        if feed_state:
            feed_states[feed_state] += 1

    reject_reason_list = [reason for reason, _ in reasons.most_common()]
    feed_state_list = [state for state, _ in feed_states.most_common()]

    if unknown_visibility:
        missed_classification = "unknown"
    elif not bot_saw:
        missed_classification = "subscription"
    elif rejected_rows:
        if any(reason.lower().startswith("feed_state_") for reason in reject_reason_list) or any(
            state not in {"", "OK"} for state in feed_state_list
        ):
            missed_classification = "feed"
        else:
            missed_classification = "gating"
    else:
        missed_classification = "unknown"

    return {
        "bot_saw": bot_saw,
        "unknown_visibility": unknown_visibility,
        "bot_rejected": bool(rejected_rows),
        "reject_reasons": reject_reason_list,
        "feed_state_at_reject": feed_state_list,
        "rejection_count": len(rejected_rows),
        "missed_classification": missed_classification,
    }


def replay_outcome_for_mover(
    events: Sequence[Mapping[str, Any]],
    mover: Mapping[str, Any],
    horizon_min: int = 45,
    target_pct: float = 0.30,
    sl_pct: float = 0.15,
) -> dict[str, Any]:
    symbol = _text(mover.get("symbol")).upper()
    t0_ts = _safe_int(mover.get("t0_ts_epoch_ms"))
    entry = _safe_float(mover.get("t0_price"))
    if t0_ts is None or entry is None or entry <= 0:
        return {
            "outcome": "NO_HIT",
            "mfe": None,
            "mae": None,
            "resolution_ts_epoch_ms": None,
            "horizon_min": int(horizon_min),
        }

    end_ts = int(t0_ts + max(1, int(horizon_min)) * 60_000)
    future_ticks: list[dict[str, Any]] = []
    for row in events:
        if not isinstance(row, Mapping):
            continue
        if _extract_symbol(row).upper() != symbol:
            continue
        if not _is_quote_event(row):
            continue
        ts = _event_ts_ms(row)
        if ts is None or ts <= t0_ts or ts > end_ts:
            continue
        price, bid, ask, ltp = _extract_price(row)
        if price is None:
            continue
        future_ticks.append(
            {
                "ts_epoch_ms": ts,
                "bid": bid,
                "ask": ask,
                "ltp": ltp if ltp is not None else price,
                "price": price,
            }
        )

    result = classify_outcome_for_rejected_trade(
        {
            "side": "BUY",
            "intended_entry": entry,
            "target": entry * (1.0 + float(target_pct)),
            "stop": entry * (1.0 - float(sl_pct)),
        },
        future_ticks,
        target_pct=float(target_pct),
        sl_pct=float(sl_pct),
    )
    resolution = result.get("resolution_ts")
    resolution_ts_epoch_ms: int | None = None
    res_float = _safe_float(resolution)
    if res_float is not None:
        if res_float < 1_000_000_000_000:
            resolution_ts_epoch_ms = int(res_float * 1000.0)
        else:
            resolution_ts_epoch_ms = int(res_float)

    return {
        "outcome": _text(result.get("outcome")) or "NO_HIT",
        "mfe": _safe_float(result.get("mfe")),
        "mae": _safe_float(result.get("mae")),
        "resolution_ts_epoch_ms": resolution_ts_epoch_ms,
        "horizon_min": int(horizon_min),
    }


def build_extreme_movers_table(
    day_events: Sequence[Mapping[str, Any]],
    day: Any,
    *,
    top_k: int = 10,
    trigger_pct: float = 0.30,
    lookback_min: int = 30,
    horizon_min: int = 45,
) -> list[dict[str, Any]]:
    movers = identify_extreme_movers(day_events, day, top_k=top_k)
    rows: list[dict[str, Any]] = []
    for mover in movers:
        pre = reconstruct_pre_move_features(day_events, mover, lookback_min=lookback_min, trigger_pct=trigger_pct)
        merged = {**mover, **pre}
        visibility = bot_visibility_and_rejects(day_events, merged)
        replay = replay_outcome_for_mover(day_events, merged, horizon_min=horizon_min, target_pct=trigger_pct, sl_pct=0.15)
        row = {
            "day": merged.get("day"),
            "underlying": merged.get("underlying"),
            "symbol": merged.get("symbol"),
            "option_side": merged.get("option_side"),
            "strike": merged.get("strike"),
            "expiry": merged.get("expiry"),
            "open_price": merged.get("open_price"),
            "high_price": merged.get("high_price"),
            "pct_move": merged.get("pct_move"),
            "obs_count": merged.get("obs_count"),
            "t0_ts_epoch_ms": merged.get("t0_ts_epoch_ms"),
            "t0_price": merged.get("t0_price"),
            "trigger_price": merged.get("trigger_price"),
            "pre_return_5m": merged.get("pre_return_5m"),
            "pre_return_15m": merged.get("pre_return_15m"),
            "compression_score": merged.get("compression_score"),
            "volume_burst_ratio": merged.get("volume_burst_ratio"),
            "spread_p95": merged.get("spread_p95"),
            "quote_age_p95": merged.get("quote_age_p95"),
            "spread_p95_pre": merged.get("spread_p95_pre"),
            "quote_age_p95_pre": merged.get("quote_age_p95_pre"),
            "execution_ok": merged.get("execution_ok"),
            "execution_unknown": merged.get("execution_unknown"),
            "index_return_5m": merged.get("index_return_5m"),
            "index_return_15m": merged.get("index_return_15m"),
            "index_position_vs_vwap": merged.get("index_position_vs_vwap"),
            "post_t0_jump_5m": merged.get("post_t0_jump_5m"),
            "bot_saw": visibility.get("bot_saw"),
            "unknown_visibility": visibility.get("unknown_visibility"),
            "bot_rejected": visibility.get("bot_rejected"),
            "reject_reasons": visibility.get("reject_reasons"),
            "feed_state_at_reject": visibility.get("feed_state_at_reject"),
            "missed_classification": visibility.get("missed_classification"),
            "outcome": replay.get("outcome"),
            "mfe": replay.get("mfe"),
            "mae": replay.get("mae"),
            "resolution_ts_epoch_ms": replay.get("resolution_ts_epoch_ms"),
            "data_quality": merged.get("data_quality"),
        }
        row["pattern"] = classify_pattern(row)
        rows.append(row)

    rows.sort(key=lambda item: float(item.get("pct_move") or 0.0), reverse=True)
    return rows


def _fmt_pct(value: Any) -> str:
    val = _safe_float(value)
    if val is None:
        return "n/a"
    return f"{val * 100.0:.1f}%"


def _fmt_price(value: Any) -> str:
    val = _safe_float(value)
    if val is None:
        return "n/a"
    return f"{val:.2f}"


def _format_ts(ts_epoch_ms: Any) -> str:
    ts = _safe_int(ts_epoch_ms)
    if ts is None:
        return "n/a"
    dt = datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc).astimezone(IST)
    return dt.strftime("%H:%M:%S")


def _table_md(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| underlying | symbol | move | open | high | T0 | exec_ok | bot_saw | rejected | outcome | pattern |",
        "|---|---|---:|---:|---:|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("underlying")),
                    _text(row.get("symbol")),
                    _fmt_pct(row.get("pct_move")),
                    _fmt_price(row.get("open_price")),
                    _fmt_price(row.get("high_price")),
                    _format_ts(row.get("t0_ts_epoch_ms")),
                    str(bool(row.get("execution_ok"))),
                    str(bool(row.get("bot_saw"))),
                    str(bool(row.get("bot_rejected"))),
                    _text(row.get("outcome")),
                    _text(row.get("pattern")),
                ]
            )
            + " |"
        )
    if len(lines) == 2:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - |")
    return lines


def _pattern_notes(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    notes: list[str] = []
    if not rows:
        return ["No movers passed liquidity filters."]

    pattern_counts = summarize_patterns(rows)
    top_patterns = sorted(pattern_counts.items(), key=lambda item: (-item[1], item[0]))
    if top_patterns:
        notes.append(
            "Pattern mix: "
            + ", ".join(f"{name}={count}" for name, count in top_patterns[:3])
            + "."
        )

    saw_count = sum(1 for row in rows if row.get("bot_saw"))
    rejected_count = sum(1 for row in rows if row.get("bot_rejected"))
    notes.append(f"Bot visibility: saw {saw_count}/{len(rows)} movers; rejected {rejected_count}/{len(rows)}.")

    missed_counts = Counter(_text(row.get("missed_classification")) or "unknown" for row in rows)
    notes.append(
        "Missed classification: "
        + ", ".join(f"{name}={count}" for name, count in sorted(missed_counts.items(), key=lambda item: (-item[1], item[0])))
        + "."
    )

    reason_counts: Counter[str] = Counter()
    for row in rows:
        for reason in list(row.get("reject_reasons") or []):
            reason_counts[_text(reason)] += 1
    if reason_counts:
        notes.append(
            "Top reject reasons: " + ", ".join(f"{name}={count}" for name, count in reason_counts.most_common(3)) + "."
        )

    exec_ok_count = sum(1 for row in rows if row.get("execution_ok"))
    notes.append(f"Executable-quality movers (spread/age checks passing): {exec_ok_count}/{len(rows)}.")
    return notes[:5]


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write(path, json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True) + "\n")


def write_outputs(rows: Sequence[Mapping[str, Any]], out_dir: Path) -> tuple[Path, Path]:
    base = Path(out_dir)
    day = _text(rows[0].get("day")) if rows else ""
    if not day and re.fullmatch(r"\d{4}-\d{2}-\d{2}", base.name):
        day = base.name
    if day and base.name != day:
        base = base / day

    json_path = base / "extreme_movers.json"
    md_path = base / "extreme_movers.md"

    ce_rows = [row for row in rows if _text(row.get("option_side")) == "CE"][:10]
    pe_rows = [row for row in rows if _text(row.get("option_side")) == "PE"][:10]
    missed_counts = Counter(_text(row.get("missed_classification")) or "unknown" for row in rows)

    payload = {
        "day": day,
        "rows": [dict(row) for row in rows],
        "summary": {
            "count": len(rows),
            "ce_count": len(ce_rows),
            "pe_count": len(pe_rows),
            "bot_saw_pct": (sum(1 for row in rows if row.get("bot_saw")) / len(rows)) if rows else 0.0,
            "bot_rejected_pct": (sum(1 for row in rows if row.get("bot_rejected")) / len(rows)) if rows else 0.0,
            "missed_counts": dict(missed_counts),
            "pattern_counts": summarize_patterns(rows),
        },
    }

    lines: list[str] = []
    lines.append("# Extreme Movers Reverse Engineering")
    lines.append("")
    lines.append(f"- day: {day or 'unknown'}")
    lines.append(f"- movers: {len(rows)}")
    lines.append("")
    lines.append("## Top 10 CE Movers")
    lines.extend(_table_md(ce_rows))
    lines.append("")
    lines.append("## Top 10 PE Movers")
    lines.extend(_table_md(pe_rows))
    lines.append("")
    lines.append("## Missed Because")
    if missed_counts:
        lines.append(
            "- "
            + ", ".join(
                f"{name}={count}" for name, count in sorted(missed_counts.items(), key=lambda item: (-item[1], item[0]))
            )
        )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Pattern Notes")
    for note in _pattern_notes(rows):
        lines.append(f"- {note}")
    lines.append("")

    _atomic_write_json(json_path, payload)
    _atomic_write(md_path, "\n".join(lines))
    return md_path, json_path
