from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import repo_root

from .execution_feasibility import load_quote_snapshots
from .schema import TradeIntentEvent, TradeOutcome
from .store import load_trade_intent_events, load_trade_outcomes


IST = ZoneInfo("Asia/Kolkata")


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
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw >= 10_000_000_000:
            return int(raw)
        return int(raw * 1000.0)
    text = _norm_text(value)
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
    base = _norm_text(getattr(cfg, "FEED_QUALITY_CORRELATION_REPORT_DIR", ""))
    if base:
        return Path(base) / date_key / "feed_quality_correlation.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "feed_quality_correlation.json"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


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
) -> list[dict]:
    rows: list[dict] = []
    source_rows = list(outcomes) if outcomes is not None else list(load_trade_outcomes())
    for row in source_rows:
        normalized = _normalize_outcome_row(row)
        if normalized is None:
            continue
        outcome = normalized.get("trade_outcome")
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
            maybe = row.get("trade_outcome")
            if isinstance(maybe, TradeOutcome):
                return maybe

    for row in outcomes:
        maybe = row.get("trade_outcome")
        if isinstance(maybe, TradeOutcome) and maybe.event_id == event.event_id:
            return maybe

    candidates: list[tuple[int, int, TradeOutcome]] = []
    for row in outcomes:
        maybe = row.get("trade_outcome")
        if not isinstance(maybe, TradeOutcome):
            continue
        if maybe.trade_key != event.trade_key:
            continue
        delta = abs(int(maybe.ts_epoch_ms) - int(event.ts_epoch_ms))
        forward_bias = 0 if int(maybe.ts_epoch_ms) >= int(event.ts_epoch_ms) else 1
        candidates.append((forward_bias, delta, maybe))
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]
    return None


def _normalize_quote_row(row: Mapping[str, Any]) -> dict | None:
    ts_ms = (
        _coerce_epoch_ms(row.get("timestamp_epoch_ms"))
        or _coerce_epoch_ms(row.get("ts_epoch_ms"))
        or _coerce_epoch_ms(row.get("timestamp_epoch"))
        or _coerce_epoch_ms(row.get("ts_epoch"))
        or _coerce_epoch_ms(row.get("timestamp_utc_iso"))
        or _coerce_epoch_ms(row.get("timestamp_iso"))
        or _coerce_epoch_ms(row.get("timestamp"))
    )
    if ts_ms is None:
        return None
    feed_state = _norm_text(row.get("feed_state") or row.get("feed_health") or row.get("state")).upper() or None
    source = _norm_text(row.get("source") or row.get("data_source")) or None
    return {
        "event_id": _norm_text(row.get("event_id")) or None,
        "trade_key": _norm_text(row.get("trade_key")) or None,
        "symbol": _norm_text(row.get("symbol")).upper() or None,
        "timestamp_epoch_ms": int(ts_ms),
        "quote_age_sec": _safe_float(row.get("quote_age_sec")),
        "spread_pct": _safe_float(row.get("spread_pct")),
        "feed_state": feed_state,
        "source": source,
    }


def _find_snapshot_for_event(event: TradeIntentEvent, quote_rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
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


def _first_float(*values: Any) -> float | None:
    for value in values:
        out = _safe_float(value)
        if out is not None:
            return out
    return None


def _extract_quality_metrics(event: TradeIntentEvent, raw_event: Mapping[str, Any], snapshot: Mapping[str, Any] | None) -> dict:
    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    snap = snapshot if isinstance(snapshot, Mapping) else {}

    quote_age_sec = _first_float(
        raw_event.get("quote_age_sec"),
        metrics.get("quote_age_sec") if isinstance(metrics, Mapping) else None,
        snap.get("quote_age_sec"),
    )
    spread_pct = _first_float(
        raw_event.get("spread_pct"),
        metrics.get("spread_pct") if isinstance(metrics, Mapping) else None,
        snap.get("spread_pct"),
    )
    feed_state = (
        _norm_text(raw_event.get("feed_state") or raw_event.get("feed_health") or raw_event.get("state")).upper()
        or _norm_text(metrics.get("feed_state") if isinstance(metrics, Mapping) else None).upper()
        or _norm_text(metrics.get("feed_health") if isinstance(metrics, Mapping) else None).upper()
        or _norm_text(snap.get("feed_state")).upper()
        or "UNKNOWN"
    )
    source = (
        _norm_text(raw_event.get("data_source"))
        or _norm_text(metrics.get("data_source") if isinstance(metrics, Mapping) else None)
        or _norm_text(snap.get("source"))
        or _norm_text(snap.get("data_source"))
        or _norm_text(raw_event.get("source"))
        or _norm_text(metrics.get("source") if isinstance(metrics, Mapping) else None)
        or _norm_text(event.source)
        or "unknown"
    )
    return {
        "quote_age_sec": quote_age_sec,
        "spread_pct": spread_pct,
        "feed_state": feed_state,
        "source": source,
    }


def _format_threshold(value: float) -> str:
    text = f"{float(value):.6g}"
    return text


def _build_bucket_labels(edges: Sequence[float]) -> list[str]:
    sorted_edges = sorted({float(edge) for edge in edges})
    if not sorted_edges:
        return ["all", "UNKNOWN"]
    labels: list[str] = []
    labels.append(f"<= {_format_threshold(sorted_edges[0])}")
    for prev, cur in zip(sorted_edges, sorted_edges[1:]):
        labels.append(f"({_format_threshold(prev)}, {_format_threshold(cur)}]")
    labels.append(f"> {_format_threshold(sorted_edges[-1])}")
    labels.append("UNKNOWN")
    return labels


def _bucket_label(value: float | None, edges: Sequence[float]) -> str:
    if value is None:
        return "UNKNOWN"
    ordered = sorted({float(edge) for edge in edges})
    if not ordered:
        return "all"
    val = float(value)
    if val <= ordered[0]:
        return f"<= {_format_threshold(ordered[0])}"
    for prev, cur in zip(ordered, ordered[1:]):
        if prev < val <= cur:
            return f"({_format_threshold(prev)}, {_format_threshold(cur)}]"
    return f"> {_format_threshold(ordered[-1])}"


def _outcome_to_win_flag(outcome: str) -> int:
    text = _norm_text(outcome).lower()
    if text == "hit_target":
        return 1
    return 0


def _pearson_correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / float(len(xs))
    mean_y = sum(ys) / float(len(ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0.0 or var_y <= 0.0:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return float(cov / ((var_x ** 0.5) * (var_y ** 0.5)))


def _bucketed_outcomes(rows: Sequence[Mapping[str, Any]], metric_key: str, edges: Sequence[float]) -> list[dict]:
    labels = _build_bucket_labels(edges)
    acc: dict[str, dict[str, Any]] = {
        label: {
            "bucket": label,
            "count": 0,
            "wins": 0,
            "losses": 0,
            "no_hit": 0,
            "win_rate": 0.0,
        }
        for label in labels
    }
    for row in rows:
        outcome = _norm_text(row.get("outcome")).lower()
        if outcome not in {"hit_target", "hit_sl", "no_hit"}:
            continue
        val = _safe_float(row.get(metric_key))
        bucket = _bucket_label(val, edges)
        slot = acc.setdefault(
            bucket,
            {"bucket": bucket, "count": 0, "wins": 0, "losses": 0, "no_hit": 0, "win_rate": 0.0},
        )
        slot["count"] = int(slot["count"]) + 1
        if outcome == "hit_target":
            slot["wins"] = int(slot["wins"]) + 1
        elif outcome == "hit_sl":
            slot["losses"] = int(slot["losses"]) + 1
        else:
            slot["no_hit"] = int(slot["no_hit"]) + 1

    out: list[dict] = []
    for label in labels:
        row = acc[label]
        count = int(row["count"])
        row["win_rate"] = (float(row["wins"]) / float(count)) if count > 0 else 0.0
        out.append(row)
    return out


def _feed_state_outcomes(rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    acc: dict[str, dict[str, Any]] = {}
    for row in rows:
        outcome = _norm_text(row.get("outcome")).lower()
        if outcome not in {"hit_target", "hit_sl", "no_hit"}:
            continue
        state = _norm_text(row.get("feed_state")).upper() or "UNKNOWN"
        slot = acc.setdefault(
            state,
            {
                "feed_state": state,
                "count": 0,
                "wins": 0,
                "losses": 0,
                "no_hit": 0,
                "win_rate": 0.0,
            },
        )
        slot["count"] = int(slot["count"]) + 1
        if outcome == "hit_target":
            slot["wins"] = int(slot["wins"]) + 1
        elif outcome == "hit_sl":
            slot["losses"] = int(slot["losses"]) + 1
        else:
            slot["no_hit"] = int(slot["no_hit"]) + 1

    out: list[dict] = []
    for state in sorted(acc.keys()):
        row = acc[state]
        count = int(row["count"])
        row["win_rate"] = (float(row["wins"]) / float(count)) if count > 0 else 0.0
        out.append(row)
    return out


def _threshold_suggestion(
    rows: Sequence[Mapping[str, Any]],
    *,
    metric_key: str,
    edges: Sequence[float],
    min_samples: int,
    min_inflection_drop: float,
) -> dict | None:
    ordered = sorted({float(edge) for edge in edges})
    candidates: list[dict] = []

    for edge in ordered:
        below = [row for row in rows if _safe_float(row.get(metric_key)) is not None and float(_safe_float(row.get(metric_key)) or 0.0) <= edge]
        above = [row for row in rows if _safe_float(row.get(metric_key)) is not None and float(_safe_float(row.get(metric_key)) or 0.0) > edge]
        if len(below) < int(min_samples) or len(above) < int(min_samples):
            continue

        below_win = sum(_outcome_to_win_flag(_norm_text(row.get("outcome")).lower()) for row in below) / float(len(below))
        above_win = sum(_outcome_to_win_flag(_norm_text(row.get("outcome")).lower()) for row in above) / float(len(above))
        drop = float(below_win - above_win)
        if drop >= float(min_inflection_drop):
            candidates.append(
                {
                    "threshold": float(edge),
                    "win_rate_at_or_below": float(below_win),
                    "win_rate_above": float(above_win),
                    "drop": float(drop),
                    "samples_at_or_below": int(len(below)),
                    "samples_above": int(len(above)),
                }
            )

    if not candidates:
        return None
    candidates.sort(key=lambda row: (float(row["drop"]), float(row["threshold"])), reverse=True)
    return candidates[0]


def _feed_state_suggestions(
    rows: Sequence[Mapping[str, Any]],
    *,
    min_samples: int,
    min_inflection_drop: float,
) -> list[dict]:
    stats = {row["feed_state"]: row for row in _feed_state_outcomes(rows)}
    ok = stats.get("OK")
    if not ok or int(ok.get("count") or 0) < int(min_samples):
        return []
    ok_win = float(ok.get("win_rate") or 0.0)

    suggestions: list[dict] = []
    for state, row in sorted(stats.items()):
        if state == "OK":
            continue
        count = int(row.get("count") or 0)
        if count < int(min_samples):
            continue
        win_rate = float(row.get("win_rate") or 0.0)
        drop = float(ok_win - win_rate)
        if drop >= float(min_inflection_drop):
            suggestions.append(
                {
                    "feed_state": state,
                    "ok_win_rate": float(ok_win),
                    "state_win_rate": float(win_rate),
                    "drop_vs_ok": float(drop),
                    "samples": int(count),
                }
            )
    return suggestions


def build_feed_quality_correlation_report(
    date: Any,
    *,
    events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    quote_rows: Sequence[Mapping[str, Any]] | None = None,
    quote_paths: Iterable[Path] | None = None,
    include_intents: Sequence[str] | None = None,
    quote_age_buckets_sec: Sequence[float] | None = None,
    spread_buckets: Sequence[float] | None = None,
    min_samples: int | None = None,
    min_inflection_drop: float | None = None,
    output_path: Path | None = None,
) -> dict:
    date_key = _parse_date_key(date)
    intents = {
        _norm_text(intent).lower()
        for intent in (include_intents if include_intents is not None else ("accepted", "rejected", "advisory"))
        if _norm_text(intent)
    }
    if not intents:
        intents = {"accepted", "rejected", "advisory"}

    age_buckets = [
        float(v)
        for v in (
            quote_age_buckets_sec
            if quote_age_buckets_sec is not None
            else getattr(cfg, "FEED_QUALITY_QUOTE_AGE_BUCKETS_SEC", (0.5, 1.0, 2.0, 5.0))
        )
    ]
    spread_bucket_values = [
        float(v)
        for v in (
            spread_buckets
            if spread_buckets is not None
            else getattr(cfg, "FEED_QUALITY_SPREAD_BUCKETS", (0.005, 0.01, 0.02, 0.05))
        )
    ]
    sample_floor = int(min_samples if min_samples is not None else getattr(cfg, "FEED_QUALITY_MIN_SAMPLES", 5))
    drop_floor = float(
        min_inflection_drop if min_inflection_drop is not None else getattr(cfg, "FEED_QUALITY_MIN_INFLECTION_DROP", 0.1)
    )

    event_rows = list(events) if events is not None else list(load_trade_intent_events())
    outcome_rows = _load_outcomes(date_key=date_key, outcomes=outcomes)

    loaded_quotes = list(quote_rows or [])
    if not loaded_quotes:
        loaded_quotes = load_quote_snapshots(date_key=date_key, quote_paths=quote_paths)
    normalized_quotes: list[dict] = []
    for row in loaded_quotes:
        normalized = _normalize_quote_row(row)
        if normalized is None:
            continue
        if _to_day_key(int(normalized["timestamp_epoch_ms"])) != date_key:
            continue
        normalized_quotes.append(normalized)

    scanned_events = 0
    matched_outcomes = 0
    rows: list[dict] = []

    for item in event_rows:
        coerced = _coerce_event(item)
        if coerced is None:
            continue
        event, raw = coerced
        if _to_day_key(int(event.ts_epoch_ms)) != date_key:
            continue
        scanned_events += 1
        if _norm_text(event.intent).lower() not in intents:
            continue

        outcome = _match_outcome(event, outcome_rows)
        if not isinstance(outcome, TradeOutcome):
            continue
        matched_outcomes += 1

        snapshot = _find_snapshot_for_event(event, normalized_quotes)
        quality = _extract_quality_metrics(event, raw, snapshot)

        rows.append(
            {
                "event_id": event.event_id,
                "trade_key": event.trade_key,
                "symbol": event.symbol,
                "intent": event.intent,
                "source": quality["source"],
                "feed_state": quality["feed_state"],
                "quote_age_sec": quality["quote_age_sec"],
                "spread_pct": quality["spread_pct"],
                "outcome": outcome.outcome,
                "ts_epoch_ms": int(event.ts_epoch_ms),
            }
        )

    quote_age_samples = [
        (_safe_float(row.get("quote_age_sec")), _outcome_to_win_flag(_norm_text(row.get("outcome")).lower()))
        for row in rows
        if _safe_float(row.get("quote_age_sec")) is not None
    ]
    spread_samples = [
        (_safe_float(row.get("spread_pct")), _outcome_to_win_flag(_norm_text(row.get("outcome")).lower()))
        for row in rows
        if _safe_float(row.get("spread_pct")) is not None
    ]

    quote_age_corr = _pearson_correlation(
        [float(x[0]) for x in quote_age_samples if x[0] is not None],
        [float(x[1]) for x in quote_age_samples if x[0] is not None],
    )
    spread_corr = _pearson_correlation(
        [float(x[0]) for x in spread_samples if x[0] is not None],
        [float(x[1]) for x in spread_samples if x[0] is not None],
    )

    quote_age_bucketed = _bucketed_outcomes(rows, "quote_age_sec", age_buckets)
    spread_bucketed = _bucketed_outcomes(rows, "spread_pct", spread_bucket_values)
    by_feed_state = _feed_state_outcomes(rows)

    threshold_suggestions = {
        "quote_age_sec": _threshold_suggestion(
            rows,
            metric_key="quote_age_sec",
            edges=age_buckets,
            min_samples=sample_floor,
            min_inflection_drop=drop_floor,
        ),
        "spread_pct": _threshold_suggestion(
            rows,
            metric_key="spread_pct",
            edges=spread_bucket_values,
            min_samples=sample_floor,
            min_inflection_drop=drop_floor,
        ),
        "feed_state": _feed_state_suggestions(rows, min_samples=sample_floor, min_inflection_drop=drop_floor),
    }

    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "params": {
            "include_intents": sorted(intents),
            "quote_age_buckets_sec": sorted({float(v) for v in age_buckets}),
            "spread_buckets": sorted({float(v) for v in spread_bucket_values}),
            "min_samples": int(sample_floor),
            "min_inflection_drop": float(drop_floor),
        },
        "counts": {
            "scanned_events": int(scanned_events),
            "matched_outcomes": int(matched_outcomes),
            "rows": int(len(rows)),
        },
        "correlations": {
            "quote_age_sec_vs_win": quote_age_corr,
            "spread_pct_vs_win": spread_corr,
        },
        "bucketed_outcomes": {
            "quote_age_sec": quote_age_bucketed,
            "spread_pct": spread_bucketed,
            "feed_state": by_feed_state,
        },
        "threshold_suggestions": threshold_suggestions,
        "rows": rows,
    }

    out_path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(out_path, report)
    report["output_path"] = str(out_path)
    return report


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Correlate outcomes with feed and quote quality metrics.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange local day).")
    parser.add_argument(
        "--include-intent",
        action="append",
        default=[],
        help="Intent(s) to include: accepted|rejected|advisory. Repeatable.",
    )
    parser.add_argument(
        "--quote-path",
        action="append",
        default=[],
        help="Optional quote JSONL path(s) with quote_age_sec/spread_pct/feed_state.",
    )
    parser.add_argument(
        "--quote-age-bucket",
        action="append",
        type=float,
        default=[],
        help="Quote age bucket edge(s) in seconds. Repeatable.",
    )
    parser.add_argument(
        "--spread-bucket",
        action="append",
        type=float,
        default=[],
        help="Spread bucket edge(s) as fractional pct. Repeatable.",
    )
    parser.add_argument("--min-samples", type=int, default=None, help="Minimum sample size per side for threshold suggestions.")
    parser.add_argument("--min-inflection-drop", type=float, default=None, help="Minimum win-rate drop for a suggestion.")
    parser.add_argument("--output", default=None, help="Optional output path override.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    include_intents = [str(v) for v in list(args.include_intent or []) if _norm_text(v)]
    quote_paths = [Path(p) for p in list(args.quote_path or []) if _norm_text(p)]
    output_path = Path(args.output) if args.output else None

    payload = build_feed_quality_correlation_report(
        args.date,
        quote_paths=quote_paths or None,
        include_intents=include_intents or None,
        quote_age_buckets_sec=list(args.quote_age_bucket or []) or None,
        spread_buckets=list(args.spread_bucket or []) or None,
        min_samples=args.min_samples,
        min_inflection_drop=args.min_inflection_drop,
        output_path=output_path,
    )
    print(
        json.dumps(
            {
                "date": payload.get("date"),
                "counts": payload.get("counts"),
                "correlations": payload.get("correlations"),
                "threshold_suggestions": payload.get("threshold_suggestions"),
                "output_path": payload.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
