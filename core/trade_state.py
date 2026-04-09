_ACTIVE_TRADE = None


def get_active_trade():
    return _ACTIVE_TRADE


def set_active_trade(trade):
    global _ACTIVE_TRADE
    _ACTIVE_TRADE = trade


def clear_active_trade():
    global _ACTIVE_TRADE
    _ACTIVE_TRADE = None
