#!/usr/bin/env python3
"""
Validate Selective Constituent Pilot V10 Script
Pre-outcome verification of data loading, candidate generation, and governance checks.
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root / "scripts" / "research" / "hypothesis_factory"))

from user_owned_selective_constituent_features_v10 import load_and_align_pilot_data, generate_v10_candidate_specs

def main():
    print("Validating V10 selective constituent pilot environment...")
    
    constituent_dir = '/Users/madhuram/tradebot-ml-evidence/context-transition-atlas-v1/context-transition-v3/constituent-structure-v1/selective-upstox-missing-v1'
    nifty_csv_path = '/Users/madhuram/tradebot-strategy-certification-kernel-v0/research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv'

    df = load_and_align_pilot_data(constituent_dir, nifty_csv_path)
    print(f"Data aligned successfully. Total 5-min bars: {len(df)}")
    assert len(df) > 100, "Insufficient aligned bars for validation."

    candidates = generate_v10_candidate_specs()
    print(f"Generated {len(candidates)} candidate specs.")
    
    for c in candidates:
        assert c["pilot_scope"] == "SELECTIVE_9_SYMBOLS_ONLY"
        assert c["not_full_nifty_breadth"] is True
        assert c["execution_viability"] is False
        assert c["edge_claimed"] is False
        assert c["structural_edge_certified"] is False

    print("ALL V10 PRE-OUTCOME VALIDATIONS PASSED CLEANLY.")

if __name__ == "__main__":
    main()
