def passes_hard_filters(candidate):
    c = candidate or {}

    spread = c.get("spread_pct")
    if spread is not None:
        try:
            if float(spread) > 0.015:
                return False
        except Exception:
            return False

    execution_score = c.get("execution_score") or c.get("execution_quality_score")
    try:
        if execution_score is not None and float(execution_score) < 0.5:
            return False
    except Exception:
        return False

    liquidity_score = c.get("liquidity_score") or c.get("liquidity_quality")
    try:
        if liquidity_score is not None and float(liquidity_score) < 0.5:
            return False
    except Exception:
        return False

    return True
