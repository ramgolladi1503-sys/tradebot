#!/bin/bash
set -e

# Run orchestrator
python3 scripts/run_upstream_backtest_integrity_codex_validation.py
echo "First run complete."

# Store first run hash manifest
cp runtime/research/upstream_backtest_integrity_codex_validation/artifact_hash_manifest.json /tmp/run1_hashes.json

# Run again
python3 scripts/run_upstream_backtest_integrity_codex_validation.py
echo "Second run complete."

# Compare
if cmp -s /tmp/run1_hashes.json runtime/research/upstream_backtest_integrity_codex_validation/artifact_hash_manifest.json; then
    echo "Determinism verified: exact match between runs."
else
    echo "Determinism failed: runs produced different artifacts."
    exit 1
fi
