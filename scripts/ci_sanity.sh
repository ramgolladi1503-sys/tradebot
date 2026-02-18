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

echo "=== [PASS] ci_sanity"
