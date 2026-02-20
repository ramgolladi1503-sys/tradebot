from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Dict, Tuple, List, Any

from config import config as cfg
from core import risk_halt
from core.audit_log import verify_chain as verify_audit_chain
from core.auth_health import get_kite_auth_health
from core.feed_circuit_breaker import is_tripped as feed_breaker_tripped
from core.time_utils import now_ist, is_market_open_ist
from core.market_calendar import IN_HOLIDAYS
from core.trade_store import init_db
from core.readiness_state import ReadinessResult, ReadinessState
from core.gate_status_log import gate_status_path


def _disk_free_gb(path: str = ".") -> float:
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)


def _check_kite_auth() -> Tuple[bool, str, str]:
    payload = get_kite_auth_health(force=False)
    ok = bool(payload.get("ok"))
    auth_state = str(payload.get("auth_state") or ("OK" if ok else "FAILED"))
    reason = str(payload.get("error") or payload.get("reason") or "unknown")
    return ok, reason, auth_state


def _check_trade_identity_schema() -> Tuple[bool, str]:
    try:
        init_db()
    except Exception as exc:
        return False, f"trade_schema_init_error:{exc}"
    db_path = Path(getattr(cfg, "TRADE_DB_PATH", "data/desks/DEFAULT/trades.db"))
    if not db_path.exists():
        return False, "trade_db_missing"
    try:
        con = sqlite3.connect(str(db_path))
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if not cur.fetchone():
            con.close()
            return False, "trades_table_missing"
        cur.execute("PRAGMA table_info(trades)")
        cols = {row[1] for row in cur.fetchall()}
        con.close()
    except Exception as exc:
        return False, f"trade_schema_query_error:{exc}"
    required_cols = {
        "instrument_id",
        "underlying",
        "instrument_type",
        "expiry",
        "strike",
        "right",
        "qty_lots",
        "qty_units",
        "validity_sec",
        "timestamp_epoch",
    }
    missing = sorted(required_cols - cols)
    if missing:
        return False, f"trade_schema_missing:{','.join(missing)}"
    return True, "ok"


def _load_recent_decision_rows(now_epoch: float) -> Dict[str, Dict[str, Any]]:
    desk = getattr(cfg, "DESK_ID", "DEFAULT")
    path = gate_status_path(desk_id=desk)
    if not path.exists():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}
    max_age = float(getattr(cfg, "READINESS_DECISION_MAX_AGE_SEC", 45.0))
    out: Dict[str, Dict[str, Any]] = {}
    for raw in reversed(lines[-500:]):
        row = raw.strip()
        if not row:
            continue
        try:
            payload = json.loads(row)
        except Exception:
            continue
        symbol = str(payload.get("symbol") or "").upper()
        if not symbol:
            continue
        if symbol in out:
            continue
        ts = payload.get("ts_epoch")
        try:
            ts_epoch = float(ts)
        except Exception:
            continue
        if (now_epoch - ts_epoch) > max_age:
            continue
        # Ignore non-decision rows (for example trade-builder reject rows) so
        # readiness is sourced from the Decision DAG output only.
        has_decision_stage = str(payload.get("decision_stage") or "").strip() != ""
        has_decision_explain = payload.get("decision_explain") is not None
        has_decision_blockers = payload.get("decision_blockers") is not None
        if not (has_decision_stage or has_decision_explain or has_decision_blockers):
            continue
        out[symbol] = payload
    return out


def _decision_gate_health(now_epoch: float, market_open: bool) -> Dict[str, Any]:
    rows = _load_recent_decision_rows(now_epoch)
    symbols = sorted(rows.keys())
    blocked_rows: List[Dict[str, Any]] = []
    allowed_rows: List[Dict[str, Any]] = []
    feed_stale_symbols: List[str] = []
    blockers_by_symbol: Dict[str, List[str]] = {}
    max_ltp_age = None
    max_depth_age = None
    latest_explain = None

    for sym, row in rows.items():
        row_blockers = [str(x) for x in (row.get("decision_blockers") or row.get("gate_reasons") or []) if str(x).strip()]
        blockers_by_symbol[sym] = row_blockers
        if bool(row.get("gate_allowed")):
            allowed_rows.append(row)
        else:
            blocked_rows.append(row)
        fhs = row.get("feed_health_snapshot") or {}
        if isinstance(fhs, dict):
            try:
                ltp_age = float(fhs.get("ltp_age_sec")) if fhs.get("ltp_age_sec") is not None else None
            except Exception:
                ltp_age = None
            try:
                depth_age = float(fhs.get("depth_age_sec")) if fhs.get("depth_age_sec") is not None else None
            except Exception:
                depth_age = None
            if ltp_age is not None:
                max_ltp_age = ltp_age if max_ltp_age is None else max(max_ltp_age, ltp_age)
            if depth_age is not None:
                max_depth_age = depth_age if max_depth_age is None else max(max_depth_age, depth_age)
            if market_open and (fhs.get("is_fresh") is False):
                feed_stale_symbols.append(sym)
        if market_open and any(str(reason).upper() == "FEED_STALE" for reason in row_blockers):
            feed_stale_symbols.append(sym)
        if latest_explain is None and row.get("decision_explain") is not None:
            latest_explain = row.get("decision_explain")

    blockers: List[str] = []
    reasons: List[str] = []
    require_decision = bool(getattr(cfg, "READINESS_REQUIRE_DECISION_GATE", True))
    if market_open and require_decision:
        if not rows:
            blockers.append("decision_gate_missing")
        elif blocked_rows:
            blockers.append("decision_gate_blocked")

    unique_feed_stale_symbols = sorted(set(feed_stale_symbols))
    if market_open and unique_feed_stale_symbols:
        reasons.append("feed_stale:" + ",".join(unique_feed_stale_symbols))

    decision_ok = (not market_open) or (not blockers)
    feed_ok = (not market_open) or (len(feed_stale_symbols) == 0)
    return {
        "ok": decision_ok,
        "feed_ok": feed_ok,
        "blockers": blockers,
        "reasons": reasons,
        "symbols": symbols,
        "allowed_symbols": sorted(str(row.get("symbol") or "").upper() for row in allowed_rows),
        "blocked_symbols": sorted(str(row.get("symbol") or "").upper() for row in blocked_rows),
        "blockers_by_symbol": blockers_by_symbol,
        "rows": rows,
        "ltp_age_sec": max_ltp_age,
        "depth_age_sec": max_depth_age,
        "latest_explain": latest_explain,
    }


def run_readiness_check(write_log: bool = True) -> Dict[str, object]:
    """
    Backwards-compatible wrapper that now exposes state-machine keys.
    """
    res = run_readiness_state(write_log=write_log)
    payload = {
        "ts_epoch": res.checks.get("ts_epoch"),
        "ts_ist": res.checks.get("ts_ist"),
        "market_open": res.market_open,
        "holiday": res.holiday,
        "ready": res.can_trade,
        "reasons": res.blockers,
        "warnings": res.warnings,
        "checks": res.checks,
        "state": res.state.value,
        "can_trade": res.can_trade,
        "blockers": res.blockers,
    }
    return payload


def run_readiness_state(write_log: bool = True) -> ReadinessResult:
    now = now_ist()
    is_holiday = now.date() in IN_HOLIDAYS
    market_open = is_market_open_ist(now=now) and not is_holiday

    blockers = []
    warnings = []
    checks: Dict[str, object] = {}
    checks["ts_epoch"] = now.timestamp()
    checks["ts_ist"] = now.isoformat()

    # Required config
    missing_cfg = []
    if not getattr(cfg, "DESK_ID", None):
        missing_cfg.append("missing_desk_id")
    if not getattr(cfg, "TRADE_DB_PATH", None):
        missing_cfg.append("missing_trade_db_path")
    if not getattr(cfg, "SYMBOLS", None):
        missing_cfg.append("missing_symbols")
    if missing_cfg:
        blockers.extend(missing_cfg)
    checks["config"] = {"ok": not missing_cfg, "missing": missing_cfg}

    # Risk halt
    halted = risk_halt.is_halted()
    if halted and getattr(cfg, "READINESS_REQUIRE_RISK_HALT_CLEAR", True):
        blockers.append("risk_halt_active")
    checks["risk_halt"] = {"ok": not halted, "halted": halted}

    # Audit chain
    audit_ok = True
    audit_reason = "ok"
    if getattr(cfg, "READINESS_REQUIRE_AUDIT_CHAIN", True):
        audit_ok, audit_reason, _ = verify_audit_chain()
        if not audit_ok:
            blockers.append(f"audit_chain:{audit_reason}")
    checks["audit_chain"] = {"ok": audit_ok, "reason": audit_reason}

    # Kite auth
    kite_ok = True
    kite_reason = "ok"
    kite_state = "OK"
    if getattr(cfg, "READINESS_REQUIRE_KITE_AUTH", True):
        kite_ok, kite_reason, kite_state = _check_kite_auth()
        if not kite_ok:
            blockers.append(kite_reason)
        elif kite_state == "UNKNOWN_NETWORK":
            warnings.append("kite_auth_unknown_network")
    checks["kite_auth"] = {"ok": kite_ok, "reason": kite_reason, "state": kite_state}

    # Trade schema readiness
    schema_ok = True
    schema_reason = "ok"
    if getattr(cfg, "READINESS_REQUIRE_TRADE_SCHEMA", True):
        schema_ok, schema_reason = _check_trade_identity_schema()
        if not schema_ok:
            blockers.append(schema_reason)
    checks["trade_identity_schema"] = {"ok": schema_ok, "reason": schema_reason}

    # Decision DAG health (single source of truth for gating/readiness)
    decision_health = _decision_gate_health(now_epoch=float(checks["ts_epoch"]), market_open=market_open)
    for reason in decision_health.get("blockers", []):
        blockers.append(reason)
    checks["decision_gate"] = {
        "ok": bool(decision_health.get("ok")),
        "symbols": decision_health.get("symbols") or [],
        "allowed_symbols": decision_health.get("allowed_symbols") or [],
        "blocked_symbols": decision_health.get("blocked_symbols") or [],
        "blockers_by_symbol": decision_health.get("blockers_by_symbol") or {},
        "rows": decision_health.get("rows") or {},
        "latest_explain": decision_health.get("latest_explain"),
    }
    feed_ok = bool(decision_health.get("feed_ok", True))
    feed_reasons = list(decision_health.get("reasons") or [])
    if market_open and not feed_ok:
        blockers.append(f"feed_health:{','.join(feed_reasons) or 'feed_stale'}")
    checks["feed_health"] = {
        "ok": feed_ok,
        "reasons": feed_reasons,
        "ltp_age_sec": decision_health.get("ltp_age_sec"),
        "depth_age_sec": decision_health.get("depth_age_sec"),
        "state": "OK" if feed_ok else "STALE",
        "market_open": market_open,
        "ltp": {
            "age_sec": decision_health.get("ltp_age_sec"),
            "max_age_sec": float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)),
        },
        "depth": {
            "age_sec": decision_health.get("depth_age_sec"),
            "max_age_sec": float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 6.0)),
        },
        "source": "decision_dag",
    }

    breaker_tripped = feed_breaker_tripped()
    checks["feed_breaker"] = {"tripped": breaker_tripped}
    if breaker_tripped:
        blockers.append("feed_circuit_breaker_tripped")

    # Disk free
    min_gb = float(getattr(cfg, "READINESS_MIN_FREE_GB", 2.0))
    free_gb = _disk_free_gb(".")
    disk_ok = free_gb >= min_gb
    if not disk_ok:
        blockers.append("disk_low")
    checks["disk_free_gb"] = {"ok": disk_ok, "free_gb": round(free_gb, 2), "min_gb": min_gb}

    if not checks.get("ts_epoch"):
        state = ReadinessState.BOOTING
        can_trade = False
    elif blockers:
        state = ReadinessState.BLOCKED
        can_trade = False
    else:
        if not market_open:
            state = ReadinessState.MARKET_CLOSED if not warnings else ReadinessState.DEGRADED
            can_trade = False
        else:
            state = ReadinessState.READY if not warnings else ReadinessState.DEGRADED
            can_trade = state == ReadinessState.READY

    res = ReadinessResult(
        state=state,
        can_trade=can_trade,
        market_open=market_open,
        holiday=is_holiday,
        blockers=blockers,
        warnings=warnings,
        checks=checks,
    )

    if write_log:
        out = Path("logs") / f"readiness_{now.date().isoformat()}.json"
        out.parent.mkdir(exist_ok=True)
        payload = {
            "ts_epoch": checks["ts_epoch"],
            "ts_ist": checks["ts_ist"],
            **res.to_payload(),
        }
        out.write_text(json.dumps(payload, indent=2))
        _log_state_transition(payload)
    return res


def _log_state_transition(payload: Dict[str, object]) -> None:
    try:
        state_path = Path("logs/readiness_state.json")
        log_path = Path("logs/readiness_state.jsonl")
        prev = {}
        if state_path.exists():
            try:
                prev = json.loads(state_path.read_text())
            except Exception:
                prev = {}
        curr = {
            "state": payload.get("state"),
            "blockers": payload.get("blockers"),
            "warnings": payload.get("warnings"),
            "market_open": payload.get("market_open"),
        }
        if prev != curr:
            state_path.write_text(json.dumps(curr, indent=2))
            with log_path.open("a") as f:
                f.write(json.dumps({
                    "ts_epoch": payload.get("ts_epoch"),
                    "ts_ist": payload.get("ts_ist"),
                    **curr,
                }) + "\n")
    except Exception:
        pass
