import os
import atexit
from pathlib import Path

import core.runtime_guard  # noqa: F401  (import side-effects intentional)
from config import config as cfg

from core.orchestrator import Orchestrator
from core.readiness_gate import run_readiness_check
from core.audit_log import append_event as audit_append
from core.events import append_event as append_runtime_event, events_path
from core.event_integrity import repair_events_file, validate_events_file
from core import risk_halt
from core.security_guard import enforce_startup_security
from core.instance_lock import InstanceLock
from core.session_guard import auto_clear_risk_halt_if_safe
from core.db_guard import ensure_db_ready
from core.trade_log_paths import ensure_trade_log_exists
from core.broker_truth_reconciler import BrokerTruthReconciler
from core.kite_client import kite_client
from core.observability.pipeline import observability_dir


tok = os.getenv("KITE_ACCESS_TOKEN") or ""
print(
    f"[ENV] KITE_ACCESS_TOKEN present={bool(tok)} len={len(tok)} "
    f"tail4={tok[-4:] if len(tok) >= 4 else '----'}"
)


def _check_env():
    missing = []
    if not getattr(cfg, "KITE_API_KEY", None):
        missing.append("KITE_API_KEY")
    if not getattr(cfg, "KITE_API_SECRET", None):
        missing.append("KITE_API_SECRET")
    if getattr(cfg, "ENABLE_TELEGRAM", False) and (
        not getattr(cfg, "TELEGRAM_BOT_TOKEN", None) or not getattr(cfg, "TELEGRAM_CHAT_ID", None)
    ):
        missing.append("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID")

    if missing:
        print("[Config Warning] Missing env vars: " + ", ".join(missing))


def _normalize_readiness_blocker(value: str) -> str:
    return str(value or "").strip().lower()


def _global_readiness_blocker_sets():
    explicit = set()
    prefixes = []
    try:
        explicit = {str(item).strip().lower() for item in (getattr(cfg, "READINESS_GLOBAL_ABORT_BLOCKERS", []) or []) if str(item).strip()}
    except Exception:
        explicit = set()
    try:
        prefixes = [str(item).strip().lower() for item in (getattr(cfg, "READINESS_GLOBAL_ABORT_PREFIXES", []) or []) if str(item).strip()]
    except Exception:
        prefixes = []
    return explicit, prefixes


def _is_global_readiness_blocker(blocker: str) -> bool:
    text = _normalize_readiness_blocker(blocker)
    if not text:
        return False
    explicit, prefixes = _global_readiness_blocker_sets()
    if text in explicit:
        return True
    for prefix in prefixes:
        if prefix and text.startswith(prefix):
            return True
    return False


def _classify_readiness_abort(readiness: dict) -> tuple[bool, list[str]]:
    market_open = readiness.get("market_open")
    state = str(readiness.get("state") or "").strip().upper()
    blockers = list(readiness.get("blockers") or readiness.get("reasons") or [])
    if market_open is False or state == "MARKET_CLOSED":
        return True, ["market_closed"]
    if state != "BLOCKED":
        return False, []
    global_blockers = [b for b in blockers if _is_global_readiness_blocker(b)]
    return bool(global_blockers), global_blockers


def _ensure_runtime_dirs(repo_root: Path) -> None:
    """
    Best-effort creation of runtime directories that many subsystems expect.
    Keeps startup deterministic and avoids scattered mkdirs.
    """
    try:
        runtime_dir = repo_root / ".runtime"
        logs_dir = runtime_dir / "logs"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        observability_dir()
        # Optional: ensure a common trade log exists even if caller forgets
        (logs_dir / "trade_log.jsonl").touch(exist_ok=True)
    except Exception as exc:
        print(f"[STARTUP_WARN] runtime dir init failed: {exc}")


def _repair_events_log_if_needed() -> None:
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


def main():
    repo_root = Path(__file__).resolve().parent
    print(f"[BOOT] repo_root={repo_root}")
    exec_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    print(f"[BOOT] exec_mode={exec_mode}")

    _ensure_runtime_dirs(repo_root)
    _repair_events_log_if_needed()

    lock = None
    if exec_mode in {"LIVE", "PAPER"}:
        lock = InstanceLock(repo_root_path=repo_root)
        try:
            acquired, holder = lock.acquire()
        except RuntimeError as exc:
            print(f"[INSTANCE_LOCK] {exc}")
            raise SystemExit(2)

        if not acquired:
            pid = holder.get("pid")
            host = holder.get("host")
            path = holder.get("lock_path") or str(lock.lock_path)
            print(
                "[INSTANCE_LOCK] Kite session already active. "
                f"pid={pid or 'unknown'} host={host or 'unknown'} path={path}"
            )
            raise SystemExit(2)

        atexit.register(lock.release)
        print(f"[INSTANCE_LOCK] acquired path={lock.lock_path} pid={holder.get('pid')}")

    try:
        ensure_db_ready()
    except RuntimeError as exc:
        print(f"[DB_INIT_ERROR] {exc}")
        return

    # IMPORTANT: this needs repo_root
    try:
        enforce_startup_security(repo_root=repo_root, require_token=True)
    except RuntimeError as exc:
        print(str(exc))
        return

    _check_env()

    try:
        ensure_trade_log_exists()
    except Exception as exc:
        print(f"[STARTUP_WARN] trade log init failed: {exc}")
        # Fallback touch (best-effort)
        try:
            (repo_root / ".runtime" / "logs" / "trade_log.jsonl").touch(exist_ok=True)
        except Exception:
            pass

    guard_result = auto_clear_risk_halt_if_safe()
    if guard_result.get("cleared"):
        print("[SessionGuard] auto-cleared stale risk halt (market closed, no open positions).")
    elif guard_result.get("reason_code") not in {"HALT_NOT_ACTIVE", "AUTO_CLEAR_DISABLED"}:
        print(f"[SessionGuard] no clear: {guard_result.get('reason_code')}")

    live_mode = exec_mode == "LIVE"
    pilot_mode = bool(getattr(cfg, "LIVE_PILOT_MODE", False))

    if live_mode or pilot_mode:
        readiness = run_readiness_check(write_log=True)
        state = readiness.get("state", "BLOCKED")
        can_trade = bool(readiness.get("can_trade", readiness.get("ready", False)))
        should_abort, abort_reasons = _classify_readiness_abort(readiness)

        if should_abort:
            risk_halt.set_halt("readiness_gate_fail", {"reasons": abort_reasons})
            try:
                audit_append(
                    {
                        "event": "READINESS_FAIL",
                        "state": state,
                        "reasons": abort_reasons,
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    }
                )
            except Exception as exc:
                print(f"[AUDIT_ERROR] readiness_fail err={exc}")
            print(f"[Readiness] Not ready: {','.join(abort_reasons)}")
            return

        if state == "BLOCKED":
            reasons = readiness.get("blockers") or readiness.get("reasons") or []
            print(f"[Readiness] non_global_blockers={','.join(reasons)}")
            try:
                audit_append(
                    {
                        "event": "READINESS_NON_GLOBAL",
                        "state": state,
                        "reasons": reasons,
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    }
                )
            except Exception as exc:
                print(f"[AUDIT_ERROR] readiness_non_global err={exc}")

        if not can_trade:
            warnings = readiness.get("warnings") or []
            print(f"[Readiness] state={state}; can_trade={can_trade}; warnings={','.join(warnings)}")

    orchestrator = Orchestrator(total_capital=getattr(cfg, "CAPITAL", 100000), poll_interval=30)

    broker_truth_reconciler = None

    recon_enabled = bool(getattr(cfg, "ORDER_RECON_ENABLED", True))
    if recon_enabled:
        try:
            interval_sec = float(getattr(cfg, "ORDER_RECON_INTERVAL_SEC", 5.0))
            orchestrator.execution_router.engine.start_reconciliation_daemon(interval_sec=interval_sec)
            print(f"[RECON] reconciliation daemon started interval_sec={interval_sec}")
        except Exception as exc:
            print(f"[RECON_WARN] failed_to_start_reconciliation_daemon: {exc}")

    # IMPORTANT: BrokerTruthReconciler requires (desk_id, broker, tolerance_cfg, lifecycle)
    if bool(getattr(cfg, "BROKER_TRUTH_RECONCILE_ENABLED", False)):
        try:
            kite_client.ensure()
            broker_api = getattr(kite_client, "kite", None)
            if broker_api is None:
                print("[BROKER_TRUTH] broker api unavailable; reconciler not started")
            else:
                broker_truth_reconciler = BrokerTruthReconciler(
                    desk_id=str(getattr(cfg, "DESK_ID", "DEFAULT")),
                    broker=broker_api,
                    tolerance_cfg={},
                    lifecycle=None,
                )
                interval_sec = float(getattr(cfg, "BROKER_TRUTH_INTERVAL_S", 60.0))
                broker_truth_reconciler.start(interval_s=interval_sec)
                print(f"[BROKER_TRUTH] reconciler started interval_sec={interval_sec}")
        except Exception as exc:
            print(f"[BROKER_TRUTH_WARN] failed_to_start_reconciler: {exc}")

    try:
        orchestrator.live_monitoring()
    finally:
        if broker_truth_reconciler is not None:
            try:
                broker_truth_reconciler.stop()
                print("[BROKER_TRUTH] reconciler stopped")
            except Exception as exc:
                print(f"[BROKER_TRUTH_WARN] failed_to_stop_reconciler: {exc}")

        try:
            orchestrator.execution_router.engine.stop_reconciliation_daemon(timeout_sec=5.0)
            print("[RECON] reconciliation daemon stopped")
        except Exception as exc:
            print(f"[RECON_WARN] failed_to_stop_reconciliation_daemon: {exc}")


if __name__ == "__main__":
    main()
