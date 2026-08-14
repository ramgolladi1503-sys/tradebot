from __future__ import annotations

import os
import time
from pathlib import Path

from config import config as cfg
from core.audit_log import AUDIT_LOG, append_event as audit_append, verify_chain
from core.events import append_event as append_runtime_event, events_path
from core.event_integrity import repair_events_file, validate_events_file
from core.observability.pipeline import observability_dir


def normalize_runtime_mode(value: str | None) -> str | None:
    if value is None:
        return None
    mode = str(value).strip().upper()
    if mode not in {"LIVE", "PAPER", "SIM"}:
        return None
    return mode


def truthy_env(value: str | None, *, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def order_reconciliation_enabled(config=cfg) -> bool:
    """Safety default is false. Live observation must be explicitly enabled."""

    env_value = os.getenv("ORDER_RECON_ENABLED")
    if env_value is not None and str(env_value).strip() != "":
        return truthy_env(env_value, default=False)
    return bool(getattr(config, "ORDER_RECON_ENABLED", False))


def resolve_orchestrator_poll_interval(exec_mode: str) -> float:
    mode = normalize_runtime_mode(exec_mode) or "SIM"
    configured = getattr(cfg, "ORCHESTRATOR_POLL_INTERVAL_SEC", None)
    if configured not in (None, "", 0, 0.0):
        try:
            return max(0.05, float(configured))
        except Exception:
            pass
    mode_defaults = {
        "LIVE": 0.25,
        "PAPER": 0.50,
        "SIM": 1.00,
    }
    return float(mode_defaults.get(mode, 1.00))


def normalize_readiness_blocker(value: str) -> str:
    return str(value or "").strip().lower()


def global_readiness_blocker_sets():
    explicit = set()
    prefixes = []
    try:
        explicit = {
            str(item).strip().lower()
            for item in (getattr(cfg, "READINESS_GLOBAL_ABORT_BLOCKERS", []) or [])
            if str(item).strip()
        }
    except Exception:
        explicit = set()
    try:
        prefixes = [
            str(item).strip().lower()
            for item in (getattr(cfg, "READINESS_GLOBAL_ABORT_PREFIXES", []) or [])
            if str(item).strip()
        ]
    except Exception:
        prefixes = []
    return explicit, prefixes


def startup_monitor_only_readiness_blockers():
    allowed = set()
    if bool(getattr(cfg, "READINESS_ALLOW_RISK_HALT_MONITORING_STARTUP", True)):
        allowed.add("risk_halt_active")
    return allowed


def is_global_readiness_blocker(blocker: str) -> bool:
    text = normalize_readiness_blocker(blocker)
    if not text:
        return False
    explicit, prefixes = global_readiness_blocker_sets()
    if text in explicit:
        return True
    for prefix in prefixes:
        if prefix and text.startswith(prefix):
            return True
    return False


def classify_readiness_abort(readiness: dict) -> tuple[bool, list[str]]:
    market_open = readiness.get("market_open")
    state = str(readiness.get("state") or "").strip().upper()
    blockers = list(readiness.get("blockers") or readiness.get("reasons") or [])
    if market_open is False or state == "MARKET_CLOSED":
        return True, ["market_closed"]
    if state != "BLOCKED":
        return False, []
    global_blockers = [b for b in blockers if is_global_readiness_blocker(b)]
    startup_monitor_only = startup_monitor_only_readiness_blockers()
    abort_blockers = [
        blocker
        for blocker in global_blockers
        if normalize_readiness_blocker(blocker) not in startup_monitor_only
    ]
    return bool(abort_blockers), abort_blockers


def ensure_runtime_dirs(repo_root: Path) -> None:
    """Best-effort creation of runtime directories that many subsystems expect."""

    try:
        runtime_dir = repo_root / ".runtime"
        logs_dir = runtime_dir / "logs"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        observability_dir()
        (logs_dir / "trade_log.jsonl").touch(exist_ok=True)
    except Exception as exc:
        print(f"[STARTUP_WARN] runtime dir init failed: {exc}")


def initialize_audit_chain(*, run_id: str | None = None, boot_epoch: float | None = None) -> dict:
    """Create one legitimate fresh-session audit event before readiness evaluation.

    Existing logs are never replaced or repaired here.  A present log must already
    verify; corruption therefore remains fail-closed.  The caller owns the runtime
    root, so a newly created log is session-scoped by that root and carries the
    session identity for independent inspection.
    """

    session_id = str(run_id or os.getenv("TRADEBOT_RUN_ID", "")).strip()
    if not session_id:
        return {"ok": False, "status": "missing_run_id", "count": 0, "path": str(AUDIT_LOG)}

    if AUDIT_LOG.exists():
        ok, status, count = verify_chain(AUDIT_LOG)
        return {"ok": bool(ok), "status": status, "count": int(count), "path": str(AUDIT_LOG), "created": False}

    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        audit_append(
            {
                "event": "AUDIT_CHAIN_BOOTSTRAP",
                "run_id": session_id,
                "boot_epoch": float(boot_epoch if boot_epoch is not None else time.time()),
                "source": "runtime_bootstrap.initialize_audit_chain",
                "is_order_action": False,
                "broker_write_authority": False,
                "order_authority": False,
                "paper_authorized": False,
                "live_authorized": False,
            }
        )
    except Exception as exc:
        return {
            "ok": False,
            "status": f"bootstrap_error:{type(exc).__name__}",
            "count": 0,
            "path": str(AUDIT_LOG),
            "created": False,
        }

    ok, status, count = verify_chain(AUDIT_LOG)
    return {"ok": bool(ok), "status": status, "count": int(count), "path": str(AUDIT_LOG), "created": True}


def repair_events_log_if_needed() -> None:
    try:
        target = events_path()
        validation = validate_events_file(target)
        if bool(validation.get("truncated_tail")):
            repair = repair_events_file(target)
            bytes_trimmed = int(repair.get("bytes_trimmed") or 0)
            append_runtime_event(
                "events_repaired",
                {
                    "bytes_trimmed": bytes_trimmed,
                    "last_good_offset": int(validation.get("last_good_offset") or 0),
                    "bad_lines": int(validation.get("bad_lines") or 0),
                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                },
            )
            print(f"[EVENTS] repaired truncated tail bytes_trimmed={bytes_trimmed} path={target}")
        elif not bool(validation.get("ok", True)):
            print(
                "[EVENTS] integrity warning bad_lines="
                f"{int(validation.get('bad_lines') or 0)} path={target}"
            )
    except Exception as exc:
        print(f"[EVENTS] integrity check failed: {exc}")


def audit_startup_state(event_name: str, *, message: str, extra: dict | None = None) -> None:
    payload = {
        "event": str(event_name),
        "message": str(message),
        "exec_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
    }
    if extra:
        payload.update(dict(extra))
    try:
        audit_append(dict(payload))
    except Exception as exc:
        print(f"[AUDIT_ERROR] {event_name.lower()} err={exc}")
    try:
        append_runtime_event(str(event_name).lower(), dict(payload))
    except Exception as exc:
        print(f"[EVENTS_ERROR] {event_name.lower()} err={exc}")
