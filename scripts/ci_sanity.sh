#!/bin/sh
set -eu

run_step() {
  step_name="$1"
  shift
  echo "=== [RUN] ${step_name}"
  if "$@"; then
    echo "=== [PASS] ${step_name}"
  else
    status=$?
    echo "=== [FAIL] ${step_name} (exit=${status})"
    exit "${status}"
  fi
}

run_step "compileall" python -m compileall -q .
run_step "pytest" pytest -q
run_step "import_core_market_calendar" python -c "import core.market_calendar"
run_step "live_enablement_gate" env \
  SLO_FAILOVER_STATE_PATH=logs/slo_failover_state.json \
  SLO_EVENT_LOG_PATH=logs/slo_events.jsonl \
  LIVE_ENABLEMENT_AUDIT_PATH=logs/live_enablement_audit_latest.json \
  ACCEPTANCE_GATE_LATEST_PATH=logs/acceptance_gate_latest.json \
  python scripts/live_enablement_gate.py --strict-if-live

echo "=== [PASS] ci_sanity"
