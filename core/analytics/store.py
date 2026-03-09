from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from config import config as cfg
from core.learning_paths import blocked_outcomes_path, rejected_candidates_paths
from core.paths import logs_dir

from .schema import (
    GateDecision,
    TradeIntentEvent,
    TradeOutcome,
    build_event_id,
    build_trade_key,
)
from .feed_context import build_feed_context

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() in {"none", "null", "nan"}:
                return None
            return float(text)
        return float(value)
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


def _normalize_option_type(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if text in {"CE", "CALL", "C"}:
        return "CE"
    if text in {"PE", "PUT", "P"}:
        return "PE"
    return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    seen = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _iter_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception as exc:
                    logger.warning("analytics_store_skip_bad_jsonl path=%s line=%s err=%s", path, lineno, exc)
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
                else:
                    logger.warning("analytics_store_skip_non_object path=%s line=%s", path, lineno)
    except Exception as exc:
        logger.warning("analytics_store_jsonl_read_failed path=%s err=%s", path, exc)
    return rows


def _read_json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("analytics_store_skip_bad_json path=%s err=%s", path, exc)
        return []
    if not isinstance(payload, list):
        logger.warning("analytics_store_skip_non_array path=%s", path)
        return []
    out = []
    for idx, item in enumerate(payload):
        if isinstance(item, dict):
            out.append(item)
        else:
            logger.warning("analytics_store_skip_non_object path=%s idx=%s", path, idx)
    return out


def _build_trade_key_from_row(row: dict) -> str:
    existing = _text(row.get("trade_key"))
    if existing:
        return existing
    symbol = row.get("symbol")
    expiry = row.get("expiry_date") or row.get("expiry")
    strike = row.get("strike")
    option_type = row.get("option_type") or row.get("type") or row.get("right")
    side = row.get("side") or row.get("direction")
    strategy_id = row.get("strategy_id") or row.get("strategy") or row.get("source")
    return build_trade_key(
        symbol=symbol,
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        side=side,
        strategy_id=strategy_id,
    )


def _event_ts_ms(row: dict) -> int | None:
    return (
        _coerce_epoch_ms(row.get("ts_epoch_ms"))
        or _coerce_epoch_ms(row.get("timestamp_epoch_ms"))
        or _coerce_epoch_ms(row.get("timestamp_epoch"))
        or _coerce_epoch_ms(row.get("ts_epoch"))
        or _coerce_epoch_ms(row.get("timestamp_utc_iso"))
        or _coerce_epoch_ms(row.get("timestamp_iso"))
        or _coerce_epoch_ms(row.get("timestamp"))
        or _coerce_epoch_ms(row.get("ts_ist"))
    )


def _default_review_queue_paths() -> list[Path]:
    base = logs_dir()
    return _unique_paths(
        [
            base / "review_queue.json",
            base / "quick_review_queue.json",
            base / "zero_hero_queue.json",
            base / "scalp_queue.json",
            base / "target_points_queue.json",
            logs_dir() / "review_queue.json",
            logs_dir() / "quick_review_queue.json",
            logs_dir() / "zero_hero_queue.json",
            logs_dir() / "scalp_queue.json",
            logs_dir() / "target_points_queue.json",
        ]
    )


def _default_decision_telemetry_paths() -> list[Path]:
    desk_dir = Path(str(getattr(cfg, "DESK_LOG_DIR", logs_dir() / "desks" / "DEFAULT")))
    reject_telemetry_dir = Path(str(getattr(cfg, "REJECT_TELEMETRY_LOG_DIR", desk_dir / "reject_telemetry")))
    paths: list[Path] = [
        desk_dir / "blocked_candidates.jsonl",
        Path(str(getattr(cfg, "DECISION_LOG_PATH", desk_dir / "decision_events.jsonl"))),
        Path(str(getattr(cfg, "REJECT_REASONS_LOG_PATH", desk_dir / "reject_reasons.jsonl"))),
        logs_dir() / "rejected_candidates.jsonl",
    ]
    try:
        paths.extend(sorted(reject_telemetry_dir.glob("rejects_*.jsonl")))
    except Exception:
        pass
    for candidate in rejected_candidates_paths():
        paths.append(candidate)
    return _unique_paths(paths)


def _int_event_from_review_row(row: dict, *, source: str) -> TradeIntentEvent | None:
    ts_ms = _event_ts_ms(row)
    symbol = _text(row.get("symbol")).upper()
    if ts_ms is None or not symbol:
        return None
    status = _text(row.get("status")).upper()
    permission = _text(row.get("permission")).upper()
    reject_reason = _text(row.get("reject_reason")) or _text(row.get("permission_reason"))

    if reject_reason or status in {"REJECTED", "BLOCKED", "INVALIDATED", "EXPIRED"} or permission == "BLOCK":
        intent = "rejected"
    elif permission in {"ADVISORY_ONLY", "QUEUE_ONLY"} or status in {"PLANNING", "PROPOSED", "REVIEW", "QUEUED_REVIEW"}:
        intent = "advisory"
    else:
        intent = "accepted"

    trade_key = _build_trade_key_from_row(row)
    event_id = build_event_id(
        trade_key=trade_key,
        event_kind=intent,
        ts_epoch_ms=ts_ms,
        source=source,
        discriminator=reject_reason,
    )
    gate_decisions = []
    if reject_reason:
        gate_decisions.append(GateDecision(gate_name="review_queue", passed=False, reason=reject_reason))
    payload = {
        "trade_key": trade_key,
        "event_id": event_id,
        "intent": intent,
        "ts_epoch_ms": int(ts_ms),
        "symbol": symbol,
        "expiry": row.get("expiry_date") or row.get("expiry"),
        "strike": _safe_float(row.get("strike")),
        "option_type": _normalize_option_type(row.get("option_type") or row.get("type") or row.get("right")),
        "side": _text(row.get("side") or row.get("direction")).upper() or None,
        "source": source,
        "reject_reason": reject_reason or None,
        "gate_decisions": [g.to_dict() for g in gate_decisions],
        "metrics_snapshot": {},
    }
    try:
        return TradeIntentEvent.from_dict(payload)
    except Exception as exc:
        logger.warning("analytics_store_skip_invalid_review_event source=%s err=%s", source, exc)
        return None


def _int_event_from_decision_row(row: dict, *, source: str) -> TradeIntentEvent | None:
    ts_ms = _event_ts_ms(row)
    symbol = _text(row.get("symbol")).upper()
    if ts_ms is None or not symbol:
        return None
    reject_reason = (
        _text(row.get("hard_reject_reason"))
        or _text(row.get("first_blocking_gate"))
        or _text(row.get("reason_code"))
        or _text(row.get("reject_reason"))
        or _text(row.get("reason"))
    )
    execution_allowed = row.get("execution_allowed")
    filled_bool = row.get("filled_bool")
    veto_reasons = _text(row.get("veto_reasons"))

    if reject_reason or execution_allowed in {0, False, "0"}:
        intent = "rejected"
    elif filled_bool in {1, True, "1", "true", "TRUE"}:
        intent = "accepted"
    else:
        intent = "advisory"

    trade_key = _build_trade_key_from_row(row)
    event_id = build_event_id(
        trade_key=trade_key,
        event_kind=intent,
        ts_epoch_ms=ts_ms,
        source=source,
        discriminator=reject_reason or veto_reasons,
    )
    gate_decisions: list[GateDecision] = []
    for gate_name, field in (
        ("gatekeeper", "gatekeeper_allowed"),
        ("risk", "risk_allowed"),
        ("exec_guard", "exec_guard_allowed"),
    ):
        if field in row:
            passed = bool(row.get(field))
            gate_decisions.append(
                GateDecision(
                    gate_name=gate_name,
                    passed=passed,
                    reason=(None if passed else (reject_reason or veto_reasons or "blocked")),
                    metrics_snapshot={},
                )
            )
    payload = {
        "trade_key": trade_key,
        "event_id": event_id,
        "intent": intent,
        "ts_epoch_ms": int(ts_ms),
        "symbol": symbol,
        "expiry": row.get("expiry_date") or row.get("expiry"),
        "strike": _safe_float(row.get("strike")),
        "option_type": _normalize_option_type(row.get("option_type") or row.get("right")),
        "side": _text(row.get("side") or row.get("direction")).upper() or None,
        "source": source,
        "reject_reason": (reject_reason or veto_reasons or None),
        "gate_decisions": [g.to_dict() for g in gate_decisions],
        "metrics_snapshot": {},
    }
    try:
        payload.update(
            build_feed_context(
                symbol=symbol,
                reject_reason=(reject_reason or veto_reasons or None),
            )
        )
    except Exception:
        pass
    try:
        return TradeIntentEvent.from_dict(payload)
    except Exception as exc:
        logger.warning("analytics_store_skip_invalid_decision_event source=%s err=%s", source, exc)
        return None


def _int_event_from_trade_row(row: dict, *, source: str) -> TradeIntentEvent | None:
    ts_ms = _event_ts_ms(row)
    symbol = _text(row.get("symbol")).upper()
    if ts_ms is None or not symbol:
        return None
    status = _text(row.get("status")).upper()
    tradable = row.get("tradable")
    blockers_raw = row.get("tradable_reasons_blocking")
    blockers_text = _text(blockers_raw)
    if blockers_text.startswith("["):
        try:
            decoded = json.loads(blockers_text)
            if isinstance(decoded, list):
                blockers_text = ",".join(str(x) for x in decoded if _text(x))
        except Exception:
            pass
    if tradable in {0, False, "0"} or blockers_text:
        intent = "rejected"
    elif status in {"ACTIVE", "FILLED", "EXECUTED", "RESOLVED"}:
        intent = "accepted"
    else:
        intent = "advisory"

    trade_key = _build_trade_key_from_row(row)
    event_id = build_event_id(
        trade_key=trade_key,
        event_kind=intent,
        ts_epoch_ms=ts_ms,
        source=source,
        discriminator=blockers_text,
    )
    payload = {
        "trade_key": trade_key,
        "event_id": event_id,
        "intent": intent,
        "ts_epoch_ms": int(ts_ms),
        "symbol": symbol,
        "expiry": row.get("expiry_date") or row.get("expiry"),
        "strike": _safe_float(row.get("strike")),
        "option_type": _normalize_option_type(row.get("option_type") or row.get("right")),
        "side": _text(row.get("side") or row.get("direction")).upper() or None,
        "source": source,
        "reject_reason": (blockers_text or None),
        "gate_decisions": [],
        "metrics_snapshot": {},
    }
    try:
        return TradeIntentEvent.from_dict(payload)
    except Exception as exc:
        logger.warning("analytics_store_skip_invalid_trade_table_event source=%s err=%s", source, exc)
        return None


def load_review_queue_events(paths: Iterable[Path] | None = None) -> list[TradeIntentEvent]:
    events: list[TradeIntentEvent] = []
    for path in _unique_paths(list(paths or _default_review_queue_paths())):
        for row in _read_json_array(path):
            event = _int_event_from_review_row(row, source=f"review_queue:{path.name}")
            if event is not None:
                events.append(event)
    events.sort(key=lambda e: e.ts_epoch_ms)
    return events


def load_decision_telemetry_events(paths: Iterable[Path] | None = None) -> list[TradeIntentEvent]:
    events: list[TradeIntentEvent] = []
    for path in _unique_paths(list(paths or _default_decision_telemetry_paths())):
        rows = _iter_jsonl(path)
        for row in rows:
            source = f"decision_telemetry:{path.name}"
            if path.name.startswith("decision_events") or "gatekeeper_allowed" in row or "execution_allowed" in row:
                event = _int_event_from_decision_row(row, source=source)
            else:
                event = _int_event_from_decision_row(row, source=source)
                if event is None:
                    event = _int_event_from_trade_row(row, source=source)
            if event is not None:
                events.append(event)
    events.sort(key=lambda e: e.ts_epoch_ms)
    return events


def _sqlite_rows(db_path: Path, table: str, limit: int) -> list[dict]:
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if cur.fetchone() is None:
                return []
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY ROWID DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("analytics_store_sqlite_read_failed table=%s path=%s err=%s", table, db_path, exc)
        return []


def load_trade_table_events(*, db_path: Path | None = None, limit: int = 2000) -> list[TradeIntentEvent]:
    events: list[TradeIntentEvent] = []
    path = db_path or Path(str(getattr(cfg, "TRADE_DB_PATH", "")))
    for row in _sqlite_rows(path, "decision_events", limit):
        event = _int_event_from_decision_row(row, source="trade_table:decision_events")
        if event is not None:
            events.append(event)
    for row in _sqlite_rows(path, "trades", limit):
        event = _int_event_from_trade_row(row, source="trade_table:trades")
        if event is not None:
            events.append(event)
    events.sort(key=lambda e: e.ts_epoch_ms)
    return events


def load_trade_intent_events(
    *,
    review_queue_paths: Iterable[Path] | None = None,
    decision_telemetry_paths: Iterable[Path] | None = None,
    db_path: Path | None = None,
    limit: int = 5000,
) -> list[TradeIntentEvent]:
    merged: list[TradeIntentEvent] = []
    merged.extend(load_review_queue_events(paths=review_queue_paths))
    merged.extend(load_decision_telemetry_events(paths=decision_telemetry_paths))
    merged.extend(load_trade_table_events(db_path=db_path, limit=limit))
    out: list[TradeIntentEvent] = []
    seen = set()
    for event in sorted(merged, key=lambda e: e.ts_epoch_ms):
        if event.event_id in seen:
            continue
        seen.add(event.event_id)
        out.append(event)
    return out


def _default_outcome_paths() -> list[Path]:
    return _unique_paths(
        [
            Path(str(getattr(cfg, "REJECT_OUTCOMES_LOG_PATH", logs_dir() / "rejected_trade_outcomes.jsonl"))),
            blocked_outcomes_path(),
            logs_dir() / "rejected_trade_outcomes.jsonl",
            logs_dir() / "blocked_outcomes.jsonl",
        ]
    )


def _normalize_outcome_label(value: Any) -> str:
    text = _text(value).lower()
    mapping = {
        "hit_target": "hit_target",
        "target_hit": "hit_target",
        "target": "hit_target",
        "hit_sl": "hit_sl",
        "stop_hit": "hit_sl",
        "stop": "hit_sl",
        "sl_hit": "hit_sl",
        "no_hit": "no_hit",
        "timeout": "no_hit",
        "none": "no_hit",
        "": "no_hit",
    }
    return mapping.get(text, "no_hit")


def _trade_outcome_from_row(row: dict, *, source: str) -> TradeOutcome | None:
    symbol = _text(row.get("symbol")).upper()
    if not symbol:
        return None
    trade_key = _build_trade_key_from_row(row)
    ts_ms = (
        _coerce_epoch_ms(row.get("resolved_ts_epoch_ms"))
        or _coerce_epoch_ms(row.get("reject_ts_epoch_ms"))
        or _coerce_epoch_ms(row.get("analyzed_ts_epoch"))
        or _event_ts_ms(row)
    )
    if ts_ms is None:
        return None
    outcome = _normalize_outcome_label(row.get("outcome"))
    outcome_reason = _text(row.get("outcome_reason")).upper()
    has_candles = outcome_reason not in {"NO_CANDLES", "NO_CANDLES_IN_WINDOW", "NO_SERIES_DATA"} and not outcome_reason.startswith(
        "SERIES_LOAD_ERROR"
    )
    ambiguous = outcome_reason == "AMBIGUOUS_SAME_CANDLE"
    exec_feasible = bool(row.get("exec_feasible")) if row.get("exec_feasible") is not None else bool(has_candles and not ambiguous)
    flags = {
        "has_candle_data": bool(has_candles),
        "has_series_data": bool(has_candles),
        "ambiguous_intrabar": bool(ambiguous),
    }
    if isinstance(row.get("exec_feasible_flags"), dict):
        for k, v in row.get("exec_feasible_flags", {}).items():
            key = str(k)
            if key == "series_source":
                continue
            flags[key] = v
    reject_reason = _text(row.get("primary_reject_reason") or row.get("reject_reason") or row.get("reason")) or None
    reject_reasons: list[str] = []
    raw_reject_reasons = row.get("reject_reasons")
    if isinstance(raw_reject_reasons, (list, tuple)):
        for reason in raw_reject_reasons:
            text = _text(reason)
            if text and text not in reject_reasons:
                reject_reasons.append(text)
    raw_reason_codes = row.get("reason_codes")
    if isinstance(raw_reason_codes, (list, tuple)):
        for reason in raw_reason_codes:
            text = _text(reason)
            if text and text not in reject_reasons:
                reject_reasons.append(text)
    if reject_reason and reject_reason not in reject_reasons:
        reject_reasons = [reject_reason] + reject_reasons
    if not has_candles:
        reject_reason = "NO_SERIES_DATA"
        reject_reasons = ["NO_SERIES_DATA"]
    elif not reject_reason and reject_reasons:
        reject_reason = reject_reasons[0]
    event_id = _text(row.get("event_id"))
    if not event_id:
        event_id = build_event_id(
            trade_key=trade_key,
            event_kind="outcome",
            ts_epoch_ms=ts_ms,
            source=source,
            discriminator=f"{outcome}|{_text(row.get('reject_reason') or row.get('reason'))}",
        )
    payload = {
        "trade_key": trade_key,
        "event_id": event_id,
        "outcome": outcome,
        "ts_epoch_ms": int(ts_ms),
        "symbol": symbol,
        "mfe_points": _safe_float(row.get("mfe_points") if row.get("mfe_points") is not None else row.get("mfe")),
        "mae_points": _safe_float(row.get("mae_points") if row.get("mae_points") is not None else row.get("mae")),
        "exec_feasible": exec_feasible,
        "exec_feasible_flags": flags,
        "source": source,
        "reject_reason": reject_reason,
        "reject_reasons": reject_reasons,
        "primary_reject_reason": reject_reason,
    }
    try:
        return TradeOutcome.from_dict(payload)
    except Exception as exc:
        logger.warning("analytics_store_skip_invalid_outcome source=%s err=%s", source, exc)
        return None


def load_outcome_files(paths: Iterable[Path] | None = None) -> list[TradeOutcome]:
    outcomes: list[TradeOutcome] = []
    for path in _unique_paths(list(paths or _default_outcome_paths())):
        for row in _iter_jsonl(path):
            outcome = _trade_outcome_from_row(row, source=f"outcome_file:{path.name}")
            if outcome is not None:
                outcomes.append(outcome)
    outcomes.sort(key=lambda o: o.ts_epoch_ms)
    return outcomes


def load_outcomes_from_trade_tables(*, db_path: Path | None = None, limit: int = 2000) -> list[TradeOutcome]:
    outcomes: list[TradeOutcome] = []
    path = db_path or Path(str(getattr(cfg, "TRADE_DB_PATH", "")))
    for row in _sqlite_rows(path, "outcomes", limit):
        normalized = dict(row)
        symbol = _text(normalized.get("symbol"))
        if not symbol:
            # outcomes table may omit symbol; use trade_id as stable fallback identity key.
            symbol = _text(normalized.get("trade_id")) or "UNKNOWN"
            normalized["symbol"] = symbol
        if not normalized.get("outcome"):
            exit_reason = _text(normalized.get("exit_reason")).upper()
            if "TARGET" in exit_reason:
                normalized["outcome"] = "hit_target"
            elif "STOP" in exit_reason:
                normalized["outcome"] = "hit_sl"
            else:
                normalized["outcome"] = "no_hit"
        outcome = _trade_outcome_from_row(normalized, source="trade_table:outcomes")
        if outcome is not None:
            outcomes.append(outcome)
    outcomes.sort(key=lambda o: o.ts_epoch_ms)
    return outcomes


def load_trade_outcomes(
    *,
    outcome_paths: Iterable[Path] | None = None,
    db_path: Path | None = None,
    limit: int = 5000,
) -> list[TradeOutcome]:
    merged = load_outcome_files(paths=outcome_paths)
    merged.extend(load_outcomes_from_trade_tables(db_path=db_path, limit=limit))
    out: list[TradeOutcome] = []
    seen = set()
    for row in sorted(merged, key=lambda o: o.ts_epoch_ms):
        if row.event_id in seen:
            continue
        seen.add(row.event_id)
        out.append(row)
    return out
