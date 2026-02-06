from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import subprocess
import sys

def run(cmd):
    subprocess.run([sys.executable] + cmd, check=True)

if __name__ == "__main__":
    run(["scripts/repair_ticks.py"])
    run(["scripts/backfill_trades_db.py"])
    run(["scripts/live_fills_sync.py"])
    run(["scripts/hash_trade_log.py"])
    run(["scripts/data_manifest.py"])
    run(["scripts/run_execution_analytics.py"])
    run(["scripts/data_qc.py"])
    run(["scripts/sla_check.py"])
    run(["scripts/daily_rollup.py"])
    run(["scripts/reconcile_fills.py"])
