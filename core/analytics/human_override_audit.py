from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import logs_dir, repo_root

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


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    text = _norm_text(value).lower()
    if text in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "f", "no", "n", "off", ""}:
        return False
    return bool(text)


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
    base = _norm_text(getattr(cfg, "HUMAN_OVERRIDE_AUDIT_REPORT_DIR", ""))
    if base:
        return Path(base) / date_key / "human_override_audit.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "human_override_audit.json"


def _default_queue_paths() -> list[Path]:
    return [
        Path(str(getattr(cfg, "REVIEW_QUEUE_PATH", logs_dir() / "review_queue.json"))),
        Path(str(getattr(cfg, "QUICK_REVIEW_QUEUE_PATH", logs_dir() / "quick_review_queue.json"))),
        Path(str(getattr(cfg, "ZERO_HERO_QUEUE_PATH", logs_dir() / "zero_hero_queue.json"))),
        Path(str(getattr(cfg, "SCALP_QUEUE_PATH", logs_dir() / "scalp_queue.json"))),
        Path(str(getattr(cfg, "TARGET_POINTS_QUEUE_PATH", logs_dir() / "target_points_queue.json"))),
    ]


def _default_approved_path() -> Path:
    return Path(str(getattr(cfg, "APPROVED_TRADES_PATH", logs_dir() / "approved_trades.json")))


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_queue_rows(paths: Iterable[Path] | None = None) -> list[dict]:
    rows: list[dict] = []
    for path in list(paths or _default_queue_paths()):
        payload = _read_json(Path(path))
        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict):
                    rows.append(dict(row))
    return rows


def _load_approved_records(path: Path | None = None) -> dict[str, dict]:
    payload = _read_json(Path(path) if path is not None else _default_approved_path())
    out: dict[str, dict] = {}

    if isinstance(payload, dict) and isinstance(payload.get("approvals"), dict):
        for trade_id, row in payload.get("approvals", {}).items():
            if not _norm_text(trade_id):
                continue
            out[str(trade_id)] = dict(row) if isinstance(row, dict) else {}
        return out

    if isinstance(payload, list):
        for trade_id in payload:
            key = _norm_text(trade_id)
            if key:
                out[key] = {"legacy": True, "status": "APPROVED"}
    return out


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
        return {"trade_outcome": item, "event_ref_id": None, "raw_payload": item.to_dict()}
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
    raw_payload = dict(raw)
    if isinstance(raw.get("trade_outcome"), Mapping):
        raw_payload = dict(raw.get("trade_outcome") or {})
        for key in ("event_ref_id", "source_event_id", "pnl_points", "pnl_value", "realized_pnl", "realized_pnl_points"):
            if key in raw:
                raw_payload[key] = raw.get(key)
    return {
        "trade_outcome": outcome,
        "event_ref_id": event_ref_id,
        "raw_payload": raw_payload,
    }


def _load_outcomes(
    *,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    source_rows = list(outcomes) if outcomes is not None else list(load_trade_outcomes())
    for row in source_rows:
        normalized = _normalize_outcome_row(row)
        if normalized is None:
            continue
        if not isinstance(normalized.get("trade_outcome"), TradeOutcome):
            continue
        rows.append(normalized)
    rows.sort(key=lambda item: int(item["trade_outcome"].ts_epoch_ms))
    return rows


def _match_outcome_row(event: TradeIntentEvent, outcomes: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for row in outcomes:
        if _norm_text(row.get("event_ref_id")) == event.event_id:
            if isinstance(row.get("trade_outcome"), TradeOutcome):
                return row

    for row in outcomes:
        out = row.get("trade_outcome")
        if isinstance(out, TradeOutcome) and out.event_id == event.event_id:
            return row

    candidates: list[tuple[int, int, Mapping[str, Any]]] = []
    for row in outcomes:
        out = row.get("trade_outcome")
        if not isinstance(out, TradeOutcome):
            continue
        if out.trade_key != event.trade_key:
            continue
        delta = abs(int(out.ts_epoch_ms) - int(event.ts_epoch_ms))
        forward_bias = 0 if int(out.ts_epoch_ms) >= int(event.ts_epoch_ms) else 1
        candidates.append((forward_bias, delta, row))
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][2]
    return None


def _extract_strategy_id(event: TradeIntentEvent, raw: Mapping[str, Any]) -> str:
    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    strategy = (
        _norm_text(raw.get("strategy_id"))
        or _norm_text(raw.get("strategy"))
        or _norm_text(metrics.get("strategy_id") if isinstance(metrics, Mapping) else None)
        or _norm_text(metrics.get("strategy") if isinstance(metrics, Mapping) else None)
    )
    if strategy:
        return strategy
    parts = _norm_text(event.trade_key).split("|")
    if len(parts) >= 6 and _norm_text(parts[-1]):
        return _norm_text(parts[-1])
    return "unknown"


def _extract_regime(event: TradeIntentEvent, raw: Mapping[str, Any]) -> str:
    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    value = (
        _norm_text(raw.get("regime"))
        or _norm_text(raw.get("regime_bucket"))
        or _norm_text(metrics.get("regime") if isinstance(metrics, Mapping) else None)
        or _norm_text(metrics.get("regime_bucket") if isinstance(metrics, Mapping) else None)
    )
    return value.upper() if value else "UNKNOWN"


def _build_queue_tradekey_map(queue_rows: Sequence[Mapping[str, Any]]) -> dict[str, dict]:
    by_trade_key: dict[str, dict] = {}
    for row in queue_rows:
        if not isinstance(row, Mapping):
            continue
        trade_key = _norm_text(row.get("trade_key"))
        if not trade_key:
            continue
        by_trade_key[trade_key] = dict(row)
    return by_trade_key


def _manual_flags_from_event(
    event: TradeIntentEvent,
    raw: Mapping[str, Any],
    *,
    queue_row: Mapping[str, Any] | None,
    approved_records: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, list[str], str | None]:
    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    reasons: list[str] = []

    def _flag(label: str, *values: Any) -> None:
        for value in values:
            if _to_bool(value):
                reasons.append(label)
                return

    _flag(
        "event_manual_override_flag",
        raw.get("manual_override_used"),
        raw.get("activation_manual_override_used"),
        raw.get("manual_approval_used"),
        metrics.get("manual_override_used") if isinstance(metrics, Mapping) else None,
        metrics.get("activation_manual_override_used") if isinstance(metrics, Mapping) else None,
    )

    approved_by = (
        _norm_text(raw.get("approved_by"))
        or _norm_text(metrics.get("approved_by") if isinstance(metrics, Mapping) else None)
        or _norm_text((queue_row or {}).get("approved_by"))
        or None
    )
    if approved_by:
        reasons.append("approved_by_present")

    if isinstance(queue_row, Mapping):
        _flag(
            "queue_manual_override_flag",
            queue_row.get("manual_override_used"),
            queue_row.get("activation_manual_override_used"),
            queue_row.get("approval_override_used"),
        )

    trade_id = (
        _norm_text(raw.get("trade_id"))
        or _norm_text((queue_row or {}).get("trade_id"))
        or _norm_text(metrics.get("trade_id") if isinstance(metrics, Mapping) else None)
        or None
    )
    if trade_id and trade_id in approved_records:
        rec = approved_records.get(trade_id) or {}
        status = _norm_text(rec.get("status")).upper() or "APPROVED"
        if status in {"APPROVED", "USED"}:
            reasons.append("approved_trades_log")
            if not approved_by:
                approved_by = _norm_text(rec.get("approved_by")) or None

    return bool(reasons), sorted(set(reasons)), approved_by


def _extract_outcome_metrics(outcome_row: Mapping[str, Any]) -> dict:
    outcome = outcome_row.get("trade_outcome")
    raw = outcome_row.get("raw_payload") if isinstance(outcome_row.get("raw_payload"), Mapping) else {}
    if not isinstance(outcome, TradeOutcome):
        return {
            "outcome": "no_hit",
            "mfe_points": None,
            "mae_points": None,
            "pnl_points": None,
            "pnl_source": "missing_outcome",
        }

    out_label = _norm_text(outcome.outcome).lower() or "no_hit"
    mfe = _safe_float(outcome.mfe_points)
    mae = _safe_float(outcome.mae_points)

    pnl = None
    pnl_source = "missing"
    for key in ("pnl_points", "realized_pnl_points", "pnl", "realized_pnl", "pnl_value"):
        candidate = _safe_float(raw.get(key) if isinstance(raw, Mapping) else None)
        if candidate is not None:
            pnl = float(candidate)
            pnl_source = f"raw:{key}"
            break

    if pnl is None:
        if out_label == "hit_target":
            pnl = float(mfe) if mfe is not None else None
            pnl_source = "proxy:mfe"
        elif out_label == "hit_sl":
            pnl = float(mae) if mae is not None else None
            pnl_source = "proxy:mae"
        else:
            pnl = 0.0
            pnl_source = "proxy:no_hit_zero"

    return {
        "outcome": out_label,
        "mfe_points": mfe,
        "mae_points": mae,
        "pnl_points": pnl,
        "pnl_source": pnl_source,
    }


def _cohort_stats(rows: Sequence[Mapping[str, Any]]) -> dict:
    count = len(rows)
    wins = sum(1 for row in rows if _norm_text(row.get("outcome")).lower() == "hit_target")
    losses = sum(1 for row in rows if _norm_text(row.get("outcome")).lower() == "hit_sl")
    no_hit = count - wins - losses

    pnl_values = [float(v) for v in (_safe_float(row.get("pnl_points")) for row in rows) if v is not None]
    mfe_values = [float(v) for v in (_safe_float(row.get("mfe_points")) for row in rows) if v is not None]
    mae_values = [float(v) for v in (_safe_float(row.get("mae_points")) for row in rows) if v is not None]

    return {
        "trade_count": int(count),
        "wins": int(wins),
        "losses": int(losses),
        "no_hit": int(no_hit),
        "win_rate": (float(wins) / float(count)) if count > 0 else 0.0,
        "avg_pnl_points": (sum(pnl_values) / float(len(pnl_values))) if pnl_values else None,
        "avg_mfe_points": (sum(mfe_values) / float(len(mfe_values))) if mfe_values else None,
        "avg_mae_points": (sum(mae_values) / float(len(mae_values))) if mae_values else None,
    }


def _cohort_delta(manual: Mapping[str, Any], auto: Mapping[str, Any]) -> dict:
    def _delta(key: str) -> float | None:
        left = _safe_float(manual.get(key))
        right = _safe_float(auto.get(key))
        if left is None or right is None:
            return None
        return float(left - right)

    return {
        "manual_minus_auto_win_rate": _delta("win_rate"),
        "manual_minus_auto_avg_pnl_points": _delta("avg_pnl_points"),
        "manual_minus_auto_avg_mfe_points": _delta("avg_mfe_points"),
        "manual_minus_auto_avg_mae_points": _delta("avg_mae_points"),
    }


def _top_examples(rows: Sequence[Mapping[str, Any]], limit: int) -> tuple[list[dict], list[dict]]:
    manual_rows = [row for row in rows if bool(row.get("manual_override"))]
    ranked = [
        row
        for row in manual_rows
        if _safe_float(row.get("pnl_points")) is not None
    ]
    ranked.sort(key=lambda row: float(_safe_float(row.get("pnl_points")) or 0.0), reverse=True)

    top = [
        {
            "event_id": row.get("event_id"),
            "trade_key": row.get("trade_key"),
            "strategy_id": row.get("strategy_id"),
            "regime": row.get("regime"),
            "symbol": row.get("symbol"),
            "outcome": row.get("outcome"),
            "pnl_points": row.get("pnl_points"),
            "mfe_points": row.get("mfe_points"),
            "mae_points": row.get("mae_points"),
            "manual_reasons": row.get("manual_reasons"),
            "approved_by": row.get("approved_by"),
            "ts_epoch_ms": row.get("ts_epoch_ms"),
        }
        for row in ranked[: max(int(limit), 0)]
    ]

    bottom = [
        {
            "event_id": row.get("event_id"),
            "trade_key": row.get("trade_key"),
            "strategy_id": row.get("strategy_id"),
            "regime": row.get("regime"),
            "symbol": row.get("symbol"),
            "outcome": row.get("outcome"),
            "pnl_points": row.get("pnl_points"),
            "mfe_points": row.get("mfe_points"),
            "mae_points": row.get("mae_points"),
            "manual_reasons": row.get("manual_reasons"),
            "approved_by": row.get("approved_by"),
            "ts_epoch_ms": row.get("ts_epoch_ms"),
        }
        for row in list(reversed(ranked[-max(int(limit), 0) :]))
    ]
    return top, bottom


def build_human_override_audit(
    date: Any,
    *,
    events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    include_intents: Sequence[str] | None = None,
    queue_rows: Sequence[Mapping[str, Any]] | None = None,
    queue_paths: Iterable[Path] | None = None,
    approved_records: Mapping[str, Mapping[str, Any]] | None = None,
    approved_path: Path | None = None,
    examples_limit: int | None = None,
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

    limit = int(examples_limit if examples_limit is not None else getattr(cfg, "HUMAN_OVERRIDE_AUDIT_EXAMPLES", 5))

    event_rows = list(events) if events is not None else list(load_trade_intent_events())
    outcome_rows = _load_outcomes(outcomes=outcomes)

    queue_loaded = list(queue_rows) if queue_rows is not None else _load_queue_rows(queue_paths)
    queue_by_trade_key = _build_queue_tradekey_map(queue_loaded)

    approved_loaded = dict(approved_records or {})
    if not approved_loaded:
        approved_loaded = _load_approved_records(path=approved_path)

    scanned_events = 0
    matched_events = 0
    rows: list[dict] = []

    for item in event_rows:
        coerced = _coerce_event(item)
        if coerced is None:
            continue
        event, raw = coerced
        if _to_day_key(int(event.ts_epoch_ms)) != date_key:
            continue

        scanned_events += 1
        intent = _norm_text(event.intent).lower()
        if intent not in intents:
            continue

        outcome_row = _match_outcome_row(event, outcome_rows)
        if not isinstance(outcome_row, Mapping):
            continue
        matched_events += 1

        queue_row = queue_by_trade_key.get(_norm_text(event.trade_key))
        manual, manual_reasons, approved_by = _manual_flags_from_event(
            event,
            raw,
            queue_row=queue_row,
            approved_records=approved_loaded,
        )
        metrics = _extract_outcome_metrics(outcome_row)

        row = {
            "event_id": event.event_id,
            "trade_key": event.trade_key,
            "symbol": event.symbol,
            "intent": event.intent,
            "strategy_id": _extract_strategy_id(event, raw),
            "regime": _extract_regime(event, raw),
            "manual_override": bool(manual),
            "manual_reasons": manual_reasons,
            "approved_by": approved_by,
            "outcome": metrics.get("outcome"),
            "pnl_points": metrics.get("pnl_points"),
            "pnl_source": metrics.get("pnl_source"),
            "mfe_points": metrics.get("mfe_points"),
            "mae_points": metrics.get("mae_points"),
            "ts_epoch_ms": int(event.ts_epoch_ms),
        }
        rows.append(row)

    rows.sort(key=lambda row: (int(row.get("ts_epoch_ms") or 0), str(row.get("event_id") or "")))

    manual_rows = [row for row in rows if bool(row.get("manual_override"))]
    auto_rows = [row for row in rows if not bool(row.get("manual_override"))]

    manual_stats = _cohort_stats(manual_rows)
    auto_stats = _cohort_stats(auto_rows)
    override_value = _cohort_delta(manual_stats, auto_stats)

    source_counts: dict[str, int] = {}
    for row in rows:
        src = _norm_text(row.get("pnl_source")) or "unknown"
        source_counts[src] = int(source_counts.get(src, 0)) + 1

    best_examples, worst_examples = _top_examples(rows, limit=limit)

    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "params": {
            "include_intents": sorted(intents),
            "examples_limit": int(limit),
        },
        "counts": {
            "scanned_events": int(scanned_events),
            "matched_events": int(matched_events),
            "manual_overrides": int(len(manual_rows)),
            "auto_trades": int(len(auto_rows)),
        },
        "cohorts": {
            "manual": manual_stats,
            "auto": auto_stats,
        },
        "override_value": override_value,
        "pnl_source_counts": dict(sorted(source_counts.items())),
        "examples": {
            "best_overrides": best_examples,
            "worst_overrides": worst_examples,
        },
        "rows": rows,
    }

    out_path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(out_path, report)
    report["output_path"] = str(out_path)
    return report


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit outcomes of manually approved/overridden trades.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange local day).")
    parser.add_argument(
        "--include-intent",
        action="append",
        default=[],
        help="Intent(s) to include: accepted|rejected|advisory. Repeatable.",
    )
    parser.add_argument("--approved-path", default=None, help="Optional approved_trades.json path override.")
    parser.add_argument("--examples", type=int, default=None, help="Top/bottom manual examples count.")
    parser.add_argument("--output", default=None, help="Optional output path override.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    include_intents = [str(v) for v in list(args.include_intent or []) if _norm_text(v)]
    approved_path = Path(args.approved_path) if args.approved_path else None
    output_path = Path(args.output) if args.output else None

    payload = build_human_override_audit(
        args.date,
        include_intents=include_intents or None,
        approved_path=approved_path,
        examples_limit=args.examples,
        output_path=output_path,
    )
    print(
        json.dumps(
            {
                "date": payload.get("date"),
                "counts": payload.get("counts"),
                "override_value": payload.get("override_value"),
                "output_path": payload.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
