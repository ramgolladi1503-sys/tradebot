#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[daily_ops] auth warmup"
python "$ROOT/scripts/auth_warmup.py"

echo "[daily_ops] readiness gate"
python "$ROOT/scripts/readiness_gate.py"

echo "[daily_ops] daily audit"
python "$ROOT/scripts/run_daily_audit.py"

echo "[daily_ops] dr backup"
python "$ROOT/scripts/dr_backup.py"

echo "[daily_ops] export trades"
python "$ROOT/scripts/export_trade_log_csv.py"
