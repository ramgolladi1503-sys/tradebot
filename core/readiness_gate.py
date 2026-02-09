from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, Tuple

from config import config as cfg
from core import risk_halt
from core.audit_log import verify_chain as verify_audit_chain
from core.feed_health import get_feed_health
from core.kite_client import kite_client
from core.time_utils import now_ist, is_market_open_ist
from core.market_calendar import IN_HOLIDAYS


def _disk_free_gb(path: str = ".") -> float:
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)


def _check_kite_auth() -> Tuple[bool, str]:
    if not cfg.KITE_API_KEY or not cfg.KITE_ACCESS_TOKEN:
        return False, "kite_creds_missing"
    try:
        kite_client.ensure()
        if not kite_client.kite:
            return False, "kite_unavailable"
        try:
            kite_client.kite.profile()
        except Exception as exc:
            return False, f"kite_profile_error:{exc}"
    except Exception as exc:
        return False, f"kite_init_error:{exc}"
    return True, "ok"


def run_readiness_check(write_log: bool = True) -> Dict[str, object]:
    now = now_ist()
    is_holiday = now.date() in IN_HOLIDAYS
    market_open = is_market_open_ist(now=now) and not is_holiday

    reasons = []
    warnings = []
    checks = {}

    # Required config
    if not getattr(cfg, "DESK_ID", None):
        reasons.append("missing_desk_id")
    if not getattr(cfg, "TRADE_DB_PATH", None):
        reasons.append("missing_trade_db_path")
    if not getattr(cfg, "SYMBOLS", None):
        reasons.append("missing_symbols")
    checks["config"] = {"ok": len(reasons) == 0}

    # Risk halt
    halted = risk_halt.is_halted()
    if halted and getattr(cfg, "READINESS_REQUIRE_RISK_HALT_CLEAR", True):
        reasons.append("risk_halt_active")
    checks["risk_halt"] = {"ok": not halted, "halted": halted}

    # Audit chain
    audit_ok = True
    audit_reason = "ok"
    if getattr(cfg, "READINESS_REQUIRE_AUDIT_CHAIN", True):
        audit_ok, audit_reason, _ = verify_audit_chain()
        if not audit_ok:
            reasons.append(f"audit_chain:{audit_reason}")
    checks["audit_chain"] = {"ok": audit_ok, "reason": audit_reason}

    # Kite auth
    kite_ok = True
    kite_reason = "ok"
    if getattr(cfg, "READINESS_REQUIRE_KITE_AUTH", True):
        kite_ok, kite_reason = _check_kite_auth()
        if not kite_ok:
            reasons.append(kite_reason)
    checks["kite_auth"] = {"ok": kite_ok, "reason": kite_reason}

    # Feed health
    feed_ok = True
    feed_reason = "ok"
    if getattr(cfg, "READINESS_REQUIRE_FEED_HEALTH", True):
        health = get_feed_health()
        feed_ok = bool(health.get("ok"))
        if market_open and not feed_ok:
            feed_reason = ",".join(health.get("reasons", [])) or "feed_stale"
            reasons.append(f"feed_health:{feed_reason}")
        if not market_open and not feed_ok:
            feed_reason = ",".join(health.get("reasons", [])) or "feed_stale"
            warnings.append(f"feed_health:{feed_reason}")
        checks["feed_health"] = {
            "ok": feed_ok,
            "reason": feed_reason,
            "tick_lag_sec": health.get("tick_lag"),
            "depth_lag_sec": health.get("depth_lag"),
        }
    else:
        checks["feed_health"] = {"ok": True, "reason": "skipped"}

    # Disk free
    min_gb = float(getattr(cfg, "READINESS_MIN_FREE_GB", 2.0))
    free_gb = _disk_free_gb(".")
    disk_ok = free_gb >= min_gb
    if not disk_ok:
        reasons.append("disk_low")
    checks["disk_free_gb"] = {"ok": disk_ok, "free_gb": round(free_gb, 2), "min_gb": min_gb}

    ready = len(reasons) == 0
    payload = {
        "ts_epoch": now.timestamp(),
        "ts_ist": now.isoformat(),
        "market_open": market_open,
        "holiday": is_holiday,
        "ready": ready,
        "reasons": reasons,
        "warnings": warnings,
        "checks": checks,
    }

    if write_log:
        out = Path("logs") / f"readiness_{now.date().isoformat()}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(payload, indent=2))
    return payload
