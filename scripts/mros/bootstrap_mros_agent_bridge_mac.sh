#!/usr/bin/env bash
set -euo pipefail

SOURCE_REPO="${1:-/Users/madhuram/tradebot}"
ROOT="${MROS_AGENT_BRIDGE_ROOT:-/Users/madhuram/.mros-agent-bridge}"
BRIDGE_WT="$ROOT/bridge"
QUEUE_WT="$ROOT/queue"
CONFIG="$ROOT/config.json"
QUEUE_BRANCH="automation/mros-agent-queue-v1"

mkdir -p "$ROOT" "$ROOT/jobs" "$ROOT/state"

cd "$SOURCE_REPO"
git fetch origin research/mros-agent-bridge-v1 "$QUEUE_BRANCH"

if [[ ! -e "$BRIDGE_WT/.git" ]]; then
  git worktree add --detach "$BRIDGE_WT" origin/research/mros-agent-bridge-v1
else
  git -C "$BRIDGE_WT" fetch origin research/mros-agent-bridge-v1
  git -C "$BRIDGE_WT" checkout --detach origin/research/mros-agent-bridge-v1
fi

if [[ ! -e "$QUEUE_WT/.git" ]]; then
  git worktree add --detach "$QUEUE_WT" "origin/$QUEUE_BRANCH"
  git -C "$QUEUE_WT" switch -C mros-agent-queue-worker "origin/$QUEUE_BRANCH"
else
  if [[ -n "$(git -C "$QUEUE_WT" status --porcelain)" ]]; then
    echo "QUEUE_WORKTREE_NOT_CLEAN: $QUEUE_WT" >&2
    exit 12
  fi
  git -C "$QUEUE_WT" fetch origin "$QUEUE_BRANCH"
  git -C "$QUEUE_WT" rebase "origin/$QUEUE_BRANCH"
fi

cat > "$CONFIG" <<JSON
{
  "repo_root": "$QUEUE_WT",
  "allowed_repo_realpath": "$QUEUE_WT",
  "worktree_root": "$ROOT/jobs",
  "state_root": "$ROOT/state",
  "max_parallel_jobs": 4,
  "backends": {
    "codex": {
      "argv": [
        "python3",
        "$BRIDGE_WT/scripts/mros/mros_codex_backend.py",
        "--worktree", "{worktree}",
        "--packet", "{packet}",
        "--output", "{output}"
      ],
      "timeout_seconds": 3600
    }
  }
}
JSON

printf '%s\n' "=== MROS AGENT BRIDGE PREFLIGHT ==="
printf 'SOURCE_REPO=%s\n' "$SOURCE_REPO"
printf 'BRIDGE_WT=%s\n' "$BRIDGE_WT"
printf 'QUEUE_WT=%s\n' "$QUEUE_WT"
printf 'QUEUE_BRANCH=%s\n' "$QUEUE_BRANCH"
printf 'CONFIG=%s\n' "$CONFIG"

git -C "$QUEUE_WT" status --short --branch
python3 --version
git --version
codex --version

printf '%s\n' "=== BRIDGE TESTS ==="
python3 -m pytest -q "$BRIDGE_WT/tests/mros/test_mros_agent_bridge.py"

printf '%s\n' "=== CODEX HEALTH ==="
codex doctor --json || true

printf '%s\n' "MROS_AGENT_BRIDGE_BOOTSTRAP_READY"
printf '%s\n' "Start worker with:"
printf 'python3 %q --config %q --queue-branch %q\n' \
  "$BRIDGE_WT/scripts/mros/mros_agent_git_worker.py" "$CONFIG" "$QUEUE_BRANCH"
