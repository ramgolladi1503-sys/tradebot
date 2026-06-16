import pytest
import numpy as np
from core.math.options_arbitrage import calculate_gex, calculate_aggregate_gex, calculate_vrp, calculate_gamma

def test_calculate_gamma():
    # Spot 100, Strike 100, DTE 30 days (0.082 years), Vol 20%
    gamma = calculate_gamma(S=100, K=100, T=30/365, r=0.0, sigma=0.2)
    assert gamma > 0
    assert np.isclose(gamma, 0.069, atol=0.01)
    
    # Zero DTE should return 0 safely
    assert calculate_gamma(S=100, K=100, T=0, r=0, sigma=0.2) == 0.0
    
    # Zero Vol should return 0 safely
    assert calculate_gamma(S=100, K=100, T=30/365, r=0, sigma=0.0) == 0.0

def test_calculate_gex():
    # CE GEX should be positive
    ce_gex = calculate_gex(open_interest=1000, option_type='CE', S=100, K=100, T=30/365, r=0.0, sigma=0.2)
    assert ce_gex > 0
    
    # PE GEX should be negative
    pe_gex = calculate_gex(open_interest=1000, option_type='PE', S=100, K=100, T=30/365, r=0.0, sigma=0.2)
    assert pe_gex < 0
    
    # Magnitudes should be equal for ATM same OI
    assert np.isclose(ce_gex, abs(pe_gex))

def test_calculate_aggregate_gex():
    chain = [
        {'strike': 90, 'option_type': 'PE', 'oi': 5000},
        {'strike': 100, 'option_type': 'PE', 'oi': 10000},
        {'strike': 100, 'option_type': 'CE', 'oi': 8000},
        {'strike': 110, 'option_type': 'CE', 'oi': 6000},
    ]
    
    total_gex = calculate_aggregate_gex(chain, S=100, T=30/365, r=0.0, sigma=0.2)
    # Puts have more OI ATM (10000 vs 8000), so GEX should be negative
    assert total_gex < 0
    
    # Invalid options should be ignored
    chain.append({'strike': 120, 'oi': 1000}) # missing option_type
    chain.append({'strike': 130, 'option_type': 'CE'}) # missing oi
    
    total_gex2 = calculate_aggregate_gex(chain, S=100, T=30/365)
    assert total_gex == total_gex2

def test_calculate_vrp():
    # Implied vol 20%
    # Realized vol 15% (annualized)
    # Let's mock a price series with exactly 15% annualized vol
    np.random.seed(42)
    returns = np.random.normal(0, 0.15 / np.sqrt(252), 100)
    prices = 100 * np.exp(np.cumsum(returns))
    
    vrp = calculate_vrp(implied_vol=0.20, realized_vol_history=prices)
    assert vrp > 0 # IV > RV
    assert np.isclose(vrp, 0.05, atol=0.02)
    
    # Edge cases
    assert calculate_vrp(None, prices) == 0.0
    assert calculate_vrp(0.20, None) == 0.0
    assert calculate_vrp(0.20, [100]) == 0.0 # Not enough history
