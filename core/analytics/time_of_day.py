from __future__ import annotations

import argparse
from datetime import date, datetime, time as dtime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core import market_calendar
from core.paths import repo_root

from .schema import TradeIntentEvent, TradeOutcome
from .store import load_trade_intent_events


IST = ZoneInfo("Asia/Kolkata")
_BUCKET_ORDER = ["OPEN", "MID", "LATE", "EXPIRY_SPECIAL"]
_OPEN_START = dtime(hour=9, minute=15)
_OPEN_END = dtime(hour=9, minute=30)
_MID_END = dtime(hour=14, minute=30)
_LATE_END = dtime(hour=15, minute=30)


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


def _parse_date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    if not text:
        return datetime.now(tz=IST).date().isoformat()
    return datetime.fromisoformat(text).date().isoformat()


def _to_day_key(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()


def _default_outcomes_path(date_key: str) -> Path:
    base = str(getattr(cfg, "OUTCOME_REPLAY_DIR", "") or "").strip()
    if base:
        return Path(base) / f"{date_key}.jsonl"
    return repo_root() / "runtime" / "analytics" / "outcomes" / f"{date_key}.jsonl"


def _default_report_path(date_key: str) -> Path:
    base = str(getattr(cfg, "TIME_OF_DAY_REPORT_DIR", "") or "").strip()
    if base:
        return Path(base) / date_key / "time_of_day.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "time_of_day.json"


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


def _normalize_outcome_row(payload: Mapping[str, Any]) -> dict | None:
    raw = dict(payload or {})
    candidate = raw.get("trade_outcome") if isinstance(raw.get("trade_outcome"), Mapping) else raw
    if not isinstance(candidate, Mapping):
        return None
    try:
        outcome = TradeOutcome.from_dict(dict(candidate))
    except Exception:
        return None
    event_ref_id = str(raw.get("event_ref_id") or raw.get("source_event_id") or "").strip() or None
    return {"trade_outcome": outcome, "event_ref_id": event_ref_id}


def load_outcome_replay_rows(date_key: str, outcome_paths: Iterable[Path] | None = None) -> list[dict]:
    rows: list[dict] = []
    for path in list(outcome_paths or [_default_outcomes_path(date_key)]):
        for payload in _iter_jsonl(path):
            normalized = _normalize_outcome_row(payload)
            if normalized is not None:
                rows.append(normalized)
    rows.sort(key=lambda row: int(row["trade_outcome"].ts_epoch_ms))
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


def _match_outcome(event: TradeIntentEvent, outcomes: Sequence[Mapping[str, Any]]) -> TradeOutcome | None:
    for row in outcomes:
        if str(row.get("event_ref_id") or "").strip() == event.event_id:
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


def _is_expiry_day(day: date, symbol: str | None) -> bool:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return False
    prev_day = day - timedelta(days=1)
    try:
        weekly = market_calendar.next_expiry_after(prev_day, expiry_type="WEEKLY", symbol=sym)
    except Exception:
        weekly = None
    try:
        monthly = market_calendar.next_expiry_after(prev_day, expiry_type="MONTHLY", symbol=sym)
    except Exception:
        monthly = None
    return bool(weekly == day or monthly == day)


def bucket_for_timestamp_ms(ts_epoch_ms: int, symbol: str | None = None) -> str:
    dt_local = datetime.fromtimestamp(float(ts_epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST)
    if _is_expiry_day(dt_local.date(), symbol):
        return "EXPIRY_SPECIAL"

    t = dt_local.time()
    if _OPEN_START <= t < _OPEN_END:
        return "OPEN"
    if _OPEN_END <= t < _MID_END:
        return "MID"
    if _MID_END <= t <= _LATE_END:
        return "LATE"
    if t < _OPEN_START:
        return "OPEN"
    if t < _MID_END:
        return "MID"
    return "LATE"


def _bucket_sort_key(bucket: str) -> tuple[int, str]:
    key = str(bucket or "").upper()
    if key in _BUCKET_ORDER:
        return (_BUCKET_ORDER.index(key), key)
    return (len(_BUCKET_ORDER), key)


def _outcome_bucket(outcome: TradeOutcome | None) -> str:
    label = str(getattr(outcome, "outcome", "") or "").strip().lower()
    if label == "hit_target":
        return "win"
    if label == "hit_sl":
        return "loss"
    return "no_hit"


def build_time_of_day_report(
    date: Any,
    *,
    events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    outcome_paths: Iterable[Path] | None = None,
    output_path: Path | None = None,
) -> dict:
    date_key = _parse_date_key(date)
    if events is None:
        event_rows = load_trade_intent_events()
    else:
        event_rows = list(events)

    if outcomes is None:
        outcome_rows = load_outcome_replay_rows(date_key, outcome_paths=outcome_paths)
    else:
        outcome_rows = []
        for row in outcomes:
            if isinstance(row, TradeOutcome):
                outcome_rows.append({"trade_outcome": row, "event_ref_id": None})
                continue
            if isinstance(row, Mapping):
                normalized = _normalize_outcome_row(row)
                if normalized is not None:
                    outcome_rows.append(normalized)

    bucket_stats: dict[str, dict[str, Any]] = {}
    total_events = 0
    matched_outcomes = 0

    for row in event_rows:
        coerced = _coerce_event(row)
        if coerced is None:
            continue
        event, _raw = coerced
        if _to_day_key(int(event.ts_epoch_ms)) != date_key:
            continue
        total_events += 1

        matched = _match_outcome(event, outcome_rows)
        if isinstance(matched, TradeOutcome):
            matched_outcomes += 1
        outcome_label = _outcome_bucket(matched)
        bucket = bucket_for_timestamp_ms(int(event.ts_epoch_ms), event.symbol)
        b = bucket_stats.setdefault(
            bucket,
            {
                "bucket": bucket,
                "count": 0,
                "wins": 0,
                "losses": 0,
                "no_hit": 0,
                "mfe_values": [],
                "mae_values": [],
            },
        )
        b["count"] += 1
        if outcome_label == "win":
            b["wins"] += 1
        elif outcome_label == "loss":
            b["losses"] += 1
        else:
            b["no_hit"] += 1

        mfe = _safe_float(getattr(matched, "mfe_points", None))
        mae = _safe_float(getattr(matched, "mae_points", None))
        if mfe is not None:
            b["mfe_values"].append(float(mfe))
        if mae is not None:
            b["mae_values"].append(float(mae))

    buckets: list[dict] = []
    for bucket, row in bucket_stats.items():
        count = int(row["count"])
        wins = int(row["wins"])
        losses = int(row["losses"])
        no_hit = int(row["no_hit"])
        mfe_vals = list(row.get("mfe_values") or [])
        mae_vals = list(row.get("mae_values") or [])
        buckets.append(
            {
                "bucket": bucket,
                "count": count,
                "wins": wins,
                "losses": losses,
                "no_hit": no_hit,
                "win_rate": (float(wins) / float(count)) if count > 0 else 0.0,
                "loss_rate": (float(losses) / float(count)) if count > 0 else 0.0,
                "no_hit_rate": (float(no_hit) / float(count)) if count > 0 else 0.0,
                "avg_mfe": (sum(mfe_vals) / len(mfe_vals)) if mfe_vals else None,
                "avg_mae": (sum(mae_vals) / len(mae_vals)) if mae_vals else None,
            }
        )
    buckets.sort(key=lambda item: _bucket_sort_key(str(item.get("bucket") or "")))

    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "total_events": total_events,
        "matched_outcomes": matched_outcomes,
        "buckets": buckets,
    }

    out_path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(out_path, report)
    report["output_path"] = str(out_path)
    return report


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build time-of-day outcome analysis for a date.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format (exchange local date).")
    parser.add_argument(
        "--outcome-path",
        action="append",
        default=[],
        help="Optional replay outcome JSONL path(s). Can be provided multiple times.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path override for time_of_day.json.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    outcome_paths = [Path(p) for p in list(args.outcome_path or []) if str(p).strip()]
    output = Path(args.output) if args.output else None
    result = build_time_of_day_report(args.date, outcome_paths=outcome_paths or None, output_path=output)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
