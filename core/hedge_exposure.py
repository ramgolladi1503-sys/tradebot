MAX_DELTA = 200_000
MAX_VEGA = 50_000
MAX_GAMMA = 20_000

def hedge_adjusted_lots(trade, current_state, position_size):
    trade_delta = trade["delta"] * position_size
    trade_vega = trade["vega"] * position_size
    trade_gamma = trade["gamma"] * position_size

    scale = 1.0
    if abs(current_state["delta"]+trade_delta) > MAX_DELTA:
        scale = min(scale, MAX_DELTA/abs(current_state["delta"]+trade_delta))
    if abs(current_state["vega"]+trade_vega) > MAX_VEGA:
        scale = min(scale, MAX_VEGA/abs(current_state["vega"]+trade_vega))
    if abs(current_state["gamma"]+trade_gamma) > MAX_GAMMA:
        scale = min(scale, MAX_GAMMA/abs(current_state["gamma"]+trade_gamma))

    adjusted_lots = max(int(position_size*scale), 0)

    current_state["delta"] += trade_delta*scale
    current_state["vega"] += trade_vega*scale
    current_state["gamma"] += trade_gamma*scale

    return adjusted_lots, current_state

