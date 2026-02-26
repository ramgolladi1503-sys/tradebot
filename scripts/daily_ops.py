# Migration note:
# Daily ops now ensures canonical trade-log creation and returns structured status/reasons.

import json
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import subprocess
import sys

from config import config as cfg
from core.trade_log_paths import ensure_trade_log_exists

ROOT = Path(__file__).resolve().parents[1]

STEPS: list[tuple[list[str], bool]] = [
    (["scripts/repair_ticks.py"], False),
    (["scripts/backfill_trades_db.py"], False),
    (["scripts/reconcile_outcomes_truth.py"], False),
    (["scripts/live_fills_sync.py"], False),
    (["scripts/hash_trade_log.py"], True),
    (["scripts/data_manifest.py"], True),
    (["scripts/run_execution_analytics.py"], False),
    (["scripts/data_qc.py"], False),
    (["scripts/sla_check.py"], False),
    (["scripts/daily_rollup.py"], False),
    (["scripts/reconcile_fills.py"], False),
    (["scripts/run_decay_daily.py"], False),
    (["scripts/run_daily_audit.py"], False),
    (["scripts/live_enablement_gate.py", "--audit-only"], False),
]


def run(cmd: list[str], *, optional: bool = False) -> str:
    resolved = list(cmd or [])
    if resolved:
        first = str(resolved[0])
        if first.endswith(".py"):
            script_path = Path(first)
            if not script_path.is_absolute():
                script_path = (ROOT / script_path).resolve()
            resolved[0] = str(script_path)
    try:
        subprocess.run([sys.executable] + resolved, check=True, cwd=ROOT)
        return "ok"
    except subprocess.CalledProcessError as exc:
        if optional:
            print(f"[daily_ops][WARN] optional step failed: {' '.join(cmd)} rc={exc.returncode}")
            return f"optional_failed:rc={exc.returncode}"
        raise


def _load_daily_audit_status() -> dict | None:
    path = Path("logs/daily_audit_status_latest.json")
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _load_outcome_truth_status() -> dict | None:
    path = Path(getattr(cfg, "OUTCOME_TRUTH_STATUS_PATH", "logs/outcome_truth_status_latest.json"))
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def main() -> dict:
    trade_log = ensure_trade_log_exists()
    try:
        size = trade_log.stat().st_size
    except Exception:
        size = 0
    reasons: list[str] = []
    optional_skips: list[str] = []
    if size <= 0:
        print(f"[daily_ops][WARN] trade log is empty: {trade_log}")
        optional_skips.append("trade_log_empty")
    step_failures: list[str] = []
    for cmd, optional in STEPS:
        try:
            outcome = run(cmd, optional=optional)
        except subprocess.CalledProcessError as exc:
            step = " ".join(cmd)
            step_failures.append(step)
            reasons.append(f"step_failed:{step}:rc={exc.returncode}")
            raise
        except Exception as exc:
            step = " ".join(cmd)
            step_failures.append(step)
            reasons.append(f"step_failed:{step}:{exc}")
            raise
        else:
            if optional and str(outcome).startswith("optional_failed:"):
                step = " ".join(cmd)
                optional_skips.append(f"optional_step_failed:{step}:{outcome}")
    audit_status = _load_daily_audit_status()
    if audit_status:
        audit_state = str(audit_status.get("status") or "").lower()
        audit_reason = str(audit_status.get("reason_code") or audit_status.get("reason") or "").strip()
        if audit_state == "ok_with_skips" and audit_reason:
            key = f"daily_audit:{audit_reason}"
            if key not in optional_skips:
                optional_skips.append(key)
            print(f"[daily_ops][INFO] daily_audit degraded: {audit_reason}")
    outcome_truth_status = _load_outcome_truth_status()
    if outcome_truth_status:
        truth_state = str(outcome_truth_status.get("status") or "").lower()
        truth_blockers = [str(x) for x in list(outcome_truth_status.get("blockers") or []) if str(x).strip()]
        if truth_state in {"degraded", "fail"} and truth_blockers:
            for code in truth_blockers:
                key = f"outcome_truth:{code}"
                if key not in optional_skips:
                    optional_skips.append(key)
            print(f"[daily_ops][INFO] outcome_truth degraded: {','.join(truth_blockers)}")
    reasons.extend(optional_skips)
    status = "ok_with_skips" if reasons and not step_failures else "ok"
    return {"status": status, "reasons": reasons, "trade_log": str(trade_log)}

if __name__ == "__main__":
    main()
