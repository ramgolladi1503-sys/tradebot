# Migration note:
# Daily ops now ensures canonical trade-log creation and returns structured status/reasons.

from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import subprocess
import sys

from core.trade_log_paths import ensure_trade_log_exists


STEPS: list[tuple[list[str], bool]] = [
    (["scripts/repair_ticks.py"], False),
    (["scripts/backfill_trades_db.py"], False),
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
]


def run(cmd: list[str], *, optional: bool = False) -> None:
    try:
        subprocess.run([sys.executable] + cmd, check=True)
    except subprocess.CalledProcessError as exc:
        if optional:
            print(f"[daily_ops][WARN] optional step failed: {' '.join(cmd)} rc={exc.returncode}")
            return
        raise


def main() -> dict:
    trade_log = ensure_trade_log_exists()
    try:
        size = trade_log.stat().st_size
    except Exception:
        size = 0
    reasons: list[str] = []
    if size <= 0:
        print(f"[daily_ops][WARN] trade log is empty: {trade_log}")
        reasons.append("trade_log_empty")
    step_failures: list[str] = []
    for cmd, optional in STEPS:
        try:
            run(cmd, optional=optional)
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
    status = "skipped" if reasons and not step_failures else "ok"
    return {"status": status, "reasons": reasons, "trade_log": str(trade_log)}

if __name__ == "__main__":
    main()
