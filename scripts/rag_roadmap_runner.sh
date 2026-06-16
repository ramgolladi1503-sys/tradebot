#!/bin/bash

# Supported commands:
# --check
# --full
# --checkpoint <id>

# Check arguments
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 [--check | --full | --checkpoint <id>]"
    exit 1
fi

COMMAND=$1

run_check() {
    echo "Running --check..."
    echo "Running git diff --check..."
    git diff --check || { echo "FAIL: git diff --check failed"; exit 1; }

    echo "Running bash scripts/rag_guard_diff.sh origin/main..."
    bash scripts/rag_guard_diff.sh origin/main || { echo "FAIL: rag_guard_diff.sh failed"; exit 1; }
}

run_full() {
    echo "Running --full..."
    run_check

    if [ -d "tests/rag" ]; then
        echo "Running pytest tests/rag..."
        pytest tests/rag || { echo "FAIL: pytest tests/rag failed"; exit 1; }
    fi

    if [ -d "tests/rag/evals" ]; then
        echo "Running pytest tests/rag/evals..."
        pytest tests/rag/evals || { echo "FAIL: pytest tests/rag/evals failed"; exit 1; }
    fi
}

run_checkpoint() {
    if [ -z "$2" ]; then
        echo "Usage: $0 --checkpoint <id>"
        exit 1
    fi
    CHECKPOINT_ID=$2
    echo "Running --checkpoint $CHECKPOINT_ID..."

    run_check

    # Run scoped tests if present
    # Currently we run standard tests
    if [ -d "tests/rag" ]; then
        echo "Running pytest tests/rag..."
        pytest tests/rag || { echo "FAIL: pytest tests/rag failed"; exit 1; }
    fi
}

if [ "$COMMAND" = "--check" ]; then
    run_check
elif [ "$COMMAND" = "--full" ]; then
    run_full
elif [ "$COMMAND" = "--checkpoint" ]; then
    run_checkpoint "$@"
else
    echo "Unknown command: $COMMAND"
    echo "Usage: $0 [--check | --full | --checkpoint <id>]"
    exit 1
fi

echo "SUCCESS: All runner checks passed."
exit 0
