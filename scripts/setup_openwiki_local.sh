#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
  echo "ERROR: run this script inside the TradeBot git repository." >&2
  exit 1
fi
cd "${REPO_ROOT}"

BRANCH="$(git branch --show-current)"
if [[ "${BRANCH}" == "main" || -z "${BRANCH}" ]]; then
  echo "ERROR: refusing to initialize OpenWiki on main or detached HEAD." >&2
  echo "Create an isolated branch/worktree first." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: refusing to run in an already-dirty worktree." >&2
  echo "Commit, stash, or use a clean isolated worktree." >&2
  exit 1
fi

command -v node >/dev/null 2>&1 || { echo "ERROR: Node.js is required." >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "ERROR: npm is required." >&2; exit 1; }

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if (( NODE_MAJOR < 20 )); then
  echo "ERROR: OpenWiki requires Node.js 20 or newer; found $(node --version)." >&2
  exit 1
fi

if ! command -v openwiki >/dev/null 2>&1; then
  echo "Installing OpenWiki CLI globally..."
  npm install --global openwiki
fi

PROMPT_FILE="docs/openwiki/TRADEBOT_WIKI_PROMPT.md"
[[ -f "${PROMPT_FILE}" ]] || { echo "ERROR: missing ${PROMPT_FILE}." >&2; exit 1; }
PROMPT="$(cat "${PROMPT_FILE}")"

WORKFLOW=".github/workflows/openwiki-update.yml"
WORKFLOW_EXISTED=0
[[ -f "${WORKFLOW}" ]] && WORKFLOW_EXISTED=1

OPENWIKI_PROVIDER=openai-chatgpt openwiki code --init "${PROMPT}"

if (( WORKFLOW_EXISTED == 0 )) && [[ -f "${WORKFLOW}" ]]; then
  rm -f "${WORKFLOW}"
  rmdir .github/workflows 2>/dev/null || true
  rmdir .github 2>/dev/null || true
  echo "Removed newly generated scheduled workflow pending human review."
fi

echo
echo "OpenWiki initialization finished. Review before committing:"
git status --short
echo
echo "Next: bash scripts/review_openwiki_output.sh"
