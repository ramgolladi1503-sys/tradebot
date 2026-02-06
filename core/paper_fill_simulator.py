import time
from core.execution_quality import (
    estimate_queue_position,
    depth_weighted_impact,
    classify_urgency,
    implementation_shortfall,
    opportunity_cost,
    alpha_decay,
    adverse_selection,
    execution_quality_score,
)


class PaperFillSimulator:
    """
    Strict paper-fill simulator using sequential quote snapshots.

    Rules:
    - BUY fills if limit >= ask at any snapshot before timeout
    - SELL fills if limit <= bid at any snapshot before timeout
    - Otherwise: no fill (timeout)
    """

    def __init__(self, timeout_sec=3.0, poll_sec=0.25):
        self.timeout_sec = timeout_sec
        self.poll_sec = poll_sec

    def simulate(self, trade, limit_price, snapshot_stream, max_replaces=2, reprice_pct=0.002, max_chase_pct=0.002):
        if snapshot_stream is None:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote",
            }

        if callable(snapshot_stream):
            def _next_snapshot():
                return snapshot_stream()
        else:
            iterator = iter(snapshot_stream)
            def _next_snapshot():
                try:
                    return next(iterator)
                except StopIteration:
                    return None

        start = time.time()
        first_bid = None
        first_ask = None
        first_depth = None
        decision_mid = None
        decision_spread = None
        mid_at_fill = None
        mid_after = None
        last_mid = None
        vwap_sum = 0.0
        vwap_n = 0
        replaces = 0
        current_limit = limit_price

        while time.time() - start <= self.timeout_sec:
            snap = _next_snapshot()
            if not snap:
                time.sleep(self.poll_sec)
                continue

            bid = snap.get("bid") or 0
            ask = snap.get("ask") or 0
            if bid <= 0 or ask <= 0:
                time.sleep(self.poll_sec)
                continue
            depth = snap.get("depth")
            if first_depth is None:
                first_depth = depth

            if first_bid is None:
                first_bid = bid
                first_ask = ask
                decision_mid = (first_bid + first_ask) / 2.0
                decision_spread = max(first_ask - first_bid, 0.0)

            mid = (bid + ask) / 2.0
            last_mid = mid
            vwap_sum += mid
            vwap_n += 1

            # cancel/replace logic
            if reprice_pct and replaces < max_replaces:
                if trade.side == "BUY" and ask > current_limit and ask <= decision_mid * (1 + max_chase_pct):
                    current_limit = ask * (1 + reprice_pct)
                    replaces += 1
                elif trade.side == "SELL" and bid < current_limit and bid >= decision_mid * (1 - max_chase_pct):
                    current_limit = bid * (1 - reprice_pct)
                    replaces += 1

            if trade.side == "BUY" and current_limit >= ask:
                mid_at_fill = mid
                fill_price = ask
                time_to_fill = time.time() - start
                urgency, urgency_score = classify_urgency(getattr(trade, "confidence", None), getattr(trade, "time_to_expiry_hrs", None), (decision_spread / decision_mid) if decision_mid else None)
                qty = getattr(trade, "qty", 1)
                queue = estimate_queue_position(first_depth, trade.side, current_limit, qty)
                impact = depth_weighted_impact(depth, trade.side, getattr(trade, "qty", 1), decision_spread)
                participation = None
                try:
                    if depth:
                        book = depth.get("sell") if trade.side == "BUY" else depth.get("buy")
                        total = 0.0
                        for level in (book or [])[:3]:
                            total += float(level.get("quantity", 0) or 0)
                        total = max(total, 1.0)
                        participation = round(qty / total, 4)
                except Exception:
                    participation = None
                report = {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": round(fill_price, 2),
                    "slippage": round(fill_price - decision_mid, 4) if decision_mid is not None else None,
                    "time_to_fill": round(time_to_fill, 4),
                    "reason_if_aborted": None,
                    "queue_position": queue.get("queue_position"),
                    "queue_priority": queue.get("queue_priority"),
                    "urgency": urgency,
                    "urgency_score": urgency_score,
                    "impact_estimate": impact,
                    "vwap": round(vwap_sum / max(vwap_n, 1), 4),
                    "participation_rate": participation,
                }
                # post-fill adverse selection using last mid
                mid_after = last_mid
                report["alpha_decay"] = alpha_decay(decision_mid, mid_at_fill, trade.side)
                report["adverse_selection"] = adverse_selection(mid_at_fill, mid_after, trade.side)
                report["implementation_shortfall"] = implementation_shortfall(decision_mid, fill_price, trade.side)
                report["opportunity_cost"] = opportunity_cost(decision_mid, mid_after, trade.side)
                report["execution_quality_score"] = execution_quality_score(report)
                return True, round(fill_price, 2), report

            if trade.side == "SELL" and current_limit <= bid:
                mid_at_fill = mid
                fill_price = bid
                time_to_fill = time.time() - start
                urgency, urgency_score = classify_urgency(getattr(trade, "confidence", None), getattr(trade, "time_to_expiry_hrs", None), (decision_spread / decision_mid) if decision_mid else None)
                qty = getattr(trade, "qty", 1)
                queue = estimate_queue_position(first_depth, trade.side, current_limit, qty)
                impact = depth_weighted_impact(depth, trade.side, getattr(trade, "qty", 1), decision_spread)
                participation = None
                try:
                    if depth:
                        book = depth.get("sell") if trade.side == "BUY" else depth.get("buy")
                        total = 0.0
                        for level in (book or [])[:3]:
                            total += float(level.get("quantity", 0) or 0)
                        total = max(total, 1.0)
                        participation = round(qty / total, 4)
                except Exception:
                    participation = None
                report = {
                    "decision_mid": round(decision_mid, 2) if decision_mid is not None else None,
                    "decision_spread": round(decision_spread, 4) if decision_spread is not None else None,
                    "fill_price": round(fill_price, 2),
                    "slippage": round(decision_mid - fill_price, 4) if decision_mid is not None else None,
                    "time_to_fill": round(time_to_fill, 4),
                    "reason_if_aborted": None,
                    "queue_position": queue.get("queue_position"),
                    "queue_priority": queue.get("queue_priority"),
                    "urgency": urgency,
                    "urgency_score": urgency_score,
                    "impact_estimate": impact,
                    "vwap": round(vwap_sum / max(vwap_n, 1), 4),
                    "participation_rate": participation,
                }
                mid_after = last_mid
                report["alpha_decay"] = alpha_decay(decision_mid, mid_at_fill, trade.side)
                report["adverse_selection"] = adverse_selection(mid_at_fill, mid_after, trade.side)
                report["implementation_shortfall"] = implementation_shortfall(decision_mid, fill_price, trade.side)
                report["opportunity_cost"] = opportunity_cost(decision_mid, mid_after, trade.side)
                report["execution_quality_score"] = execution_quality_score(report)
                return True, round(fill_price, 2), report

            time.sleep(self.poll_sec)

        if first_bid is None or first_ask is None:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote",
            }

        decision_mid = (first_bid + first_ask) / 2.0
        decision_spread = max(first_ask - first_bid, 0.0)
        qty = getattr(trade, "qty", 1)
        queue = estimate_queue_position(first_depth, trade.side, current_limit, qty)
        urgency, urgency_score = classify_urgency(getattr(trade, "confidence", None), getattr(trade, "time_to_expiry_hrs", None), (decision_spread / decision_mid) if decision_mid else None)
        report = {
            "decision_mid": round(decision_mid, 2),
            "decision_spread": round(decision_spread, 4),
            "fill_price": None,
            "slippage": None,
            "reason_if_aborted": "timeout",
            "queue_position": queue.get("queue_position"),
            "queue_priority": queue.get("queue_priority"),
            "urgency": urgency,
            "urgency_score": urgency_score,
            "impact_estimate": None,
            "vwap": round(vwap_sum / max(vwap_n, 1), 4),
        }
        if last_mid is not None:
            report["opportunity_cost"] = opportunity_cost(decision_mid, last_mid, trade.side)
        report["execution_quality_score"] = execution_quality_score(report)
        return False, None, report
