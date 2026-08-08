#!/usr/bin/env bash
set -euo pipefail
SOURCE_REPO="${1:-/Users/madhuram/tradebot}"
ROOT="${MROS_AGENT_BRIDGE_ROOT:-/Users/madhuram/.mros-agent-bridge}"
BRIDGE_WT="$ROOT/bridge"
STATE="$ROOT/state"
cd "$SOURCE_REPO"
git fetch origin research/mros-agent-bridge-v1 research/mros-program-v1 automation/mros-agent-queue-v1
if [[ ! -e "$BRIDGE_WT/.git" ]]; then
  git worktree add --detach "$BRIDGE_WT" origin/research/mros-agent-bridge-v1
else
  if [[ -n "$(git -C "$BRIDGE_WT" status --porcelain)" ]]; then echo "BRIDGE_WORKTREE_NOT_CLEAN:$BRIDGE_WT" >&2; exit 10; fi
  git -C "$BRIDGE_WT" fetch origin research/mros-agent-bridge-v1
  git -C "$BRIDGE_WT" checkout --detach origin/research/mros-agent-bridge-v1
fi
printf '%s\n' '=== MROS AUTONOMOUS SUPERVISOR TESTS ==='
python3 -m pytest -q \
  "$BRIDGE_WT/tests/mros/test_mros_agent_bridge.py" \
  "$BRIDGE_WT/tests/mros/test_mros_autonomous_supervisor.py" \
  "$BRIDGE_WT/tests/mros/test_mros_state_transition_engine.py"
printf '%s\n' '=== SUPERVISOR ONE-SHOT DRY/REAL DISCOVERY ==='
# One-shot may legally perform the stale-calibration -> review-preparation transition.
python3 "$BRIDGE_WT/scripts/mros/install_mros_autonomous_services_mac.sh" "$SOURCE_REPO"
sleep 5
printf '%s\n' '=== SERVICE STATUS ==='
launchctl print "gui/$(id -u)/com.aixion.mros-agent-worker" | grep -E 'state =|pid =|last exit code' | head -20 || true
launchctl print "gui/$(id -u)/com.aixion.mros-autonomous-supervisor" | grep -E 'state =|pid =|last exit code' | head -20 || true
printf '%s\n' '=== SUPERVISOR HEALTH ==='
if [[ -f "$STATE/supervisor_health.json" ]]; then cat "$STATE/supervisor_health.json"; else echo SUPERVISOR_HEALTH_NOT_YET_CREATED; fi
printf '%s\n' MROS_AUTONOMOUS_SUPERVISOR_BOOTSTRAP_COMPLETE
