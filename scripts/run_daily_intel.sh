#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_daily_intel.sh [--date YYYY-MM-DD]
  scripts/run_daily_intel.sh -d YYYY-MM-DD
  scripts/run_daily_intel.sh --help

Runs:
  1) python -m core.analytics.outcome_replay --date DATE --scope rejected
  2) python -m core.analytics.daily_report --date DATE

Default DATE:
  Yesterday in local timezone.
EOF
}

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]] && command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "$PYTHON_BIN"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return
  fi
  if [[ -x "/opt/anaconda3/bin/python" ]]; then
    echo "/opt/anaconda3/bin/python"
    return
  fi
  if [[ -x "/usr/bin/python3" ]]; then
    echo "/usr/bin/python3"
    return
  fi
  echo ""
}

PYTHON_BIN="$(resolve_python)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python not found. Set PYTHON_BIN or install python." >&2
  exit 1
fi

DATE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--date)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for $1" >&2
        usage
        exit 2
      fi
      DATE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$DATE" ]]; then
  DATE="$("$PYTHON_BIN" - <<'PY'
from datetime import datetime, timedelta

print((datetime.now().astimezone().date() - timedelta(days=1)).isoformat())
PY
)"
fi

echo "[daily_intel] date=$DATE"
echo "[daily_intel] running outcome replay (rejected)"
"$PYTHON_BIN" -m core.analytics.outcome_replay --date "$DATE" --scope rejected

echo "[daily_intel] running daily report"
"$PYTHON_BIN" -m core.analytics.daily_report --date "$DATE"

OUTCOME_PATH="$ROOT/runtime/analytics/outcomes/${DATE}.jsonl"
REPORT_MD_PATH="$ROOT/runtime/analytics/reports/${DATE}/daily_report.md"
REPORT_JSON_PATH="$ROOT/runtime/analytics/reports/${DATE}/daily_report.json"

echo "[daily_intel] outputs:"
echo "  outcome_replay: $OUTCOME_PATH"
echo "  daily_report_md: $REPORT_MD_PATH"
echo "  daily_report_json: $REPORT_JSON_PATH"
echo "[daily_intel] done"
