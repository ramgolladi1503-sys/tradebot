import numpy as np
from scipy.stats import norm

def _black_scholes_d1(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    return (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))

def calculate_gamma(S, K, T, r, sigma):
    """
    Calculate the Black-Scholes Gamma for an option.
    Gamma is identical for Calls and Puts.
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = _black_scholes_d1(S, K, T, r, sigma)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

def calculate_gex(open_interest, option_type, S, K, T, r=0.0, sigma=0.2):
    """
    Calculates Dealer Gamma Exposure (GEX) for a single strike.
    
    Standard GEX assumption:
    - Dealers are short calls (retail buys calls) -> Negative Gamma exposure if spot rises.
    - Dealers are long puts (retail sells puts for income) -> Positive Gamma exposure if spot drops.
    - Result: Call GEX is positive (when dealers delta hedge they sell into strength, stabilizing market).
    
    Total GEX = Sum(Call GEX) - Sum(Put GEX)
    Call GEX = Gamma * OI * Spot * Contract_Multiplier
    Put GEX = -Gamma * OI * Spot * Contract_Multiplier
    If Total GEX > 0: Dealers are Long Gamma -> Market is low volatility (dealers trade against trend).
    If Total GEX < 0: Dealers are Short Gamma -> Market is high volatility (dealers trade with trend, exacerbating moves).
    """
    gamma = calculate_gamma(S, K, T, r, sigma)
    gex = gamma * open_interest * S * 100  # 100 is generic multiplier
    if option_type.upper() == 'PE':
        return -gex
    return gex

def calculate_aggregate_gex(options_chain, S, T, r=0.0, sigma=0.2):
    """
    Calculate total aggregate Dealer Gamma Exposure across the entire options chain.
    options_chain: list of dicts with 'strike', 'option_type' ('CE' or 'PE'), 'oi'
    """
    if not options_chain:
        return 0.0
        
    total_gex = 0.0
    for opt in options_chain:
        try:
            oi = opt.get('oi', 0)
            if oi <= 0:
                continue
            strike = opt.get('strike')
            opt_type = opt.get('option_type')
            if not strike or not opt_type:
                continue
                
            gex = calculate_gex(oi, opt_type, S, strike, T, r, sigma)
            total_gex += gex
        except Exception:
            continue
            
    return total_gex

def calculate_vrp(implied_vol, realized_vol_history, periods_per_year=252):
    """
    Volatility Risk Premium (VRP) = Implied Volatility - Expected Realized Volatility.
    
    Args:
        implied_vol: Current IV (e.g., VIX or ATM option IV, as a decimal 0.20)
        realized_vol_history: Array of historical prices.
        periods_per_year: 252 for daily, 252*375 for 1-minute data, etc.
        
    Returns:
        float: The VRP spread. Positive means options are expensive relative to actual movement.
    """
    try:
        if implied_vol is None or realized_vol_history is None or len(realized_vol_history) < 2:
            return 0.0
            
        prices = np.array(realized_vol_history, dtype=float)
        # Avoid division by zero in log
        prices = np.where(prices <= 0, 1e-9, prices)
        
        returns = np.diff(np.log(prices))
        if len(returns) == 0:
            return 0.0
            
        daily_rv = np.std(returns)
        annualized_rv = daily_rv * np.sqrt(periods_per_year)
        
        vrp = implied_vol - annualized_rv
        return vrp
    except Exception:
        return 0.0
