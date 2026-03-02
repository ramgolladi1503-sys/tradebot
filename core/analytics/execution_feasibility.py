from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.learning_paths import rejected_candidates_paths
from core.paths import logs_dir, repo_root

from .schema import TradeIntentEvent, TradeOutcome, build_trade_key
from .store import load_trade_intent_events, load_trade_outcomes


IST = ZoneInfo("Asia/Kolkata")


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
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw >= 10_000_000_000:
            return int(raw)
        return int(raw * 1000.0)
    text = str(value).strip()
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


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_side(value: Any) -> str | None:
    text = _norm_text(value).upper()
    return text or None


def _parse_date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = _norm_text(value)
    if not text:
        return datetime.now(tz=IST).date().isoformat()
    return datetime.fromisoformat(text).date().isoformat()


def _to_day_key(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()


def _default_report_path(date_key: str) -> Path:
    base = _norm_text(getattr(cfg, "EXECUTION_FEASIBILITY_REPORT_DIR", ""))
    if base:
        return Path(base) / date_key / "execution_feasibility.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "execution_feasibility.json"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _iter_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    return rows


def _default_quote_paths() -> list[Path]:
    desk_dir = Path(str(getattr(cfg, "DESK_LOG_DIR", logs_dir() / "desks" / "DEFAULT")))
    reject_telemetry_dir = Path(str(getattr(cfg, "REJECT_TELEMETRY_LOG_DIR", desk_dir / "reject_telemetry")))
    paths: list[Path] = [
        Path(str(getattr(cfg, "DECISION_LOG_PATH", desk_dir / "decision_events.jsonl"))),
        desk_dir / "blocked_candidates.jsonl",
        Path(str(getattr(cfg, "REJECT_REASONS_LOG_PATH", desk_dir / "reject_reasons.jsonl"))),
        logs_dir() / "rejected_candidates.jsonl",
    ]
    try:
        paths.extend(sorted(reject_telemetry_dir.glob("rejects_*.jsonl")))
    except Exception:
        pass
    paths.extend(rejected_candidates_paths())

    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _build_trade_key_from_row(row: Mapping[str, Any]) -> str:
    existing = _norm_text(row.get("trade_key"))
    if existing:
        return existing
    return build_trade_key(
        symbol=row.get("symbol"),
        expiry=row.get("expiry_date") or row.get("expiry"),
        strike=row.get("strike"),
        option_type=row.get("option_type") or row.get("type") or row.get("right"),
        side=row.get("side") or row.get("trade_side") or row.get("direction"),
        strategy_id=row.get("strategy_id") or row.get("strategy") or row.get("source"),
    )


def _normalize_quote_row(row: Mapping[str, Any]) -> dict | None:
    ts_ms = (
        _coerce_epoch_ms(row.get("timestamp_epoch_ms"))
        or _coerce_epoch_ms(row.get("ts_epoch_ms"))
        or _coerce_epoch_ms(row.get("timestamp_epoch"))
        or _coerce_epoch_ms(row.get("ts_epoch"))
        or _coerce_epoch_ms(row.get("timestamp_utc_iso"))
        or _coerce_epoch_ms(row.get("timestamp_iso"))
        or _coerce_epoch_ms(row.get("timestamp"))
        or _coerce_epoch_ms(row.get("ts_ist"))
    )
    if ts_ms is None:
        return None
    symbol = _norm_text(row.get("symbol")).upper() or None
    return {
        "event_id": _norm_text(row.get("event_id")) or None,
        "trade_key": _build_trade_key_from_row(row),
        "symbol": symbol,
        "timestamp_epoch_ms": int(ts_ms),
        "side": _safe_side(row.get("side") or row.get("trade_side") or row.get("direction")),
        "intended_entry": _safe_float(row.get("intended_entry") or row.get("entry") or row.get("entry_price")),
        "target": _safe_float(row.get("target") or row.get("target_price")),
        "bid": _safe_float(row.get("bid") or row.get("option_bid") or row.get("best_bid")),
        "ask": _safe_float(row.get("ask") or row.get("option_ask") or row.get("best_ask")),
        "ltp": _safe_float(row.get("ltp") or row.get("last_price") or row.get("option_ltp")),
        "mark_price": _safe_float(row.get("mark_price") or row.get("mark") or row.get("mid")),
        "spread_pct": _safe_float(row.get("spread_pct")),
        "quote_age_sec": _safe_float(row.get("quote_age_sec")),
    }


def load_quote_snapshots(
    *,
    date_key: str,
    quote_paths: Iterable[Path] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    for path in list(quote_paths or _default_quote_paths()):
        for raw in _iter_jsonl(path):
            normalized = _normalize_quote_row(raw)
            if normalized is None:
                continue
            if _to_day_key(int(normalized["timestamp_epoch_ms"])) != date_key:
                continue
            rows.append(normalized)
    rows.sort(key=lambda item: int(item["timestamp_epoch_ms"]))
    return rows


def _coerce_event(item: TradeIntentEvent | Mapping[str, Any]) -> tuple[TradeIntentEvent, dict] | None:
    if isinstance(item, TradeIntentEvent):
        return item, item.to_dict()
    if not isinstance(item, Mapping):
        return None
    raw = dict(item)
    try:
        event = TradeIntentEvent.from_dict(raw)
    except Exception:
        return None
    return event, raw


def _normalize_outcome_row(item: TradeOutcome | Mapping[str, Any]) -> dict | None:
    if isinstance(item, TradeOutcome):
        return {"trade_outcome": item, "event_ref_id": None}
    if not isinstance(item, Mapping):
        return None
    raw = dict(item)
    candidate = raw.get("trade_outcome") if isinstance(raw.get("trade_outcome"), Mapping) else raw
    if not isinstance(candidate, Mapping):
        return None
    try:
        outcome = TradeOutcome.from_dict(dict(candidate))
    except Exception:
        return None
    event_ref_id = _norm_text(raw.get("event_ref_id") or raw.get("source_event_id")) or None
    return {"trade_outcome": outcome, "event_ref_id": event_ref_id}


def _load_outcomes(
    *,
    date_key: str,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    outcome_paths: Iterable[Path] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    if outcomes is not None:
        source_rows = list(outcomes)
    elif outcome_paths:
        source_rows = []
        for path in list(outcome_paths):
            source_rows.extend(_iter_jsonl(path))
    else:
        source_rows = list(load_trade_outcomes())

    for row in source_rows:
        normalized = _normalize_outcome_row(row)
        if normalized is None:
            continue
        outcome = normalized["trade_outcome"]
        if not isinstance(outcome, TradeOutcome):
            continue
        if _to_day_key(int(outcome.ts_epoch_ms)) != date_key:
            continue
        rows.append(normalized)
    rows.sort(key=lambda item: int(item["trade_outcome"].ts_epoch_ms))
    return rows


def _match_outcome(event: TradeIntentEvent, outcomes: Sequence[Mapping[str, Any]]) -> TradeOutcome | None:
    for row in outcomes:
        if _norm_text(row.get("event_ref_id")) == event.event_id:
            out = row.get("trade_outcome")
            if isinstance(out, TradeOutcome):
                return out

    for row in outcomes:
        out = row.get("trade_outcome")
        if isinstance(out, TradeOutcome) and out.event_id == event.event_id:
            return out

    candidates: list[tuple[int, int, TradeOutcome]] = []
    for row in outcomes:
        out = row.get("trade_outcome")
        if not isinstance(out, TradeOutcome):
            continue
        if out.trade_key != event.trade_key:
            continue
        delta = abs(int(out.ts_epoch_ms) - int(event.ts_epoch_ms))
        forward_bias = 0 if int(out.ts_epoch_ms) >= int(event.ts_epoch_ms) else 1
        candidates.append((forward_bias, delta, out))
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]
    return None


def _find_snapshot_for_event(
    event: TradeIntentEvent,
    quote_rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    event_ts = int(event.ts_epoch_ms)

    def _best(candidates: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda row: (
                abs(int(row.get("timestamp_epoch_ms") or 0) - event_ts),
                0 if int(row.get("timestamp_epoch_ms") or 0) <= event_ts else 1,
            ),
        )
        return ranked[0]

    by_event_id = [row for row in quote_rows if _norm_text(row.get("event_id")) == event.event_id]
    found = _best(by_event_id)
    if found is not None:
        return found

    by_trade_key = [row for row in quote_rows if _norm_text(row.get("trade_key")) == event.trade_key]
    found = _best(by_trade_key)
    if found is not None:
        return found

    by_symbol = [row for row in quote_rows if _norm_text(row.get("symbol")).upper() == str(event.symbol).upper()]
    return _best(by_symbol)


def _quote_from_event(event: TradeIntentEvent, raw_event: Mapping[str, Any], snapshot: Mapping[str, Any] | None) -> dict:
    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    snap = snapshot if isinstance(snapshot, Mapping) else {}

    def _first_float(*values: Any) -> float | None:
        for value in values:
            out = _safe_float(value)
            if out is not None:
                return out
        return None

    side = (
        _safe_side(raw_event.get("side") or raw_event.get("trade_side") or raw_event.get("direction"))
        or _safe_side(metrics.get("side") if isinstance(metrics, Mapping) else None)
        or _safe_side(snap.get("side"))
        or _safe_side(event.side)
    )
    intended_entry = _first_float(
        raw_event.get("intended_entry"),
        raw_event.get("entry"),
        raw_event.get("entry_price"),
        metrics.get("intended_entry") if isinstance(metrics, Mapping) else None,
        metrics.get("entry") if isinstance(metrics, Mapping) else None,
        metrics.get("entry_price") if isinstance(metrics, Mapping) else None,
        snap.get("intended_entry"),
    )
    target = _first_float(
        raw_event.get("target"),
        raw_event.get("target_price"),
        metrics.get("target") if isinstance(metrics, Mapping) else None,
        metrics.get("target_price") if isinstance(metrics, Mapping) else None,
        snap.get("target"),
    )
    bid = _first_float(
        raw_event.get("bid"),
        raw_event.get("option_bid"),
        metrics.get("bid") if isinstance(metrics, Mapping) else None,
        metrics.get("option_bid") if isinstance(metrics, Mapping) else None,
        snap.get("bid"),
    )
    ask = _first_float(
        raw_event.get("ask"),
        raw_event.get("option_ask"),
        metrics.get("ask") if isinstance(metrics, Mapping) else None,
        metrics.get("option_ask") if isinstance(metrics, Mapping) else None,
        snap.get("ask"),
    )
    ltp = _first_float(
        raw_event.get("ltp"),
        raw_event.get("last_price"),
        raw_event.get("option_ltp"),
        metrics.get("ltp") if isinstance(metrics, Mapping) else None,
        metrics.get("last_price") if isinstance(metrics, Mapping) else None,
        snap.get("ltp"),
    )
    mark_price = _first_float(
        raw_event.get("mark_price"),
        raw_event.get("mark"),
        metrics.get("mark_price") if isinstance(metrics, Mapping) else None,
        metrics.get("mark") if isinstance(metrics, Mapping) else None,
        snap.get("mark_price"),
    )
    spread_pct = _first_float(
        raw_event.get("spread_pct"),
        metrics.get("spread_pct") if isinstance(metrics, Mapping) else None,
        snap.get("spread_pct"),
    )
    quote_age_sec = _first_float(
        raw_event.get("quote_age_sec"),
        metrics.get("quote_age_sec") if isinstance(metrics, Mapping) else None,
        snap.get("quote_age_sec"),
    )

    quote_ts = _coerce_epoch_ms(snap.get("timestamp_epoch_ms")) if isinstance(snap, Mapping) else None
    if quote_age_sec is None and quote_ts is not None:
        quote_age_sec = max(0.0, abs(float(int(event.ts_epoch_ms) - int(quote_ts))) / 1000.0)

    return {
        "side": side,
        "intended_entry": intended_entry,
        "target": target,
        "bid": bid,
        "ask": ask,
        "ltp": ltp,
        "mark_price": mark_price,
        "spread_pct": spread_pct,
        "quote_age_sec": quote_age_sec,
    }


def evaluate_feasibility(
    *,
    side: str | None,
    intended_entry: float | None,
    target: float | None,
    bid: float | None,
    ask: float | None,
    ltp: float | None,
    mark_price: float | None,
    spread_pct: float | None,
    quote_age_sec: float | None,
    max_spread_pct: float,
    max_quote_age_sec: float,
    slippage_allowance: float,
) -> dict:
    bid_v = _safe_float(bid)
    ask_v = _safe_float(ask)
    ltp_v = _safe_float(ltp)
    mark_v = _safe_float(mark_price)
    spread_v = _safe_float(spread_pct)
    age_v = _safe_float(quote_age_sec)
    entry_v = _safe_float(intended_entry)
    target_v = _safe_float(target)

    quote_present = bool(
        bid_v is not None
        and ask_v is not None
        and bid_v > 0
        and ask_v > 0
        and ask_v >= bid_v
    )
    if mark_v is None and quote_present:
        mark_v = (float(bid_v) + float(ask_v)) / 2.0
    if mark_v is None:
        mark_v = ltp_v

    if spread_v is None and quote_present and mark_v is not None and mark_v > 0:
        spread_v = (float(ask_v) - float(bid_v)) / float(mark_v)

    spread_ok = bool(spread_v is not None and spread_v <= float(max_spread_pct)) if quote_present else False
    quote_age_ok = bool(age_v is not None and age_v <= float(max_quote_age_sec))

    sell_side = str(side or "").upper().startswith("SELL") or str(side or "").upper() in {"SHORT", "S"}
    entry_feasible = False
    target_feasible = False

    if quote_present and entry_v is not None:
        if sell_side:
            entry_feasible = bool(float(bid_v) >= float(entry_v) - float(slippage_allowance))
        else:
            entry_feasible = bool(float(ask_v) <= float(entry_v) + float(slippage_allowance))

    if quote_present and target_v is not None:
        if sell_side:
            target_feasible = bool(float(ask_v) <= float(target_v) + float(slippage_allowance))
        else:
            target_feasible = bool(float(bid_v) >= float(target_v) - float(slippage_allowance))

    if not quote_present:
        quality_label = "NO_BID_ASK"
    elif not spread_ok and not quote_age_ok:
        quality_label = "WIDE_AND_STALE"
    elif not spread_ok:
        quality_label = "WIDE_SPREAD"
    elif not quote_age_ok:
        quality_label = "STALE_QUOTE"
    elif entry_v is None:
        quality_label = "MISSING_ENTRY"
    elif not entry_feasible:
        quality_label = "ENTRY_NOT_FEASIBLE"
    elif target_v is None:
        quality_label = "MISSING_TARGET"
    elif not target_feasible:
        quality_label = "TARGET_NOT_FEASIBLE"
    else:
        quality_label = "FEASIBLE"

    return {
        "side": str(side or "").upper() or None,
        "intended_entry": entry_v,
        "target": target_v,
        "bid": bid_v,
        "ask": ask_v,
        "ltp": ltp_v,
        "mark_price": mark_v,
        "spread_pct": spread_v,
        "quote_age_sec": age_v,
        "quote_present": quote_present,
        "spread_ok": bool(spread_ok),
        "quote_age_ok": bool(quote_age_ok),
        "entry_feasible": bool(entry_feasible),
        "target_feasible": bool(target_feasible),
        "quality_label": quality_label,
    }


def _enrich_outcome(outcome: TradeOutcome, feasibility: Mapping[str, Any]) -> TradeOutcome:
    flags = dict(outcome.exec_feasible_flags or {})
    flags.update(
        {
            "exec_quote_present": bool(feasibility.get("quote_present")),
            "exec_spread_ok": bool(feasibility.get("spread_ok")),
            "exec_quote_age_ok": bool(feasibility.get("quote_age_ok")),
            "exec_entry_feasible": bool(feasibility.get("entry_feasible")),
            "exec_target_feasible": bool(feasibility.get("target_feasible")),
        }
    )
    exec_feasible = bool(
        bool(outcome.exec_feasible)
        and flags["exec_quote_present"]
        and flags["exec_spread_ok"]
        and flags["exec_quote_age_ok"]
        and flags["exec_entry_feasible"]
        and flags["exec_target_feasible"]
    )
    return TradeOutcome(
        trade_key=outcome.trade_key,
        event_id=outcome.event_id,
        outcome=outcome.outcome,
        ts_epoch_ms=outcome.ts_epoch_ms,
        symbol=outcome.symbol,
        mfe_points=outcome.mfe_points,
        mae_points=outcome.mae_points,
        exec_feasible=exec_feasible,
        exec_feasible_flags=flags,
        source=outcome.source,
        reject_reason=outcome.reject_reason,
    )


def build_execution_feasibility_report(
    date: Any,
    *,
    events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    outcome_paths: Iterable[Path] | None = None,
    quote_rows: Sequence[Mapping[str, Any]] | None = None,
    quote_paths: Iterable[Path] | None = None,
    max_spread_pct: float | None = None,
    max_quote_age_sec: float | None = None,
    slippage_allowance: float | None = None,
    output_path: Path | None = None,
) -> dict:
    date_key = _parse_date_key(date)
    spread_threshold = float(
        max_spread_pct
        if max_spread_pct is not None
        else getattr(cfg, "EXECUTION_FEASIBILITY_MAX_SPREAD_PCT", getattr(cfg, "EXEC_MAX_SPREAD_PCT", 0.02))
    )
    quote_age_threshold = float(
        max_quote_age_sec
        if max_quote_age_sec is not None
        else getattr(cfg, "EXECUTION_FEASIBILITY_MAX_QUOTE_AGE_SEC", getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0))
    )
    slippage = float(
        slippage_allowance
        if slippage_allowance is not None
        else getattr(cfg, "EXECUTION_FEASIBILITY_SLIPPAGE_ALLOWANCE", 0.0)
    )

    event_rows = list(events) if events is not None else list(load_trade_intent_events())
    outcome_rows = _load_outcomes(date_key=date_key, outcomes=outcomes, outcome_paths=outcome_paths)
    quotes = list(quote_rows or [])
    if not quotes:
        quotes = load_quote_snapshots(date_key=date_key, quote_paths=quote_paths)

    normalized_quotes: list[dict] = []
    for row in quotes:
        normalized = _normalize_quote_row(row)
        if normalized is None:
            continue
        normalized_quotes.append(normalized)

    total_events = 0
    matched_outcomes = 0
    rows: list[dict] = []

    for item in event_rows:
        coerced = _coerce_event(item)
        if coerced is None:
            continue
        event, raw = coerced
        if _to_day_key(int(event.ts_epoch_ms)) != date_key:
            continue
        total_events += 1

        outcome = _match_outcome(event, outcome_rows)
        if not isinstance(outcome, TradeOutcome):
            continue
        matched_outcomes += 1

        snapshot = _find_snapshot_for_event(event, normalized_quotes)
        quote = _quote_from_event(event, raw, snapshot)
        feasibility = evaluate_feasibility(
            side=quote.get("side") or event.side,
            intended_entry=quote.get("intended_entry"),
            target=quote.get("target"),
            bid=quote.get("bid"),
            ask=quote.get("ask"),
            ltp=quote.get("ltp"),
            mark_price=quote.get("mark_price"),
            spread_pct=quote.get("spread_pct"),
            quote_age_sec=quote.get("quote_age_sec"),
            max_spread_pct=spread_threshold,
            max_quote_age_sec=quote_age_threshold,
            slippage_allowance=slippage,
        )
        enriched = _enrich_outcome(outcome, feasibility)
        rows.append(
            {
                "event_id": event.event_id,
                "trade_key": event.trade_key,
                "symbol": event.symbol,
                "ts_epoch_ms": int(event.ts_epoch_ms),
                "intent": event.intent,
                "side": feasibility.get("side"),
                "intended_entry": feasibility.get("intended_entry"),
                "target": feasibility.get("target"),
                "bid": feasibility.get("bid"),
                "ask": feasibility.get("ask"),
                "ltp": feasibility.get("ltp"),
                "mark_price": feasibility.get("mark_price"),
                "spread_pct": feasibility.get("spread_pct"),
                "quote_age_sec": feasibility.get("quote_age_sec"),
                "exec_entry_feasible": bool(feasibility.get("entry_feasible")),
                "exec_target_feasible": bool(feasibility.get("target_feasible")),
                "exec_quality_label": str(feasibility.get("quality_label") or "UNKNOWN"),
                "trade_outcome": enriched.to_dict(),
            }
        )

    quality_counts: dict[str, int] = {}
    entry_true = 0
    target_true = 0
    feasible_true = 0
    for row in rows:
        label = str(row.get("exec_quality_label") or "UNKNOWN")
        quality_counts[label] = int(quality_counts.get(label, 0)) + 1
        if bool(row.get("exec_entry_feasible")):
            entry_true += 1
        if bool(row.get("exec_target_feasible")):
            target_true += 1
        out = row.get("trade_outcome")
        if isinstance(out, Mapping) and bool(out.get("exec_feasible")):
            feasible_true += 1

    evaluated = len(rows)
    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "thresholds": {
            "max_spread_pct": spread_threshold,
            "max_quote_age_sec": quote_age_threshold,
            "slippage_allowance": slippage,
        },
        "total_events": total_events,
        "matched_outcomes": matched_outcomes,
        "evaluated_outcomes": evaluated,
        "entry_feasible_rate": (float(entry_true) / float(evaluated)) if evaluated else 0.0,
        "target_feasible_rate": (float(target_true) / float(evaluated)) if evaluated else 0.0,
        "exec_feasible_rate": (float(feasible_true) / float(evaluated)) if evaluated else 0.0,
        "exec_quality_counts": dict(sorted(quality_counts.items())),
        "rows": rows,
    }

    out_path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(out_path, report)
    report["output_path"] = str(out_path)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build execution-feasibility analytics report.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange local day).")
    parser.add_argument(
        "--outcome-path",
        action="append",
        default=[],
        help="Optional outcome JSONL path(s); accepts rows with trade_outcome payload.",
    )
    parser.add_argument(
        "--quote-path",
        action="append",
        default=[],
        help="Optional quote snapshot JSONL path(s) with bid/ask at decision time.",
    )
    parser.add_argument("--max-spread-pct", type=float, default=None, help="Override max spread threshold.")
    parser.add_argument("--max-quote-age-sec", type=float, default=None, help="Override max quote age threshold.")
    parser.add_argument("--slippage-allowance", type=float, default=None, help="Override slippage allowance.")
    parser.add_argument("--output", default=None, help="Optional output path override.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    outcome_paths = [Path(p) for p in list(args.outcome_path or []) if _norm_text(p)]
    quote_paths = [Path(p) for p in list(args.quote_path or []) if _norm_text(p)]
    output_path = Path(args.output) if args.output else None

    result = build_execution_feasibility_report(
        args.date,
        outcome_paths=outcome_paths or None,
        quote_paths=quote_paths or None,
        max_spread_pct=args.max_spread_pct,
        max_quote_age_sec=args.max_quote_age_sec,
        slippage_allowance=args.slippage_allowance,
        output_path=output_path,
    )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
