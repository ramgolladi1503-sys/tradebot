from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import repo_root

from .schema import GateDecision, TradeIntentEvent, TradeOutcome
from .store import load_trade_intent_events


IST = ZoneInfo("Asia/Kolkata")
_CLEAR_MISS = "CLEAR_MISS"
_PARTIAL_EDGE = "PARTIAL_EDGE"
_NO_EDGE = "NO_EDGE"


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
    base = str(getattr(cfg, "MISSED_OPPORTUNITY_REPORT_DIR", "") or "").strip()
    if base:
        return Path(base) / date_key / "missed_opportunity.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "missed_opportunity.json"


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

    event_ref_id = (
        str(raw.get("event_ref_id") or raw.get("source_event_id") or "").strip()
        or None
    )
    target_points = _safe_float(raw.get("target_points"))
    entry = _safe_float(raw.get("entry") or raw.get("entry_ref") or raw.get("intended_entry"))
    target = _safe_float(raw.get("target") or raw.get("target_price"))
    if target_points is None and entry is not None and target is not None:
        diff = abs(float(target) - float(entry))
        if diff > 0:
            target_points = diff
    return {
        "trade_outcome": outcome,
        "event_ref_id": event_ref_id,
        "target_points": target_points,
        "entry": entry,
        "target": target,
    }


def load_outcome_replay_rows(date_key: str, outcome_paths: Iterable[Path] | None = None) -> list[dict]:
    rows: list[dict] = []
    paths = list(outcome_paths or [_default_outcomes_path(date_key)])
    for path in paths:
        for payload in _iter_jsonl(path):
            normalized = _normalize_outcome_row(payload)
            if normalized is not None:
                rows.append(normalized)
    rows.sort(key=lambda row: int(row["trade_outcome"].ts_epoch_ms))
    return rows


def _is_rejected_event(event: TradeIntentEvent, raw: Mapping[str, Any]) -> bool:
    if str(event.intent).lower() == "rejected":
        return True
    status = str(raw.get("status") or "").strip().upper()
    permission = str(raw.get("permission") or "").strip().upper()
    reason = str(raw.get("reject_reason") or raw.get("permission_reason") or "").strip()
    return bool(reason or permission == "BLOCK" or status in {"REJECTED", "BLOCKED", "INVALIDATED", "EXPIRED"})


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


def _extract_gate_name(event: TradeIntentEvent, raw: Mapping[str, Any]) -> str:
    for gd in event.gate_decisions:
        if isinstance(gd, GateDecision) and (not gd.passed) and str(gd.gate_name or "").strip():
            return str(gd.gate_name)
    gate_decisions = raw.get("gate_decisions")
    if isinstance(gate_decisions, list):
        for gd in gate_decisions:
            if not isinstance(gd, Mapping):
                continue
            if gd.get("passed") is False and str(gd.get("gate_name") or "").strip():
                return str(gd.get("gate_name"))
    for gd in event.gate_decisions:
        if isinstance(gd, GateDecision) and str(gd.gate_name or "").strip():
            return str(gd.gate_name)
    return "unknown_gate"


def _extract_target_points(event: TradeIntentEvent, raw: Mapping[str, Any], matched_outcome: Mapping[str, Any] | None) -> float | None:
    if matched_outcome:
        tp = _safe_float(matched_outcome.get("target_points"))
        if tp is not None and tp > 0:
            return tp
        out = matched_outcome.get("trade_outcome")
        if isinstance(out, TradeOutcome):
            flags = out.exec_feasible_flags or {}
            if isinstance(flags, Mapping):
                tp_flag = _safe_float(flags.get("target_points"))
                if tp_flag is not None and tp_flag > 0:
                    return tp_flag

    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    target_points = _safe_float(metrics.get("target_points") if isinstance(metrics, Mapping) else None)
    if target_points is not None and target_points > 0:
        return target_points

    raw_target_points = _safe_float(raw.get("target_points"))
    if raw_target_points is not None and raw_target_points > 0:
        return raw_target_points

    entry = _safe_float(
        raw.get("entry")
        or raw.get("entry_price")
        or raw.get("intended_entry")
        or (metrics.get("entry") if isinstance(metrics, Mapping) else None)
        or (metrics.get("entry_price") if isinstance(metrics, Mapping) else None)
    )
    target = _safe_float(
        raw.get("target")
        or raw.get("target_price")
        or (metrics.get("target") if isinstance(metrics, Mapping) else None)
        or (metrics.get("target_price") if isinstance(metrics, Mapping) else None)
    )
    if entry is not None and target is not None:
        diff = abs(float(target) - float(entry))
        if diff > 0:
            return diff
    if target is not None and target > 0:
        return abs(float(target))
    return None


def classify_missed_label(outcome: TradeOutcome | None, *, target_points: float | None) -> str:
    if outcome is None:
        return _NO_EDGE
    if str(outcome.outcome).lower() == "hit_target":
        return _CLEAR_MISS
    mfe = _safe_float(outcome.mfe_points)
    if mfe is None:
        return _NO_EDGE
    tp = _safe_float(target_points)
    if tp is None or tp <= 0:
        return _NO_EDGE
    if float(mfe) >= float(tp) * 0.5:
        return _PARTIAL_EDGE
    return _NO_EDGE


def _match_outcome(event: TradeIntentEvent, outcome_rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    # Strongest match: explicit source-event ID.
    for row in outcome_rows:
        if str(row.get("event_ref_id") or "").strip() == event.event_id:
            return row

    # Backward-compatible fallback: outcome.event_id equals intent event_id.
    for row in outcome_rows:
        out = row.get("trade_outcome")
        if isinstance(out, TradeOutcome) and out.event_id == event.event_id:
            return row

    # Fallback by stable trade_key and nearest timestamp.
    scored: list[tuple[int, int, Mapping[str, Any]]] = []
    for row in outcome_rows:
        out = row.get("trade_outcome")
        if not isinstance(out, TradeOutcome):
            continue
        if out.trade_key != event.trade_key:
            continue
        delta = abs(int(out.ts_epoch_ms) - int(event.ts_epoch_ms))
        forward_bias = 0 if int(out.ts_epoch_ms) >= int(event.ts_epoch_ms) else 1
        scored.append((forward_bias, delta, row))
    if scored:
        scored.sort(key=lambda item: (item[0], item[1]))
        return scored[0][2]

    # Last fallback by symbol and nearest timestamp.
    scored_symbol: list[tuple[int, Mapping[str, Any]]] = []
    for row in outcome_rows:
        out = row.get("trade_outcome")
        if not isinstance(out, TradeOutcome):
            continue
        if str(out.symbol or "").upper() != str(event.symbol or "").upper():
            continue
        delta = abs(int(out.ts_epoch_ms) - int(event.ts_epoch_ms))
        scored_symbol.append((delta, row))
    if scored_symbol:
        scored_symbol.sort(key=lambda item: item[0])
        if scored_symbol[0][0] <= 6 * 60 * 60 * 1000:  # 6h guardrail
            return scored_symbol[0][1]
    return None


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        reason = str(row.get("reject_reason") or "unknown_reject")
        gate = str(row.get("gate_name") or "unknown_gate")
        key = (reason, gate)
        ref = buckets.setdefault(
            key,
            {
                "reject_reason": reason,
                "gate_name": gate,
                "count": 0,
                "clear_miss_count": 0,
                "mfe": [],
                "mae": [],
            },
        )
        ref["count"] += 1
        if str(row.get("label") or "") == _CLEAR_MISS:
            ref["clear_miss_count"] += 1
        mfe = _safe_float(row.get("mfe_points"))
        mae = _safe_float(row.get("mae_points"))
        if mfe is not None:
            ref["mfe"].append(float(mfe))
        if mae is not None:
            ref["mae"].append(float(mae))

    out: list[dict] = []
    for (_reason, _gate), ref in buckets.items():
        count = int(ref["count"])
        mfe_vals = list(ref.get("mfe") or [])
        mae_vals = list(ref.get("mae") or [])
        out.append(
            {
                "reject_reason": ref["reject_reason"],
                "gate_name": ref["gate_name"],
                "count": count,
                "clear_miss_rate": (float(ref["clear_miss_count"]) / float(count)) if count > 0 else 0.0,
                "avg_mfe": (sum(mfe_vals) / len(mfe_vals)) if mfe_vals else None,
                "avg_mae": (sum(mae_vals) / len(mae_vals)) if mae_vals else None,
            }
        )
    out.sort(key=lambda row: (-(int(row.get("count") or 0)), str(row.get("reject_reason") or ""), str(row.get("gate_name") or "")))
    return out


def analyze_missed_opportunity(
    date: Any,
    *,
    rejected_events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    outcome_paths: Iterable[Path] | None = None,
    output_path: Path | None = None,
) -> dict:
    date_key = _parse_date_key(date)

    if rejected_events is None:
        loaded = load_trade_intent_events()
        rejected_items: list[tuple[TradeIntentEvent, dict]] = []
        for event in loaded:
            raw = event.to_dict()
            if _to_day_key(int(event.ts_epoch_ms)) != date_key:
                continue
            if not _is_rejected_event(event, raw):
                continue
            rejected_items.append((event, raw))
    else:
        rejected_items = []
        for item in rejected_events:
            coerced = _coerce_event(item)
            if coerced is None:
                continue
            event, raw = coerced
            if _to_day_key(int(event.ts_epoch_ms)) != date_key:
                continue
            if not _is_rejected_event(event, raw):
                continue
            rejected_items.append((event, raw))

    if outcomes is None:
        normalized_outcomes = load_outcome_replay_rows(date_key, outcome_paths=outcome_paths)
    else:
        normalized_outcomes = []
        for item in outcomes:
            if isinstance(item, TradeOutcome):
                normalized_outcomes.append({"trade_outcome": item, "event_ref_id": None, "target_points": None})
                continue
            if isinstance(item, Mapping):
                normalized = _normalize_outcome_row(item)
                if normalized is not None:
                    normalized_outcomes.append(normalized)

    rows: list[dict] = []
    label_counts = {_CLEAR_MISS: 0, _PARTIAL_EDGE: 0, _NO_EDGE: 0}
    matched_outcomes = 0

    for event, raw in rejected_items:
        matched = _match_outcome(event, normalized_outcomes)
        trade_outcome = matched.get("trade_outcome") if isinstance(matched, Mapping) else None
        if isinstance(trade_outcome, TradeOutcome):
            matched_outcomes += 1
        else:
            trade_outcome = None

        target_points = _extract_target_points(event, raw, matched if isinstance(matched, Mapping) else None)
        label = classify_missed_label(trade_outcome, target_points=target_points)
        label_counts[label] = int(label_counts.get(label, 0)) + 1

        reject_reason = str(event.reject_reason or raw.get("reject_reason") or "unknown_reject")
        gate_name = _extract_gate_name(event, raw)

        rows.append(
            {
                "event_id": event.event_id,
                "trade_key": event.trade_key,
                "symbol": event.symbol,
                "ts_epoch_ms": int(event.ts_epoch_ms),
                "reject_reason": reject_reason,
                "gate_name": gate_name,
                "label": label,
                "outcome": (str(trade_outcome.outcome) if isinstance(trade_outcome, TradeOutcome) else None),
                "mfe_points": (float(trade_outcome.mfe_points) if isinstance(trade_outcome, TradeOutcome) and trade_outcome.mfe_points is not None else None),
                "mae_points": (float(trade_outcome.mae_points) if isinstance(trade_outcome, TradeOutcome) and trade_outcome.mae_points is not None else None),
                "target_points": (float(target_points) if target_points is not None else None),
            }
        )

    rows.sort(key=lambda row: int(row.get("ts_epoch_ms") or 0))
    aggregates = _aggregate(rows)

    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "total_rejected": len(rejected_items),
        "matched_outcomes": int(matched_outcomes),
        "labels": {
            "CLEAR_MISS": int(label_counts.get(_CLEAR_MISS, 0)),
            "PARTIAL_EDGE": int(label_counts.get(_PARTIAL_EDGE, 0)),
            "NO_EDGE": int(label_counts.get(_NO_EDGE, 0)),
        },
        "aggregates": aggregates,
        "rows": rows,
    }

    report_path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(report_path, report)
    report["output_path"] = str(report_path)
    return report


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Missed-opportunity analysis for rejected trades.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange day).")
    parser.add_argument(
        "--outcomes-path",
        action="append",
        default=None,
        help="Optional outcome replay JSONL path (can be provided multiple times).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    outcome_paths = [Path(p) for p in (args.outcomes_path or [])] if args.outcomes_path else None
    payload = analyze_missed_opportunity(args.date, outcome_paths=outcome_paths)
    print(
        json.dumps(
            {
                "date": payload.get("date"),
                "total_rejected": payload.get("total_rejected"),
                "matched_outcomes": payload.get("matched_outcomes"),
                "labels": payload.get("labels"),
                "output_path": payload.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
