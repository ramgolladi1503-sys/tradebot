import math
from config import config as cfg

def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))

def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

def bs_price(spot, strike, t, r, vol, is_call=True):
    if t <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if is_call:
        return spot * _norm_cdf(d1) - strike * math.exp(-r * t) * _norm_cdf(d2)
    return strike * math.exp(-r * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)

def implied_vol(price, spot, strike, t, is_call=True):
    if price <= 0 or t <= 0:
        return 0.0
    vol = 0.3
    for _ in range(50):
        d1 = (math.log(spot / strike) + (cfg.RISK_FREE_RATE + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
        vega = spot * _norm_pdf(d1) * math.sqrt(t)
        if vega < 1e-6:
            break
        price_est = bs_price(spot, strike, t, cfg.RISK_FREE_RATE, vol, is_call)
        diff = price_est - price
        vol -= diff / vega
        if abs(diff) < 1e-4:
            break
    return max(vol, 1e-4)

def greeks(spot, strike, t, vol, is_call=True):
    if t <= 0 or vol <= 0:
        return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
    d1 = (math.log(spot / strike) + (cfg.RISK_FREE_RATE + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    delta = _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1
    gamma = _norm_pdf(d1) / (spot * vol * math.sqrt(t))
    theta = -(spot * _norm_pdf(d1) * vol / (2 * math.sqrt(t))) - (cfg.RISK_FREE_RATE * strike * math.exp(-cfg.RISK_FREE_RATE * t) * (_norm_cdf(d2) if is_call else _norm_cdf(-d2)))
    vega = spot * _norm_pdf(d1) * math.sqrt(t)
    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}
