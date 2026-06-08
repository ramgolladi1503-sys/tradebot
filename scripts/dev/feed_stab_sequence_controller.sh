#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/Users/madhuram/tradebot"
POLL_SECONDS="${POLL_SECONDS:-120}"

cd "$REPO_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

current_branch() {
  git branch --show-current
}

sync_main() {
  log "Syncing main with origin/main"
  git checkout main
  git fetch origin
  git reset --hard origin/main
  git status -sb
}

check_required_green() {
  local pr="$1"

  local pr_json
  if ! pr_json="$(gh pr view "$pr" --json statusCheckRollup,mergeStateStatus,isDraft 2>/dev/null)"; then
    echo "PENDING_CHECKS"
    echo "gh pr view failed for PR #$pr"
    return 1
  fi

  if [[ -z "$pr_json" ]]; then
    echo "PENDING_CHECKS"
    echo "empty GitHub response for PR #$pr"
    return 1
  fi

  local pr_json_file
  pr_json_file="$(mktemp "/tmp/pr_checks_${pr}.XXXXXX.json")"
  printf '%s\n' "$pr_json" > "$pr_json_file"

  python - "$pr" "$pr_json_file" <<'PY'
import json
import sys

pr = sys.argv[1]
path = sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)

if data.get("isDraft"):
    print(f"PR #{pr} is draft")
    sys.exit(3)

checks = data.get("statusCheckRollup") or []
bad = []
pending = []

for c in checks:
    name = c.get("name") or c.get("context") or c.get("__typename") or "unknown"
    state = (c.get("state") or c.get("conclusion") or "").upper()
    if state in {"FAILURE", "ERROR", "TIMED_OUT", "ACTION_REQUIRED", "CANCELLED", "STALE"}:
        bad.append((name, state))
    elif state in {"PENDING", "IN_PROGRESS", "QUEUED", "WAITING", "REQUESTED", "EXPECTED", ""}:
        pending.append((name, state))

if bad:
    print("BAD_CHECKS")
    for name, state in bad:
        print(f"{state}: {name}")
    sys.exit(2)

if pending:
    print("PENDING_CHECKS")
    for name, state in pending:
        print(f"{state}: {name}")
    sys.exit(1)

print("ALL_GREEN_OR_NON_BLOCKING")
sys.exit(0)
PY
  rm -f "$pr_json_file"
}

watch_until_green_or_red() {
  local pr="$1"

  while true; do
    log "Polling PR #$pr"
    gh pr checks "$pr" || true

    set +e
    check_required_green "$pr"
    rc="$?"
    set -e

    if [[ "$rc" == "0" ]]; then
      log "PR #$pr checks are green/non-blocking."
      return 0
    fi

    if [[ "$rc" == "2" ]]; then
      log "PR #$pr has red checks."
      log "Inspect with:"
      log "  gh run list --branch \$(gh pr view $pr --json headRefName -q .headRefName) --limit 10"
      log "  gh run view <FAILED_RUN_ID> --log-failed"
      return 2
    fi

    if [[ "$rc" == "3" ]]; then
      log "PR #$pr is draft or blocked."
      return 3
    fi

    log "PR #$pr checks still pending. Sleeping ${POLL_SECONDS}s."
    sleep "$POLL_SECONDS"
  done
}

merge_green_pr() {
  local pr="$1"

  log "Merging PR #$pr with normal squash merge"
  gh pr view "$pr" --json mergeStateStatus,statusCheckRollup,isDraft,url

  if ! gh pr merge "$pr" --squash --delete-branch; then
    log "Normal merge failed for PR #$pr."
    log "Rechecking PR #$pr after merge failure..."
    local pr_state
    pr_state="$(gh pr view "$pr" --json mergeStateStatus,statusCheckRollup,isDraft,mergedAt,state,url || true)"
    printf '%s\n' "$pr_state"

    if printf '%s' "$pr_state" | grep -Eq '"status":"(OPEN|MERGEABLE|BLOCKED)"|"statusCheckRollup".*"status":"(IN_PROGRESS|QUEUED|PENDING)"'; then
      log "Merge failed while checks or mergeability are still unsettled; continue polling."
      return 1
    fi

    log "If branch protection or permissions require human action, this is a hard blocker."
    return 2
  fi

  while true; do
    merged="$(gh pr view "$pr" --json mergedAt,state -q 'if .state == "MERGED" then "true" else "false" end' || echo false)"
    if [[ "$merged" == "true" ]]; then
      log "PR #$pr is merged."
      break
    fi

    log "Merge command returned but PR #$pr is not yet marked merged. Sleeping ${POLL_SECONDS}s."
    sleep "$POLL_SECONDS"
  done

  sync_main
}

continue_current_pr() {
  local pr="$1"

  log "Continuing current PR #$pr"
  while true; do
    set +e
    watch_until_green_or_red "$pr"
    rc="$?"
    set -e

    if [[ "$rc" == "0" ]]; then
      set +e
      merge_green_pr "$pr"
      rc="$?"
      set -e
      if [[ "$rc" == "0" ]]; then
        break
      fi
      if [[ "$rc" == "1" ]]; then
        continue
      fi
      exit "$rc"
    fi

    if [[ "$rc" == "1" ]]; then
      continue
    fi

    log "Cannot merge PR #$pr because checks are not green."
    exit "$rc"
  done
}

next_branch_for_pr_number() {
  local seq="$1"

  case "$seq" in
    2) echo "ram/feed-stab-02-feed-supervisor-state-machine" ;;
    3) echo "ram/feed-stab-03-reconnect-quarantine" ;;
    4) echo "ram/feed-stab-04-feed-readiness-contract" ;;
    5) echo "ram/feed-stab-05-exact-option-token-freshness" ;;
    6) echo "ram/feed-stab-06-subscription-truth-resubscribe" ;;
    7) echo "ram/feed-stab-07-feed-event-journal" ;;
    8) echo "ram/feed-stab-08-feed-soak-runner" ;;
    9) echo "ram/feed-stab-09-feed-soak-acceptance-gate" ;;
    10) echo "ram/feed-stab-10-candidate-resume-integrity" ;;
    11) echo "ram/feed-stab-11-crash-containment-watchdog" ;;
    12) echo "ram/feed-stab-12-market-session-proof-pack" ;;
    *) echo "" ;;
  esac
}

next_title_for_pr_number() {
  local seq="$1"

  case "$seq" in
    2) echo "FEED-STAB-02: Feed supervisor state machine" ;;
    3) echo "FEED-STAB-03: Reconnect quarantine window" ;;
    4) echo "FEED-STAB-04: Feed readiness for candidates contract" ;;
    5) echo "FEED-STAB-05: Exact option token freshness gate" ;;
    6) echo "FEED-STAB-06: Subscription truth and resubscribe verification" ;;
    7) echo "FEED-STAB-07: Feed event journal" ;;
    8) echo "FEED-STAB-08: Feed soak runner" ;;
    9) echo "FEED-STAB-09: Feed soak acceptance gate" ;;
    10) echo "FEED-STAB-10: Candidate resume integrity after recovery" ;;
    11) echo "FEED-STAB-11: Feed crash containment and watchdog exit policy" ;;
    12) echo "FEED-STAB-12: Full market session proof pack" ;;
    *) echo "" ;;
  esac
}

main() {
  local current_pr="${1:-534}"
  local current_seq="${2:-2}"

  log "Starting durable FEED-STAB controller from PR #$current_pr / sequence $current_seq"

  continue_current_pr "$current_pr"

  local next_seq=$((current_seq + 1))

  if [[ "$next_seq" -gt 12 ]]; then
    log "FEED-STAB-12 merged. Sequence complete."
    exit 0
  fi

  local next_branch
  next_branch="$(next_branch_for_pr_number "$next_seq")"

  log "Ready for next PR: FEED-STAB-${next_seq}"
  log "Next branch should be: $next_branch"
  log "READY_FOR_NEXT_PR_IMPLEMENTATION: FEED-STAB-${next_seq}"
  log "Stop here for Codex to implement the next scoped PR from updated main."
}

main "$@"
