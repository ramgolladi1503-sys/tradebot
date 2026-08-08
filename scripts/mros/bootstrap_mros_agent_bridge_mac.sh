#!/usr/bin/env bash
set -euo pipefail

SOURCE_REPO="${1:-/Users/madhuram/tradebot}"
ROOT="${MROS_AGENT_BRIDGE_ROOT:-/Users/madhuram/.mros-agent-bridge}"
BRIDGE_WT="$ROOT/bridge"
PROGRAM_WT="$ROOT/program"
CONFIG="$ROOT/config.json"

mkdir -p "$ROOT" "$ROOT/jobs" "$ROOT/state"

cd "$SOURCE_REPO"
git fetch origin research/mros-agent-bridge-v1 research/mros-program-v1

if [[ ! -e "$BRIDGE_WT/.git" ]]; then
  git worktree add --detach "$BRIDGE_WT" origin/research/mros-agent-bridge-v1
else
  git -C "$BRIDGE_WT" fetch origin research/mros-agent-bridge-v1
  git -C "$BRIDGE_WT" checkout --detach origin/research/mros-agent-bridge-v1
fi

if [[ ! -e "$PROGRAM_WT/.git" ]]; then
  # A local branch may already exist elsewhere, so create the worker checkout
  # from the remote ref and then attach it only if legal.
  git worktree add --detach "$PROGRAM_WT" origin/research/mros-program-v1
  git -C "$PROGRAM_WT" switch -C research/mros-program-v1 --track origin/research/mros-program-v1 || \
    git -C "$PROGRAM_WT" switch -C research/mros-program-v1 origin/research/mros-program-v1
else
  git -C "$PROGRAM_WT" fetch origin research/mros-program-v1
  git -C "$PROGRAM_WT" checkout research/mros-program-v1
  git -C "$PROGRAM_WT" pull --ff-only origin research/mros-program-v1
fi

cat > "$CONFIG" <<JSON
{
  "repo_root": "$PROGRAM_WT",
  "allowed_repo_realpath": "$PROGRAM_WT",
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
printf 'PROGRAM_WT=%s\n' "$PROGRAM_WT"
printf 'CONFIG=%s\n' "$CONFIG"

git -C "$PROGRAM_WT" status --short --branch
python3 --version
git --version
codex --version

printf '%s\n' "=== BRIDGE TESTS ==="
python3 -m pytest -q "$BRIDGE_WT/tests/mros/test_mros_agent_bridge.py"

printf '%s\n' "=== CODEX HEALTH ==="
codex doctor --json || true

printf '%s\n' "MROS_AGENT_BRIDGE_BOOTSTRAP_READY"
printf '%s\n' "Start worker with:"
printf 'python3 %q --config %q --branch research/mros-program-v1\n' \
  "$BRIDGE_WT/scripts/mros/mros_agent_git_worker.py" "$CONFIG"
