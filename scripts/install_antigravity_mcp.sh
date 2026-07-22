#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${TRADEBOT_MCP_VENV:-$ROOT/.venv-mcp}"
CONFIG_DIR="$ROOT/.agents"
CONFIG_PATH="$CONFIG_DIR/mcp_config.json"
EVIDENCE_ROOT="${TRADEBOT_EVIDENCE_ROOT:-$ROOT/../tradebot-ml-evidence}"
DATA_ROOTS="${TRADEBOT_DATA_ROOTS:-$ROOT/runtime}"

if [[ ! -d "$EVIDENCE_ROOT" ]]; then
  EVIDENCE_ROOT="$ROOT/runtime"
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$ROOT/requirements-mcp.txt"

mkdir -p "$CONFIG_DIR"

ROOT="$ROOT" \
VENV_DIR="$VENV_DIR" \
EVIDENCE_ROOT="$EVIDENCE_ROOT" \
DATA_ROOTS="$DATA_ROOTS" \
CONFIG_PATH="$CONFIG_PATH" \
"$VENV_DIR/bin/python" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

root = Path(os.environ["ROOT"]).resolve()
venv = Path(os.environ["VENV_DIR"]).resolve()
config_path = Path(os.environ["CONFIG_PATH"]).resolve()
python = str(venv / "bin" / "python")
common_env = {
    "TRADEBOT_ROOT": str(root),
    "TRADEBOT_EVIDENCE_ROOTS": os.environ["EVIDENCE_ROOT"],
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
        "cwd": str(root),
        "env": common_env,
    }
config_path.write_text(
    json.dumps({"mcpServers": servers}, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

chmod 600 "$CONFIG_PATH"

TRADEBOT_ROOT="$ROOT" \
TRADEBOT_EVIDENCE_ROOTS="$EVIDENCE_ROOT" \
TRADEBOT_DATA_ROOTS="$DATA_ROOTS" \
"$VENV_DIR/bin/python" - <<'PY'
from tools.tradebot_mcp.core import Settings
from tools.tradebot_mcp import __version__

settings = Settings.from_env()
print(f"TradeBot MCP package {__version__} import: OK")
print(f"Configured root: {settings.root}")
PY

cat <<EOF
Installed TradeBot MCP servers.

Config: $CONFIG_PATH
Virtual environment: $VENV_DIR

Next:
1. Open Antigravity MCP Servers and reload the workspace configuration.
2. Keep MCP permissions in Ask mode initially.
3. Grant only read-only tools after reviewing docs/antigravity/TRADEBOT_MCP.md.
EOF
