import hashlib
import math


class FillModel:
    """
    Deterministic fill model for limit-order simulation.

    This model has no runtime randomness. Any stochastic-looking behavior is
    deterministically derived from (run_id, symbol, side, quote, limit, qty).
    """

    def __init__(self):
        self.min_latency_ms = 35
        self.max_latency_ms = 280
        self.max_mid_drift_bp = 8.0

    def _uniform(self, *parts):
        key = "|".join(str(p) for p in parts)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return int(digest[:16], 16) / float(16 ** 16)

    def _latency_ms(self, run_id, symbol, side):
        u = self._uniform(run_id, symbol, side, "latency")
        span = max(self.max_latency_ms - self.min_latency_ms, 1)
        return int(self.min_latency_ms + u * span)

    def simulate(self, order, market_snapshot, run_id):
        side = str(order.get("side", "")).upper()
        symbol = str(order.get("symbol", "UNKNOWN"))
        qty = int(max(order.get("qty", 0) or 0, 0))
        limit_price = float(order.get("limit_price", 0.0) or 0.0)
        bid = float(market_snapshot.get("bid", 0.0) or 0.0)
        ask = float(market_snapshot.get("ask", 0.0) or 0.0)

        latency_ms = self._latency_ms(run_id, symbol, side)
        result = {
            "fill_qty": 0,
            "fill_price": None,
            "status": "NOFILL",
            "slippage_bp": None,
            "latency_ms": latency_ms,
            "reason": "cross_not_met",
        }

        if side not in ("BUY", "SELL"):
            result["reason"] = "invalid_side"
            return result
        if qty <= 0:
            result["reason"] = "invalid_qty"
            return result
        if limit_price <= 0:
            result["reason"] = "invalid_limit"
            return result
        if bid <= 0 or ask <= 0:
            result["reason"] = "invalid_quote"
            return result

        mid = (bid + ask) / 2.0
        spread = abs(ask - bid)
        spread_pct = spread / max(mid, 1e-9)
        vol = abs(float(market_snapshot.get("volatility", market_snapshot.get("vol_z", 0.0)) or 0.0))

        # Deterministic micro mid-drift proxy within the modeled latency window.
        drift_draw = self._uniform(run_id, symbol, side, limit_price, bid, ask, qty, "mid_drift")
        drift_bp = (drift_draw * 2.0 - 1.0) * self.max_mid_drift_bp
        mid_after_latency = mid * (1.0 + drift_bp / 10000.0)

        if side == "BUY":
            near_limit = ask <= (limit_price * 1.0005)
            drift_through = near_limit and mid_after_latency < limit_price
            can_fill = ask <= limit_price or drift_through
        else:
            # SELL remains strict to bid crossing.
            can_fill = bid >= limit_price
        if not can_fill:
            return result

        book_qty = float(
            market_snapshot.get("ask_qty", 0.0) if side == "BUY" else market_snapshot.get("bid_qty", 0.0)
        )
        volume = float(market_snapshot.get("volume", 0.0) or 0.0)
        oi = float(market_snapshot.get("oi", 0.0) or 0.0)
        if book_qty <= 0:
            # Conservative fallback liquidity proxy.
            book_qty = max(volume * 0.01, oi * 0.002, 1.0)

        size_ratio = qty / max(book_qty, 1.0)
        spread_penalty = 1.0 + min(2.0, spread_pct * 25.0)
        vol_penalty = 1.0 + min(2.0, vol * 0.25)
        effective_ratio = size_ratio * spread_penalty * vol_penalty
        fill_ratio = 1.0 / (1.0 + effective_ratio)
        fill_qty = int(math.floor(qty * fill_ratio))
        if fill_qty <= 0:
            fill_qty = 1
        fill_qty = min(fill_qty, qty)

        impact_bp = min(90.0, spread_pct * 10000.0 * 0.45 + effective_ratio * 6.5 + vol * 3.0)
        micro_bp = self._uniform(run_id, symbol, side, bid, ask, qty, "impact_jitter") * 1.25
        total_bp = max(0.0, impact_bp + micro_bp)

        if side == "BUY":
            # If ask has crossed the limit, execution occurs at ask; otherwise at limit
            # when modeled mid drift indicates passive crossing within latency window.
            fill_price = ask if ask <= limit_price else limit_price
        else:
            fill_price = bid
        slippage_bp = total_bp

        result["fill_qty"] = int(fill_qty)
        result["fill_price"] = round(float(fill_price), 2)
        result["status"] = "FILLED" if fill_qty >= qty else "PARTIAL"
        result["slippage_bp"] = round(float(slippage_bp), 4)
        result["reason"] = None
        return result
