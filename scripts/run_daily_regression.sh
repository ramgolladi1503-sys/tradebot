#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="${PYTHONPATH:-.}"
DESK_ID="${DESK_ID:-DEFAULT}"
RUN_DATE="${RUN_DATE:-$(python - <<'PY'
from datetime import datetime
from zoneinfo import ZoneInfo
print(datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d"))
PY
)}"

pytest_exit=0
health_gate_exit=0

echo "[daily_regression] running pytest -q"
pytest -q || pytest_exit=$?

echo "[daily_regression] running health gate --strict"
python -m core.health_gate --desk "$DESK_ID" --strict || health_gate_exit=$?

export PYTEST_EXIT="$pytest_exit"
export HEALTH_GATE_EXIT="$health_gate_exit"
export DESK_ID
export RUN_DATE

python - <<'PY'
import json
import os
from core.events import write_json_atomic
from core.paths import logs_dir

run_date = str(os.environ.get("RUN_DATE", "")).strip() or "unknown-date"
desk_id = str(os.environ.get("DESK_ID", "DEFAULT") or "DEFAULT")
pytest_exit = int(os.environ.get("PYTEST_EXIT", "1"))
health_gate_exit = int(os.environ.get("HEALTH_GATE_EXIT", "1"))

daily_dir = logs_dir() / "daily_regression"
report_path = daily_dir / f"{run_date}.json"
payload = {
    "date": run_date,
    "desk_id": desk_id,
    "status": "PASS" if pytest_exit == 0 and health_gate_exit == 0 else "FAIL",
    "pytest_exit": pytest_exit,
    "health_gate_exit": health_gate_exit,
    "artifacts": {
        "health_gate_report_json": str(logs_dir() / "health_gate_report.json"),
        "health_gate_report_md": str(logs_dir() / "health_gate_report.md"),
    },
}
write_json_atomic(report_path, payload)
print(f"[daily_regression] wrote report: {report_path}")
PY

if [[ "$pytest_exit" -ne 0 || "$health_gate_exit" -ne 0 ]]; then
  exit 1
fi

exit 0
