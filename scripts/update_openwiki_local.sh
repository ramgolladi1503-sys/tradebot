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
  echo "ERROR: refusing to update OpenWiki on main or detached HEAD." >&2
  exit 1
fi

command -v openwiki >/dev/null 2>&1 || {
  echo "ERROR: OpenWiki is not installed. Run scripts/setup_openwiki_local.sh first." >&2
  exit 1
}

PROMPT_FILE="docs/openwiki/TRADEBOT_WIKI_PROMPT.md"
[[ -f "${PROMPT_FILE}" ]] || { echo "ERROR: missing ${PROMPT_FILE}." >&2; exit 1; }
PROMPT="$(cat "${PROMPT_FILE}")"

WORKFLOW=".github/workflows/openwiki-update.yml"
WORKFLOW_EXISTED=0
[[ -f "${WORKFLOW}" ]] && WORKFLOW_EXISTED=1

OPENWIKI_PROVIDER=openai-chatgpt openwiki code --update "${PROMPT}"

if (( WORKFLOW_EXISTED == 0 )) && [[ -f "${WORKFLOW}" ]]; then
  rm -f "${WORKFLOW}"
  rmdir .github/workflows 2>/dev/null || true
  rmdir .github 2>/dev/null || true
  echo "Removed newly generated scheduled workflow pending human review."
fi

echo
echo "OpenWiki update finished. Review before committing:"
git status --short
echo
echo "Next: bash scripts/review_openwiki_output.sh"
