from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from .confidence import should_emit_suggestion
from .replay import classify_outcome_for_rejected_trade


IST = ZoneInfo("Asia/Kolkata")
_OUTCOME_LABELS = {"hit_target", "hit_sl", "no_hit"}


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except Exception:
        return None


def _coerce_epoch_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw >= 1_000_000_000_000:
            return int(raw)
        if raw >= 1_000_000_000:
            return int(raw * 1000.0)
        return None
    text = _text(value)
    if not text:
        return None
    try:
        return _coerce_epoch_ms(float(text))
    except Exception:
        pass
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return int(parsed.timestamp() * 1000.0)
    except Exception:
        return None


def _event_ts_ms(row: Mapping[str, Any]) -> int | None:
    for key in (
        "ts_epoch_ms",
        "timestamp_epoch_ms",
        "reject_ts_epoch_ms",
        "reject_ts_epoch",
        "event_ts_epoch_ms",
        "ts",
        "timestamp",
        "ts_utc",
    ):
        ts = _coerce_epoch_ms(row.get(key))
        if ts is not None:
            return ts
    return None


def _normalize_outcome(value: Any) -> str | None:
    text = _text(value).lower()
    if not text:
        return None
    mapping = {
        "hit": "hit_target",
        "target_hit": "hit_target",
        "hit_target": "hit_target",
        "sl": "hit_sl",
        "stop_hit": "hit_sl",
        "sl_hit": "hit_sl",
        "hit_sl": "hit_sl",
        "no_hit": "no_hit",
        "none": "no_hit",
        "timeout": "no_hit",
        "unknown": "no_hit",
    }
    return mapping.get(text)


def _intent(row: Mapping[str, Any]) -> str:
    raw_intent = _text(row.get("intent")).lower()
    if raw_intent in {"rejected", "accepted", "advisory"}:
        return raw_intent
    event_type = _text(row.get("event_type")).upper()
    if event_type == "REJECTED_TRADE":
        return "rejected"
    if event_type == "ACCEPTED_TRADE":
        return "accepted"
    if event_type == "ADVISORY_TRADE":
        return "advisory"
    return ""


def _is_trade_event(row: Mapping[str, Any]) -> bool:
    if _intent(row):
        return True
    if row.get("trade_key") and row.get("symbol") and row.get("event_id"):
        if row.get("event_type") in {None, "", "TRADE_EVENT"}:
            return True
    return False


def _is_tick_like(row: Mapping[str, Any]) -> bool:
    event_type = _text(row.get("event_type")).upper()
    if event_type in {"TICK", "SNAPSHOT"}:
        return True
    if event_type:
        return False
    if not row.get("symbol"):
        return False
    # Rows with market prices but without explicit trade intent are treated as ticks/snapshots.
    if any(key in row for key in ("ltp", "bid", "ask", "mark_price")) and not _intent(row):
        return True
    return False


def _extract_gate_reasons(row: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    from_list = row.get("gate_reasons")
    if isinstance(from_list, list):
        for item in from_list:
            text = _text(item)
            if text:
                reasons.append(text)
    reason = _text(row.get("reject_reason"))
    if reason:
        reasons.append(reason)
    gate_decisions = row.get("gate_decisions")
    if isinstance(gate_decisions, list):
        for item in gate_decisions:
            if not isinstance(item, Mapping):
                continue
            passed = item.get("passed")
            if passed is True:
                continue
            item_reason = _text(item.get("reason")) or _text(item.get("gate_name"))
            if item_reason:
                reasons.append(item_reason)
    seen: set[str] = set()
    out: list[str] = []
    for item in reasons:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _primary_reason(row: Mapping[str, Any]) -> str:
    reasons = _extract_gate_reasons(row)
    if reasons:
        return reasons[0]
    return "unknown_reject"


def _feed_state(row: Mapping[str, Any]) -> str:
    direct = _text(row.get("feed_state")).upper()
    if direct:
        return direct
    metrics = row.get("metrics_snapshot")
    if isinstance(metrics, Mapping):
        nested = _text(metrics.get("feed_state")).upper()
        if nested:
            return nested
    return "UNKNOWN"


def _feed_group(row: Mapping[str, Any]) -> str:
    direct = _text(row.get("feed_group")).upper()
    if direct:
        return direct
    return "UNKNOWN"


def _regime(row: Mapping[str, Any]) -> str:
    direct = _text(row.get("regime")).upper()
    if direct:
        return direct
    metrics = row.get("metrics_snapshot")
    if isinstance(metrics, Mapping):
        nested = _text(metrics.get("regime")).upper()
        if nested:
            return nested
    return "UNKNOWN"


def _metric_float(row: Mapping[str, Any], key: str) -> float | None:
    direct = _safe_float(row.get(key))
    if direct is not None:
        return direct
    metrics = row.get("metrics_snapshot")
    if isinstance(metrics, Mapping):
        return _safe_float(metrics.get(key))
    return None


def _is_feed_related_reject(row: Mapping[str, Any]) -> bool:
    reason = _primary_reason(row).lower()
    if reason.startswith("feed_state_"):
        return True
    return _feed_state(row) != "OK"


def _suggestion(
    *,
    suggestion_id: str,
    text: str,
    sample_size: int,
    effect_size: float,
    sessions_count: int,
) -> dict[str, Any]:
    passed = should_emit_suggestion(sample_size, effect_size, sessions_count)
    if passed:
        suggestion_text = text
    else:
        suggestion_text = "NO SUGGESTION (insufficient confidence)"
    return {
        "id": suggestion_id,
        "text": suggestion_text,
        "sample_size": int(sample_size),
        "effect_size": float(effect_size),
        "sessions_count": int(sessions_count),
        "confidence_passed": bool(passed),
    }


def _time_of_day_bucket(ts_epoch_ms: int, is_expiry_day: bool = False) -> str:
    if is_expiry_day:
        return "EXPIRY_SPECIAL"
    local_dt = datetime.fromtimestamp(float(ts_epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST)
    local_t = local_dt.time()
    if time(9, 15) <= local_t < time(9, 30):
        return "OPEN"
    if time(9, 30) <= local_t < time(14, 30):
        return "MID"
    if time(14, 30) <= local_t <= time(15, 30):
        return "LATE"
    return "OFF_HOURS"


def _extract_outcome_payload(row: Mapping[str, Any]) -> tuple[str | None, str | None, str | None, float | None, float | None]:
    payload = row.get("trade_outcome")
    if isinstance(payload, Mapping):
        event_ref = _text(row.get("event_ref_id")) or _text(payload.get("event_ref_id")) or None
        trade_key = _text(payload.get("trade_key")) or _text(row.get("trade_key")) or None
        outcome = _normalize_outcome(payload.get("outcome"))
        mfe = _safe_float(payload.get("mfe_points") if payload.get("mfe_points") is not None else payload.get("mfe"))
        mae = _safe_float(payload.get("mae_points") if payload.get("mae_points") is not None else payload.get("mae"))
        return event_ref, trade_key, outcome, mfe, mae

    outcome = _normalize_outcome(row.get("outcome"))
    if outcome is None:
        return None, None, None, None, None
    event_ref = _text(row.get("event_ref_id")) or _text(row.get("event_id")) or None
    trade_key = _text(row.get("trade_key")) or None
    mfe = _safe_float(row.get("mfe_points") if row.get("mfe_points") is not None else row.get("mfe"))
    mae = _safe_float(row.get("mae_points") if row.get("mae_points") is not None else row.get("mae"))
    return event_ref, trade_key, outcome, mfe, mae


def _normalize_event_row(row: Mapping[str, Any]) -> dict[str, Any]:
    ts_epoch_ms = _event_ts_ms(row)
    trade_key = _text(row.get("trade_key")) or _text(row.get("event_id")) or f"unknown|{ts_epoch_ms or 0}"
    return {
        "event_id": _text(row.get("event_id")) or trade_key,
        "trade_key": trade_key,
        "intent": _intent(row),
        "symbol": _text(row.get("symbol")).upper() or "UNKNOWN",
        "ts_epoch_ms": ts_epoch_ms,
        "run_id": _text(row.get("run_id")) or "UNKNOWN_RUN",
        "gate_reasons": _extract_gate_reasons(row),
        "reject_reason": _text(row.get("reject_reason")) or None,
        "feed_state": _feed_state(row),
        "feed_group": _feed_group(row),
        "regime": _regime(row),
        "quote_age_sec": _metric_float(row, "quote_age_sec"),
        "spread_pct": _metric_float(row, "spread_pct"),
        "entry": _safe_float(row.get("entry") if row.get("entry") is not None else row.get("intended_entry")),
        "target": _safe_float(row.get("target") if row.get("target") is not None else row.get("target_price")),
        "stop": _safe_float(row.get("stop") if row.get("stop") is not None else row.get("stop_price")),
        "is_expiry_day": bool(row.get("is_expiry_day")),
        "raw": dict(row),
    }


def _infer_outcome_from_ticks(
    *,
    event_row: Mapping[str, Any],
    ticks: Sequence[Mapping[str, Any]],
    lookahead_minutes: int,
) -> tuple[str | None, float | None, float | None]:
    ts_epoch_ms = _safe_int(event_row.get("ts_epoch_ms"))
    if ts_epoch_ms is None:
        return None, None, None
    max_ts = int(ts_epoch_ms + max(1, int(lookahead_minutes)) * 60_000)
    future = [
        row
        for row in ticks
        if (_safe_int(row.get("ts_epoch_ms")) or 0) > ts_epoch_ms and (_safe_int(row.get("ts_epoch_ms")) or 0) <= max_ts
    ]
    if not future:
        return None, None, None
    result = classify_outcome_for_rejected_trade(event_row, future)
    outcome = _normalize_outcome(result.get("outcome"))
    if outcome is None:
        return None, None, None
    return outcome, _safe_float(result.get("mfe")), _safe_float(result.get("mae"))


def analyze_events(events: Sequence[Mapping[str, Any]], *, lookahead_minutes: int = 30) -> dict[str, Any]:
    trade_events: list[dict[str, Any]] = []
    ticks_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outcomes_by_event_id: dict[str, dict[str, Any]] = {}
    outcomes_by_trade_key: dict[str, dict[str, Any]] = {}

    for row in events:
        if not isinstance(row, Mapping):
            continue
        event_ref, trade_key, outcome, mfe, mae = _extract_outcome_payload(row)
        if outcome in _OUTCOME_LABELS:
            payload = {"outcome": outcome, "mfe_points": mfe, "mae_points": mae}
            if event_ref:
                outcomes_by_event_id[event_ref] = payload
            if trade_key:
                outcomes_by_trade_key[trade_key] = payload
            continue
        if _is_trade_event(row):
            trade_events.append(_normalize_event_row(row))
            continue
        if _is_tick_like(row):
            ts_epoch_ms = _event_ts_ms(row)
            symbol = _text(row.get("symbol")).upper()
            if ts_epoch_ms is None or not symbol:
                continue
            ticks_by_symbol[symbol].append(
                {
                    "symbol": symbol,
                    "ts_epoch_ms": ts_epoch_ms,
                    "ts": ts_epoch_ms,
                    "ltp": _safe_float(row.get("ltp")),
                    "bid": _safe_float(row.get("bid")),
                    "ask": _safe_float(row.get("ask")),
                    "mark_price": _safe_float(row.get("mark_price")),
                }
            )

    for rows in ticks_by_symbol.values():
        rows.sort(key=lambda item: int(item.get("ts_epoch_ms") or 0))

    for event in trade_events:
        payload = outcomes_by_event_id.get(event["event_id"]) or outcomes_by_trade_key.get(event["trade_key"])
        if payload:
            event["outcome"] = payload.get("outcome")
            event["mfe_points"] = payload.get("mfe_points")
            event["mae_points"] = payload.get("mae_points")
            continue
        direct = _normalize_outcome(event["raw"].get("outcome"))
        if direct is not None:
            event["outcome"] = direct
            event["mfe_points"] = _safe_float(event["raw"].get("mfe_points") if event["raw"].get("mfe_points") is not None else event["raw"].get("mfe"))
            event["mae_points"] = _safe_float(event["raw"].get("mae_points") if event["raw"].get("mae_points") is not None else event["raw"].get("mae"))
            continue
        if event["intent"] == "rejected":
            symbol_ticks = ticks_by_symbol.get(event["symbol"], [])
            inferred, mfe, mae = _infer_outcome_from_ticks(
                event_row=event,
                ticks=symbol_ticks,
                lookahead_minutes=lookahead_minutes,
            )
            event["outcome"] = inferred
            event["mfe_points"] = mfe
            event["mae_points"] = mae
            event["outcome_inferred"] = inferred is not None

    rejected = [row for row in trade_events if row.get("intent") == "rejected"]
    accepted = [row for row in trade_events if row.get("intent") == "accepted"]
    advisory = [row for row in trade_events if row.get("intent") == "advisory"]
    rejected_with_outcomes = [row for row in rejected if row.get("outcome") in _OUTCOME_LABELS]

    sessions_count = len({_text(row.get("run_id")) for row in trade_events if _text(row.get("run_id"))}) or 0
    reject_reason_counter = Counter(_primary_reason(row) for row in rejected)
    feed_state_counter = Counter(_feed_state(row) for row in rejected)
    feed_group_counter = Counter(_feed_group(row) for row in rejected)
    feed_block_rejects = sum(1 for row in rejected if _primary_reason(row).lower().startswith("feed_state_"))

    quote_age_values = [float(row["quote_age_sec"]) for row in trade_events if _safe_float(row.get("quote_age_sec")) is not None]
    spread_values = [float(row["spread_pct"]) for row in trade_events if _safe_float(row.get("spread_pct")) is not None]

    missed_edge_count = sum(1 for row in rejected_with_outcomes if row.get("outcome") == "hit_target")
    saved_count = sum(1 for row in rejected_with_outcomes if row.get("outcome") == "hit_sl")
    neutral_count = sum(1 for row in rejected_with_outcomes if row.get("outcome") == "no_hit")

    missed_edge_due_to_feed = sum(
        1
        for row in rejected_with_outcomes
        if row.get("outcome") == "hit_target" and _is_feed_related_reject(row)
    )
    missed_edge_due_to_other = max(0, missed_edge_count - missed_edge_due_to_feed)

    total_outcome_count = len(rejected_with_outcomes)
    baseline_hit_rate = (missed_edge_count / total_outcome_count) if total_outcome_count else 0.0
    baseline_sl_rate = (saved_count / total_outcome_count) if total_outcome_count else 0.0

    gate_stats: list[dict[str, Any]] = []
    reason_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rejected_with_outcomes:
        reason_groups[_primary_reason(row)].append(row)
    for reason, items in reason_groups.items():
        count = len(items)
        hits = sum(1 for row in items if row.get("outcome") == "hit_target")
        sls = sum(1 for row in items if row.get("outcome") == "hit_sl")
        no_hits = sum(1 for row in items if row.get("outcome") == "no_hit")
        hit_rate = (hits / count) if count else 0.0
        sl_rate = (sls / count) if count else 0.0
        gate_stats.append(
            {
                "gate_reason": reason,
                "count": count,
                "hits": hits,
                "sls": sls,
                "no_hits": no_hits,
                "hit_rate": hit_rate,
                "sl_rate": sl_rate,
                "effect_size_vs_hit_baseline": hit_rate - baseline_hit_rate,
                "effect_size_vs_sl_baseline": sl_rate - baseline_sl_rate,
            }
        )
    gate_stats.sort(key=lambda row: (-int(row["hits"]), -int(row["count"]), _text(row["gate_reason"])))

    regime_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rejected_with_outcomes:
        regime_rows[_regime(row)].append(row)
    regime_stats: list[dict[str, Any]] = []
    for regime_name, items in regime_rows.items():
        count = len(items)
        hits = sum(1 for row in items if row.get("outcome") == "hit_target")
        sls = sum(1 for row in items if row.get("outcome") == "hit_sl")
        no_hits = sum(1 for row in items if row.get("outcome") == "no_hit")
        regime_stats.append(
            {
                "regime": regime_name,
                "count": count,
                "hits": hits,
                "sls": sls,
                "no_hits": no_hits,
                "hit_rate": (hits / count) if count else 0.0,
            }
        )
    regime_stats.sort(key=lambda row: (-float(row["hit_rate"]), -int(row["count"]), _text(row["regime"])))

    bucket_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rejected_with_outcomes:
        ts = _safe_int(row.get("ts_epoch_ms"))
        if ts is None:
            continue
        bucket = _time_of_day_bucket(ts, is_expiry_day=bool(row.get("is_expiry_day")))
        bucket_rows[bucket].append(row)
    time_of_day_stats: list[dict[str, Any]] = []
    for bucket, items in bucket_rows.items():
        count = len(items)
        hits = sum(1 for row in items if row.get("outcome") == "hit_target")
        sls = sum(1 for row in items if row.get("outcome") == "hit_sl")
        no_hits = sum(1 for row in items if row.get("outcome") == "no_hit")
        time_of_day_stats.append(
            {
                "bucket": bucket,
                "count": count,
                "hits": hits,
                "sls": sls,
                "no_hits": no_hits,
                "hit_rate": (hits / count) if count else 0.0,
            }
        )
    time_of_day_stats.sort(key=lambda row: _text(row["bucket"]))

    target_rows = [
        row
        for row in rejected_with_outcomes
        if _safe_float(row.get("entry")) is not None
        and _safe_float(row.get("target")) is not None
        and _safe_float(row.get("mfe_points")) is not None
    ]
    stop_rows = [
        row
        for row in rejected_with_outcomes
        if _safe_float(row.get("entry")) is not None
        and _safe_float(row.get("stop")) is not None
        and _safe_float(row.get("mae_points")) is not None
    ]

    target_success = 0
    target_left_on_table: list[float] = []
    target_distances: list[float] = []
    for row in target_rows:
        entry = abs(float(row["entry"]))
        target = abs(float(row["target"]))
        mfe = abs(float(row["mfe_points"]))
        distance = abs(target - entry)
        target_distances.append(distance)
        if mfe >= distance:
            target_success += 1
        if mfe > distance:
            target_left_on_table.append(mfe - distance)

    stop_breaches = 0
    stop_too_tight: list[float] = []
    stop_distances: list[float] = []
    for row in stop_rows:
        entry = abs(float(row["entry"]))
        stop = abs(float(row["stop"]))
        mae = abs(float(row["mae_points"]))
        distance = abs(entry - stop)
        stop_distances.append(distance)
        if mae >= distance:
            stop_breaches += 1
            stop_too_tight.append(mae - distance)

    def _avg(values: Sequence[float]) -> float | None:
        if not values:
            return None
        return float(sum(values) / len(values))

    target_sl_metrics = {
        "target_samples": len(target_rows),
        "stop_samples": len(stop_rows),
        "pct_mfe_ge_target": (target_success / len(target_rows)) if target_rows else None,
        "pct_mae_ge_stop": (stop_breaches / len(stop_rows)) if stop_rows else None,
        "avg_left_on_table": _avg(target_left_on_table),
        "avg_too_tight": _avg(stop_too_tight),
        "avg_target_distance": _avg(target_distances),
        "avg_stop_distance": _avg(stop_distances),
    }

    sessions_by_day: Counter[str] = Counter()
    for row in trade_events:
        ts = _safe_int(row.get("ts_epoch_ms"))
        if ts is None:
            continue
        local_day = datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()
        sessions_by_day[local_day] += 1

    return {
        "trade_events": trade_events,
        "rejected": rejected,
        "accepted": accepted,
        "advisory": advisory,
        "rejected_with_outcomes": rejected_with_outcomes,
        "sessions_count": sessions_count,
        "sessions_by_day": dict(sessions_by_day),
        "rejects_by_reason": dict(reject_reason_counter.most_common(10)),
        "rejects_by_feed_state": dict(feed_state_counter),
        "rejects_by_feed_group": dict(feed_group_counter),
        "feed_block_rejects": feed_block_rejects,
        "quote_age_values": quote_age_values,
        "spread_values": spread_values,
        "missed_edge_count": missed_edge_count,
        "saved_count": saved_count,
        "neutral_count": neutral_count,
        "missed_edge_due_to_feed": missed_edge_due_to_feed,
        "missed_edge_due_to_other": missed_edge_due_to_other,
        "baseline_hit_rate": baseline_hit_rate,
        "baseline_sl_rate": baseline_sl_rate,
        "gate_stats": gate_stats,
        "regime_stats": regime_stats,
        "time_of_day_stats": time_of_day_stats,
        "target_sl_metrics": target_sl_metrics,
        "outcome_replay_missing": len(rejected_with_outcomes) == 0,
    }


def _analysis_or_build(events: Sequence[Mapping[str, Any]], analysis: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if isinstance(analysis, Mapping):
        return analysis
    return analyze_events(events)


def insight_feed_blocked_edge(
    events: Sequence[Mapping[str, Any]],
    *,
    analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    stats = _analysis_or_build(events, analysis)
    rejected_count = len(list(stats.get("rejected") or []))
    sessions_count = int(stats.get("sessions_count") or 0)
    feed_block_rejects = int(stats.get("feed_block_rejects") or 0)
    feed_groups = dict(stats.get("rejects_by_feed_group") or {})
    top_group = "UNKNOWN"
    if feed_groups:
        top_group = sorted(feed_groups.items(), key=lambda item: (-int(item[1]), item[0]))[0][0]

    missed_total = int(stats.get("missed_edge_count") or 0)
    missed_feed = int(stats.get("missed_edge_due_to_feed") or 0)
    missed_other = int(stats.get("missed_edge_due_to_other") or 0)
    rejected_with_outcomes = list(stats.get("rejected_with_outcomes") or [])

    if rejected_with_outcomes:
        feed_pct = (100.0 * missed_feed / missed_total) if missed_total else 0.0
        title = f"Feed blocked {feed_pct:.0f}% of missed winners (HIT)"
        what_happened = (
            f"Feed-related rejects missed {missed_feed} winners while non-feed gates missed {missed_other}; "
            f"{top_group} had the highest feed reject concentration."
        )
        feed_related_count = sum(1 for row in rejected_with_outcomes if _is_feed_related_reject(row))
        non_feed_count = max(0, len(rejected_with_outcomes) - feed_related_count)
        feed_hit_rate = (missed_feed / feed_related_count) if feed_related_count else 0.0
        other_hit_rate = (missed_other / non_feed_count) if non_feed_count else 0.0
        effect_size = feed_hit_rate - other_hit_rate
        sample_size = feed_related_count
    else:
        block_pct = (100.0 * feed_block_rejects / rejected_count) if rejected_count else 0.0
        title = f"Feed blocks were {block_pct:.0f}% of rejects"
        what_happened = (
            "Outcome replay missing; feed impact measured as block frequency only."
        )
        effect_size = block_pct / 100.0
        sample_size = feed_block_rejects

    action = _suggestion(
        suggestion_id="feed_quality_review",
        text=f"Prioritize feed-quality investigation for {top_group} before changing non-feed gate thresholds.",
        sample_size=sample_size,
        effect_size=effect_size,
        sessions_count=sessions_count,
    )
    return {
        "title": title,
        "what_happened": what_happened,
        "evidence": {
            "rejected_count": rejected_count,
            "feed_block_rejects": feed_block_rejects,
            "missed_edge_total": missed_total,
            "missed_edge_due_to_feed": missed_feed,
            "missed_edge_due_to_other_gates": missed_other,
            "top_feed_group": top_group,
            "outcomes_available": bool(rejected_with_outcomes),
        },
        "action": action,
    }


def insight_top_bad_gates(
    events: Sequence[Mapping[str, Any]],
    *,
    analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    stats = _analysis_or_build(events, analysis)
    sessions_count = int(stats.get("sessions_count") or 0)
    gate_stats = list(stats.get("gate_stats") or [])
    if not gate_stats:
        return {
            "title": "What blocked real edge yesterday? (insufficient data)",
            "what_happened": "No rejected trades with outcomes were available for gate ranking.",
            "evidence": {"top_gates": []},
            "action": _suggestion(
                suggestion_id="bad_gate_review",
                text="Run outcome replay first, then review net-negative gates.",
                sample_size=0,
                effect_size=0.0,
                sessions_count=sessions_count,
            ),
        }

    top = sorted(gate_stats, key=lambda row: (-int(row["hits"]), -int(row["count"])))[:3]
    leader = top[0]
    effect_size = float(leader.get("effect_size_vs_hit_baseline") or 0.0)
    title = f"{leader['gate_reason']} blocked the most winners ({leader['hits']} HIT rejects)"
    what_happened = "Top reject reasons ranked by missed winners (HIT outcomes among blocked trades)."
    action = _suggestion(
        suggestion_id="bad_gate_review",
        text=f"Audit {leader['gate_reason']} thresholds against replay outcomes before enabling config changes.",
        sample_size=int(leader.get("count") or 0),
        effect_size=effect_size,
        sessions_count=sessions_count,
    )
    return {
        "title": title,
        "what_happened": what_happened,
        "evidence": {
            "baseline_hit_rate": float(stats.get("baseline_hit_rate") or 0.0),
            "top_gates": top,
        },
        "action": action,
    }


def insight_top_protective_gates(
    events: Sequence[Mapping[str, Any]],
    *,
    analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    stats = _analysis_or_build(events, analysis)
    sessions_count = int(stats.get("sessions_count") or 0)
    gate_stats = list(stats.get("gate_stats") or [])
    if not gate_stats:
        return {
            "title": "What saved you? (insufficient data)",
            "what_happened": "No rejected trades with outcomes were available to estimate protective value.",
            "evidence": {"top_protective_gates": []},
            "action": _suggestion(
                suggestion_id="protective_gate_review",
                text="Run outcome replay first, then assess protective gates.",
                sample_size=0,
                effect_size=0.0,
                sessions_count=sessions_count,
            ),
        }

    ranked = sorted(gate_stats, key=lambda row: (-float(row["sl_rate"]), -int(row["sls"]), -int(row["count"])))[:3]
    leader = ranked[0]
    effect_size = float(leader.get("effect_size_vs_sl_baseline") or 0.0)
    title = f"{leader['gate_reason']} prevented the most likely losers ({leader['sls']} SL outcomes)"
    what_happened = "Protective gates ranked by stop-loss rate among rejected trades."
    action = _suggestion(
        suggestion_id="protective_gate_review",
        text=f"Keep {leader['gate_reason']} protective checks in place; monitor for drift before loosening.",
        sample_size=int(leader.get("count") or 0),
        effect_size=effect_size,
        sessions_count=sessions_count,
    )
    return {
        "title": title,
        "what_happened": what_happened,
        "evidence": {
            "baseline_sl_rate": float(stats.get("baseline_sl_rate") or 0.0),
            "top_protective_gates": ranked,
        },
        "action": action,
    }


def insight_regime_flip(
    events: Sequence[Mapping[str, Any]],
    *,
    analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    stats = _analysis_or_build(events, analysis)
    sessions_count = int(stats.get("sessions_count") or 0)
    regime_stats = list(stats.get("regime_stats") or [])
    if len(regime_stats) < 2:
        return {
            "title": "Regime notes (insufficient data)",
            "what_happened": "Not enough regime-labeled outcomes to compare hit-rate differences.",
            "evidence": {"regimes": regime_stats},
            "action": _suggestion(
                suggestion_id="regime_gate_review",
                text="Collect more regime-tagged sessions before making regime-specific changes.",
                sample_size=len(regime_stats),
                effect_size=0.0,
                sessions_count=sessions_count,
            ),
        }

    best = max(regime_stats, key=lambda row: float(row.get("hit_rate") or 0.0))
    worst = min(regime_stats, key=lambda row: float(row.get("hit_rate") or 0.0))
    delta = float(best.get("hit_rate") or 0.0) - float(worst.get("hit_rate") or 0.0)
    sample_size = int(best.get("count") or 0) + int(worst.get("count") or 0)
    title = f"Regime divergence: {best['regime']} beat {worst['regime']} by {delta * 100.0:.1f}pp"
    what_happened = "Hit rates vary materially by regime among rejected-trade outcomes."
    action = _suggestion(
        suggestion_id="regime_gate_review",
        text=f"Evaluate regime-specific guardrails for {worst['regime']} where edge retention is weakest.",
        sample_size=sample_size,
        effect_size=delta,
        sessions_count=sessions_count,
    )
    return {
        "title": title,
        "what_happened": what_happened,
        "evidence": {"regime_stats": regime_stats, "best_regime": best, "worst_regime": worst, "delta": delta},
        "action": action,
    }


def insight_target_sl_calibration(
    events: Sequence[Mapping[str, Any]],
    *,
    analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    stats = _analysis_or_build(events, analysis)
    sessions_count = int(stats.get("sessions_count") or 0)
    metrics = dict(stats.get("target_sl_metrics") or {})
    target_samples = int(metrics.get("target_samples") or 0)
    stop_samples = int(metrics.get("stop_samples") or 0)
    pct_mfe_ge_target = _safe_float(metrics.get("pct_mfe_ge_target"))
    pct_mae_ge_stop = _safe_float(metrics.get("pct_mae_ge_stop"))

    if target_samples <= 0 and stop_samples <= 0:
        return {
            "title": "Target/SL calibration (insufficient data)",
            "what_happened": "MFE/MAE or entry/target/stop metrics were missing for rejected outcomes.",
            "evidence": metrics,
            "action": _suggestion(
                suggestion_id="target_sl_calibration",
                text="Collect MFE/MAE telemetry before changing target or stop settings.",
                sample_size=0,
                effect_size=0.0,
                sessions_count=sessions_count,
            ),
        }

    if pct_mfe_ge_target is not None and pct_mfe_ge_target >= 0.6:
        headline = "Targets appear conservative in replayed rejects"
    elif pct_mae_ge_stop is not None and pct_mae_ge_stop >= 0.6:
        headline = "Stops appear tight in replayed rejects"
    else:
        headline = "Target/SL distances look balanced in replayed rejects"

    mfe_delta = abs((pct_mfe_ge_target or 0.0) - 0.5)
    mae_delta = abs((pct_mae_ge_stop or 0.0) - 0.5)
    effect_size = max(mfe_delta, mae_delta)
    sample_size = max(target_samples, stop_samples)
    action = _suggestion(
        suggestion_id="target_sl_calibration",
        text="Review volatility-scaled target/stop bands using replayed MFE/MAE distributions.",
        sample_size=sample_size,
        effect_size=effect_size,
        sessions_count=sessions_count,
    )
    return {
        "title": headline,
        "what_happened": "Calibration compares replayed MFE/MAE against configured target and stop distances.",
        "evidence": metrics,
        "action": action,
    }
