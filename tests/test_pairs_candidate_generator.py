import pytest
from core.pairs_candidate_generator import build_pairs_candidate_intents

def test_pairs_candidate_generator_spread_zscore():
    cross_asset_data = {
        "prices": {
            "BANKNIFTY_INDEX": 45000,
            "NIFTY_INDEX": 21000
        },
        "features": {
            "x_banknifty_index_z": 2.5,
            "x_nifty_index_z": 0.1,
            "x_banknifty_nifty_spread_z": 2.6,
            "x_banknifty_nifty_beta": 1.2,
            "x_banknifty_nifty_cointegrated": True,
            "x_banknifty_nifty_adf_pvalue": 0.01
        }
    }
    
    report = build_pairs_candidate_intents(cross_asset_data, min_zscore=2.0)
    print(report.pool_report)
    assert report.valid is True
    assert report.generated_intents
    
    intent = report.generated_intents[0]
    assert intent.direction == "SHORT"
    assert intent.instrument == "BANKNIFTY_NIFTY"
    assert intent.metadata["spread_z"] == 2.6

def test_pairs_candidate_generator_no_trade():
    cross_asset_data = {
        "prices": {
            "BANKNIFTY_INDEX": 45000,
            "NIFTY_INDEX": 21000
        },
        "features": {
            "x_banknifty_index_z": 1.0,
            "x_nifty_index_z": 0.8
        }
    }
    
    report = build_pairs_candidate_intents(cross_asset_data, min_zscore=2.0)
    assert not report.generated_intents

def test_pairs_candidate_generator_missing_data():
    cross_asset_data = {
        "prices": {},
        "features": {}
    }
    
    report = build_pairs_candidate_intents(cross_asset_data, min_zscore=2.0)
    assert not report.generated_intents
    assert report.warnings
