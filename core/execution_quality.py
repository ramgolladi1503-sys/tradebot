import math


def estimate_queue_position(depth, side, limit_price=None, qty=1):
    if not depth:
        return {"queue_position": None, "queue_priority": None}
    try:
        book = depth.get("buy") if side == "BUY" else depth.get("sell")
        if not book:
            return {"queue_position": None, "queue_priority": None}
        top = book[0]
        top_qty = float(top.get("quantity", 0) or 0)
        top_price = float(top.get("price", 0) or 0)
        if limit_price is not None and top_price:
            if side == "BUY" and limit_price > top_price:
                return {"queue_position": 0.0, "queue_priority": 1.0}
            if side == "SELL" and limit_price < top_price:
                return {"queue_position": 0.0, "queue_priority": 1.0}
        ahead = max(top_qty, 0.0)
        denom = max(ahead + max(qty, 1), 1.0)
        queue_position = ahead / denom
        queue_priority = 1.0 - queue_position
        return {"queue_position": round(queue_position, 4), "queue_priority": round(queue_priority, 4)}
    except Exception:
        return {"queue_position": None, "queue_priority": None}


def depth_weighted_impact(depth, side, qty, spread):
    if not depth or spread is None:
        return None
    try:
        book = depth.get("sell") if side == "BUY" else depth.get("buy")
        if not book:
            return None
        total = 0.0
        for level in book[:3]:
            total += float(level.get("quantity", 0) or 0)
        total = max(total, 1.0)
        impact = (qty / total) * float(spread)
        return round(impact, 6)
    except Exception:
        return None


def classify_urgency(confidence, time_to_expiry_hrs=None, spread_pct=None):
    score = 0.0
    try:
        if confidence is not None:
            score += float(confidence)
    except Exception:
        pass
    try:
        if time_to_expiry_hrs is not None:
            if time_to_expiry_hrs <= 1:
                score += 0.4
            elif time_to_expiry_hrs <= 4:
                score += 0.2
    except Exception:
        pass
    try:
        if spread_pct is not None and spread_pct > 0.02:
            score -= 0.1
    except Exception:
        pass
    if score >= 0.8:
        return "HIGH", round(score, 3)
    if score >= 0.55:
        return "MED", round(score, 3)
    return "LOW", round(score, 3)


def implementation_shortfall(decision_mid, fill_price, side):
    if decision_mid is None or fill_price is None:
        return None
    if side == "BUY":
        return round(fill_price - decision_mid, 4)
    return round(decision_mid - fill_price, 4)


def opportunity_cost(decision_mid, mid_end, side):
    if decision_mid is None or mid_end is None:
        return None
    if side == "BUY":
        return round(mid_end - decision_mid, 4)
    return round(decision_mid - mid_end, 4)


def alpha_decay(decision_mid, mid_at_fill, side):
    if decision_mid is None or mid_at_fill is None:
        return None
    if side == "BUY":
        return round(mid_at_fill - decision_mid, 4)
    return round(decision_mid - mid_at_fill, 4)


def adverse_selection(mid_at_fill, mid_after, side):
    if mid_at_fill is None or mid_after is None:
        return None
    if side == "BUY":
        return round(mid_after - mid_at_fill, 4)
    return round(mid_at_fill - mid_after, 4)


def execution_quality_score(report):
    """
    Produces a 0-100 score based on slippage, spread, time-to-fill, and adverse selection.
    """
    if not report:
        return None
    score = 100.0
    try:
        slippage = report.get("slippage_vs_mid")
        if slippage is not None:
            score -= min(30.0, abs(float(slippage)) * 100.0)
    except Exception:
        pass
    try:
        spread = report.get("decision_spread")
        if spread is not None:
            score -= min(20.0, float(spread) * 10.0)
    except Exception:
        pass
    try:
        ttf = report.get("time_to_fill")
        if ttf is not None:
            score -= min(20.0, float(ttf) * 5.0)
    except Exception:
        pass
    try:
        adverse = report.get("adverse_selection")
        if adverse is not None:
            score -= min(20.0, abs(float(adverse)) * 50.0)
    except Exception:
        pass
    try:
        queue_pos = report.get("queue_position")
        if queue_pos is not None:
            score -= min(10.0, float(queue_pos) * 10.0)
    except Exception:
        pass
    return round(max(0.0, min(100.0, score)), 2)
