#!/usr/bin/env bash
set -euo pipefail
ROOT="${MROS_AGENT_BRIDGE_ROOT:-/Users/madhuram/.mros-agent-bridge}"
SOURCE_REPO="${1:-/Users/madhuram/tradebot}"
BRIDGE_WT="$ROOT/bridge"
AUTHORITY_WT="$ROOT/authority"
CONFIG="$ROOT/config.json"
STATE="$ROOT/state"
LOGS="$ROOT/logs"
LAUNCH="$HOME/Library/LaunchAgents"
mkdir -p "$STATE" "$LOGS" "$LAUNCH"
PYTHON="$(command -v python3)"
[[ -x "$PYTHON" ]] || { echo PYTHON3_NOT_FOUND >&2; exit 2; }
[[ -f "$CONFIG" ]] || { echo "CONFIG_MISSING:$CONFIG" >&2; exit 3; }
[[ -f "$BRIDGE_WT/scripts/mros/mros_agent_git_worker.py" ]] || { echo BRIDGE_WORKER_MISSING >&2; exit 4; }
[[ -f "$BRIDGE_WT/scripts/mros/mros_autonomous_supervisor.py" ]] || { echo SUPERVISOR_MISSING >&2; exit 5; }
[[ -f "$BRIDGE_WT/scripts/mros/mros_bridge_autoupdater.py" ]] || { echo BRIDGE_AUTOUPDATER_MISSING >&2; exit 8; }
SERVICE_PATH="${PATH:-/opt/anaconda3/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin}"
if command -v git-lfs >/dev/null 2>&1; then
  GIT_LFS_BIN="$(command -v git-lfs)"; GIT_LFS_DIR="$(dirname "$GIT_LFS_BIN")"
  case ":$SERVICE_PATH:" in *":$GIT_LFS_DIR:"*) ;; *) SERVICE_PATH="$GIT_LFS_DIR:$SERVICE_PATH" ;; esac
else
  echo GIT_LFS_NOT_FOUND_IN_BOOTSTRAP_PATH >&2; exit 7
fi
cd "$SOURCE_REPO"
git fetch origin research/mros-program-v1 research/mros-agent-bridge-v1 automation/mros-agent-queue-v1
if [[ ! -e "$AUTHORITY_WT/.git" ]]; then
  git worktree add "$AUTHORITY_WT" research/mros-program-v1
else
  if [[ -n "$(git -C "$AUTHORITY_WT" status --porcelain)" ]]; then echo "AUTHORITY_WORKTREE_NOT_CLEAN:$AUTHORITY_WT" >&2; exit 6; fi
  git -C "$AUTHORITY_WT" fetch origin research/mros-program-v1
  git -C "$AUTHORITY_WT" switch research/mros-program-v1
  git -C "$AUTHORITY_WT" merge --ff-only origin/research/mros-program-v1
fi
cat > "$LAUNCH/com.aixion.mros-agent-worker.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.aixion.mros-agent-worker</string>
<key>ProgramArguments</key><array><string>$PYTHON</string><string>$BRIDGE_WT/scripts/mros/mros_agent_git_worker.py</string><string>--config</string><string>$CONFIG</string><string>--queue-branch</string><string>automation/mros-agent-queue-v1</string></array>
<key>EnvironmentVariables</key><dict><key>PATH</key><string>$SERVICE_PATH</string></dict>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>10</integer>
<key>StandardOutPath</key><string>$LOGS/worker.out.log</string><key>StandardErrorPath</key><string>$LOGS/worker.err.log</string>
</dict></plist>
PLIST
cat > "$LAUNCH/com.aixion.mros-autonomous-supervisor.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.aixion.mros-autonomous-supervisor</string>
<key>ProgramArguments</key><array><string>$PYTHON</string><string>$BRIDGE_WT/scripts/mros/mros_autonomous_supervisor.py</string><string>--repo</string><string>$AUTHORITY_WT</string><string>--state-root</string><string>$STATE</string><string>--poll-seconds</string><string>15</string></array>
<key>EnvironmentVariables</key><dict><key>PATH</key><string>$SERVICE_PATH</string></dict>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>10</integer>
<key>StandardOutPath</key><string>$LOGS/supervisor.out.log</string><key>StandardErrorPath</key><string>$LOGS/supervisor.err.log</string>
</dict></plist>
PLIST
cat > "$LAUNCH/com.aixion.mros-bridge-autoupdater.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.aixion.mros-bridge-autoupdater</string>
<key>ProgramArguments</key><array><string>$PYTHON</string><string>$BRIDGE_WT/scripts/mros/mros_bridge_autoupdater.py</string><string>--source-repo</string><string>$SOURCE_REPO</string><string>--bridge-worktree</string><string>$BRIDGE_WT</string><string>--state-root</string><string>$STATE</string></array>
<key>EnvironmentVariables</key><dict><key>PATH</key><string>$SERVICE_PATH</string></dict>
<key>RunAtLoad</key><true/><key>StartInterval</key><integer>60</integer>
<key>StandardOutPath</key><string>$LOGS/updater.out.log</string><key>StandardErrorPath</key><string>$LOGS/updater.err.log</string>
</dict></plist>
PLIST
for label in com.aixion.mros-agent-worker com.aixion.mros-autonomous-supervisor com.aixion.mros-bridge-autoupdater; do
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$LAUNCH/$label.plist"
  launchctl enable "gui/$(id -u)/$label"
done
sleep 2
for label in com.aixion.mros-agent-worker com.aixion.mros-autonomous-supervisor com.aixion.mros-bridge-autoupdater; do launchctl print "gui/$(id -u)/$label" | head -45; done
printf '%s\n' MROS_AUTONOMOUS_SERVICES_INSTALLED
printf 'Authority worktree: %s\n' "$AUTHORITY_WT"
printf 'Health: %s\n' "$STATE/supervisor_health.json"
printf 'git-lfs: %s\n' "$GIT_LFS_BIN"
printf 'service PATH: %s\n' "$SERVICE_PATH"
printf '%s\n' "Stop: launchctl bootout gui/$(id -u)/com.aixion.mros-bridge-autoupdater ; launchctl bootout gui/$(id -u)/com.aixion.mros-autonomous-supervisor ; launchctl bootout gui/$(id -u)/com.aixion.mros-agent-worker"
