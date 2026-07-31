"""Reject-shadow evaluation and candidate decision telemetry.

Migration note:
- Adds `rejected_trades_shadow` (idempotent shadow outcomes for blocked/non-executable candidates).
- Adds `candidate_decision_events` and `price_trace` support for deterministic replay.
- Provides CLI: `python -m core.reject_shadow --mode evaluate --date YYYY-MM-DD`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any
from zoneinfo import ZoneInfo
from collections import defaultdict

from core.audit_log import append_event
from core.persistence_state_compression import should_write_persistent_state, record_written_state
from config import config as cfg
from core.runtime_paths import DB_ROOT, LOGS_ROOT
from core.time_utils import now_utc_epoch


IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
    except Exception:
        return default
    if out != out:  # NaN
        return default
    return out


def _safe_json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return [str(x) for x in decoded if str(x)]
        except Exception:
            return [value] if value else []
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value if str(x)]
    return []


def _telemetry_value(payload: dict[str, Any], field: str, default: Any = None) -> Any:
    value = payload.get(field)
    if value is None:
        for nested_key in ("score_inputs_used", "score_breakdown", "source_flags", "decision_trace"):
            nested = payload.get(nested_key)
            if isinstance(nested, dict) and field in nested:
                value = nested.get(field)
                break
    if value is None:
        for nested_key in ("score_inputs_used", "score_breakdown", "source_flags", "decision_trace", "quality_detail"):
            nested = payload.get(nested_key)
            if isinstance(nested, dict) and field in nested:
                value = nested.get(field)
                break
    if value is None:
        for nested_key in ("score_inputs_used", "score_breakdown", "source_flags", "decision_trace"):
            nested = payload.get(nested_key)
            if isinstance(nested, dict):
                qd = nested.get("quality_detail")
                if isinstance(qd, dict) and field in qd:
                    value = qd.get(field)
                    break
    if value is None and field == "raw_rank_score":
        for fallback_field in ("ranking_score", "rank_score"):
            value = payload.get(fallback_field)
            if value is None:
                for nested_key in ("score_inputs_used", "score_breakdown", "source_flags", "decision_trace"):
                    nested = payload.get(nested_key)
                    if isinstance(nested, dict) and fallback_field in nested:
                        value = nested.get(fallback_field)
                        break
            if value is not None:
                break
    return default if value is None else value


def _quote_freshness_state(*, quote_validation_status: Any, quote_age_sec: Any) -> str | None:
    status = str(quote_validation_status or "").strip().upper()
    age = _safe_float(quote_age_sec)
    max_age = _safe_float(getattr(cfg, "MAX_OPTION_QUOTE_AGE_SEC", 8.0))
    if max_age is None or max_age <= 0:
        max_age = 8.0
    if status in {"STALE_OPTION_LTP", "NO_LIVE_OPTION_FEED", "MISSING_OPTION_TOKEN"}:
        return "stale"
    if age is None:
        return "unknown"
    return "fresh" if float(age) <= float(max_age) else "stale"


def _setup_score_telemetry(payload: dict[str, Any]) -> tuple[float | None, float | None, str | None]:
    native_setup_score = _safe_float(_telemetry_value(payload, "setup_score"))
    quality_detail = _telemetry_block(payload, "quality_detail")
    setup_values = [
        float(value)
        for value in (
            quality_detail.get("setup_regime_alignment_score"),
            quality_detail.get("setup_structure_score"),
            quality_detail.get("setup_thesis_score"),
        )
        if isinstance(value, (int, float))
    ]
    quality_detail_source = str(payload.get("quality_detail_source") or "").strip() or ""
    if (
        not bool(getattr(cfg, "CANDIDATE_DECISION_SETUP_SCORE_DERIVE_FROM_PROXY_ENABLE", True))
        or not setup_values
    ):
        return native_setup_score, native_setup_score, (quality_detail_source or "native")
    derived_setup_score = round(sum(setup_values) / float(len(setup_values)), 6)
    if quality_detail_source and quality_detail_source != "native":
        return native_setup_score, derived_setup_score, quality_detail_source
    if native_setup_score is None:
        return native_setup_score, derived_setup_score, "derived_from_setup_proxies"
    return native_setup_score, native_setup_score, "native"


def _telemetry_block(payload: dict[str, Any], field: str) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    direct = payload.get(field)
    if isinstance(direct, dict):
        merged.update(direct)
    for nested_key in ("score_inputs_used", "score_breakdown", "source_flags", "decision_trace"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            nested_value = nested.get(field)
            if isinstance(nested_value, dict):
                merged.update(nested_value)
    return merged


def _mode_key(raw_mode: Any | None = None) -> str:
    mode = str(raw_mode or getattr(cfg, "EXECUTION_MODE", getattr(cfg, "TRADING_MODE", "SIM"))).strip().upper()
    if mode in {"LIVE", "PAPER", "SIM", "OFFHOURS"}:
        return mode
    return "SIM"


def _desk_id(raw: Any | None = None) -> str:
    text = str(raw or getattr(cfg, "DESK_ID", "DEFAULT")).strip()
    return text or "DEFAULT"


def _primary_db_path(desk: str) -> Path:
    explicit = str(getattr(cfg, "TRADE_DB_PATH", "")).strip()
    if explicit:
        return Path(explicit)
    return Path(DB_ROOT) / f"{desk}.sqlite"


def _fallback_db_path(desk: str) -> Path:
    safe_desk = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in str(desk)
    ) or "DEFAULT"
    uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
    return Path(tempfile.gettempdir()) / f"tradebot_shadow_{uid}" / f"{safe_desk}.sqlite"


def _connect_db(desk: str) -> tuple[sqlite3.Connection, Path, str | None]:
    warning = None
    primary = _primary_db_path(desk)
    for path in (primary, _fallback_db_path(desk)):
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(path.parent, 0o700)
            conn = sqlite3.connect(path)
            if path != Path(":memory:"):
                os.chmod(path, 0o600)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=3000")
            if path != primary:
                warning = "primary_db_readonly_or_unwritable"
            return conn, path, warning
        except (OSError, sqlite3.Error):
            continue
    # Final fallback in-memory (degraded but non-crashing).
    conn = sqlite3.connect(":memory:")
    warning = "all_shadow_db_paths_unavailable"
    return conn, Path(":memory:"), warning


def _candidate_id(*, ts_epoch: float, symbol: str, side: str, entry: float, stop: float, target: float) -> str:
    bucket_sec = max(1, int(getattr(cfg, "REJECT_SHADOW_CANDIDATE_BUCKET_SEC", 30)))
    ts_bucket = int(float(ts_epoch) // bucket_sec)
    key = f"{ts_bucket}|{symbol}|{side}|{entry:.4f}|{stop:.4f}|{target:.4f}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return f"cand_{digest}"


def _decision_log_path(desk: str) -> Path:
    base = Path(LOGS_ROOT) / "desks" / desk
    return base / "candidate_decisions.jsonl"


def _price_trace_log_path(desk: str) -> Path:
    base = Path(LOGS_ROOT) / "desks" / desk
    return base / "price_trace.jsonl"


def _trade_date(ts_epoch: float) -> str:
    return datetime.fromtimestamp(float(ts_epoch), tz=IST).date().isoformat()


def _resolve_levels(
    *,
    side: str,
    entry: Any,
    stop: Any,
    target: Any,
    ltp: Any,
    atr: Any,
) -> tuple[float | None, float | None, float | None, bool]:
    side_norm = str(side or "BUY_CALL").upper()
    entry_f = _safe_float(entry)
    if entry_f is None:
        entry_f = _safe_float(ltp)
    if entry_f is None:
        return None, None, None, False
    stop_f = _safe_float(stop)
    target_f = _safe_float(target)
    derived = False
    atr_f = _safe_float(atr, default=entry_f * 0.01) or max(0.01, entry_f * 0.01)
    risk = max(0.01, atr_f)
    rr = float(getattr(cfg, "REJECT_SHADOW_DEFAULT_RR", 1.5))

    long_side = side_norm in {"BUY", "BUY_CALL", "LONG"}
    if stop_f is None:
        stop_f = entry_f - risk if long_side else entry_f + risk
        derived = True
    if target_f is None:
        target_f = entry_f + (risk * rr) if long_side else entry_f - (risk * rr)
        derived = True
    return float(entry_f), float(stop_f), float(target_f), bool(derived)


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rejected_trades_shadow (
            candidate_id TEXT PRIMARY KEY,
            ts REAL NOT NULL,
            trade_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry REAL NOT NULL,
            stop REAL NOT NULL,
            target REAL NOT NULL,
            regime TEXT,
            confidence_score REAL,
            gates_failed TEXT,
            soft_vetos TEXT,
            first_blocking_gate TEXT,
            shadow_status TEXT NOT NULL DEFAULT 'PENDING',
            mfe REAL,
            mae REAL,
            best_rr REAL,
            resolved_ts REAL,
            expiry TEXT,
            mode TEXT,
            instrument_id TEXT,
            derived_levels INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gate_quality_daily (
            trade_date TEXT NOT NULL,
            gate_name TEXT NOT NULL,
            rejected_count INTEGER NOT NULL,
            win_count INTEGER NOT NULL,
            loss_count INTEGER NOT NULL,
            timeout_count INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            avg_mfe REAL,
            avg_best_rr REAL,
            missed_expectancy REAL NOT NULL,
            verdict TEXT NOT NULL,
            first_blocking_only INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (trade_date, gate_name, first_blocking_only)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_decision_events (
            candidate_id TEXT PRIMARY KEY,
            ts REAL NOT NULL,
            trade_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            mode TEXT NOT NULL,
            execution_allowed INTEGER NOT NULL,
            hard_reject_reason TEXT,
            first_blocking_gate TEXT,
            gates_failed TEXT,
            soft_vetos TEXT,
            initial_score REAL,
            final_score REAL,
            score_penalties TEXT,
            confidence_score REAL,
            entry REAL,
            stop REAL,
            target REAL,
            regime TEXT,
            instrument_id TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_trace (
            ts REAL NOT NULL,
            symbol TEXT NOT NULL,
            price REAL NOT NULL,
            mode TEXT,
            instrument_id TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rts_trade_date ON rejected_trades_shadow(trade_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rts_status ON rejected_trades_shadow(shadow_status, trade_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rts_gate ON rejected_trades_shadow(first_blocking_gate, trade_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_price_trace_symbol_ts ON price_trace(symbol, ts)")


def record_price_trace(
    *,
    symbol: str,
    price: Any,
    ts_epoch: Any | None = None,
    mode: str | None = None,
    instrument_id: str | None = None,
    desk: str | None = None,
) -> None:
    sym = str(symbol or "").strip().upper()
    px = _safe_float(price)
    if not sym or px is None or px <= 0:
        return
    ts = _safe_float(ts_epoch, default=now_utc_epoch()) or now_utc_epoch()
    mode_key = _mode_key(mode)
    desk_id = _desk_id(desk)

    rec = {
        "ts_epoch": float(ts),
        "ts_ist": datetime.fromtimestamp(float(ts), tz=IST).isoformat(),
        "symbol": sym,
        "price": float(px),
        "mode": mode_key,
        "instrument_id": instrument_id,
    }
    try:
        path = _price_trace_log_path(desk_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(rec, ensure_ascii=True) + "\n")
    except Exception:
        pass
    try:
        conn, _, _ = _connect_db(desk_id)
        with conn:
            ensure_tables(conn)
            conn.execute(
                "INSERT INTO price_trace(ts, symbol, price, mode, instrument_id) VALUES(?,?,?,?,?)",
                (float(ts), sym, float(px), mode_key, instrument_id),
            )
        conn.close()
    except Exception:
        pass


def record_candidate_decision(event: dict, *, desk: str | None = None) -> dict:
    if not isinstance(event, dict):
        return {}

    """Persist candidate decision trace and, when blocked/non-executable, shadow row."""
    payload = dict(event or {})
    hard_reason = str(payload.get("hard_reject_reason") or "").strip().lower()
    first_gate = str(payload.get("first_blocking_gate") or "").strip().lower()
    if hard_reason == "unresolved_contract" or first_gate == "unresolved_contract":
        return {"status": "skipped", "reason": "unresolved_contract"}
    desk_id = _desk_id(desk)
    ts = _safe_float(payload.get("ts_epoch"), default=now_utc_epoch()) or now_utc_epoch()
    symbol = str(payload.get("symbol") or "").strip().upper() or "UNKNOWN"
    side = str(payload.get("side") or payload.get("direction") or "BUY_CALL").strip().upper()
    entry, stop, target, derived = _resolve_levels(
        side=side,
        entry=payload.get("entry"),
        stop=payload.get("stop"),
        target=payload.get("target"),
        ltp=payload.get("ltp"),
        atr=payload.get("atr"),
    )
    if entry is None or stop is None or target is None:
        return {"status": "skipped", "reason": "missing_price_levels"}
    candidate_id = str(payload.get("candidate_id") or _candidate_id(ts_epoch=ts, symbol=symbol, side=side, entry=entry, stop=stop, target=target))
    mode = _mode_key(payload.get("mode"))
    gates_failed = _safe_json_list(payload.get("gates_failed"))
    soft_vetos = _safe_json_list(payload.get("soft_vetos"))
    hard_reject_reason = str(payload.get("hard_reject_reason") or "").strip() or None
    first_blocking_gate = (
        str(payload.get("first_blocking_gate") or "").strip()
        or hard_reject_reason
        or (gates_failed[0] if gates_failed else (soft_vetos[0] if soft_vetos else None))
    )
    exec_allowed = bool(payload.get("execution_allowed", False))
    trade_date = _trade_date(ts)
    native_setup_score, derived_setup_score, setup_score_source = _setup_score_telemetry(payload)
    quote_truth_block = _telemetry_block(payload, "quote_truth")
    quote_truth_snapshot_block = _telemetry_block(payload, "quote_truth_snapshot")

    decision_event = {
        "candidate_id": candidate_id,
        "ts_epoch": float(ts),
        "ts_ist": datetime.fromtimestamp(float(ts), tz=IST).isoformat(),
        "trade_date": trade_date,
        "symbol": symbol,
        "side": side,
        "mode": mode,
        "execution_allowed": bool(exec_allowed),
        "hard_reject_reason": hard_reject_reason,
        "first_blocking_gate": first_blocking_gate,
        "gates_failed": list(gates_failed),
        "soft_vetos": list(soft_vetos),
        "initial_score": _safe_float(payload.get("initial_score")),
        "final_score": _safe_float(payload.get("final_score")),
        "score_penalties": payload.get("score_penalties") if isinstance(payload.get("score_penalties"), (list, tuple, dict)) else [],
        "confidence_score": _safe_float(payload.get("confidence_score"), default=_safe_float(payload.get("confidence"))),
        "entry": float(entry),
        "stop": float(stop),
        "target": float(target),
        "regime": str(payload.get("regime") or ""),
        "signal_score": _safe_float(payload.get("signal_score")),
        "regime_conf": _safe_float(payload.get("regime_conf")),
        "orb_bias": payload.get("orb_bias"),
        "orb_factor": _safe_float(payload.get("orb_factor")),
        "reg_penalty": _safe_float(payload.get("reg_penalty")),
        "global_conf": _safe_float(payload.get("global_conf")),
        "source_flags": payload.get("source_flags") if isinstance(payload.get("source_flags"), dict) else {},
        "score_breakdown": payload.get("score_breakdown") if isinstance(payload.get("score_breakdown"), dict) else {},
        "decision_trace": payload.get("decision_trace") if isinstance(payload.get("decision_trace"), dict) else {},
        "quality_detail": _telemetry_block(payload, "quality_detail"),
        "quality_detail_source": str(payload.get("quality_detail_source") or "").strip() or None,
        "candidate_quality_score": _safe_float(_telemetry_value(payload, "candidate_quality_score")),
        "family_consensus_score": _safe_float(_telemetry_value(payload, "family_consensus_score")),
        "family_consensus_components": _telemetry_value(payload, "family_consensus_components", {}),
        "family_survival_score": _safe_float(_telemetry_value(payload, "family_survival_score")),
        "family_survival_components": _telemetry_value(payload, "family_survival_components", {}),
        "liquidity_score": _safe_float(_telemetry_value(payload, "liquidity_score")),
        "quote_consistency_score": _safe_float(_telemetry_value(payload, "quote_consistency_score")),
        "quote_validation_status": str(_telemetry_value(payload, "quote_validation_status") or "").strip() or None,
        "quote_age_sec": _safe_float(_telemetry_value(payload, "quote_age_sec")),
        "quote_truth_source": str(
            _telemetry_value(payload, "quote_truth_source")
            or quote_truth_block.get("quote_source")
            or quote_truth_snapshot_block.get("quote_source")
            or (payload.get("source_flags") or {}).get("ltp_source")
            or payload.get("quote_source")
            or "live"
        ).strip() or None,
        "quote_freshness_state": _quote_freshness_state(
            quote_validation_status=_telemetry_value(payload, "quote_validation_status"),
            quote_age_sec=_telemetry_value(payload, "quote_age_sec"),
        ),
        "liquidity_flow_score": _safe_float(_telemetry_value(payload, "liquidity_flow_score")),
        "liquidity_book_score": _safe_float(_telemetry_value(payload, "liquidity_book_score")),
        "liquidity_spread_score": _safe_float(_telemetry_value(payload, "liquidity_spread_score")),
        "liquidity_volume_score": _safe_float(_telemetry_value(payload, "liquidity_volume_score")),
        "liquidity_oi_score": _safe_float(_telemetry_value(payload, "liquidity_oi_score")),
        "native_setup_score": native_setup_score,
        "setup_score": derived_setup_score,
        "setup_score_source": setup_score_source,
        "setup_regime_alignment_score": _safe_float(_telemetry_value(payload, "setup_regime_alignment_score")),
        "setup_structure_score": _safe_float(_telemetry_value(payload, "setup_structure_score")),
        "setup_thesis_score": _safe_float(_telemetry_value(payload, "setup_thesis_score")),
        "trigger_score": _safe_float(_telemetry_value(payload, "trigger_score")),
        "trigger_base_score": _safe_float(_telemetry_value(payload, "trigger_base_score")),
        "entry_quality_score": _safe_float(_telemetry_value(payload, "entry_quality_score")),
        "entry_invalidation_score": _safe_float(_telemetry_value(payload, "entry_invalidation_score")),
        "entry_overextension_score": _safe_float(_telemetry_value(payload, "entry_overextension_score")),
        "entry_timing_quality_score": _safe_float(_telemetry_value(payload, "entry_timing_quality_score")),
        "execution_quality_score": _safe_float(_telemetry_value(payload, "execution_quality_score")),
        "rank_score": _safe_float(_telemetry_value(payload, "rank_score")),
        "raw_rank_score": _safe_float(_telemetry_value(payload, "raw_rank_score")),
        "terminal_rank_score": _safe_float(_telemetry_value(payload, "terminal_rank_score")),
        "opportunity_score": _safe_float(_telemetry_value(payload, "opportunity_score")),
        "permission": payload.get("permission"),
        "permission_reason": payload.get("permission_reason"),
        "entry_status": payload.get("entry_status"),
        "entry_block_reason": payload.get("entry_block_reason"),
        "final_action": payload.get("final_action"),
        "instrument_id": payload.get("instrument_id"),
        "derived_levels": bool(derived),
        "status": str(payload.get("candidate_status") or "rejected"),
    }

    # JSONL trace for quick operator inspection.
    try:
        path = _decision_log_path(desk_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision_event, ensure_ascii=True) + "\n")
    except Exception:
        pass

    if not should_write_persistent_state(payload, "candidate_decision_events"):
        return {
            "status": "ok",
            "candidate_id": candidate_id,
            "db_path": "",
            "warning": "skipped by persistence compression",
        }

    record_written_state(payload, "candidate_decision_events")

    conn, db_path, warning = _connect_db(desk_id)
    with conn:
        ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO candidate_decision_events(
                candidate_id, ts, trade_date, symbol, side, mode, execution_allowed,
                hard_reject_reason, first_blocking_gate, gates_failed, soft_vetos,
                initial_score, final_score, score_penalties, confidence_score,
                entry, stop, target, regime, instrument_id
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                ts=excluded.ts,
                trade_date=excluded.trade_date,
                symbol=excluded.symbol,
                side=excluded.side,
                mode=excluded.mode,
                execution_allowed=excluded.execution_allowed,
                hard_reject_reason=excluded.hard_reject_reason,
                first_blocking_gate=excluded.first_blocking_gate,
                gates_failed=excluded.gates_failed,
                soft_vetos=excluded.soft_vetos,
                initial_score=excluded.initial_score,
                final_score=excluded.final_score,
                score_penalties=excluded.score_penalties,
                confidence_score=excluded.confidence_score,
                entry=excluded.entry,
                stop=excluded.stop,
                target=excluded.target,
                regime=excluded.regime,
                instrument_id=excluded.instrument_id
            """,
            (
                candidate_id,
                float(ts),
                trade_date,
                symbol,
                side,
                mode,
                1 if exec_allowed else 0,
                hard_reject_reason,
                first_blocking_gate,
                json.dumps(gates_failed, ensure_ascii=True),
                json.dumps(soft_vetos, ensure_ascii=True),
                decision_event["initial_score"],
                decision_event["final_score"],
                json.dumps(decision_event["score_penalties"], ensure_ascii=True),
                decision_event["confidence_score"],
                float(entry),
                float(stop),
                float(target),
                decision_event["regime"],
                decision_event["instrument_id"],
            ),
        )

        should_shadow = bool((not exec_allowed) or hard_reject_reason)
        if should_shadow:
            conn.execute(
                """
                INSERT INTO rejected_trades_shadow(
                    candidate_id, ts, trade_date, symbol, side, entry, stop, target,
                    regime, confidence_score, gates_failed, soft_vetos, first_blocking_gate,
                    shadow_status, expiry, mode, instrument_id, derived_levels
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'PENDING',?,?,?,?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    ts=excluded.ts,
                    trade_date=excluded.trade_date,
                    symbol=excluded.symbol,
                    side=excluded.side,
                    entry=excluded.entry,
                    stop=excluded.stop,
                    target=excluded.target,
                    regime=excluded.regime,
                    confidence_score=excluded.confidence_score,
                    gates_failed=excluded.gates_failed,
                    soft_vetos=excluded.soft_vetos,
                    first_blocking_gate=excluded.first_blocking_gate,
                    mode=excluded.mode,
                    instrument_id=excluded.instrument_id,
                    derived_levels=excluded.derived_levels
                """,
                (
                    candidate_id,
                    float(ts),
                    trade_date,
                    symbol,
                    side,
                    float(entry),
                    float(stop),
                    float(target),
                    decision_event["regime"],
                    decision_event["confidence_score"],
                    json.dumps(gates_failed, ensure_ascii=True),
                    json.dumps(soft_vetos, ensure_ascii=True),
                    first_blocking_gate,
                    str(payload.get("expiry") or ""),
                    mode,
                    decision_event["instrument_id"],
                    1 if derived else 0,
                ),
            )
    conn.close()
    return {
        "status": "ok",
        "candidate_id": candidate_id,
        "db_path": str(db_path),
        "warning": warning,
    }


@dataclass(frozen=True)
class _ShadowRow:
    candidate_id: str
    ts: float
    symbol: str
    side: str
    entry: float
    stop: float
    target: float
    first_blocking_gate: str | None
    mode: str


def _price_path(conn: sqlite3.Connection, *, symbol: str, start_ts: float, end_ts: float) -> list[tuple[float, float]]:
    rows = conn.execute(
        """
        SELECT ts, price
        FROM price_trace
        WHERE symbol = ?
          AND ts >= ?
          AND ts <= ?
        ORDER BY ts ASC
        """,
        (str(symbol).upper(), float(start_ts), float(end_ts)),
    ).fetchall()
    points: list[tuple[float, float]] = []
    for ts, px in rows:
        ts_f = _safe_float(ts)
        px_f = _safe_float(px)
        if ts_f is None or px_f is None:
            continue
        points.append((float(ts_f), float(px_f)))
    return points


def _resolve_status(row: _ShadowRow, points: list[tuple[float, float]], *, end_ts: float, now_ts: float) -> tuple[str, float | None, float | None, float | None, float | None]:
    risk = max(0.01, abs(float(row.entry) - float(row.stop)))
    side = str(row.side).upper()
    long_side = side in {"BUY", "BUY_CALL", "LONG"}

    pnl_points: list[float] = []
    status = "PENDING"
    hit_ts = None
    for ts, px in points:
        pnl = (float(px) - float(row.entry)) if long_side else (float(row.entry) - float(px))
        pnl_points.append(float(pnl))
        if long_side:
            if float(px) >= float(row.target):
                status = "WIN"
                hit_ts = float(ts)
                break
            if float(px) <= float(row.stop):
                status = "LOSS"
                hit_ts = float(ts)
                break
        else:
            if float(px) <= float(row.target):
                status = "WIN"
                hit_ts = float(ts)
                break
            if float(px) >= float(row.stop):
                status = "LOSS"
                hit_ts = float(ts)
                break
    if status == "PENDING" and now_ts >= end_ts:
        status = "TIMEOUT"
        hit_ts = float(end_ts)

    mfe = max(pnl_points) if pnl_points else None
    mae = min(pnl_points) if pnl_points else None
    best_rr = (mfe / risk) if mfe is not None else None
    return status, mfe, mae, best_rr, hit_ts


def _day_bounds_ist(day_text: str) -> tuple[float, float]:
    day = datetime.fromisoformat(day_text).date()
    start_dt = datetime.combine(day, dtime(0, 0), tzinfo=IST)
    end_dt = datetime.combine(day, dtime(23, 59, 59), tzinfo=IST)
    return float(start_dt.timestamp()), float(end_dt.timestamp())


def evaluate_pending(*, date: str, desk: str | None = None, batch_limit: int | None = None) -> dict:
    desk_id = _desk_id(desk)
    timeout_min = max(1, int(getattr(cfg, "REJECT_SHADOW_TIMEOUT_MIN", 30)))
    batch = max(1, int(batch_limit or getattr(cfg, "REJECT_SHADOW_BATCH_LIMIT", 5000)))
    now_ts = float(now_utc_epoch())
    _day_start, day_end = _day_bounds_ist(date)

    conn, db_path, warning = _connect_db(desk_id)
    processed = 0
    resolved = {"WIN": 0, "LOSS": 0, "TIMEOUT": 0, "PENDING": 0}
    with conn:
        ensure_tables(conn)
        rows = conn.execute(
            """
            SELECT candidate_id, ts, symbol, side, entry, stop, target, first_blocking_gate, mode
            FROM rejected_trades_shadow
            WHERE trade_date = ?
              AND shadow_status = 'PENDING'
            ORDER BY ts ASC
            LIMIT ?
            """,
            (str(date), int(batch)),
        ).fetchall()
        for candidate_id, ts, symbol, side, entry, stop, target, first_blocking_gate, mode in rows:
            ts_f = _safe_float(ts)
            entry_f = _safe_float(entry)
            stop_f = _safe_float(stop)
            target_f = _safe_float(target)
            if ts_f is None or entry_f is None or stop_f is None or target_f is None:
                continue
            row = _ShadowRow(
                candidate_id=str(candidate_id),
                ts=float(ts_f),
                symbol=str(symbol or "").upper(),
                side=str(side or "BUY_CALL"),
                entry=float(entry_f),
                stop=float(stop_f),
                target=float(target_f),
                first_blocking_gate=(str(first_blocking_gate) if first_blocking_gate else None),
                mode=str(mode or "SIM"),
            )
            timeout_ts = float(ts_f + (timeout_min * 60))
            end_ts = min(timeout_ts, day_end)
            points = _price_path(conn, symbol=row.symbol, start_ts=float(ts_f), end_ts=end_ts)
            status, mfe, mae, best_rr, resolved_ts = _resolve_status(row, points, end_ts=end_ts, now_ts=now_ts)
            conn.execute(
                """
                UPDATE rejected_trades_shadow
                SET shadow_status = ?,
                    mfe = ?,
                    mae = ?,
                    best_rr = ?,
                    resolved_ts = ?
                WHERE candidate_id = ?
                """,
                (
                    str(status),
                    mfe,
                    mae,
                    best_rr,
                    resolved_ts,
                    row.candidate_id,
                ),
            )
            processed += 1
            resolved[str(status)] = int(resolved.get(str(status), 0)) + 1
    conn.close()
    return {
        "status": "ok",
        "desk": desk_id,
        "date": str(date),
        "processed": int(processed),
        "resolved": resolved,
        "db_path": str(db_path),
        "warning": warning,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Reject-shadow evaluator")
    parser.add_argument("--mode", choices=["evaluate"], default="evaluate")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD (IST)")
    parser.add_argument("--desk", default=getattr(cfg, "DESK_ID", "DEFAULT"))
    parser.add_argument("--limit", type=int, default=int(getattr(cfg, "REJECT_SHADOW_BATCH_LIMIT", 5000)))
    args = parser.parse_args(argv)

    payload = evaluate_pending(date=str(args.date), desk=str(args.desk), batch_limit=int(args.limit))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
