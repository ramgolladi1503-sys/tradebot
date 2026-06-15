#!/bin/bash

# Default to origin/main if no base branch is provided
BASE_BRANCH=${1:-origin/main}

# Fetch the latest to ensure we have the base branch to compare against
git fetch origin main >/dev/null 2>&1 || true

echo "Comparing current branch against $BASE_BRANCH..."

# Get the list of changed files
CHANGED_FILES=$(git diff --name-only "$BASE_BRANCH")

if [ -z "$CHANGED_FILES" ]; then
    echo "No files changed."
    exit 0
fi

echo "Changed files:"
echo "$CHANGED_FILES"
echo ""

# Define allowed prefixes explicitly
ALLOWED_PREFIXES=(
    "scripts/rag_"
    "docs/rag/"
)

# Define forbidden paths explicitly
# Note: we use regex for strict matching
FORBIDDEN_REGEXES=(
    "^\.env$"
    "^\.env\..*"
    "^runtime/secrets/"
    "^secrets/"
    "^config/broker"
    "^configs/live"
    "^core/execution"
    "^core/order"
    "^core/risk"
    "^core/orchestrator"
    "^core/engine_phase2_adapter\.py"
    "^core/feed_execution_truth\.py"
    "^strategies/"
    "^core/strategies/"
    "^core/backtest_elite\.py"
    "^core/backtesting/"
    "^core/vectorized_signals\.py"
    "^scripts/run_wfa_intraday\.py"
)

# Check for forbidden and allowed files
for FILE in $CHANGED_FILES; do

    # 1. Check if the file matches any forbidden regex
    for REGEX in "${FORBIDDEN_REGEXES[@]}"; do
        if echo "$FILE" | grep -Eq "$REGEX"; then
            echo "FAIL: Changed file matches forbidden path: $FILE (matches regex $REGEX)"
            exit 1
        fi
    done

    # 2. Check if the file is in allowed paths
    IS_ALLOWED=false
    for PREFIX in "${ALLOWED_PREFIXES[@]}"; do
        if [[ "$FILE" == "$PREFIX"* ]]; then
            IS_ALLOWED=true
            break
        fi
    done

    # explicit pass for agent review docs required by CE
    if [[ "$FILE" == "docs/agent_reviews/"* ]]; then
        IS_ALLOWED=true
    fi

    if [ "$IS_ALLOWED" = false ]; then
        echo "FAIL: Changed file is outside allowed RAG paths: $FILE"
        exit 1
    fi
done

# Check for skip markers in added lines
echo "Checking for skip markers in added code..."
# Get added lines from the diff (lines starting with + but not +++)
# Then search for any of the forbidden skip markers
SKIP_MARKERS=(
    "pytest.mark.skip"
    "pytest.mark.xfail"
    "unittest.skip"
    "@skip"
    "skip this test"
)

# Run git diff, get lines added (+), grep for markers
for MARKER in "${SKIP_MARKERS[@]}"; do
    # Exclude scripts/rag_guard_diff.sh from the diff to avoid matching the script's own definitions
    if git diff -U0 "$BASE_BRANCH" -- ':!scripts/rag_guard_diff.sh' | grep "^+" | grep -v "^+++" | grep -qFi "$MARKER"; then
        echo "FAIL: Found skip marker in diff: $MARKER"
        exit 1
    fi
done

echo "SUCCESS: All guard checks passed."
exit 0
