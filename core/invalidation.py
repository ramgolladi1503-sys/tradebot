# core/invalidation.py

from core.market_data import get_nifty_ltp, get_index_vwap, analyze_oi, fetch_option_chain


def check_vwap_invalidation():
    ltp = get_nifty_ltp()
    vwap = get_index_vwap()

    if ltp is None or vwap is None:
        return None

    if ltp < vwap:
        return "VWAP_BREAKDOWN"

    return None


def check_oi_invalidation():
    chain = fetch_option_chain("NIFTY")
    if not chain:
        return None

    oi_bias = analyze_oi(chain)

    if oi_bias == "PUT_FAVOURED":
        return "OI_FLIP_BEARISH"

    return None


def check_premium_invalidation(entry_price, current_price, nifty_direction):
    """
    nifty_direction: 'UP' or 'DOWN'
    """

    if nifty_direction == "UP" and current_price <= entry_price:
        return "PREMIUM_NOT_RESPONDING"

    if nifty_direction == "DOWN" and current_price >= entry_price:
        return "PREMIUM_NOT_RESPONDING"

    return None

