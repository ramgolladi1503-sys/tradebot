import json
from pathlib import Path

def test_nifty_rsi2_mean_reversion_closure_record():
    p = Path("research/strategy_edge_registry/records/nifty_rsi2_mean_reversion.json")
    assert p.exists()
    
    with open(p) as f:
        data = json.load(f)
        
    assert data["hypothesis_id"] == "nifty_rsi2_mean_reversion"
    assert data["publication_commit"] == "f806c02917152b5f2bac44521d14530a9d470f4b"
    assert data["index_signal_verdict"] == "PARAMETER_FRAGILE"
    assert data["tradable_instrument_verdict"] == "INSUFFICIENT_TRADABLE_DATA"
    assert data["overall_verdict"] == "NO_STRUCTURAL_EDGE"
    assert data["fraction_of_random_replicates_beating_strategy"] == 0.827
    assert data["trend_filter_incremental_value_result"] == "NO_INCREMENTAL_VALUE"
    assert data["worst_trade"] == "REGIME_TRANSITION_TAIL_EVENT"
    assert data["production_integration_status"] == "REJECTED"
