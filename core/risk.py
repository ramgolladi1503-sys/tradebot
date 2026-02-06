def calculate_position_size(capital, entry, stop_loss, lot_size=50):
    risk_per_trade = capital * 0.01
    risk_per_lot = abs(entry - stop_loss) * lot_size

    if risk_per_lot == 0:
        return 0

    lots = int(risk_per_trade // risk_per_lot)
    return max(lots, 0)

