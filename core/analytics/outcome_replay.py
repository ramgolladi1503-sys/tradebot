from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import repo_root

from .schema import TradeIntentEvent, TradeOutcome
from .store import load_trade_intent_events


IST = ZoneInfo("Asia/Kolkata")
SeriesRow = dict[str, Any]
SeriesLoader = Callable[[dict[str, Any], int, int, str], tuple[list[SeriesRow], str]]


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:  # NaN guard
            return None
        return out
    except Exception:
        return None


def _coerce_epoch_ms(value: Any) -> int | None:
    try:
        if value is None:
            return None
        out = int(float(value))
        if out < 1_000_000_000_000:
            out *= 1000
        return out
    except Exception:
        return None


def _to_day_key(ts_epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(ts_epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()


def _event_ts_ms(event: Mapping[str, Any]) -> int | None:
    for key in (
        "ts_epoch_ms",
        "reject_ts_epoch_ms",
        "reject_ts_epoch",
        "timestamp_epoch_ms",
        "event_ts_epoch_ms",
        "event_ts_epoch",
        "timestamp",
        "ts",
    ):
        ts_ms = _coerce_epoch_ms(event.get(key))
        if ts_ms is not None:
            return ts_ms
    return None


def _event_side(event: Mapping[str, Any]) -> str:
    return _norm_text(event.get("side")).upper() or "BUY"


def _event_symbol(event: Mapping[str, Any]) -> str:
    return _norm_text(event.get("symbol")).upper() or "UNKNOWN"


def _event_trade_key(event: Mapping[str, Any], ts_ms: int) -> str:
    return _norm_text(event.get("trade_key")) or f"{_event_symbol(event)}|{ts_ms}"


def _event_id(event: Mapping[str, Any], trade_key: str, ts_ms: int) -> str:
    return _norm_text(event.get("event_id")) or f"evt_{trade_key}_{ts_ms}"


def _event_price(event: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float(event.get(key))
        if value is not None:
            return value
    metrics = event.get("metrics_snapshot")
    if isinstance(metrics, Mapping):
        for key in keys:
            value = _safe_float(metrics.get(key))
            if value is not None:
                return value
    return None


def _append_reason(reason_list: list[str], reason: Any) -> None:
    text = _norm_text(reason)
    if not text:
        return
    if text not in reason_list:
        reason_list.append(text)


def _event_reason_codes(event: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    _append_reason(reasons, event.get("reject_reason"))
    for key in ("reason_codes", "reject_reasons", "gate_reasons"):
        raw = event.get(key)
        if isinstance(raw, (list, tuple)):
            for item in raw:
                _append_reason(reasons, item)
    gate_decisions = event.get("gate_decisions")
    if isinstance(gate_decisions, (list, tuple)):
        for decision in gate_decisions:
            if not isinstance(decision, Mapping):
                continue
            if decision.get("passed") is False:
                _append_reason(reasons, decision.get("reason"))
    return reasons


def _build_reject_attribution(
    event: Mapping[str, Any],
    *,
    outcome_reason: str,
    has_candle_data: bool,
    series_source: str,
) -> tuple[str | None, list[str]]:
    normalized_outcome_reason = _norm_text(outcome_reason).upper()
    normalized_series_source = _norm_text(series_source).lower()
    missing_series = (not has_candle_data) or normalized_outcome_reason == "NO_SERIES_DATA" or normalized_series_source in {
        "no_series_data",
        "no_market_data_loader",
    }
    if missing_series:
        return "NO_SERIES_DATA", ["NO_SERIES_DATA"]

    reasons = _event_reason_codes(event)
    primary = reasons[0] if reasons else None
    if primary is None:
        return None, []
    ordered = [primary] + [item for item in reasons[1:] if item != primary]
    return primary, ordered


def _rows_from_table_like(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [dict(row) for row in data if isinstance(row, Mapping)]
    if isinstance(data, tuple):
        return [dict(row) for row in data if isinstance(row, Mapping)]
    to_dict = getattr(data, "to_dict", None)
    if callable(to_dict):
        try:
            rows = to_dict(orient="records")
            if isinstance(rows, list):
                return [dict(row) for row in rows if isinstance(row, Mapping)]
        except Exception:
            return []
    return []


def _normalize_ohlc_rows(rows: Sequence[Mapping[str, Any]]) -> list[SeriesRow]:
    out: list[SeriesRow] = []
    for row in rows:
        ts_ms = _coerce_epoch_ms(
            row.get("time_ms")
            if row.get("time_ms") is not None
            else row.get("timestamp_epoch_ms")
            if row.get("timestamp_epoch_ms") is not None
            else row.get("ts_epoch_ms")
            if row.get("ts_epoch_ms") is not None
            else row.get("date")
            if row.get("date") is not None
            else row.get("time")
        )
        high = _safe_float(row.get("high"))
        low = _safe_float(row.get("low"))
        close = _safe_float(row.get("close"))
        open_px = _safe_float(row.get("open"))
        if ts_ms is None:
            continue
        if high is None:
            high = close if close is not None else open_px
        if low is None:
            low = close if close is not None else open_px
        if high is None or low is None:
            continue
        ref_price = close if close is not None else ((high + low) / 2.0)
        out.append(
            {
                "time_ms": int(ts_ms),
                "high": float(high),
                "low": float(low),
                "ref_price": float(ref_price),
                "source": _norm_text(row.get("source")) or "instrument_candle",
            }
        )
    out.sort(key=lambda r: int(r["time_ms"]))
    return out


def _normalize_option_rows(rows: Sequence[Mapping[str, Any]]) -> list[SeriesRow]:
    out: list[SeriesRow] = []
    for row in rows:
        ts_ms = _coerce_epoch_ms(
            row.get("time_ms")
            if row.get("time_ms") is not None
            else row.get("timestamp_epoch_ms")
            if row.get("timestamp_epoch_ms") is not None
            else row.get("ts_epoch_ms")
            if row.get("ts_epoch_ms") is not None
            else row.get("date")
        )
        if ts_ms is None:
            continue

        bid = _safe_float(row.get("bid"))
        ask = _safe_float(row.get("ask"))
        mark = _safe_float(row.get("mark_price"))
        ltp = _safe_float(row.get("ltp"))
        close = _safe_float(row.get("close"))

        if mark is None and bid is not None and ask is not None:
            mark = (bid + ask) / 2.0
        if mark is None:
            mark = ltp if ltp is not None else close
        if mark is None:
            continue

        high_candidates = [mark]
        low_candidates = [mark]
        if bid is not None:
            high_candidates.append(bid)
            low_candidates.append(bid)
        if ask is not None:
            high_candidates.append(ask)
            low_candidates.append(ask)

        out.append(
            {
                "time_ms": int(ts_ms),
                "high": float(max(high_candidates)),
                "low": float(min(low_candidates)),
                "ref_price": float(mark),
                "source": _norm_text(row.get("source")) or "option_mark_series",
                "bid": bid,
                "ask": ask,
                "mark_price": mark,
                "ltp": ltp,
            }
        )
    out.sort(key=lambda r: int(r["time_ms"]))
    return out


def _resolve_underlying_symbol(event: Mapping[str, Any]) -> str:
    symbol = _event_symbol(event)
    tradingsymbol = _norm_text(event.get("tradingsymbol")).upper()
    text = f"{symbol} {tradingsymbol}"
    for name in ("BANKNIFTY", "NIFTY", "SENSEX"):
        if name in text:
            return name
    return symbol


def _default_series_loader(event_row: dict[str, Any], start_ms: int, end_ms: int, interval: str) -> tuple[list[SeriesRow], str]:
    try:
        from core.market_data import get_candles, get_option_candles_or_snapshots
    except Exception:
        return [], "no_market_data_loader"

    trade_row = {
        "instrument_token": event_row.get("instrument_token") or event_row.get("token"),
        "tradingsymbol": event_row.get("tradingsymbol"),
        "symbol": event_row.get("symbol"),
    }
    option_rows: list[SeriesRow] = []
    try:
        option_df = get_option_candles_or_snapshots(trade_row, interval, int(start_ms), int(end_ms))
        option_rows = _normalize_option_rows(_rows_from_table_like(option_df))
    except Exception:
        option_rows = []
    if option_rows:
        return option_rows, "option_mark_series"

    symbol = _resolve_underlying_symbol(event_row)
    candle_rows: list[SeriesRow] = []
    try:
        candle_df = get_candles(symbol, interval, int(start_ms), int(end_ms))
        candle_rows = _normalize_ohlc_rows(_rows_from_table_like(candle_df))
    except Exception:
        candle_rows = []
    if candle_rows:
        return candle_rows, "instrument_candles"
    return [], "no_series_data"


def _empty_outcome_row(event: Mapping[str, Any], *, reason: str, series_source: str = "no_series_data") -> dict:
    ts_ms = _event_ts_ms(event) or int(datetime.now(tz=timezone.utc).timestamp() * 1000.0)
    trade_key = _event_trade_key(event, ts_ms)
    event_id = _event_id(event, trade_key, ts_ms)
    reject_reason, reason_codes = _build_reject_attribution(
        event,
        outcome_reason=reason,
        has_candle_data=False,
        series_source=series_source,
    )
    outcome = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_id}",
        outcome="no_hit",
        ts_epoch_ms=int(ts_ms),
        symbol=_event_symbol(event),
        mfe_points=0.0,
        mae_points=0.0,
        exec_feasible=False,
        exec_feasible_flags={"has_candle_data": False, "has_series_data": False},
        source="analytics_outcome_replay",
        reject_reason=reject_reason,
        reject_reasons=tuple(reason_codes),
        primary_reject_reason=reject_reason,
    )
    trade_outcome = outcome.to_dict()
    trade_outcome["reason_codes"] = list(reason_codes)
    entry = _event_price(event, "entry", "intended_entry", "entry_price", "mark")
    target = _event_price(event, "target", "target_price")
    stop = _event_price(event, "stop", "stop_price", "stop_loss")
    target_points = abs(target - entry) if (entry is not None and target is not None) else None
    stop_points = abs(entry - stop) if (entry is not None and stop is not None) else None
    return {
        "event_ref_id": event_id,
        "trade_key": trade_key,
        "symbol": _event_symbol(event),
        "series_source": series_source,
        "outcome_reason": reason,
        "resolution_ts_epoch_ms": int(ts_ms),
        "target_points": target_points,
        "stop_points": stop_points,
        "reason_codes": list(reason_codes),
        "trade_outcome": trade_outcome,
    }


def analyze_event_outcome(
    event: TradeIntentEvent | Mapping[str, Any],
    lookahead_minutes: int | Sequence[Mapping[str, Any]] = 30,
    candle_interval: str = "1minute",
    *,
    series_loader: SeriesLoader | None = None,
) -> dict:
    event_row = event.to_dict() if isinstance(event, TradeIntentEvent) else dict(event or {})
    event_ts_ms = _event_ts_ms(event_row)
    if event_ts_ms is None:
        return _empty_outcome_row(event_row, reason="MISSING_EVENT_TS")

    if isinstance(lookahead_minutes, Sequence) and not isinstance(lookahead_minutes, (str, bytes)):
        legacy_rows = _normalize_ohlc_rows(lookahead_minutes)

        def _legacy_loader(_: dict[str, Any], _start: int, _end: int, _interval: str) -> tuple[list[SeriesRow], str]:
            return legacy_rows, "legacy_candle_series"

        replay_lookahead_min = 30
        loader = _legacy_loader
    else:
        replay_lookahead_min = max(1, int(lookahead_minutes))
        loader = series_loader or _default_series_loader

    side = _event_side(event_row)
    window_start_ms = int(event_ts_ms)
    window_end_ms = int(window_start_ms + replay_lookahead_min * 60 * 1000)

    try:
        series_rows, series_source = loader(event_row, window_start_ms, window_end_ms, str(candle_interval or "1minute"))
    except Exception as exc:
        return _empty_outcome_row(
            event_row,
            reason=f"SERIES_LOAD_ERROR:{type(exc).__name__}",
            series_source="series_loader_error",
        )
    series_rows = [row for row in list(series_rows or []) if _coerce_epoch_ms(row.get("time_ms")) is not None]
    series_rows = [
        row
        for row in series_rows
        if window_start_ms <= int(_coerce_epoch_ms(row.get("time_ms")) or 0) <= window_end_ms
    ]
    series_rows.sort(key=lambda r: int(_coerce_epoch_ms(r.get("time_ms")) or 0))
    if not series_rows:
        return _empty_outcome_row(event_row, reason="NO_SERIES_DATA", series_source=series_source)

    entry = _event_price(event_row, "entry", "intended_entry", "entry_price", "mark")
    if entry is None:
        entry = _safe_float(series_rows[0].get("ref_price"))
    target = _event_price(event_row, "target", "target_price")
    stop = _event_price(event_row, "stop", "stop_price", "stop_loss")
    if entry is None or target is None or stop is None:
        return _empty_outcome_row(event_row, reason="MISSING_LEVELS", series_source=series_source)

    outcome_label = "no_hit"
    outcome_reason = "WINDOW_EXHAUSTED"
    resolution_ts_ms = int(_coerce_epoch_ms(series_rows[-1].get("time_ms")) or window_end_ms)
    mfe_points: float | None = None
    mae_points: float | None = None

    for row in series_rows:
        high = _safe_float(row.get("high"))
        low = _safe_float(row.get("low"))
        ts_ms = int(_coerce_epoch_ms(row.get("time_ms")) or 0)
        if high is None or low is None or ts_ms <= 0:
            continue

        if side == "SELL":
            favorable = float(entry - low)
            adverse = float(entry - high)
            target_hit = bool(low <= target)
            sl_hit = bool(high >= stop)
        else:
            favorable = float(high - entry)
            adverse = float(low - entry)
            target_hit = bool(high >= target)
            sl_hit = bool(low <= stop)

        mfe_points = favorable if mfe_points is None else max(mfe_points, favorable)
        mae_points = adverse if mae_points is None else min(mae_points, adverse)

        if target_hit and sl_hit:
            outcome_label = "no_hit"
            outcome_reason = "AMBIGUOUS_SAME_CANDLE"
            resolution_ts_ms = ts_ms
            break
        if target_hit:
            outcome_label = "hit_target"
            outcome_reason = "TARGET_FIRST"
            resolution_ts_ms = ts_ms
            break
        if sl_hit:
            outcome_label = "hit_sl"
            outcome_reason = "SL_FIRST"
            resolution_ts_ms = ts_ms
            break

    trade_key = _event_trade_key(event_row, event_ts_ms)
    event_id = _event_id(event_row, trade_key, event_ts_ms)
    reject_reason, reason_codes = _build_reject_attribution(
        event_row,
        outcome_reason=outcome_reason,
        has_candle_data=True,
        series_source=series_source,
    )
    trade_outcome = TradeOutcome(
        trade_key=trade_key,
        event_id=f"out_{event_id}",
        outcome=outcome_label,  # type: ignore[arg-type]
        ts_epoch_ms=int(resolution_ts_ms),
        symbol=_event_symbol(event_row),
        mfe_points=(round(float(mfe_points), 6) if mfe_points is not None else None),
        mae_points=(round(float(mae_points), 6) if mae_points is not None else None),
        exec_feasible=True,
        exec_feasible_flags={"has_candle_data": True, "has_series_data": True},
        source="analytics_outcome_replay",
        reject_reason=reject_reason,
        reject_reasons=tuple(reason_codes),
        primary_reject_reason=reject_reason,
    )
    trade_outcome_payload = trade_outcome.to_dict()
    trade_outcome_payload["reason_codes"] = list(reason_codes)
    return {
        "event_ref_id": event_id,
        "trade_key": trade_key,
        "symbol": _event_symbol(event_row),
        "series_source": series_source,
        "outcome_reason": outcome_reason,
        "resolution_ts_epoch_ms": int(resolution_ts_ms),
        "target_points": abs(float(target - entry)),
        "stop_points": abs(float(entry - stop)),
        "reason_codes": list(reason_codes),
        "trade_outcome": trade_outcome_payload,
    }


def _default_outcomes_path(date_key: str) -> Path:
    base = _norm_text(getattr(cfg, "OUTCOME_REPLAY_DIR", ""))
    if base:
        return Path(base) / f"{date_key}.jsonl"
    return repo_root() / "runtime" / "analytics" / "outcomes" / f"{date_key}.jsonl"


def _parse_date_key(text: str) -> str:
    return datetime.fromisoformat(str(text).strip()).date().isoformat()


def _atomic_write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")
    tmp.replace(path)


def build_outcomes_for_date(
    date: str,
    *,
    scope: str = "rejected",
    lookahead_minutes: int = 30,
    candle_interval: str = "1minute",
    output_path: Path | None = None,
) -> dict:
    date_key = _parse_date_key(date)
    normalized_scope = _norm_text(scope).lower() or "rejected"
    if normalized_scope not in {"rejected", "accepted", "advisory"}:
        raise ValueError(f"invalid_scope:{scope}")

    events = [
        event
        for event in load_trade_intent_events()
        if _to_day_key(int(event.ts_epoch_ms)) == date_key and _norm_text(event.intent).lower() == normalized_scope
    ]

    rows = [
        analyze_event_outcome(
            event,
            lookahead_minutes=int(lookahead_minutes),
            candle_interval=str(candle_interval or "1minute"),
        )
        for event in events
    ]

    path = Path(output_path) if output_path is not None else _default_outcomes_path(date_key)
    _atomic_write_jsonl(path, rows)

    outcome_counts = {"hit_target": 0, "hit_sl": 0, "no_hit": 0}
    for row in rows:
        out = _norm_text(((row.get("trade_outcome") or {}).get("outcome"))).lower()
        if out in outcome_counts:
            outcome_counts[out] += 1

    return {
        "date": date_key,
        "scope": normalized_scope,
        "lookahead_minutes": int(lookahead_minutes),
        "candle_interval": str(candle_interval),
        "count": len(rows),
        "outcome_counts": outcome_counts,
        "output_path": str(path),
    }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline analytics outcome replay for a trading date.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange local day).")
    parser.add_argument(
        "--scope",
        default="rejected",
        choices=["rejected", "accepted", "advisory"],
        help="Intent scope to replay.",
    )
    parser.add_argument("--lookahead-min", type=int, default=30, help="Replay lookahead in minutes.")
    parser.add_argument("--candle-interval", default="1minute", help="Candle interval label for replay.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    payload = build_outcomes_for_date(
        args.date,
        scope=args.scope,
        lookahead_minutes=int(args.lookahead_min),
        candle_interval=str(args.candle_interval),
    )
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
