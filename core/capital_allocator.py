def calculate_qty(capital, risk_pct, entry, stop):
    risk_amount = capital * risk_pct
    per_unit_risk = abs(entry - stop)

    if per_unit_risk == 0:
        return 0

    return int(risk_amount / per_unit_risk)

