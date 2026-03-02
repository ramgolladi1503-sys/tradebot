from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from config import config as cfg
from core.paths import repo_root

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
    base = _norm_text(getattr(cfg, "STRATEGY_DRIFT_REPORT_DIR", ""))
    if base:
        return Path(base) / date_key / "strategy_drift.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "strategy_drift.json"


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
    candidates = [
        raw.get("regime"),
        raw.get("regime_bucket"),
        raw.get("market_regime"),
        raw.get("primary_regime"),
        raw.get("market_state"),
        metrics.get("regime") if isinstance(metrics, Mapping) else None,
        metrics.get("regime_bucket") if isinstance(metrics, Mapping) else None,
        metrics.get("market_regime") if isinstance(metrics, Mapping) else None,
        metrics.get("primary_regime") if isinstance(metrics, Mapping) else None,
        metrics.get("market_state") if isinstance(metrics, Mapping) else None,
    ]

    text = " ".join(_norm_text(value).upper() for value in candidates if _norm_text(value))
    if not text:
        return "UNKNOWN"
    if any(token in text for token in ("UNSTABLE", "VOLATILE", "EVENT", "CHAOTIC", "SHOCK")):
        return "UNSTABLE"
    if any(token in text for token in ("TREND", "UP", "DOWN", "BULL", "BEAR", "MOMENTUM", "BREAKOUT")):
        return "TREND"
    if any(token in text for token in ("RANGE", "SIDEWAYS", "NEUTRAL", "MEAN", "CHOP")):
        return "RANGE"
    return "UNKNOWN"


def _agg_metrics(rows: Sequence[Mapping[str, Any]]) -> dict:
    count = len(rows)
    wins = sum(1 for row in rows if _norm_text(row.get("outcome")).lower() == "hit_target")
    losses = sum(1 for row in rows if _norm_text(row.get("outcome")).lower() == "hit_sl")
    no_hit = count - wins - losses

    mfe_values = [
        float(v)
        for v in (_safe_float(row.get("mfe_points")) for row in rows)
        if v is not None
    ]
    mae_values = [
        float(v)
        for v in (_safe_float(row.get("mae_points")) for row in rows)
        if v is not None
    ]

    return {
        "trade_count": int(count),
        "wins": int(wins),
        "losses": int(losses),
        "no_hit": int(no_hit),
        "win_rate": (float(wins) / float(count)) if count > 0 else 0.0,
        "avg_mfe": (sum(mfe_values) / float(len(mfe_values))) if mfe_values else None,
        "avg_mae": (sum(mae_values) / float(len(mae_values))) if mae_values else None,
    }


def _pct_change(recent: float | None, baseline: float | None) -> float | None:
    if recent is None or baseline is None:
        return None
    denom = abs(float(baseline))
    if denom <= 1e-12:
        if abs(float(recent) - float(baseline)) <= 1e-12:
            return 0.0
        return None
    return (float(recent) - float(baseline)) / denom


def _window_days(
    *,
    available_days: Sequence[str],
    anchor_day: str,
    recent_days: int,
    baseline_days: int,
    baseline_excludes_recent: bool,
) -> tuple[list[str], list[str]]:
    filtered = sorted({day for day in available_days if day <= anchor_day})
    if not filtered:
        return [], []

    recent_window = filtered[-max(int(recent_days), 1) :]

    if baseline_excludes_recent:
        baseline_candidates = [day for day in filtered if day < recent_window[0]]
    else:
        baseline_candidates = filtered[:-1]

    baseline_window = baseline_candidates[-max(int(baseline_days), 1) :] if baseline_candidates else []
    return recent_window, baseline_window


def _build_group_rows(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (str(row.get("strategy_id") or "unknown"), str(row.get("regime") or "UNKNOWN"))
        grouped.setdefault(key, []).append(dict(row))
    return grouped


def _drift_for_group(
    *,
    recent_metrics: Mapping[str, Any],
    baseline_metrics: Mapping[str, Any],
    min_group_trades: int,
    win_rate_abs_threshold: float,
    mfe_pct_threshold: float,
    mae_pct_threshold: float,
) -> dict:
    recent_count = int(recent_metrics.get("trade_count") or 0)
    baseline_count = int(baseline_metrics.get("trade_count") or 0)

    wr_recent = _safe_float(recent_metrics.get("win_rate"))
    wr_base = _safe_float(baseline_metrics.get("win_rate"))
    mfe_recent = _safe_float(recent_metrics.get("avg_mfe"))
    mfe_base = _safe_float(baseline_metrics.get("avg_mfe"))
    mae_recent = _safe_float(recent_metrics.get("avg_mae"))
    mae_base = _safe_float(baseline_metrics.get("avg_mae"))

    win_rate_delta = (float(wr_recent) - float(wr_base)) if wr_recent is not None and wr_base is not None else None
    mfe_delta = (float(mfe_recent) - float(mfe_base)) if mfe_recent is not None and mfe_base is not None else None
    mae_delta = (float(mae_recent) - float(mae_base)) if mae_recent is not None and mae_base is not None else None

    mfe_pct_change = _pct_change(mfe_recent, mfe_base)
    mae_pct_change = _pct_change(mae_recent, mae_base)

    reasons: list[str] = []
    if win_rate_delta is not None and abs(float(win_rate_delta)) >= float(win_rate_abs_threshold):
        reasons.append("win_rate_delta")
    if mfe_pct_change is not None and abs(float(mfe_pct_change)) >= float(mfe_pct_threshold):
        reasons.append("avg_mfe_pct_change")
    if mae_pct_change is not None and abs(float(mae_pct_change)) >= float(mae_pct_threshold):
        reasons.append("avg_mae_pct_change")

    score_components: list[float] = []
    if win_rate_delta is not None and win_rate_abs_threshold > 0:
        score_components.append(abs(float(win_rate_delta)) / float(win_rate_abs_threshold))
    if mfe_pct_change is not None and mfe_pct_threshold > 0:
        score_components.append(abs(float(mfe_pct_change)) / float(mfe_pct_threshold))
    if mae_pct_change is not None and mae_pct_threshold > 0:
        score_components.append(abs(float(mae_pct_change)) / float(mae_pct_threshold))
    drift_score = (sum(score_components) / float(len(score_components))) if score_components else 0.0

    enough_samples = recent_count >= int(min_group_trades) and baseline_count >= int(min_group_trades)
    significant = bool(enough_samples and reasons)

    deterioration_flags: list[str] = []
    if win_rate_delta is not None and float(win_rate_delta) < 0:
        deterioration_flags.append("win_rate_down")
    if mfe_delta is not None and float(mfe_delta) < 0:
        deterioration_flags.append("avg_mfe_down")
    # MAE is typically adverse and often negative; lower (more negative) generally means worse.
    if mae_delta is not None and float(mae_delta) < 0:
        deterioration_flags.append("avg_mae_worse")

    return {
        "win_rate_delta": win_rate_delta,
        "avg_mfe_delta": mfe_delta,
        "avg_mae_delta": mae_delta,
        "avg_mfe_pct_change": mfe_pct_change,
        "avg_mae_pct_change": mae_pct_change,
        "drift_score": float(drift_score),
        "significant": bool(significant),
        "reasons": reasons,
        "deterioration": bool(significant and bool(deterioration_flags)),
        "deterioration_flags": deterioration_flags,
        "enough_samples": bool(enough_samples),
    }


def build_strategy_drift_report(
    date: Any,
    *,
    events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    include_intents: Sequence[str] | None = None,
    recent_days: int | None = None,
    baseline_days: int | None = None,
    baseline_excludes_recent: bool | None = None,
    min_group_trades: int | None = None,
    win_rate_abs_threshold: float | None = None,
    mfe_pct_threshold: float | None = None,
    mae_pct_threshold: float | None = None,
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

    recent_window_size = int(recent_days if recent_days is not None else getattr(cfg, "STRATEGY_DRIFT_RECENT_DAYS", 5))
    baseline_window_size = int(
        baseline_days if baseline_days is not None else getattr(cfg, "STRATEGY_DRIFT_BASELINE_DAYS", 30)
    )
    exclude_recent = bool(
        baseline_excludes_recent
        if baseline_excludes_recent is not None
        else getattr(cfg, "STRATEGY_DRIFT_BASELINE_EXCLUDES_RECENT", True)
    )
    min_count = int(min_group_trades if min_group_trades is not None else getattr(cfg, "STRATEGY_DRIFT_MIN_GROUP_TRADES", 5))
    win_thr = float(
        win_rate_abs_threshold
        if win_rate_abs_threshold is not None
        else getattr(cfg, "STRATEGY_DRIFT_WIN_RATE_ABS_THRESHOLD", 0.15)
    )
    mfe_thr = float(
        mfe_pct_threshold if mfe_pct_threshold is not None else getattr(cfg, "STRATEGY_DRIFT_MFE_PCT_THRESHOLD", 0.25)
    )
    mae_thr = float(
        mae_pct_threshold if mae_pct_threshold is not None else getattr(cfg, "STRATEGY_DRIFT_MAE_PCT_THRESHOLD", 0.25)
    )

    event_rows = list(events) if events is not None else list(load_trade_intent_events())
    outcome_rows = _load_outcomes(outcomes=outcomes)

    matched_rows: list[dict] = []
    scanned_events = 0

    for item in event_rows:
        coerced = _coerce_event(item)
        if coerced is None:
            continue
        event, raw = coerced
        day_key = _to_day_key(int(event.ts_epoch_ms))
        if day_key > date_key:
            continue
        scanned_events += 1

        intent = _norm_text(event.intent).lower()
        if intent not in intents:
            continue

        outcome = _match_outcome(event, outcome_rows)
        if not isinstance(outcome, TradeOutcome):
            continue

        matched_rows.append(
            {
                "event_id": event.event_id,
                "trade_key": event.trade_key,
                "strategy_id": _extract_strategy_id(event, raw),
                "regime": _extract_regime(event, raw),
                "day": day_key,
                "intent": event.intent,
                "outcome": outcome.outcome,
                "mfe_points": outcome.mfe_points,
                "mae_points": outcome.mae_points,
                "ts_epoch_ms": int(event.ts_epoch_ms),
            }
        )

    available_days = sorted({str(row.get("day")) for row in matched_rows if _norm_text(row.get("day"))})
    recent_days_window, baseline_days_window = _window_days(
        available_days=available_days,
        anchor_day=date_key,
        recent_days=recent_window_size,
        baseline_days=baseline_window_size,
        baseline_excludes_recent=exclude_recent,
    )

    recent_rows = [row for row in matched_rows if row.get("day") in set(recent_days_window)]
    baseline_rows = [row for row in matched_rows if row.get("day") in set(baseline_days_window)]

    recent_groups = _build_group_rows(recent_rows)
    baseline_groups = _build_group_rows(baseline_rows)
    group_keys = sorted(set(recent_groups.keys()) | set(baseline_groups.keys()), key=lambda item: (item[0], item[1]))

    group_rows: list[dict] = []
    drift_alerts: list[dict] = []

    for strategy_id, regime in group_keys:
        recent_metrics = _agg_metrics(recent_groups.get((strategy_id, regime), []))
        baseline_metrics = _agg_metrics(baseline_groups.get((strategy_id, regime), []))
        drift = _drift_for_group(
            recent_metrics=recent_metrics,
            baseline_metrics=baseline_metrics,
            min_group_trades=min_count,
            win_rate_abs_threshold=win_thr,
            mfe_pct_threshold=mfe_thr,
            mae_pct_threshold=mae_thr,
        )

        row = {
            "strategy_id": strategy_id,
            "regime": regime,
            "recent": recent_metrics,
            "baseline": baseline_metrics,
            "drift": drift,
        }
        group_rows.append(row)

        if bool(drift.get("significant")):
            drift_alerts.append(
                {
                    "strategy_id": strategy_id,
                    "regime": regime,
                    "drift_score": float(drift.get("drift_score") or 0.0),
                    "deterioration": bool(drift.get("deterioration")),
                    "reasons": list(drift.get("reasons") or []),
                    "deterioration_flags": list(drift.get("deterioration_flags") or []),
                    "recent_trade_count": int(recent_metrics.get("trade_count") or 0),
                    "baseline_trade_count": int(baseline_metrics.get("trade_count") or 0),
                }
            )

    group_rows.sort(
        key=lambda row: (
            -float(row.get("drift", {}).get("drift_score") or 0.0),
            str(row.get("strategy_id") or ""),
            str(row.get("regime") or ""),
        )
    )
    drift_alerts.sort(key=lambda row: (-float(row.get("drift_score") or 0.0), str(row.get("strategy_id") or "")))

    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "params": {
            "include_intents": sorted(intents),
            "recent_days": int(recent_window_size),
            "baseline_days": int(baseline_window_size),
            "baseline_excludes_recent": bool(exclude_recent),
            "min_group_trades": int(min_count),
            "win_rate_abs_threshold": float(win_thr),
            "mfe_pct_threshold": float(mfe_thr),
            "mae_pct_threshold": float(mae_thr),
        },
        "windows": {
            "recent_days": recent_days_window,
            "baseline_days": baseline_days_window,
        },
        "counts": {
            "scanned_events": int(scanned_events),
            "matched_rows": int(len(matched_rows)),
            "recent_rows": int(len(recent_rows)),
            "baseline_rows": int(len(baseline_rows)),
            "groups": int(len(group_rows)),
            "drift_alerts": int(len(drift_alerts)),
        },
        "groups": group_rows,
        "drift_alerts": drift_alerts,
    }

    out_path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(out_path, report)
    report["output_path"] = str(out_path)
    return report


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect strategy/regime drift between recent and baseline trading windows.")
    parser.add_argument("--date", required=True, help="Anchor date in YYYY-MM-DD (exchange local day).")
    parser.add_argument(
        "--include-intent",
        action="append",
        default=[],
        help="Intent(s) to include: accepted|rejected|advisory. Repeatable.",
    )
    parser.add_argument("--recent-days", type=int, default=None, help="Recent trading-day window size.")
    parser.add_argument("--baseline-days", type=int, default=None, help="Baseline trading-day window size.")
    parser.add_argument(
        "--baseline-includes-recent",
        action="store_true",
        help="If set, baseline may overlap with recent window (default excludes recent).",
    )
    parser.add_argument("--min-group-trades", type=int, default=None, help="Minimum trades in each window to flag drift.")
    parser.add_argument("--win-rate-abs-threshold", type=float, default=None, help="Absolute win-rate delta threshold.")
    parser.add_argument("--mfe-pct-threshold", type=float, default=None, help="Absolute avg MFE pct-change threshold.")
    parser.add_argument("--mae-pct-threshold", type=float, default=None, help="Absolute avg MAE pct-change threshold.")
    parser.add_argument("--output", default=None, help="Optional output path override.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    include_intents = [str(v) for v in list(args.include_intent or []) if _norm_text(v)]
    output_path = Path(args.output) if args.output else None

    payload = build_strategy_drift_report(
        args.date,
        include_intents=include_intents or None,
        recent_days=args.recent_days,
        baseline_days=args.baseline_days,
        baseline_excludes_recent=(not bool(args.baseline_includes_recent)),
        min_group_trades=args.min_group_trades,
        win_rate_abs_threshold=args.win_rate_abs_threshold,
        mfe_pct_threshold=args.mfe_pct_threshold,
        mae_pct_threshold=args.mae_pct_threshold,
        output_path=output_path,
    )
    print(
        json.dumps(
            {
                "date": payload.get("date"),
                "windows": payload.get("windows"),
                "counts": payload.get("counts"),
                "drift_alerts": payload.get("drift_alerts"),
                "output_path": payload.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
