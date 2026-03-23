from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.analytics.time_of_day import bucket_for_timestamp_ms
from core.learning_paths import canonical_suggestions_log_path
from core.trade_log_paths import resolve_trade_log_path


METRIC_COLUMNS = ["bucket", "trade_count", "expectancy", "win_rate", "avg_win", "avg_loss"]


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
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _coerce_epoch_ms(float(text))
    except Exception:
        pass
    try:
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return int(dt.timestamp() * 1000.0)
    except Exception:
        return None


def _iter_jsonl(path: Path | None) -> list[dict]:
    rows: list[dict] = []
    if path is None or not Path(path).exists():
        return rows
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = str(raw_line or "").strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    return rows


def _trade_id(row: Mapping[str, Any]) -> str | None:
    for key in ("trade_id", "advisory_id", "decision_trace_id", "trace_id"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return None


def _json_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _first_text(row: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return None


def _normalized_setup_type(row: Mapping[str, Any]) -> str:
    source_flags = _json_dict(row.get("source_flags")) or _json_dict(row.get("source_flags_json"))
    candidate_origin = source_flags.get("candidate_origin") if isinstance(source_flags.get("candidate_origin"), dict) else {}
    setup = (
        _first_text(row, "setup_type", "setup_family")
        or _first_text(source_flags, "setup_type", "setup_family")
        or _first_text(candidate_origin, "setup_family")
        or _first_text(row, "reason")
        or "UNKNOWN"
    )
    return str(setup).strip().upper()


def _normalized_strategy(row: Mapping[str, Any]) -> str:
    return str(
        _first_text(row, "strategy_name", "strategy_id", "strategy", "source") or "UNKNOWN"
    ).strip().upper()


def _normalized_regime(row: Mapping[str, Any]) -> str:
    source_flags = _json_dict(row.get("source_flags")) or _json_dict(row.get("source_flags_json"))
    regime = (
        _first_text(row, "regime", "primary_regime", "regime_path", "regime_day")
        or _first_text(source_flags, "regime", "primary_regime", "regime_path")
        or "UNKNOWN"
    )
    return str(regime).strip().upper()


def _allocation_bucket(row: Mapping[str, Any]) -> str:
    reason = str(row.get("allocation_reason") or "").strip().lower()
    if reason == "allocated" or row.get("slot_id") not in (None, ""):
        return "ALLOCATED"
    if reason.startswith("deferred_"):
        return "DEFERRED"
    if reason.startswith("replaced_") or reason.startswith("replaced"):
        return "REPLACED"
    if reason:
        return reason.upper()
    return "UNALLOCATED"


def _timestamp_ms(row: Mapping[str, Any]) -> int | None:
    return (
        _coerce_epoch_ms(row.get("timestamp_epoch_ms"))
        or _coerce_epoch_ms(row.get("ts_epoch_ms"))
        or _coerce_epoch_ms(row.get("ts_epoch"))
        or _coerce_epoch_ms(row.get("timestamp"))
        or _coerce_epoch_ms(row.get("trade_lifecycle_ts"))
    )


def _time_bucket(row: Mapping[str, Any]) -> str:
    ts_ms = _timestamp_ms(row)
    if ts_ms is None:
        return "UNKNOWN"
    return str(bucket_for_timestamp_ms(ts_ms, row.get("symbol")) or "UNKNOWN").upper()


def _qty_units(row: Mapping[str, Any]) -> float | None:
    units = _safe_float(row.get("qty_units"))
    if units is not None and units > 0:
        return units
    qty = _safe_float(row.get("qty"))
    return qty if qty is not None and qty > 0 else None


def _realized_pnl(row: Mapping[str, Any]) -> float | None:
    pnl = _safe_float(row.get("realized_pnl"))
    if pnl is not None:
        return pnl
    entry = _safe_float(row.get("entry")) or _safe_float(row.get("entry_price"))
    exit_price = _safe_float(row.get("exit_price")) or _safe_float(row.get("exit"))
    if entry is None or exit_price is None:
        return None
    side = str(row.get("side") or "BUY").strip().upper()
    direction = -1.0 if side == "SELL" else 1.0
    units = _qty_units(row) or 1.0
    return (exit_price - entry) * units * direction


def _outcome_label(row: Mapping[str, Any], pnl: float | None) -> str:
    label = str(row.get("outcome_label") or row.get("outcome") or "").strip().upper()
    if label:
        return label
    if pnl is None:
        return "UNREALIZED"
    if pnl > 0:
        return "WIN"
    if pnl < 0:
        return "LOSS"
    return "BREAKEVEN"


def _fill_missing(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if target.get(key) in (None, "", "UNKNOWN", "UNALLOCATED"):
            if value not in (None, ""):
                target[key] = value


def load_trade_quality_rows(
    *,
    suggestions_path: Path | None = None,
    trade_log_path: Path | None = None,
    trade_updates_path: Path | None = None,
) -> list[dict]:
    suggestion_rows = _iter_jsonl(suggestions_path or canonical_suggestions_log_path())
    trade_log_rows = _iter_jsonl(trade_log_path or resolve_trade_log_path(kind="trade_log"))
    trade_update_rows = _iter_jsonl(trade_updates_path or resolve_trade_log_path(kind="trade_updates"))

    metadata_by_trade: dict[str, dict[str, Any]] = {}

    for row in suggestion_rows + trade_log_rows:
        trade_id = _trade_id(row)
        if not trade_id:
            continue
        payload = {
            "trade_id": trade_id,
            "symbol": str(_first_text(row, "symbol", "underlying") or "UNKNOWN").strip().upper(),
            "strategy": _normalized_strategy(row),
            "setup_type": _normalized_setup_type(row),
            "regime": _normalized_regime(row),
            "allocation_bucket": _allocation_bucket(row),
            "time_bucket": _time_bucket(row),
            "timestamp_ms": _timestamp_ms(row),
        }
        current = metadata_by_trade.setdefault(trade_id, {})
        _fill_missing(current, payload)
        if payload.get("timestamp_ms") is not None and (
            current.get("timestamp_ms") is None or int(payload["timestamp_ms"]) > int(current["timestamp_ms"])
        ):
            current["timestamp_ms"] = int(payload["timestamp_ms"])

    outcome_by_trade: dict[str, dict[str, Any]] = {}
    for row in trade_log_rows + trade_update_rows:
        trade_id = _trade_id(row)
        if not trade_id:
            continue
        pnl = _realized_pnl(row)
        if pnl is None:
            continue
        payload = {
            "trade_id": trade_id,
            "realized_pnl": float(pnl),
            "outcome_label": _outcome_label(row, pnl),
            "timestamp_ms": _timestamp_ms(row),
        }
        current = outcome_by_trade.get(trade_id)
        if current is None:
            outcome_by_trade[trade_id] = payload
            continue
        current_ts = current.get("timestamp_ms")
        payload_ts = payload.get("timestamp_ms")
        if payload_ts is not None and (current_ts is None or int(payload_ts) >= int(current_ts)):
            outcome_by_trade[trade_id] = payload

    rows: list[dict] = []
    for trade_id in sorted(set(metadata_by_trade) | set(outcome_by_trade)):
        meta = dict(metadata_by_trade.get(trade_id) or {})
        outcome = dict(outcome_by_trade.get(trade_id) or {})
        row = {
            "trade_id": trade_id,
            "symbol": meta.get("symbol", "UNKNOWN"),
            "strategy": meta.get("strategy", "UNKNOWN"),
            "setup_type": meta.get("setup_type", "UNKNOWN"),
            "regime": meta.get("regime", "UNKNOWN"),
            "allocation_bucket": meta.get("allocation_bucket", "UNALLOCATED"),
            "time_bucket": meta.get("time_bucket", "UNKNOWN"),
            "timestamp_ms": meta.get("timestamp_ms") or outcome.get("timestamp_ms"),
            "realized_pnl": outcome.get("realized_pnl"),
            "outcome_label": outcome.get("outcome_label", "UNREALIZED"),
        }
        rows.append(row)
    rows.sort(key=lambda row: (int(row["timestamp_ms"]) if row.get("timestamp_ms") is not None else -1, row["trade_id"]))
    return rows


def calculate_expectancy(rows: list[Mapping[str, Any]]) -> dict[str, float | int]:
    pnl_values = [float(row["realized_pnl"]) for row in rows if _safe_float(row.get("realized_pnl")) is not None]
    trade_count = len(pnl_values)
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    expectancy = (sum(pnl_values) / trade_count) if trade_count else 0.0
    win_rate = (len(wins) / trade_count) if trade_count else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    return {
        "trade_count": int(trade_count),
        "expectancy": round(float(expectancy), 6),
        "win_rate": round(float(win_rate), 6),
        "avg_win": round(float(avg_win), 6),
        "avg_loss": round(float(avg_loss), 6),
    }


def _metric_table(rows: list[Mapping[str, Any]], field: str, *, label: str | None = None) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        bucket = str(row.get(field) or "UNKNOWN").strip().upper()
        grouped.setdefault(bucket, []).append(row)
    table_rows = []
    for bucket in sorted(grouped):
        metrics = calculate_expectancy(grouped[bucket])
        table_rows.append(
            {
                "bucket": bucket,
                "trade_count": metrics["trade_count"],
                "expectancy": metrics["expectancy"],
                "win_rate": metrics["win_rate"],
                "avg_win": metrics["avg_win"],
                "avg_loss": metrics["avg_loss"],
            }
        )
    return {
        "label": str(label or field),
        "columns": list(METRIC_COLUMNS),
        "rows": table_rows,
    }


def _write_report(path: Path | None, report: Mapping[str, Any]) -> None:
    if path is None:
        return
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(report), indent=2, sort_keys=True), encoding="utf-8")


def build_setup_expectancy_report(
    *,
    suggestions_path: Path | None = None,
    trade_log_path: Path | None = None,
    trade_updates_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    rows = load_trade_quality_rows(
        suggestions_path=suggestions_path,
        trade_log_path=trade_log_path,
        trade_updates_path=trade_updates_path,
    )
    evaluated = [row for row in rows if _safe_float(row.get("realized_pnl")) is not None]
    report = {
        "source_trade_count": int(len(rows)),
        "evaluated_trade_count": int(len(evaluated)),
        **calculate_expectancy(evaluated),
        "performance_by_strategy": _metric_table(evaluated, "strategy", label="strategy"),
        "performance_by_setup_type": _metric_table(evaluated, "setup_type", label="setup_type"),
        "performance_by_allocation_bucket": _metric_table(evaluated, "allocation_bucket", label="allocation_bucket"),
        "notes": [],
    }
    if not evaluated:
        report["notes"].append("no_realized_trade_rows")
    _write_report(output_path, report)
    return report
