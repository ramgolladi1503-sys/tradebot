#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHONPATH=. python - <<'PY'
from core import risk_halt

payload = risk_halt.set_halt(
    "manual_kill_switch",
    {"source": "scripts/kill_switch.sh"},
)
print(payload)
PY
