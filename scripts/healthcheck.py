"""Migration note:
Unified healthcheck entrypoint for operators.
Outputs PASS/DEGRADED/FAIL with explicit reasons and mode-aware severity.
"""

from __future__ import annotations

from core.paths import data_root, logs_dir
import json
import sqlite3
import sys
import time
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.market_context import derive_market_context
from core.outcome_truth_pipeline import assess_outcome_truth
from core.readiness_gate import run_readiness_state
from core.slo_guard import evaluate_slo_status
from core.time_utils import now_ist, now_utc_epoch
from core.trade_log_paths import ensure_trade_log_exists


def _check_config() -> tuple[bool, list[str]]:
    reasons: list[str] = []
    mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    if mode not in {"LIVE", "PAPER", "SIM"}:
        reasons.append(f"invalid_execution_mode:{mode}")
    symbols = list(getattr(cfg, "SYMBOLS", []) or [])
    if not symbols:
        reasons.append("missing_symbols")
    db_path = str(getattr(cfg, "TRADE_DB_PATH", "") or "").strip()
    if not db_path:
        reasons.append("missing_trade_db_path")
    return (len(reasons) == 0), reasons


def _check_db_writable() -> tuple[bool, str]:
    try:
        db_path = Path(getattr(cfg, "TRADE_DB_PATH", str(data_root() / "trades.db")))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS __healthcheck_probe__ (id INTEGER PRIMARY KEY, ts REAL)")
            conn.execute("INSERT INTO __healthcheck_probe__ (ts) VALUES (?)", (float(now_utc_epoch()),))
            conn.execute("DELETE FROM __healthcheck_probe__")
            conn.commit()
        return True, "ok"
    except Exception as exc:
        return False, f"db_not_writable:{exc}"


def _check_clock_sanity() -> tuple[bool, str]:
    t1 = time.time()
    t2 = time.time()
    if t2 < t1:
        return False, "non_monotonic_clock"
    return True, "ok"


def _downgrade_non_live_blockers(blockers: list[str], mode: str) -> tuple[list[str], list[str]]:
    if mode == "LIVE":
        return blockers, []
    downgraded = []
    kept = []
    soft_prefixes = (
        "auth",
        "kite",
        "feed",
        "decision_gate",
        "readiness",
    )
    for reason in blockers:
        reason_text = str(reason)
        if reason_text.lower().startswith(soft_prefixes):
            downgraded.append(reason_text)
        else:
            kept.append(reason_text)
    return kept, downgraded


def run_healthcheck() -> dict:
    ensure_trade_log_exists()
    for raw_path in (
        getattr(cfg, "EXECUTION_INTENTS_LOG_PATH", str(logs_dir() / "execution_intents.jsonl")),
        getattr(cfg, "DECISION_LOG_PATH", str(logs_dir() / "decision_events.jsonl")),
        getattr(cfg, "REJECT_REASONS_LOG_PATH", str(logs_dir() / "reject_reasons.jsonl")),
    ):
        try:
            p = Path(str(raw_path))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch(exist_ok=True)
        except Exception:
            pass
    ctx = derive_market_context()
    mode = str(ctx.mode)

    checks: dict[str, object] = {
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now_ist().isoformat(),
        "mode": mode,
        "market_open": bool(ctx.is_market_open),
        "require_live_quotes": bool(ctx.require_live_quotes),
        "allow_stale_quotes": bool(ctx.allow_stale_quotes),
        "planning_only": bool(getattr(ctx, "planning_only", False)),
    }
    blockers: list[str] = []
    warnings: list[str] = []

    cfg_ok, cfg_reasons = _check_config()
    checks["config"] = {"ok": cfg_ok, "reasons": cfg_reasons}
    if not cfg_ok:
        blockers.extend(cfg_reasons)

    db_ok, db_reason = _check_db_writable()
    checks["db_writable"] = {"ok": db_ok, "reason": db_reason}
    if not db_ok:
        blockers.append(db_reason)

    clock_ok, clock_reason = _check_clock_sanity()
    checks["clock_sanity"] = {"ok": clock_ok, "reason": clock_reason}
    if not clock_ok:
        blockers.append(clock_reason)

    readiness = run_readiness_state(write_log=False)
    checks["readiness"] = {
        "state": readiness.state.value,
        "can_trade": readiness.can_trade,
        "blockers": list(readiness.blockers),
        "warnings": list(readiness.warnings),
    }
    readiness_blockers = [f"readiness:{r}" for r in list(readiness.blockers)]
    blockers.extend(readiness_blockers)
    warnings.extend([f"readiness_warn:{w}" for w in list(readiness.warnings)])

    slo = evaluate_slo_status(enforce_failover=False)
    checks["slo_guard"] = slo
    if not bool(slo.get("ok", False)):
        reason = ",".join(list(slo.get("reasons") or [])) or "slo_breach"
        if mode == "LIVE":
            blockers.append(f"slo:{reason}")
        else:
            warnings.append(f"slo:{reason}")
    warnings.extend([f"slo_warn:{w}" for w in list(slo.get("warnings") or [])])

    data_truth = assess_outcome_truth(strict=False)
    checks["data_truth"] = data_truth
    data_truth_blockers = [str(x) for x in list(data_truth.get("blockers") or []) if str(x).strip()]
    if data_truth_blockers:
        reason_text = ",".join(data_truth_blockers)
        enforce_live = bool(getattr(cfg, "HEALTHCHECK_ENFORCE_DATA_TRUTH_LIVE", True))
        if mode == "LIVE" and enforce_live:
            blockers.append(f"data_truth:{reason_text}")
        else:
            warnings.append(f"data_truth:{reason_text}")

    blockers, downgraded = _downgrade_non_live_blockers(blockers, mode=mode)
    warnings.extend([f"downgraded:{r}" for r in downgraded])

    if blockers:
        status = "FAIL"
    elif warnings:
        status = "DEGRADED"
    else:
        status = "PASS"

    payload = {
        "status": status,
        "mode": mode,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
    }
    print(json.dumps(payload, indent=2, default=str))
    print(f"HEALTHCHECK_STATUS={status}")
    return payload


def main() -> int:
    payload = run_healthcheck()
    return 1 if payload.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
