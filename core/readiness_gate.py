from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Dict, Tuple

from config import config as cfg
from core import risk_halt
from core.audit_log import verify_chain as verify_audit_chain
from core.freshness_sla import get_freshness_status
from core.auth_health import get_kite_auth_health
from core.feed_circuit_breaker import is_tripped as feed_breaker_tripped
from core.time_utils import now_ist, is_market_open_ist
from core.market_calendar import IN_HOLIDAYS
from core.trade_store import init_db
from core.readiness_state import ReadinessResult, ReadinessState


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

    # Feed health
    feed_ok = True
    feed_reasons = []
    ltp_age = None
    depth_age = None
    if getattr(cfg, "READINESS_REQUIRE_FEED_HEALTH", True):
        freshness = get_freshness_status(force=False)
        feed_ok = bool(freshness.get("ok"))
        feed_reasons = freshness.get("reasons") or []
        ltp_age = (freshness.get("ltp") or {}).get("age_sec")
        depth_age = (freshness.get("depth") or {}).get("age_sec")
        if market_open and not feed_ok:
            blockers.append(f"feed_health:{','.join(feed_reasons) or 'feed_stale'}")
        checks["feed_health"] = {
            "ok": feed_ok,
            "reasons": feed_reasons,
            "ltp_age_sec": ltp_age,
            "depth_age_sec": depth_age,
            "state": freshness.get("state"),
            "market_open": freshness.get("market_open"),
        }
    else:
        checks["feed_health"] = {"ok": True, "reason": "skipped", "reasons": []}

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
