#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}"

SHOW_LIVE=0
ALLOW_DIRTY=0

usage() {
  cat <<'EOF'
Usage: scripts/validate_merge_safe.sh [--live] [--allow-dirty]

Default mode is offline-only:
  - verifies the branch is clean
  - checks it is based on origin/main when that ref is available locally
  - runs the targeted pytest set
  - runs the no-executable-trades diagnostic
  - greps runtime logs for fallback/executable markers

--live
  After the offline gates pass, run the safe live wrapper so market-open
  validation can confirm auth and startup behavior.

--allow-dirty
  Skip the clean-worktree gate. This is intended for debugging only.
EOF
}

log() {
  echo "[VALIDATE_MERGE] $*"
}

run_step() {
  local name="$1"
  shift
  log "Running: $name"
  "$@"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --live)
      SHOW_LIVE=1
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log "Unknown argument: $1"
      usage
      exit 2
      ;;
  esac
  shift
done

cd "$ROOT_DIR"

log "Repo: $ROOT_DIR"
log "Branch: $(git branch --show-current)"
log "HEAD: $(git rev-parse --short HEAD)"

if [[ -n "$(git status --short)" && "$ALLOW_DIRTY" -ne 1 ]]; then
  log "Working tree is dirty; refusing to validate merge safety."
  git status --short
  exit 2
fi

if git rev-parse --verify --quiet origin/main >/dev/null; then
  if ! git merge-base --is-ancestor origin/main HEAD; then
    log "origin/main is not an ancestor of HEAD."
    log "Fetch the latest main and rebase before merging:"
    log "  git fetch origin"
    log "  git rebase origin/main"
    exit 2
  fi
  log "Branch is based on local origin/main: $(git rev-parse --short origin/main)"
else
  log "Local origin/main ref is unavailable; skipping ancestry check."
fi

run_step \
  "targeted pytest suite" \
  python -m pytest \
    tests/test_option_token_resolver.py \
    tests/test_review_queue_live_entry.py \
    tests/test_trade_state_engine.py \
    tests/test_diagnose_no_executable_trades.py \
    tests/core/test_token_coverage_threshold.py \
    tests/test_main_startup_audit.py \
    -q

run_step "no-executable-trades diagnostic" python scripts/diagnose_no_executable_trades.py logs/

log "Log markers: looking for fallback and executable signals"
log_targets=()
for candidate in logs runtime .runtime; do
  if [[ -d "$candidate" ]]; then
    log_targets+=("$candidate")
  fi
done
if [[ "${#log_targets[@]}" -gt 0 ]]; then
  rg -n \
    "OPTION_TOKEN_RESOLVED|safe_nearest_contract_fallback|OPTION_TOKEN_NOT_FOUND|CONTRACT_RESOLUTION_FAILED|recovered_fallback|EXECUTABLE|ADVISORY_ONLY|READY_NOT_APPROVED" \
    "${log_targets[@]}" \
    || true
else
  log "No logs/runtime directories found; skipping marker grep."
fi

if [[ "$SHOW_LIVE" -eq 1 ]]; then
  log "Live mode enabled."
  run_step "kite auth check" python scripts/check_kite_auth.py --mode LIVE
  log "Starting safe live wrapper; stop with Ctrl+C after startup is confirmed."
  run_step "live wrapper" bash "$ROOT_DIR/scripts/run_live_safe.sh"
fi

log "Validation complete."
