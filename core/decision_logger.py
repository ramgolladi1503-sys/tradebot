from __future__ import annotations

import json
import sqlite3
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from config import config as cfg
from core.audit_log import append_event as audit_append
from core.paths import logs_dir
from core.reason_codes import normalize_reason_codes


DECISION_JSONL = Path(getattr(cfg, "DECISION_LOG_PATH", str(logs_dir() / "decision_events.jsonl")))
DECISION_CHAIN_GENESIS = "GENESIS"
DECISION_ERROR_LOG = Path(
    getattr(cfg, "DECISION_ERROR_LOG_PATH", str(logs_dir() / "decision_event_errors.jsonl"))
)

REQUIRED_FIELDS = (
    "trace_id",
    "desk_id",
    "timestamp_epoch",
    "quote_age_sec",
    "instrument_id",
)


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def _canonical_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_json_default)


def _read_last_hash() -> str:
    if not DECISION_JSONL.exists():
        return DECISION_CHAIN_GENESIS
    try:
        with DECISION_JSONL.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return DECISION_CHAIN_GENESIS
            offset = min(size, 16384)
            f.seek(-offset, 2)
            data = f.read().splitlines()
            if not data:
                return DECISION_CHAIN_GENESIS
            for raw in reversed(data):
                if not raw:
                    continue
                try:
                    last = json.loads(raw.decode("utf-8"))
                except Exception:
                    continue
                if last.get("event_hash"):
                    return last.get("event_hash")
            return DECISION_CHAIN_GENESIS
    except Exception:
        return DECISION_CHAIN_GENESIS


def _compute_event_hash(event: Dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    canonical = _canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _log_decision_error(payload: Dict[str, Any]) -> None:
    try:
        DECISION_ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with DECISION_ERROR_LOG.open("a") as f:
            f.write(json.dumps(payload, default=_json_default) + "\n")
    except Exception as exc:
        print(f"[DECISION_ERROR_LOG] {exc}")


def _validate_event(event: Dict[str, Any]) -> None:
    missing = []
    for field in REQUIRED_FIELDS:
        if field not in event or event.get(field) is None:
            missing.append(field)
    if missing:
        _log_decision_error({
            "ts": time.time(),
            "error": "decision_event_missing_fields",
            "missing": missing,
            "trade_id": event.get("trade_id"),
            "trace_id": event.get("trace_id"),
        })
        raise ValueError(f"Missing required fields: {missing}")


def verify_decision_chain(path: Path = DECISION_JSONL) -> Tuple[bool, str, int]:
    if not path.exists():
        return False, "missing_log", 0
    prev_hash = DECISION_CHAIN_GENESIS
    count = 0
    hashed_count = 0
    legacy_count = 0
    with path.open("r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except Exception:
                return False, "invalid_json", count
            if "prev_hash" not in event or "event_hash" not in event:
                if hashed_count > 0:
                    return False, "legacy_after_hashed", count
                legacy_count += 1
                continue
            expected_prev = event.get("prev_hash")
            if expected_prev != prev_hash:
                return False, "prev_hash_mismatch", count
            expected_hash = event.get("event_hash")
            calc_hash = _compute_event_hash(event)
            if expected_hash != calc_hash:
                return False, "event_hash_mismatch", count
            prev_hash = expected_hash
            count += 1
            hashed_count += 1
    if hashed_count == 0:
        return False, "no_hashed_events", legacy_count
    return True, prev_hash, hashed_count


def _conn():
    Path(cfg.TRADE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(cfg.TRADE_DB_PATH)


def _init_db():
    with _conn() as conn:
        conn.execute(
            """
        CREATE TABLE IF NOT EXISTS decision_events (
            trade_id TEXT PRIMARY KEY,
            prev_hash TEXT,
            event_hash TEXT,
            ts TEXT,
            timestamp_epoch REAL,
            timestamp_iso TEXT,
            symbol TEXT,
            underlying TEXT,
            strategy_id TEXT,
            regime TEXT,
            regime_probs TEXT,
            shock_score REAL,
            side TEXT,
            instrument TEXT,
            instrument_type TEXT,
            instrument_id TEXT,
            strike INTEGER,
            expiry TEXT,
            option_type TEXT,
            right TEXT,
            qty_lots INTEGER,
            qty_units INTEGER,
            validity_sec INTEGER,
            dte REAL,
            expiry_bucket TEXT,
            score_0_100 REAL,
            xgb_proba REAL,
            deep_proba REAL,
            micro_proba REAL,
            ensemble_proba REAL,
            ensemble_uncertainty REAL,
            champion_proba REAL,
            challenger_proba REAL,
            champion_model_id TEXT,
            challenger_model_id TEXT,
            model_id TEXT,
            dataset_hash TEXT,
            feature_hash TEXT,
            bid REAL,
            ask REAL,
            spread_pct REAL,
            bid_qty REAL,
            ask_qty REAL,
            depth_imbalance REAL,
            quote_age_sec REAL,
            quote_ts_epoch REAL,
            depth_age_sec REAL,
            fill_prob_est REAL,
            portfolio_equity REAL,
            equity REAL,
            equity_high REAL,
            daily_pnl REAL,
            daily_pnl_pct REAL,
            drawdown_pct REAL,
            loss_streak REAL,
            open_risk REAL,
            open_risk_pct REAL,
            delta_exposure REAL,
            gamma_exposure REAL,
            vega_exposure REAL,
            gatekeeper_allowed INTEGER,
            veto_reasons TEXT,
            risk_allowed INTEGER,
            exec_guard_allowed INTEGER,
            pilot_allowed INTEGER,
            pilot_reasons TEXT,
            action_size_multiplier REAL,
            filled_bool INTEGER,
            fill_price REAL,
            time_to_fill REAL,
            slippage_vs_mid REAL,
            pnl_horizon_5m REAL,
            pnl_horizon_15m REAL,
            mae_15m REAL,
            mfe_15m REAL
        )
        """
        )
        # Add missing columns for backward-compatible schema upgrades
        try:
            cur = conn.execute("PRAGMA table_info(decision_events)")
            existing = {row[1] for row in cur.fetchall()}
            desired = {
                "prev_hash": "TEXT",
                "event_hash": "TEXT",
                "timestamp_epoch": "REAL",
                "timestamp_iso": "TEXT",
                "equity": "REAL",
                "equity_high": "REAL",
                "daily_pnl_pct": "REAL",
                "open_risk_pct": "REAL",
                "champion_proba": "REAL",
                "challenger_proba": "REAL",
                "champion_model_id": "TEXT",
                "challenger_model_id": "TEXT",
                "model_id": "TEXT",
                "dataset_hash": "TEXT",
                "feature_hash": "TEXT",
                "instrument_id": "TEXT",
                "strike": "INTEGER",
                "expiry": "TEXT",
                "option_type": "TEXT",
                "right": "TEXT",
                "instrument_type": "TEXT",
                "underlying": "TEXT",
                "qty_lots": "INTEGER",
                "qty_units": "INTEGER",
                "validity_sec": "INTEGER",
                "quote_age_sec": "REAL",
                "quote_ts_epoch": "REAL",
                "depth_age_sec": "REAL",
                "pilot_allowed": "INTEGER",
                "pilot_reasons": "TEXT",
            }
            for col, col_type in desired.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE decision_events ADD COLUMN {col} {col_type}")
        except Exception:
            pass


def log_decision(event: Dict[str, Any]):
    _init_db()
    now_epoch = time.time()
    now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    event.setdefault("timestamp_epoch", now_epoch)
    event.setdefault("timestamp_iso", now_iso)
    event.setdefault("desk_id", getattr(cfg, "DESK_ID", "DEFAULT"))
    trade_id = event.get("trade_id") or event.get("decision_id")
    if not trade_id:
        base = f"{event.get('symbol','UNKNOWN')}|{event.get('timestamp_epoch')}"
        trade_id = f"decision-{hashlib.sha256(base.encode('utf-8')).hexdigest()[:16]}"
        event["trade_id"] = trade_id
        event["decision_id"] = trade_id
    event.setdefault("trace_id", trade_id)

    # Normalize JSON fields
    if isinstance(event.get("regime_probs"), dict):
        event["regime_probs"] = json.dumps(event.get("regime_probs"))
    veto_codes = normalize_reason_codes(event.get("veto_reasons"))
    if veto_codes is not None:
        event["veto_reasons"] = json.dumps(veto_codes)
    pilot_codes = normalize_reason_codes(event.get("pilot_reasons"))
    if pilot_codes is not None:
        event["pilot_reasons"] = json.dumps(pilot_codes)

    _validate_event(event)
    prev_hash = _read_last_hash()
    event["prev_hash"] = prev_hash
    event["event_hash"] = _compute_event_hash(event)

    DECISION_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with DECISION_JSONL.open("a") as f:
        f.write(_canonical_json(event) + "\n")

    cols = [
        "trade_id",
        "prev_hash",
        "event_hash",
        "ts",
        "timestamp_epoch",
        "timestamp_iso",
        "symbol",
        "underlying",
        "strategy_id",
        "regime",
        "regime_probs",
        "shock_score",
        "side",
        "instrument",
        "instrument_type",
        "instrument_id",
        "strike",
        "expiry",
        "option_type",
        "right",
        "qty_lots",
        "qty_units",
        "validity_sec",
        "dte",
        "expiry_bucket",
        "score_0_100",
        "xgb_proba",
        "deep_proba",
        "micro_proba",
        "ensemble_proba",
        "ensemble_uncertainty",
        "champion_proba",
        "challenger_proba",
        "champion_model_id",
        "challenger_model_id",
        "model_id",
        "dataset_hash",
        "feature_hash",
        "bid",
        "ask",
        "spread_pct",
        "bid_qty",
        "ask_qty",
        "depth_imbalance",
        "quote_age_sec",
        "quote_ts_epoch",
        "depth_age_sec",
        "fill_prob_est",
        "portfolio_equity",
        "equity",
        "equity_high",
        "daily_pnl",
        "daily_pnl_pct",
        "drawdown_pct",
        "loss_streak",
        "open_risk",
        "open_risk_pct",
        "delta_exposure",
        "gamma_exposure",
        "vega_exposure",
        "gatekeeper_allowed",
        "veto_reasons",
        "risk_allowed",
        "exec_guard_allowed",
        "pilot_allowed",
        "pilot_reasons",
        "action_size_multiplier",
        "filled_bool",
        "fill_price",
        "time_to_fill",
        "slippage_vs_mid",
        "pnl_horizon_5m",
        "pnl_horizon_15m",
        "mae_15m",
        "mfe_15m",
    ]
    values = [event.get(c) for c in cols]
    try:
        with _conn() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO decision_events
                ({",".join(cols)}) VALUES ({",".join(["?"] * len(cols))})
                """,
                values,
            )
    except Exception as exc:
        try:
            from core.incidents import trigger_db_write_fail
            trigger_db_write_fail({"table": "decision_events", "error": str(exc)})
        except Exception as inner:
            print(f"[INCIDENT_ERROR] db_write_fail err={inner}")
        raise
    try:
        audit_append({
            "event": "DECISION",
            "trade_id": trade_id,
            "symbol": event.get("symbol"),
            "strategy_id": event.get("strategy_id"),
            "decision_hash": event.get("event_hash"),
            "gatekeeper_allowed": event.get("gatekeeper_allowed"),
            "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
        })
    except Exception as exc:
        print(f"[AUDIT_ERROR] decision_audit_failed err={exc}")
    return trade_id


def update_execution(trade_id: str, exec_fields: Dict[str, Any]):
    if not trade_id:
        return
    _init_db()
    fields = exec_fields.copy()
    veto_codes = normalize_reason_codes(fields.get("veto_reasons"))
    if veto_codes is not None:
        fields["veto_reasons"] = json.dumps(veto_codes)
    pilot_codes = normalize_reason_codes(fields.get("pilot_reasons"))
    if pilot_codes is not None:
        fields["pilot_reasons"] = json.dumps(pilot_codes)
    sets = ", ".join([f"{k} = ?" for k in fields.keys()])
    vals = list(fields.values()) + [trade_id]
    try:
        with _conn() as conn:
            conn.execute(f"UPDATE decision_events SET {sets} WHERE trade_id = ?", vals)
    except Exception as exc:
        try:
            from core.incidents import trigger_db_write_fail
            trigger_db_write_fail({"table": "decision_events", "error": str(exc)})
        except Exception as inner:
            print(f"[INCIDENT_ERROR] db_write_fail err={inner}")
        raise


def update_outcome(trade_id: str, outcome_fields: Dict[str, Any]):
    if not trade_id:
        return
    _init_db()
    sets = ", ".join([f"{k} = ?" for k in outcome_fields.keys()])
    vals = list(outcome_fields.values()) + [trade_id]
    try:
        with _conn() as conn:
            conn.execute(f"UPDATE decision_events SET {sets} WHERE trade_id = ?", vals)
    except Exception as exc:
        try:
            from core.incidents import trigger_db_write_fail
            trigger_db_write_fail({"table": "decision_events", "error": str(exc)})
        except Exception as inner:
            print(f"[INCIDENT_ERROR] db_write_fail err={inner}")
        raise
