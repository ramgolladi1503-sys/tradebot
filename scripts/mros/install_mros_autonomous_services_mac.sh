#!/usr/bin/env bash
set -euo pipefail
ROOT="${MROS_AGENT_BRIDGE_ROOT:-/Users/madhuram/.mros-agent-bridge}"
BRIDGE_WT="$ROOT/bridge"
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
cat > "$LAUNCH/com.aixion.mros-agent-worker.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.aixion.mros-agent-worker</string>
<key>ProgramArguments</key><array><string>$PYTHON</string><string>$BRIDGE_WT/scripts/mros/mros_agent_git_worker.py</string><string>--config</string><string>$CONFIG</string><string>--queue-branch</string><string>automation/mros-agent-queue-v1</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>10</integer>
<key>StandardOutPath</key><string>$LOGS/worker.out.log</string><key>StandardErrorPath</key><string>$LOGS/worker.err.log</string>
</dict></plist>
PLIST
cat > "$LAUNCH/com.aixion.mros-autonomous-supervisor.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.aixion.mros-autonomous-supervisor</string>
<key>ProgramArguments</key><array><string>$PYTHON</string><string>$BRIDGE_WT/scripts/mros/mros_autonomous_supervisor.py</string><string>--repo</string><string>/Users/madhuram/tradebot</string><string>--state-root</string><string>$STATE</string><string>--poll-seconds</string><string>15</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>10</integer>
<key>StandardOutPath</key><string>$LOGS/supervisor.out.log</string><key>StandardErrorPath</key><string>$LOGS/supervisor.err.log</string>
</dict></plist>
PLIST
for label in com.aixion.mros-agent-worker com.aixion.mros-autonomous-supervisor; do
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$LAUNCH/$label.plist"
  launchctl enable "gui/$(id -u)/$label"
done
sleep 2
launchctl print "gui/$(id -u)/com.aixion.mros-agent-worker" | head -40
launchctl print "gui/$(id -u)/com.aixion.mros-autonomous-supervisor" | head -40
printf '%s\n' MROS_AUTONOMOUS_SERVICES_INSTALLED
printf 'Health: %s\n' "$STATE/supervisor_health.json"
printf '%s\n' "Stop: launchctl bootout gui/$(id -u)/com.aixion.mros-autonomous-supervisor ; launchctl bootout gui/$(id -u)/com.aixion.mros-agent-worker"
