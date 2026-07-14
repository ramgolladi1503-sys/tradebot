#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
  echo "ERROR: run this script inside the TradeBot git repository." >&2
  exit 1
fi
cd "${REPO_ROOT}"

FAIL=0

check_forbidden() {
  local pattern="$1"
  local label="$2"
  if git diff --name-only --cached -- . ':!openwiki/**' ':!docs/openwiki/**' ':!AGENTS.md' ':!CLAUDE.md' ':!scripts/setup_openwiki_local.sh' ':!scripts/update_openwiki_local.sh' ':!scripts/review_openwiki_output.sh' | grep -Eq "${pattern}"; then
    echo "FAIL: staged OpenWiki change touches forbidden ${label} paths." >&2
    FAIL=1
  fi
  if git diff --name-only -- . ':!openwiki/**' ':!docs/openwiki/**' ':!AGENTS.md' ':!CLAUDE.md' ':!scripts/setup_openwiki_local.sh' ':!scripts/update_openwiki_local.sh' ':!scripts/review_openwiki_output.sh' | grep -Eq "${pattern}"; then
    echo "FAIL: unstaged OpenWiki change touches forbidden ${label} paths." >&2
    FAIL=1
  fi
}

check_forbidden '(^|/)(\.env|credentials\.py|secrets)' 'credential/secret'
check_forbidden '^(core/(execution|broker|order|risk|feed)|strategies/|main\.py$|run_live\.sh$|config/)' 'runtime/high-risk'

if [[ -f .github/workflows/openwiki-update.yml ]]; then
  echo "FAIL: scheduled OpenWiki workflow is present. This evaluation is manual-review only." >&2
  FAIL=1
fi

if [[ -d openwiki ]]; then
  echo "Generated OpenWiki pages:"
  find openwiki -type f | sort
else
  echo "WARN: openwiki/ does not exist yet. Run setup first."
fi

echo
echo "Changed files:"
git status --short

echo
echo "Suspicious readiness language (manual review required):"
if [[ -d openwiki ]]; then
  grep -RInE 'production[- ]ready|ready for (merge|live|production)|live[- ]market proof|all constraints met|guaranteed|canonical production' openwiki || true
fi

echo
echo "Evidence-state language coverage:"
if [[ -d openwiki ]]; then
  grep -RInE 'PROVEN|PARTIALLY_PROVEN|CLAIMED|UNKNOWN|ACTIVE_PRODUCTION|LEGACY_ACTIVE|RESEARCH_ONLY|DEPRECATED|DEAD' openwiki | head -n 80 || true
fi

if (( FAIL != 0 )); then
  exit 1
fi

echo
echo "Automated boundary checks passed. This does NOT validate documentation correctness."
echo "Review startup wiring, callers/callees, config defaults, tests, and runtime evidence manually."
