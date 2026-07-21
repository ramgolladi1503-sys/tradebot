#!/usr/bin/env bash
set -euo pipefail

python scripts/run_rsi2_publication_gate_v2.py
pytest -q \
  tests/test_rsi2_mean_reversion_research.py \
  tests/test_rsi2_publication_semantics_v2.py \
  tests/test_rsi2_independent_publication_oracle_v2.py \
  tests/test_rsi2_permanent_research_closure_v2.py
python scripts/run_rsi2_publication_gate_v2.py --verify
