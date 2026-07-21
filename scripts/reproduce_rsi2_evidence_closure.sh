#!/usr/bin/env bash
set -euo pipefail

python scripts/run_rsi2_evidence_closure.py --input runtime/research/rsi2_mean_reversion/frozen_data/nifty50_yfinance_2010-01-01_2026-01-01_auto_adjust_true.csv
pytest -q tests/test_rsi2_mean_reversion_research.py
python scripts/run_rsi2_evidence_closure.py --verify-hashes
