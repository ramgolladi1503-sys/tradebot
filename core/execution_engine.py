import time
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

    def calibrate_slippage(self, slippage, instrument="OPT"):
        """
        Update slippage bps estimate using recent fill slippage.
        """
        if slippage is None:
            return
        # crude calibration: adjust bps toward observed slippage
        self.slippage_bps = max(1, min(25, int(self.slippage_bps * 0.9 + slippage * 10 * 0.1)))
        self.instrument_slippage[instrument] = self.slippage_bps

    def place_limit_order(self, trade, bid, ask):
        """
        Simulated limit order placement with retry logic.
        Replace with broker API call for live execution.
        """
        retries = getattr(cfg, "ORDER_RETRIES", 3)
        sleep_sec = getattr(cfg, "RETRY_SLEEP_SEC", 2)
        for _ in range(retries):
            limit_price = self.build_limit_price(trade.side, bid, ask)
            # Simulated fill condition
            if trade.side == "BUY" and limit_price >= ask:
                return True, limit_price
            if trade.side == "SELL" and limit_price <= bid:
                return True, limit_price
            time.sleep(sleep_sec)

        self.register_failure()
        return False, None

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
