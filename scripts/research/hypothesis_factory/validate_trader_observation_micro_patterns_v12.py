#!/usr/bin/env python3
"""
Validate Trader Observation Micro Patterns V12 Script
Pre-outcome verification of data loading and frozen hypotheses.
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root / "scripts" / "research" / "hypothesis_factory"))

from trader_observation_micro_features_v12 import load_and_align_v12_data, generate_v12_frozen_candidate_specs

def main():
    print("Validating V12 environment and frozen hypotheses...")
    constituent_dir = '/Users/madhuram/tradebot-ml-evidence/context-transition-atlas-v1/context-transition-v3/constituent-structure-v1/selective-upstox-missing-v1'
    nifty_csv_path = '/Users/madhuram/tradebot-strategy-certification-kernel-v0/research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv'

    df = load_and_align_v12_data(constituent_dir, nifty_csv_path)
    print(f"Data aligned. Aligned 5-min bars: {len(df)}")
    assert len(df) > 500, "Insufficient aligned bars for V12 validation."

    candidates = generate_v12_frozen_candidate_specs()
    print(f"Loaded {len(candidates)} frozen candidate specs.")
    assert len(candidates) <= 6, "Maximum 6 frozen hypotheses allowed."

    print("ALL V12 PRE-OUTCOME VALIDATIONS PASSED CLEANLY.")

if __name__ == "__main__":
    main()
