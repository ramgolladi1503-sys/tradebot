from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import repo_root
from core.ml_governance import calibration_curve

from .schema import TradeIntentEvent, TradeOutcome
from .store import load_trade_intent_events, load_trade_outcomes


IST = ZoneInfo("Asia/Kolkata")


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
    base = str(getattr(cfg, "CONFIDENCE_CALIBRATION_REPORT_DIR", "") or "").strip()
    if base:
        return Path(base) / date_key / "confidence_calibration.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "confidence_calibration.json"


def _report_root() -> Path:
    base = str(getattr(cfg, "CONFIDENCE_CALIBRATION_REPORT_DIR", "") or "").strip()
    if base:
        return Path(base)
    return repo_root() / "runtime" / "analytics" / "reports"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _event_predicted_confidence(event: TradeIntentEvent) -> tuple[float | None, str | None]:
    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    for key in (
        "predicted_confidence",
        "confidence_raw_canonical",
        "builder_confidence",
        "gating_final_confidence",
        "confidence_after_soft_veto",
        "confidence_final",
    ):
        value = _safe_float(metrics.get(key))
        if value is not None:
            source = str(metrics.get("predicted_confidence_source") or key)
            return max(0.0, min(1.0, float(value))), source
    return None, None


def _match_outcome(event: TradeIntentEvent, outcomes: Sequence[TradeOutcome]) -> TradeOutcome | None:
    for outcome in outcomes:
        if outcome.event_id == event.event_id:
            return outcome

    scored: list[tuple[int, int, TradeOutcome]] = []
    for outcome in outcomes:
        if outcome.trade_key != event.trade_key:
            continue
        delta = abs(int(outcome.ts_epoch_ms) - int(event.ts_epoch_ms))
        forward_bias = 0 if int(outcome.ts_epoch_ms) >= int(event.ts_epoch_ms) else 1
        scored.append((forward_bias, delta, outcome))
    if scored:
        scored.sort(key=lambda item: (item[0], item[1]))
        return scored[0][2]

    scored_symbol: list[tuple[int, TradeOutcome]] = []
    for outcome in outcomes:
        if str(outcome.symbol or "").upper() != str(event.symbol or "").upper():
            continue
        delta = abs(int(outcome.ts_epoch_ms) - int(event.ts_epoch_ms))
        scored_symbol.append((delta, outcome))
    if scored_symbol:
        scored_symbol.sort(key=lambda item: item[0])
        if scored_symbol[0][0] <= 6 * 60 * 60 * 1000:
            return scored_symbol[0][1]
    return None


def _outcome_to_actual(outcome: TradeOutcome) -> float:
    return 1.0 if str(outcome.outcome or "").lower() == "hit_target" else 0.0


def _brier_score(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
    if not actual or not predicted or len(actual) != len(predicted):
        return None
    total = 0.0
    count = 0
    for y, p in zip(actual, predicted):
        total += (float(p) - float(y)) ** 2
        count += 1
    if count <= 0:
        return None
    return float(total / count)


def calibrate_confidence(
    confidence_raw: float | None,
    reliability_curve_rows: Sequence[Mapping[str, Any]],
    *,
    min_bin_count: int | None = None,
) -> float | None:
    value = _safe_float(confidence_raw)
    if value is None:
        return None
    clipped = max(0.0, min(1.0, float(value)))
    required = max(1, int(min_bin_count if min_bin_count is not None else getattr(cfg, "CONFIDENCE_CALIBRATION_MIN_BIN_COUNT", 3)))
    for row in list(reliability_curve_rows or []):
        try:
            lo = float(row.get("bin_low"))
            hi = float(row.get("bin_high"))
        except Exception:
            continue
        in_bin = (clipped >= lo and clipped < hi) or (clipped == 1.0 and clipped <= hi)
        if not in_bin:
            continue
        count = int(row.get("count") or 0)
        win_rate = _safe_float(row.get("win_rate"))
        if count >= required and win_rate is not None:
            return max(0.0, min(1.0, float(win_rate)))
        avg_conf = _safe_float(row.get("avg_conf"))
        if avg_conf is not None:
            return max(0.0, min(1.0, float(avg_conf)))
        return clipped
    return clipped


def load_latest_confidence_calibration_report(*, require_eligible: bool = True) -> dict[str, Any] | None:
    root = _report_root()
    if not root.exists():
        return None
    candidates = sorted(
        root.glob("*/confidence_calibration.json"),
        key=lambda path: (str(path.parent.name), path.stat().st_mtime),
        reverse=True,
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        calibration = dict(payload.get("calibration") or {})
        if require_eligible and not bool(calibration.get("eligible")):
            continue
        payload["output_path"] = str(path)
        return payload
    return None


def build_confidence_calibration_report(
    date_key: str | datetime | None = None,
    *,
    events: Sequence[TradeIntentEvent] | None = None,
    outcomes: Sequence[TradeOutcome] | None = None,
    output_path: Path | None = None,
    bins: int | None = None,
    min_rows: int | None = None,
    min_bin_count: int | None = None,
) -> dict[str, Any]:
    resolved_date = _parse_date_key(date_key)
    resolved_bins = max(2, int(bins if bins is not None else getattr(cfg, "CONFIDENCE_CALIBRATION_BINS", 10)))
    resolved_min_rows = max(1, int(min_rows if min_rows is not None else getattr(cfg, "CONFIDENCE_CALIBRATION_MIN_ROWS", 25)))
    resolved_min_bin_count = max(1, int(min_bin_count if min_bin_count is not None else getattr(cfg, "CONFIDENCE_CALIBRATION_MIN_BIN_COUNT", 3)))

    intent_events = list(events) if events is not None else list(load_trade_intent_events())
    outcome_rows = list(outcomes) if outcomes is not None else list(load_trade_outcomes())
    intent_events = [event for event in intent_events if _to_day_key(int(event.ts_epoch_ms)) == resolved_date]
    outcome_rows = [outcome for outcome in outcome_rows if _to_day_key(int(outcome.ts_epoch_ms)) == resolved_date]

    matched_rows: list[dict[str, Any]] = []
    skipped_no_prediction = 0
    skipped_no_outcome = 0
    for event in intent_events:
        predicted_confidence, predicted_source = _event_predicted_confidence(event)
        if predicted_confidence is None:
            skipped_no_prediction += 1
            continue
        matched = _match_outcome(event, outcome_rows)
        if matched is None:
            skipped_no_outcome += 1
            continue
        actual = _outcome_to_actual(matched)
        matched_rows.append(
            {
                "event_id": event.event_id,
                "trade_key": event.trade_key,
                "symbol": event.symbol,
                "intent": event.intent,
                "predicted_confidence": float(predicted_confidence),
                "predicted_confidence_source": str(predicted_source or "unknown"),
                "actual_outcome": str(matched.outcome),
                "actual_outcome_binary": float(actual),
                "outcome_event_id": matched.event_id,
                "outcome_ts_epoch_ms": int(matched.ts_epoch_ms),
            }
        )

    actuals = [float(row["actual_outcome_binary"]) for row in matched_rows]
    predicted = [float(row["predicted_confidence"]) for row in matched_rows]
    reliability = calibration_curve(predicted, actuals, bins=resolved_bins) if matched_rows else []
    calibrated_rows = []
    calibrated_scores: list[float] = []
    for row in matched_rows:
        calibrated = calibrate_confidence(
            row.get("predicted_confidence"),
            reliability,
            min_bin_count=resolved_min_bin_count,
        )
        out = dict(row)
        out["confidence_calibrated"] = calibrated
        calibrated_rows.append(out)
        if calibrated is not None:
            calibrated_scores.append(float(calibrated))

    raw_brier = _brier_score(actuals, predicted)
    calibrated_brier = _brier_score(actuals, calibrated_scores) if len(calibrated_scores) == len(actuals) else None
    report = {
        "date": resolved_date,
        "counts": {
            "events": int(len(intent_events)),
            "outcomes": int(len(outcome_rows)),
            "matched_rows": int(len(matched_rows)),
            "skipped_no_prediction": int(skipped_no_prediction),
            "skipped_no_outcome": int(skipped_no_outcome),
            "positive_outcomes": int(sum(1 for value in actuals if value > 0.0)),
        },
        "calibration": {
            "method": "reliability_curve_lookup",
            "bins": int(resolved_bins),
            "min_rows": int(resolved_min_rows),
            "min_bin_count": int(resolved_min_bin_count),
            "eligible": bool(len(matched_rows) >= resolved_min_rows),
            "reliability_curve": list(reliability),
            "brier_score_raw": raw_brier,
            "brier_score_calibrated_in_sample": calibrated_brier,
        },
        "samples": list(calibrated_rows),
    }
    resolved_output = output_path or _default_report_path(resolved_date)
    _atomic_write_json(resolved_output, report)
    report["output_path"] = str(resolved_output)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build offline confidence calibration report from intent/outcome analytics.")
    parser.add_argument("--date", dest="date_key", default=None, help="Local date key YYYY-MM-DD. Defaults to today (IST).")
    parser.add_argument("--bins", type=int, default=None, help="Reliability-curve bin count.")
    parser.add_argument("--min-rows", type=int, default=None, help="Minimum matched rows before report is considered eligible.")
    parser.add_argument("--min-bin-count", type=int, default=None, help="Minimum rows per bin before using empirical win rate.")
    parser.add_argument("--output", type=str, default=None, help="Optional explicit output path.")
    args = parser.parse_args(argv)
    payload = build_confidence_calibration_report(
        args.date_key,
        output_path=(Path(args.output) if args.output else None),
        bins=args.bins,
        min_rows=args.min_rows,
        min_bin_count=args.min_bin_count,
    )
    print(
        json.dumps(
            {
                "date": payload.get("date"),
                "matched_rows": ((payload.get("counts") or {}).get("matched_rows")),
                "eligible": (((payload.get("calibration") or {}).get("eligible"))),
                "brier_score_raw": (((payload.get("calibration") or {}).get("brier_score_raw"))),
                "output_path": payload.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
