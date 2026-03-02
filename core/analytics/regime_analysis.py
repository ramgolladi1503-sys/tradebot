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

from .schema import GateDecision, TradeIntentEvent, TradeOutcome, build_trade_key
from .store import load_trade_intent_events


IST = ZoneInfo("Asia/Kolkata")
_REGIME_ORDER = ["TREND", "RANGE", "UNSTABLE", "UNKNOWN"]


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


def _event_ts_ms(raw: Mapping[str, Any]) -> int | None:
    return (
        _coerce_epoch_ms(raw.get("ts_epoch_ms"))
        or _coerce_epoch_ms(raw.get("timestamp_epoch_ms"))
        or _coerce_epoch_ms(raw.get("timestamp_epoch"))
        or _coerce_epoch_ms(raw.get("ts_epoch"))
        or _coerce_epoch_ms(raw.get("timestamp_utc_iso"))
        or _coerce_epoch_ms(raw.get("timestamp_iso"))
        or _coerce_epoch_ms(raw.get("timestamp"))
        or _coerce_epoch_ms(raw.get("ts_ist"))
    )


def _parse_date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    if not text:
        return datetime.now(tz=IST).date().isoformat()
    return datetime.fromisoformat(text).date().isoformat()


def _to_day_key(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_option_type(value: Any) -> str | None:
    text = _norm_text(value).upper()
    if text in {"CE", "CALL", "C"}:
        return "CE"
    if text in {"PE", "PUT", "P"}:
        return "PE"
    return None


def _default_outcomes_path(date_key: str) -> Path:
    base = str(getattr(cfg, "OUTCOME_REPLAY_DIR", "") or "").strip()
    if base:
        return Path(base) / f"{date_key}.jsonl"
    return repo_root() / "runtime" / "analytics" / "outcomes" / f"{date_key}.jsonl"


def _default_report_path(date_key: str) -> Path:
    base = str(getattr(cfg, "REGIME_ANALYSIS_REPORT_DIR", "") or "").strip()
    if base:
        return Path(base) / date_key / "regime_analysis.json"
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / "regime_analysis.json"


def _default_telemetry_paths() -> list[Path]:
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

    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


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


def _event_type(event: TradeIntentEvent, raw: Mapping[str, Any]) -> str:
    intent = str(event.intent or "").strip().lower()
    if intent in {"accepted", "rejected", "advisory"}:
        return intent
    status = _norm_text(raw.get("status")).upper()
    reject_reason = _norm_text(raw.get("reject_reason") or raw.get("permission_reason"))
    if reject_reason or status in {"REJECTED", "BLOCKED", "INVALIDATED", "EXPIRED"}:
        return "rejected"
    if status in {"ACTIVE", "FILLED", "EXECUTED", "RESOLVED"}:
        return "accepted"
    return "advisory"


def _extract_regime_from_payload(payload: Mapping[str, Any]) -> str:
    metrics = payload.get("metrics_snapshot")
    metrics_map = metrics if isinstance(metrics, Mapping) else {}

    unstable_reasons = payload.get("unstable_reasons")
    if not isinstance(unstable_reasons, list):
        unstable_reasons = metrics_map.get("unstable_reasons") if isinstance(metrics_map.get("unstable_reasons"), list) else []
    if unstable_reasons:
        return "UNSTABLE"

    feed_state = _norm_text(payload.get("feed_state") or metrics_map.get("feed_state")).upper()
    if feed_state in {"DEGRADED", "DOWN"}:
        return "UNSTABLE"

    candidates = [
        payload.get("regime_bucket"),
        payload.get("regime"),
        payload.get("primary_regime"),
        payload.get("market_regime"),
        payload.get("regime_label"),
        payload.get("market_state"),
        payload.get("day_type"),
        metrics_map.get("regime_bucket"),
        metrics_map.get("regime"),
        metrics_map.get("primary_regime"),
        metrics_map.get("market_regime"),
        metrics_map.get("regime_label"),
        metrics_map.get("market_state"),
        metrics_map.get("day_type"),
    ]

    text = " ".join(_norm_text(item).upper() for item in candidates if _norm_text(item))
    if not text:
        return "UNKNOWN"

    unstable_tokens = ("UNSTABLE", "VOLATILE", "EVENT", "CHAOTIC", "SHOCK")
    trend_tokens = ("TREND", "UP", "DOWN", "BULL", "BEAR", "MOMENTUM", "BREAKOUT")
    range_tokens = ("RANGE", "SIDEWAYS", "NEUTRAL", "MEAN", "CHOP")

    if any(tok in text for tok in unstable_tokens):
        return "UNSTABLE"
    if any(tok in text for tok in trend_tokens):
        return "TREND"
    if any(tok in text for tok in range_tokens):
        return "RANGE"
    return "UNKNOWN"


def _build_trade_key_from_raw(raw: Mapping[str, Any]) -> str:
    existing = _norm_text(raw.get("trade_key"))
    if existing:
        return existing
    return build_trade_key(
        symbol=raw.get("symbol"),
        expiry=raw.get("expiry_date") or raw.get("expiry"),
        strike=raw.get("strike"),
        option_type=_normalize_option_type(raw.get("option_type") or raw.get("type") or raw.get("right")),
        side=raw.get("side") or raw.get("direction"),
        strategy_id=raw.get("strategy_id") or raw.get("strategy") or raw.get("source"),
    )


def _load_regime_hints(date_key: str, telemetry_paths: Iterable[Path] | None = None) -> dict[str, str]:
    latest: dict[str, tuple[int, str]] = {}
    for path in list(telemetry_paths or _default_telemetry_paths()):
        for row in _iter_jsonl(path):
            ts_ms = _event_ts_ms(row)
            if ts_ms is None or _to_day_key(int(ts_ms)) != date_key:
                continue
            regime = _extract_regime_from_payload(row)
            if regime == "UNKNOWN":
                continue
            trade_key = _build_trade_key_from_raw(row)
            if not trade_key:
                continue
            prev = latest.get(trade_key)
            if prev is None or int(ts_ms) >= int(prev[0]):
                latest[trade_key] = (int(ts_ms), regime)
    return {key: value[1] for key, value in latest.items()}


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


def _normalize_gate_decisions(event: TradeIntentEvent, raw: Mapping[str, Any], kind: str) -> list[GateDecision]:
    out: list[GateDecision] = []
    for gd in list(event.gate_decisions or ()):  # type: ignore[arg-type]
        if isinstance(gd, GateDecision):
            out.append(gd)
    if out:
        return out

    raw_gates = raw.get("gate_decisions")
    if isinstance(raw_gates, list):
        for item in raw_gates:
            if not isinstance(item, Mapping):
                continue
            try:
                out.append(GateDecision.from_dict(item))
            except Exception:
                continue
    if out:
        return out

    if kind == "rejected":
        gate_name = _norm_text(raw.get("gate_name") or "unknown_gate") or "unknown_gate"
        reason = _norm_text(event.reject_reason or raw.get("reject_reason") or "unknown_reject") or "unknown_reject"
        out.append(GateDecision(gate_name=gate_name, passed=False, reason=reason, metrics_snapshot={}))
    return out


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


def _regime_sort_key(regime: str) -> tuple[int, str]:
    reg = str(regime or "UNKNOWN").upper()
    if reg in _REGIME_ORDER:
        return (_REGIME_ORDER.index(reg), reg)
    return (len(_REGIME_ORDER), reg)


def _recommendations(
    gate_regime_rows: Sequence[Mapping[str, Any]],
    *,
    min_blocked_count: int,
    negative_threshold: float,
) -> list[dict]:
    by_gate: dict[str, list[Mapping[str, Any]]] = {}
    for row in gate_regime_rows:
        gate = _norm_text(row.get("gate_name")) or "unknown_gate"
        by_gate.setdefault(gate, []).append(row)

    out: list[dict] = []
    for gate, rows in by_gate.items():
        eligible = [row for row in rows if int(row.get("blocked_count") or 0) >= int(min_blocked_count)]
        if len(eligible) < 2:
            continue
        negative = [row for row in eligible if float(row.get("net_edge_score") or 0.0) < float(negative_threshold)]
        non_negative = [row for row in eligible if float(row.get("net_edge_score") or 0.0) >= 0.0]
        if not negative or not non_negative:
            continue
        for row in sorted(negative, key=lambda item: _regime_sort_key(str(item.get("regime")))):
            out.append(
                {
                    "gate_name": gate,
                    "regime": str(row.get("regime") or "UNKNOWN"),
                    "net_edge_score": float(row.get("net_edge_score") or 0.0),
                    "blocked_count": int(row.get("blocked_count") or 0),
                    "positive_regimes": sorted({str(item.get("regime") or "UNKNOWN") for item in non_negative}, key=_regime_sort_key),
                    "recommendation": "Gate is net-negative only in this regime; review regime-specific thresholding or disablement.",
                }
            )
    return out


def build_regime_analysis(
    date: Any,
    *,
    events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    outcomes: Sequence[TradeOutcome | Mapping[str, Any]] | None = None,
    outcome_paths: Iterable[Path] | None = None,
    telemetry_paths: Iterable[Path] | None = None,
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
        for item in outcomes:
            if isinstance(item, TradeOutcome):
                outcome_rows.append({"trade_outcome": item, "event_ref_id": None})
            elif isinstance(item, Mapping):
                normalized = _normalize_outcome_row(item)
                if normalized is not None:
                    outcome_rows.append(normalized)

    regime_hints = _load_regime_hints(date_key, telemetry_paths=telemetry_paths)

    regime_stats: dict[str, dict[str, Any]] = {}
    gate_regime_reason: dict[tuple[str, str, str], dict[str, Any]] = {}

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

        kind = _event_type(event, raw)
        matched = _match_outcome(event, outcome_rows)
        if isinstance(matched, TradeOutcome):
            matched_outcomes += 1

        regime = _extract_regime_from_payload(raw)
        if regime == "UNKNOWN":
            regime = _extract_regime_from_payload({"metrics_snapshot": event.metrics_snapshot})
        if regime == "UNKNOWN":
            regime = str(regime_hints.get(event.trade_key) or "UNKNOWN")

        r = regime_stats.setdefault(
            regime,
            {
                "regime": regime,
                "count": 0,
                "wins": 0,
                "losses": 0,
                "neutral": 0,
                "mfe_values": [],
                "mae_values": [],
            },
        )
        r["count"] += 1

        outcome_label = str(getattr(matched, "outcome", "") or "").lower()
        if outcome_label == "hit_target":
            r["wins"] += 1
        elif outcome_label == "hit_sl":
            r["losses"] += 1
        else:
            r["neutral"] += 1

        mfe = _safe_float(getattr(matched, "mfe_points", None))
        mae = _safe_float(getattr(matched, "mae_points", None))
        if mfe is not None:
            r["mfe_values"].append(float(mfe))
        if mae is not None:
            r["mae_values"].append(float(mae))

        if kind == "rejected":
            gate_decisions = _normalize_gate_decisions(event, raw, kind)
            for gd in gate_decisions:
                if gd.passed is not False:
                    continue
                gate_name = _norm_text(gd.gate_name) or "unknown_gate"
                reject_reason = _norm_text(event.reject_reason or gd.reason or raw.get("reject_reason")) or "unknown_reject"
                key = (regime, gate_name, reject_reason)
                bucket = gate_regime_reason.setdefault(
                    key,
                    {
                        "regime": regime,
                        "gate_name": gate_name,
                        "reject_reason": reject_reason,
                        "blocked_count": 0,
                        "blocked_would_win": 0,
                        "blocked_would_lose": 0,
                        "blocked_neutral": 0,
                    },
                )
                bucket["blocked_count"] += 1
                if outcome_label == "hit_target":
                    bucket["blocked_would_win"] += 1
                elif outcome_label == "hit_sl":
                    bucket["blocked_would_lose"] += 1
                else:
                    bucket["blocked_neutral"] += 1

    gate_regime: dict[tuple[str, str], dict[str, Any]] = {}
    for (_regime, _gate, _reason), row in gate_regime_reason.items():
        key = (row["regime"], row["gate_name"])
        dst = gate_regime.setdefault(
            key,
            {
                "regime": row["regime"],
                "gate_name": row["gate_name"],
                "blocked_count": 0,
                "blocked_would_win": 0,
                "blocked_would_lose": 0,
                "blocked_neutral": 0,
            },
        )
        dst["blocked_count"] += int(row["blocked_count"])
        dst["blocked_would_win"] += int(row["blocked_would_win"])
        dst["blocked_would_lose"] += int(row["blocked_would_lose"])
        dst["blocked_neutral"] += int(row["blocked_neutral"])

    gate_net_edge_by_regime: list[dict] = []
    for (_regime, _gate), row in gate_regime.items():
        blocked_count = int(row["blocked_count"])
        win = int(row["blocked_would_win"])
        lose = int(row["blocked_would_lose"])
        gate_net_edge_by_regime.append(
            {
                "regime": row["regime"],
                "gate_name": row["gate_name"],
                "blocked_count": blocked_count,
                "blocked_would_win": win,
                "blocked_would_lose": lose,
                "blocked_neutral": int(row["blocked_neutral"]),
                "net_edge_score": ((float(win) - float(lose)) / float(blocked_count)) if blocked_count > 0 else 0.0,
            }
        )
    gate_net_edge_by_regime.sort(key=lambda row: (_regime_sort_key(str(row.get("regime"))), str(row.get("gate_name") or "")))

    regime_splits: list[dict] = []
    for regime, row in regime_stats.items():
        count = int(row["count"])
        wins = int(row["wins"])
        losses = int(row["losses"])
        neutral = int(row["neutral"])
        mfe_vals = list(row.get("mfe_values") or [])
        mae_vals = list(row.get("mae_values") or [])
        regime_splits.append(
            {
                "regime": regime,
                "count": count,
                "wins": wins,
                "losses": losses,
                "neutral": neutral,
                "win_rate": (float(wins) / float(count)) if count > 0 else 0.0,
                "loss_rate": (float(losses) / float(count)) if count > 0 else 0.0,
                "avg_mfe": (sum(mfe_vals) / len(mfe_vals)) if mfe_vals else None,
                "avg_mae": (sum(mae_vals) / len(mae_vals)) if mae_vals else None,
                "gate_net_edge": [
                    g
                    for g in gate_net_edge_by_regime
                    if str(g.get("regime") or "") == regime
                ],
            }
        )
    regime_splits.sort(key=lambda item: _regime_sort_key(str(item.get("regime") or "UNKNOWN")))

    min_samples = max(1, int(getattr(cfg, "REGIME_RECOMMEND_MIN_BLOCKED_COUNT", 3)))
    neg_threshold = float(getattr(cfg, "REGIME_RECOMMEND_NEGATIVE_THRESHOLD", 0.0))
    recommendations = _recommendations(
        gate_net_edge_by_regime,
        min_blocked_count=min_samples,
        negative_threshold=neg_threshold,
    )

    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "total_events": total_events,
        "matched_outcomes": matched_outcomes,
        "regime_splits": regime_splits,
        "gate_net_edge_by_regime": gate_net_edge_by_regime,
        "gate_reject_reason_by_regime": sorted(
            [
                {
                    **row,
                    "net_edge_score": (
                        (float(row["blocked_would_win"]) - float(row["blocked_would_lose"])) / float(row["blocked_count"])
                    )
                    if int(row["blocked_count"]) > 0
                    else 0.0,
                }
                for row in gate_regime_reason.values()
            ],
            key=lambda item: (
                _regime_sort_key(str(item.get("regime") or "UNKNOWN")),
                str(item.get("gate_name") or ""),
                str(item.get("reject_reason") or ""),
            ),
        ),
        "regime_recommendations": recommendations,
        "recommendation_params": {
            "min_blocked_count": min_samples,
            "negative_threshold": neg_threshold,
        },
    }

    out_path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(out_path, report)
    report["output_path"] = str(out_path)
    return report


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build regime-specific outcome and gate analysis.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange day).")
    parser.add_argument(
        "--outcomes-path",
        action="append",
        default=None,
        help="Optional outcome replay JSONL path (repeatable).",
    )
    parser.add_argument(
        "--telemetry-path",
        action="append",
        default=None,
        help="Optional telemetry JSONL path for regime hints (repeatable).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    outcome_paths = [Path(p) for p in (args.outcomes_path or [])] if args.outcomes_path else None
    telemetry_paths = [Path(p) for p in (args.telemetry_path or [])] if args.telemetry_path else None
    result = build_regime_analysis(args.date, outcome_paths=outcome_paths, telemetry_paths=telemetry_paths)
    print(
        json.dumps(
            {
                "date": result.get("date"),
                "total_events": result.get("total_events"),
                "matched_outcomes": result.get("matched_outcomes"),
                "recommendations": len(result.get("regime_recommendations") or []),
                "output_path": result.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
