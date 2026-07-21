#!/usr/bin/env bash
set -euo pipefail

pytest -q tests/test_rsi2_mean_reversion_research.py
python scripts/run_rsi2_publication_gate.py --replicates 1000
python scripts/run_rsi2_publication_gate.py --verify-hashes
