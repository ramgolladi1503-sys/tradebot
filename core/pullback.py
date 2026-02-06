# core/pullback.py

def pullback_and_hold(premium_series):
    """
    premium_series: last 5 candles premiums
    """
    if len(premium_series) < 5:
        return False

    high = max(premium_series[:3])
    pullback = premium_series[3] < high * 0.85
    hold = premium_series[4] >= premium_series[3]

    return pullback and hold

