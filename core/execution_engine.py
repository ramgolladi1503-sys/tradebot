import time
import random
from config import config as cfg

class ExecutionEngine:
    def __init__(self):
        self.failed_executions = 0
        self.MAX_FAILED_EXECUTIONS = 3
        self.slippage_bps = getattr(cfg, "SLIPPAGE_BPS", 8)
        self.instrument_slippage = {}

    # -----------------------------
    # Slippage estimation
    # -----------------------------
    def estimate_slippage(self, bid, ask, volume):
        spread = ask - bid

        if spread <= 0:
            return 0

        # Liquidity-based slippage
        if volume < 5000:
            return spread * 0.8
        elif volume < 15000:
            return spread * 0.5
        else:
            return spread * 0.3

    # -----------------------------
    # Spread guard
    # -----------------------------
    def spread_ok(self, bid, ask, ltp, max_spread_pct=None):
        if not ltp:
            return False
        spread_pct = (ask - bid) / ltp
        if max_spread_pct is None:
            max_spread_pct = getattr(cfg, "MAX_SPREAD_PCT", 0.015)
        # Reject wide spreads
        return spread_pct <= max_spread_pct

    # -----------------------------
    # Latency penalty
    # -----------------------------
    def latency_penalty(self, data_timestamp):
        age = time.time() - data_timestamp

        if age <= 1:
            return 1.0
        elif age <= 2:
            return 0.9
        elif age <= 3:
            return 0.8
        else:
            return 0.6

    # -----------------------------
    # Execution kill switch
    # -----------------------------
    def register_failure(self):
        self.failed_executions += 1
        if self.failed_executions >= self.MAX_FAILED_EXECUTIONS:
            raise RuntimeError("❌ EXECUTION KILL SWITCH TRIGGERED")

    def reset_failures(self):
        self.failed_executions = 0

    # -----------------------------
    # Limit order helpers (simulated)
    # -----------------------------
    def build_limit_price(self, side, bid, ask):
        buffer = (self.slippage_bps / 10000.0)
        if side == "BUY":
            return round(ask * (1 + buffer), 2)
        return round(bid * (1 - buffer), 2)

    def adaptive_limit_price(self, side, bid, ask, spread_pct=None, depth_imbalance=None, vol_z=None):
        if bid <= 0 or ask <= 0:
            return None, {"reason": "bad_quote"}
        mid = (bid + ask) / 2.0
        if mid <= 0:
            return None, {"reason": "bad_mid"}
        base = (self.slippage_bps / 10000.0)
        spread_pct = spread_pct if spread_pct is not None else (ask - bid) / mid
        spread_buf = max(0.0, min(spread_pct * float(getattr(cfg, "EXEC_ALPHA_SPREAD_MULT", 0.6)),
                                   float(getattr(cfg, "EXEC_ALPHA_MAX_BUFFER_PCT", 0.01))))
        vol_z = float(vol_z) if vol_z is not None else 0.0
        vol_buf = abs(vol_z) * float(getattr(cfg, "EXEC_ALPHA_VOL_Z_BPS", 3.0)) / 10000.0
        imb = 0.0
        try:
            if depth_imbalance is not None:
                imb = max(-1.0, min(1.0, float(depth_imbalance)))
        except Exception:
            imb = 0.0
        imb_buf = abs(imb) * float(getattr(cfg, "EXEC_ALPHA_IMBALANCE_BPS", 2.0)) / 10000.0
        # Favor aggressive price when imbalance supports direction.
        if side == "BUY":
            buffer = base + spread_buf + vol_buf - (imb_buf if imb > 0 else 0.0)
            limit = ask * (1 + max(buffer, 0.0))
        else:
            buffer = base + spread_buf + vol_buf - (imb_buf if imb < 0 else 0.0)
            limit = bid * (1 - max(buffer, 0.0))
        return round(limit, 2), {
            "base_buffer": round(base, 6),
            "spread_buffer": round(spread_buf, 6),
            "vol_buffer": round(vol_buf, 6),
            "imb_buffer": round(imb_buf, 6),
            "spread_pct": round(spread_pct, 6) if spread_pct is not None else None,
        }

    def calibrate_slippage(self, slippage, instrument="OPT"):
        """
        Update slippage bps estimate using recent fill slippage.
        """
        if slippage is None:
            return
        # crude calibration: adjust bps toward observed slippage
        self.slippage_bps = max(1, min(25, int(self.slippage_bps * 0.9 + slippage * 10 * 0.1)))
        self.instrument_slippage[instrument] = self.slippage_bps

    def place_limit_order(self, trade, quote_fn, spread_pct=None, depth_imbalance=None, vol_z=None):
        """
        Simulated limit order placement with retry logic.
        Replace with broker API call for live execution.
        """
        if quote_fn is None or not callable(quote_fn):
            return False, None
        decision = quote_fn()
        if not decision:
            return False, None
        bid = decision.get("bid", 0) or 0
        ask = decision.get("ask", 0) or 0
        if bid <= 0 or ask <= 0:
            return False, None
        limit_price, _ = self.adaptive_limit_price(
            trade.side, bid, ask, spread_pct=spread_pct, depth_imbalance=depth_imbalance, vol_z=vol_z
        )
        if limit_price is None:
            return False, None
        filled, price, _ = self.simulate_limit_fill(
            trade,
            limit_price,
            quote_fn,
            timeout_sec=getattr(cfg, "EXEC_SIM_TIMEOUT_SEC", 3.0),
            poll_sec=getattr(cfg, "EXEC_SIM_POLL_SEC", 0.25),
            max_chase_pct=getattr(cfg, "EXEC_MAX_CHASE_PCT", 0.002),
            spread_widen_pct=getattr(cfg, "EXEC_SPREAD_WIDEN_PCT", 0.5),
            max_spread_pct=getattr(cfg, "MAX_SPREAD_PCT", 0.015),
            max_quote_age_sec=getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0),
            fill_prob=getattr(cfg, "EXEC_FILL_PROB", 0.85),
        )
        if not filled:
            self.register_failure()
            return False, None
        return True, price

    def simulate_order_slicing(self, trade, bid, ask, volume, depth=None):
        """
        Simulate sliced fills using spread and volume as liquidity proxies.
        """
        if trade.instrument == "OPT":
            slices = getattr(cfg, "ORDER_SLICES_OPT", 3)
        elif trade.instrument == "FUT":
            slices = getattr(cfg, "ORDER_SLICES_FUT", 2)
        else:
            slices = getattr(cfg, "ORDER_SLICES_EQ", 1)
        total_qty = max(1, trade.qty)
        slice_qty = max(1, total_qty // slices)
        filled_qty = 0
        fill_price = 0.0
        spread = max(ask - bid, 0)
        impact_alpha = getattr(cfg, "IMPACT_ALPHA", 0.15)
        queue_alpha = getattr(cfg, "QUEUE_ALPHA", 0.25) if getattr(cfg, "QUEUE_POSITION_MODEL", True) else 0.0
        for _ in range(slices):
            # simple slippage model
            base_slip = self.estimate_slippage(bid, ask, volume)
            if depth:
                try:
                    top_bid = depth.get("buy", [{}])[0].get("price", bid)
                    top_ask = depth.get("sell", [{}])[0].get("price", ask)
                    spread = max(top_ask - top_bid, spread)
                except Exception:
                    pass
            impact = (slice_qty / max(volume, 1)) * impact_alpha * spread
            queue_penalty = queue_alpha * spread
            slippage = base_slip + impact + queue_penalty
            price = (ask + slippage) if trade.side == "BUY" else (bid - slippage)
            fill_price += price * slice_qty
            filled_qty += slice_qty
        if filled_qty == 0:
            return False, None
        avg_price = round(fill_price / filled_qty, 2)
        return True, avg_price

    # -----------------------------
    # Queue position estimator (depth-based)
    # -----------------------------
    def estimate_queue_position(self, depth, side, limit_price=None, qty=1):
        if not depth:
            return None
        try:
            book = depth.get("buy") if side == "BUY" else depth.get("sell")
            if not book:
                return None
            top = book[0]
            top_qty = float(top.get("quantity", 0) or 0)
            top_price = float(top.get("price", 0) or 0)
            if limit_price is not None and top_price:
                if side == "BUY" and limit_price > top_price:
                    return 0.0
                if side == "SELL" and limit_price < top_price:
                    return 0.0
            denom = max(top_qty + max(qty, 1), 1.0)
            return round(top_qty / denom, 4)
        except Exception:
            return None

    # -----------------------------
    # Quote-driven limit simulation
    # -----------------------------
    def simulate_limit_fill(
        self,
        trade,
        limit_price,
        quote_fn=None,
        snapshot_fn=None,
        timeout_sec=0.0,
        poll_sec=0.0,
        max_chase_pct=0.0,
        spread_widen_pct=0.0,
        max_spread_pct=0.0,
        max_quote_age_sec=None,
        fill_prob=1.0,
    ):
        """
        Simulate a limit order using sequential quote snapshots.
        Buy fills ONLY if limit >= ask on a later snapshot.
        Sell fills ONLY if limit <= bid on a later snapshot.
        """
        def _mid_spread(bid, ask):
            mid = (bid + ask) / 2.0 if bid and ask else 0.0
            spread = max(ask - bid, 0.0) if bid and ask else 0.0
            return mid, spread

        if quote_fn is None:
            quote_fn = snapshot_fn
        decision = quote_fn() if quote_fn else None
        if not decision:
            return False, None, {
                "decision_mid": None,
                "decision_spread": None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "no_quote",
            }
        bid0 = decision.get("bid", 0) or 0
        ask0 = decision.get("ask", 0) or 0
        ts0 = decision.get("ts")
        if ts0 is None:
            ts0 = time.time()
        decision_mid, decision_spread = _mid_spread(bid0, ask0)
        if decision_mid <= 0 or decision_spread <= 0:
            return False, None, {
                "decision_mid": decision_mid or None,
                "decision_spread": decision_spread or None,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "bad_initial_quote",
            }
        # If we still do not have a timestamp, fail closed.
        if ts0 is None:
            return False, None, {
                "decision_mid": decision_mid,
                "decision_spread": decision_spread,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "missing_quote_ts",
            }
        if max_quote_age_sec is not None and (time.time() - ts0) > max_quote_age_sec:
            return False, None, {
                "decision_mid": decision_mid,
                "decision_spread": decision_spread,
                "fill_price": None,
                "slippage": None,
                "reason_if_aborted": "stale_quote",
            }

        start = time.time()
        current_limit = limit_price
        reason = "timeout"
        attempts = [{
            "ts": ts0,
            "bid": bid0,
            "ask": ask0,
            "spread": round(decision_spread, 6),
        }]

        while time.time() - start <= timeout_sec:
            snap = quote_fn()
            if not snap:
                reason = "no_quote"
                break
            bid = snap.get("bid", 0) or 0
            ask = snap.get("ask", 0) or 0
            ts = snap.get("ts")
            if ts is None:
                ts = time.time()
            if bid <= 0 or ask <= 0:
                time.sleep(poll_sec)
                continue

            mid, spread = _mid_spread(bid, ask)
            attempts.append({
                "ts": ts,
                "bid": bid,
                "ask": ask,
                "spread": round(spread, 6),
            })
            if ts is None:
                reason = "missing_quote_ts"
                break
            if max_quote_age_sec is not None and (time.time() - ts) > max_quote_age_sec:
                reason = "stale_quote"
                break
            # Optional chase (bounded)
            if max_chase_pct and max_chase_pct > 0:
                if trade.side == "BUY":
                    max_limit = decision_mid * (1 + max_chase_pct)
                    if ask > current_limit and ask <= max_limit:
                        current_limit = ask
                    elif ask > max_limit:
                        reason = "max_chase_exceeded"
                        break
                else:
                    min_limit = decision_mid * (1 - max_chase_pct)
                    if bid < current_limit and bid >= min_limit:
                        current_limit = bid
                    elif bid < min_limit:
                        reason = "max_chase_exceeded"
                        break

            if max_spread_pct and mid > 0 and (spread / mid) > max_spread_pct:
                reason = "spread_too_wide"
                break
            if spread_widen_pct and decision_spread > 0 and spread > decision_spread * (1 + spread_widen_pct):
                reason = "spread_widened"
                break

            can_fill = (trade.side == "BUY" and current_limit >= ask) or (trade.side == "SELL" and current_limit <= bid)
            if can_fill:
                if fill_prob < 1.0 and random.random() > fill_prob:
                    time.sleep(poll_sec)
                    continue
                fill_price = ask if trade.side == "BUY" else bid
                slippage = (fill_price - decision_mid) if trade.side == "BUY" else (decision_mid - fill_price)
                return True, round(fill_price, 2), {
                    "decision_mid": round(decision_mid, 2),
                    "decision_spread": round(decision_spread, 2),
                    "fill_price": round(fill_price, 2),
                    "slippage": round(slippage, 4),
                    "reason_if_aborted": None,
                    "attempts": attempts,
                }

            time.sleep(poll_sec)

        return False, None, {
            "decision_mid": round(decision_mid, 2),
            "decision_spread": round(decision_spread, 2),
            "fill_price": None,
            "slippage": None,
            "reason_if_aborted": reason,
            "attempts": attempts,
        }
