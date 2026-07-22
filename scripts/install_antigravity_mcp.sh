#!/usr/bin/env bash
set -euo pipefail

CODE_ROOT="$(git rev-parse --show-toplevel)"
cd "$CODE_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${TRADEBOT_MCP_VENV:-$CODE_ROOT/.venv-mcp}"
TARGET_ROOT="${TRADEBOT_TARGET_ROOT:-$CODE_ROOT}"
CONFIG_ROOT="${TRADEBOT_MCP_CONFIG_ROOT:-$TARGET_ROOT}"
CONFIG_DIR="$CONFIG_ROOT/.agents"
CONFIG_PATH="$CONFIG_DIR/mcp_config.json"
EVIDENCE_ROOTS="${TRADEBOT_EVIDENCE_ROOTS:-${TRADEBOT_EVIDENCE_ROOT:-$TARGET_ROOT/../tradebot-ml-evidence}}"
DATA_ROOTS="${TRADEBOT_DATA_ROOTS:-$TARGET_ROOT/runtime}"

if [[ ! -d "$TARGET_ROOT" ]]; then
  echo "TradeBot target root does not exist: $TARGET_ROOT" >&2
  exit 2
fi

# Preserve the legacy single-root default while allowing an os.pathsep-separated
# TRADEBOT_EVIDENCE_ROOTS value for the active research worktree plus external evidence.
if [[ "$EVIDENCE_ROOTS" != *:* && ! -d "$EVIDENCE_ROOTS" ]]; then
  EVIDENCE_ROOTS="$TARGET_ROOT/runtime"
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$CODE_ROOT/requirements-mcp.txt"

mkdir -p "$CONFIG_DIR"

CODE_ROOT="$CODE_ROOT" \
TARGET_ROOT="$TARGET_ROOT" \
VENV_DIR="$VENV_DIR" \
EVIDENCE_ROOTS="$EVIDENCE_ROOTS" \
DATA_ROOTS="$DATA_ROOTS" \
CONFIG_PATH="$CONFIG_PATH" \
"$VENV_DIR/bin/python" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

code_root = Path(os.environ["CODE_ROOT"]).resolve()
target_root = Path(os.environ["TARGET_ROOT"]).resolve()
venv = Path(os.environ["VENV_DIR"]).resolve()
config_path = Path(os.environ["CONFIG_PATH"]).resolve()
python = str(venv / "bin" / "python")
common_env = {
    "TRADEBOT_ROOT": str(target_root),
    "TRADEBOT_EVIDENCE_ROOTS": os.environ["EVIDENCE_ROOTS"],
    "TRADEBOT_DATA_ROOTS": os.environ["DATA_ROOTS"],
    "TRADEBOT_MCP_MAX_TEXT_BYTES": "5000000",
    "TRADEBOT_MCP_MAX_HASH_BYTES": "2000000000",
    "TRADEBOT_MCP_MAX_RESULT_ROWS": "100",
    "TRADEBOT_MCP_MAX_FILES": "500",
}
servers = {}
for name, module in {
    "tradebot-evidence": "tools.tradebot_mcp.evidence_server",
    "tradebot-data-audit": "tools.tradebot_mcp.data_audit_server",
    "tradebot-gates": "tools.tradebot_mcp.gates_server",
    "tradebot-git-audit": "tools.tradebot_mcp.git_audit_server",
}.items():
    servers[name] = {
        "command": python,
        "args": ["-m", module],
        "cwd": str(code_root),
        "env": common_env,
    }
config_path.write_text(
    json.dumps({"mcpServers": servers}, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

chmod 600 "$CONFIG_PATH"

TRADEBOT_ROOT="$TARGET_ROOT" \
TRADEBOT_EVIDENCE_ROOTS="$EVIDENCE_ROOTS" \
TRADEBOT_DATA_ROOTS="$DATA_ROOTS" \
"$VENV_DIR/bin/python" - <<'PY'
from tools.tradebot_mcp.core import Settings
from tools.tradebot_mcp import __version__

settings = Settings.from_env()
print(f"TradeBot MCP package {__version__} import: OK")
print(f"Configured target root: {settings.root}")
print(f"Configured evidence roots: {settings.evidence_roots}")
print(f"Configured data roots: {settings.data_roots}")
PY

cat <<EOF
Installed TradeBot MCP servers.

Server code root: $CODE_ROOT
Audited target root: $TARGET_ROOT
Config: $CONFIG_PATH
Virtual environment: $VENV_DIR

Next:
1. Open the target worktree in Antigravity and reload its workspace MCP configuration.
2. Keep MCP permissions in Ask mode initially.
3. Grant only read-only tools after reviewing docs/antigravity/TRADEBOT_MCP.md.
EOF
