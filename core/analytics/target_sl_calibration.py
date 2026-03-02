from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import repo_root

from .schema import TradeIntentEvent, TradeOutcome
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


def _parse_date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    if not text:
        return datetime.now(tz=IST).date().isoformat()
    return datetime.fromisoformat(text).date().isoformat()


def _to_day_key(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()


def _default_report_path(date_key: str) -> Path:
    base = str(getattr(cfg, "TARGET_SL_CALIBRATION_REPORT_DIR", "") or "").strip()
    if base:
        return Path(base) / date_key / "target_sl_calibration.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "target_sl_calibration.json"


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
        return {"trade_outcome": item, "event_ref_id": None, "target_points": None, "stop_points": None}
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

    event_ref_id = str(raw.get("event_ref_id") or raw.get("source_event_id") or "").strip() or None
    target_points = _safe_float(raw.get("target_points"))
    stop_points = _safe_float(raw.get("stop_points") or raw.get("stop_distance_points"))
    entry = _safe_float(raw.get("intended_entry") or raw.get("entry") or raw.get("entry_price"))
    target = _safe_float(raw.get("target") or raw.get("target_price"))
    stop = _safe_float(raw.get("stop") or raw.get("stop_price") or raw.get("stop_loss"))
    if target_points is None and entry is not None and target is not None:
        diff = abs(float(target) - float(entry))
        if diff > 0:
            target_points = diff
    if stop_points is None and entry is not None and stop is not None:
        diff = abs(float(entry) - float(stop))
        if diff > 0:
            stop_points = diff
    return {
        "trade_outcome": outcome,
        "event_ref_id": event_ref_id,
        "target_points": target_points,
        "stop_points": stop_points,
    }


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
        out = normalized.get("trade_outcome")
        if not isinstance(out, TradeOutcome):
            continue
        if _to_day_key(int(out.ts_epoch_ms)) != date_key:
            continue
        rows.append(normalized)
    rows.sort(key=lambda row: int(row["trade_outcome"].ts_epoch_ms))
    return rows


def _match_outcome(event: TradeIntentEvent, outcomes: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for row in outcomes:
        if str(row.get("event_ref_id") or "").strip() == event.event_id:
            return row

    for row in outcomes:
        out = row.get("trade_outcome")
        if isinstance(out, TradeOutcome) and out.event_id == event.event_id:
            return row

    scored: list[tuple[int, int, Mapping[str, Any]]] = []
    for row in outcomes:
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

    scored_symbol: list[tuple[int, Mapping[str, Any]]] = []
    for row in outcomes:
        out = row.get("trade_outcome")
        if not isinstance(out, TradeOutcome):
            continue
        if str(out.symbol or "").upper() != str(event.symbol or "").upper():
            continue
        delta = abs(int(out.ts_epoch_ms) - int(event.ts_epoch_ms))
        scored_symbol.append((delta, row))
    if scored_symbol:
        scored_symbol.sort(key=lambda item: item[0])
        if scored_symbol[0][0] <= 6 * 60 * 60 * 1000:
            return scored_symbol[0][1]
    return None


def _extract_target_points(event: TradeIntentEvent, raw: Mapping[str, Any], matched_outcome: Mapping[str, Any] | None) -> float | None:
    if matched_outcome:
        tp = _safe_float(matched_outcome.get("target_points"))
        if tp is not None and tp > 0:
            return tp

    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    target_points = _safe_float(metrics.get("target_points") if isinstance(metrics, Mapping) else None)
    if target_points is not None and target_points > 0:
        return target_points

    raw_target_points = _safe_float(raw.get("target_points"))
    if raw_target_points is not None and raw_target_points > 0:
        return raw_target_points

    entry = _safe_float(
        raw.get("intended_entry")
        or raw.get("entry")
        or raw.get("entry_price")
        or (metrics.get("intended_entry") if isinstance(metrics, Mapping) else None)
        or (metrics.get("entry") if isinstance(metrics, Mapping) else None)
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
    return None


def _extract_stop_points(event: TradeIntentEvent, raw: Mapping[str, Any], matched_outcome: Mapping[str, Any] | None) -> float | None:
    if matched_outcome:
        sp = _safe_float(matched_outcome.get("stop_points"))
        if sp is not None and sp > 0:
            return sp

    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    stop_points = _safe_float(
        (metrics.get("stop_points") if isinstance(metrics, Mapping) else None)
        or (metrics.get("stop_distance_points") if isinstance(metrics, Mapping) else None)
    )
    if stop_points is not None and stop_points > 0:
        return stop_points

    raw_stop_points = _safe_float(raw.get("stop_points") or raw.get("stop_distance_points"))
    if raw_stop_points is not None and raw_stop_points > 0:
        return raw_stop_points

    entry = _safe_float(
        raw.get("intended_entry")
        or raw.get("entry")
        or raw.get("entry_price")
        or (metrics.get("intended_entry") if isinstance(metrics, Mapping) else None)
        or (metrics.get("entry") if isinstance(metrics, Mapping) else None)
    )
    stop = _safe_float(
        raw.get("stop")
        or raw.get("stop_loss")
        or raw.get("stop_price")
        or (metrics.get("stop") if isinstance(metrics, Mapping) else None)
        or (metrics.get("stop_loss") if isinstance(metrics, Mapping) else None)
    )
    if entry is not None and stop is not None:
        diff = abs(float(entry) - float(stop))
        if diff > 0:
            return diff
    return None


def _extract_atr_points(event: TradeIntentEvent, raw: Mapping[str, Any]) -> float | None:
    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    atr = _safe_float(
        (metrics.get("atr_points") if isinstance(metrics, Mapping) else None)
        or (metrics.get("atr") if isinstance(metrics, Mapping) else None)
        or (metrics.get("atr_value") if isinstance(metrics, Mapping) else None)
        or (metrics.get("option_atr") if isinstance(metrics, Mapping) else None)
        or raw.get("atr_points")
        or raw.get("atr")
        or raw.get("atr_value")
    )
    if atr is None or atr <= 0:
        return None
    return float(atr)


def _quantile(values: Sequence[float], q: float) -> float | None:
    vals = sorted(float(v) for v in values if _safe_float(v) is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    qq = max(0.0, min(1.0, float(q)))
    idx = (len(vals) - 1) * qq
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    if hi == lo:
        return vals[lo]
    weight = idx - lo
    return vals[lo] + ((vals[hi] - vals[lo]) * weight)


def _distribution_band(values: Sequence[float], low_q: float, high_q: float) -> dict:
    low = _quantile(values, low_q)
    high = _quantile(values, high_q)
    median = _quantile(values, 0.5)
    return {
        "count": len([v for v in values if _safe_float(v) is not None]),
        "p50": median,
        "p_low": low,
        "p_high": high,
        "q_low": float(low_q),
        "q_high": float(high_q),
    }


def _build_empirical_recommendation(rows: Sequence[Mapping[str, Any]], *, target_q: tuple[float, float], stop_q: tuple[float, float]) -> dict:
    mfe_values = [float(row["mfe_points"]) for row in rows if _safe_float(row.get("mfe_points")) is not None and float(row.get("mfe_points")) >= 0]
    mae_abs_values = [float(row["mae_abs_points"]) for row in rows if _safe_float(row.get("mae_abs_points")) is not None and float(row.get("mae_abs_points")) >= 0]
    return {
        "method": "empirical_quantiles",
        "target_band_points": _distribution_band(mfe_values, target_q[0], target_q[1]),
        "stop_band_points": _distribution_band(mae_abs_values, stop_q[0], stop_q[1]),
    }


def _build_atr_bucket_recommendation(
    rows: Sequence[Mapping[str, Any]],
    *,
    target_q: tuple[float, float],
    stop_q: tuple[float, float],
) -> dict:
    atr_rows = [row for row in rows if _safe_float(row.get("atr_points")) is not None and float(row.get("atr_points")) > 0]
    if len(atr_rows) < 3:
        return _build_empirical_recommendation(rows, target_q=target_q, stop_q=stop_q)

    atr_values = [float(row["atr_points"]) for row in atr_rows]
    q33 = _quantile(atr_values, 0.33)
    q66 = _quantile(atr_values, 0.66)
    if q33 is None or q66 is None or q66 <= 0:
        return _build_empirical_recommendation(rows, target_q=target_q, stop_q=stop_q)

    buckets: dict[str, list[Mapping[str, Any]]] = {"LOW": [], "MID": [], "HIGH": []}
    for row in atr_rows:
        atr = float(row["atr_points"])
        if atr <= q33:
            buckets["LOW"].append(row)
        elif atr <= q66:
            buckets["MID"].append(row)
        else:
            buckets["HIGH"].append(row)

    bucket_rows: list[dict] = []
    for label in ("LOW", "MID", "HIGH"):
        sample = buckets[label]
        if not sample:
            continue
        mfe_values = [float(r["mfe_points"]) for r in sample if _safe_float(r.get("mfe_points")) is not None and float(r.get("mfe_points")) >= 0]
        mae_abs_values = [float(r["mae_abs_points"]) for r in sample if _safe_float(r.get("mae_abs_points")) is not None and float(r.get("mae_abs_points")) >= 0]
        atr_bucket_values = [float(r["atr_points"]) for r in sample if _safe_float(r.get("atr_points")) is not None and float(r.get("atr_points")) > 0]
        atr_median = _quantile(atr_bucket_values, 0.5)
        target_band = _distribution_band(mfe_values, target_q[0], target_q[1])
        stop_band = _distribution_band(mae_abs_values, stop_q[0], stop_q[1])

        target_mult_low = (float(target_band["p_low"]) / float(atr_median)) if target_band.get("p_low") is not None and atr_median else None
        target_mult_high = (float(target_band["p_high"]) / float(atr_median)) if target_band.get("p_high") is not None and atr_median else None
        stop_mult_low = (float(stop_band["p_low"]) / float(atr_median)) if stop_band.get("p_low") is not None and atr_median else None
        stop_mult_high = (float(stop_band["p_high"]) / float(atr_median)) if stop_band.get("p_high") is not None and atr_median else None

        bucket_rows.append(
            {
                "atr_bucket": label,
                "count": len(sample),
                "atr_median": atr_median,
                "atr_min": min(atr_bucket_values) if atr_bucket_values else None,
                "atr_max": max(atr_bucket_values) if atr_bucket_values else None,
                "target_band_points": target_band,
                "stop_band_points": stop_band,
                "target_band_atr_mult": {"low": target_mult_low, "high": target_mult_high},
                "stop_band_atr_mult": {"low": stop_mult_low, "high": stop_mult_high},
            }
        )

    if not bucket_rows:
        return _build_empirical_recommendation(rows, target_q=target_q, stop_q=stop_q)

    return {
        "method": "atr_buckets",
        "atr_split": {"q33": q33, "q66": q66},
        "buckets": bucket_rows,
        "fallback_empirical": _build_empirical_recommendation(rows, target_q=target_q, stop_q=stop_q),
    }


def build_target_sl_calibration_report(
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
    outcome_rows = _load_outcomes(date_key=date_key, outcomes=outcomes, outcome_paths=outcome_paths)

    target_low_q = float(getattr(cfg, "TARGET_SL_CAL_TARGET_Q_LOW", 0.6))
    target_high_q = float(getattr(cfg, "TARGET_SL_CAL_TARGET_Q_HIGH", 0.8))
    stop_low_q = float(getattr(cfg, "TARGET_SL_CAL_STOP_Q_LOW", 0.6))
    stop_high_q = float(getattr(cfg, "TARGET_SL_CAL_STOP_Q_HIGH", 0.8))

    rows: list[dict] = []
    total_events = 0
    matched_outcomes = 0

    for item in event_rows:
        coerced = _coerce_event(item)
        if coerced is None:
            continue
        event, raw = coerced
        if _to_day_key(int(event.ts_epoch_ms)) != date_key:
            continue
        total_events += 1

        matched = _match_outcome(event, outcome_rows)
        out = matched.get("trade_outcome") if isinstance(matched, Mapping) else None
        if not isinstance(out, TradeOutcome):
            continue
        matched_outcomes += 1

        target_points = _extract_target_points(event, raw, matched if isinstance(matched, Mapping) else None)
        stop_points = _extract_stop_points(event, raw, matched if isinstance(matched, Mapping) else None)
        mfe_points = _safe_float(out.mfe_points)
        mae_points = _safe_float(out.mae_points)
        mae_abs = abs(float(mae_points)) if mae_points is not None else None
        atr_points = _extract_atr_points(event, raw)

        target_hit = bool(
            target_points is not None
            and target_points > 0
            and mfe_points is not None
            and float(mfe_points) >= float(target_points)
        )
        left_on_table = (
            float(mfe_points) - float(target_points)
            if target_points is not None
            and target_points > 0
            and mfe_points is not None
            and float(mfe_points) > float(target_points)
            else None
        )
        stop_breach = bool(
            stop_points is not None
            and stop_points > 0
            and mae_abs is not None
            and float(mae_abs) >= float(stop_points)
        )
        too_tight = (
            float(mae_abs) - float(stop_points)
            if stop_points is not None
            and stop_points > 0
            and mae_abs is not None
            and float(mae_abs) > float(stop_points)
            else None
        )

        rows.append(
            {
                "event_id": event.event_id,
                "trade_key": event.trade_key,
                "symbol": event.symbol,
                "ts_epoch_ms": int(event.ts_epoch_ms),
                "target_points": target_points,
                "stop_points": stop_points,
                "mfe_points": mfe_points,
                "mae_points": mae_points,
                "mae_abs_points": mae_abs,
                "atr_points": atr_points,
                "target_hit": target_hit,
                "stop_breach": stop_breach,
                "left_on_table_points": left_on_table,
                "too_tight_points": too_tight,
                "outcome": str(out.outcome),
            }
        )

    rows.sort(key=lambda row: int(row.get("ts_epoch_ms") or 0))

    target_samples = [row for row in rows if _safe_float(row.get("target_points")) is not None and _safe_float(row.get("mfe_points")) is not None]
    stop_samples = [row for row in rows if _safe_float(row.get("stop_points")) is not None and _safe_float(row.get("mae_abs_points")) is not None]

    target_hit_count = sum(1 for row in target_samples if bool(row.get("target_hit")))
    stop_breach_count = sum(1 for row in stop_samples if bool(row.get("stop_breach")))
    left_on_table_vals = [float(row["left_on_table_points"]) for row in target_samples if _safe_float(row.get("left_on_table_points")) is not None]
    too_tight_vals = [float(row["too_tight_points"]) for row in stop_samples if _safe_float(row.get("too_tight_points")) is not None]
    target_points_vals = [float(row["target_points"]) for row in target_samples if _safe_float(row.get("target_points")) is not None]
    stop_points_vals = [float(row["stop_points"]) for row in stop_samples if _safe_float(row.get("stop_points")) is not None]

    recommendations = _build_atr_bucket_recommendation(
        rows,
        target_q=(target_low_q, target_high_q),
        stop_q=(stop_low_q, stop_high_q),
    )

    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "total_events": total_events,
        "matched_outcomes": matched_outcomes,
        "evaluated_rows": len(rows),
        "target_metrics": {
            "samples": len(target_samples),
            "pct_mfe_ge_target": (float(target_hit_count) / float(len(target_samples))) if target_samples else 0.0,
            "avg_left_on_table_points": (sum(left_on_table_vals) / len(left_on_table_vals)) if left_on_table_vals else 0.0,
            "avg_target_points": (sum(target_points_vals) / len(target_points_vals)) if target_points_vals else None,
        },
        "stop_metrics": {
            "samples": len(stop_samples),
            "pct_mae_ge_stop": (float(stop_breach_count) / float(len(stop_samples))) if stop_samples else 0.0,
            "avg_too_tight_points": (sum(too_tight_vals) / len(too_tight_vals)) if too_tight_vals else 0.0,
            "avg_stop_points": (sum(stop_points_vals) / len(stop_points_vals)) if stop_points_vals else None,
        },
        "recommendations": recommendations,
        "rows": rows,
    }

    report_path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(report_path, report)
    report["output_path"] = str(report_path)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Target/stop calibration analysis for event outcomes.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange day).")
    parser.add_argument(
        "--outcome-path",
        action="append",
        default=[],
        help="Optional outcome JSONL path(s), supports rows with trade_outcome payload.",
    )
    parser.add_argument("--output", default=None, help="Optional output path override.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    outcome_paths = [Path(p) for p in list(args.outcome_path or []) if str(p).strip()]
    output_path = Path(args.output) if args.output else None
    payload = build_target_sl_calibration_report(
        args.date,
        outcome_paths=outcome_paths or None,
        output_path=output_path,
    )
    print(
        json.dumps(
            {
                "date": payload.get("date"),
                "matched_outcomes": payload.get("matched_outcomes"),
                "target_metrics": payload.get("target_metrics"),
                "stop_metrics": payload.get("stop_metrics"),
                "recommendation_method": (payload.get("recommendations") or {}).get("method"),
                "output_path": payload.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
