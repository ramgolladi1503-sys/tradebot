"""Sentinel Live 1-Minute Candle Real-Time Paper Advisor.

Fetches live completed 1m candles directly from Upstox intraday endpoint
while live chunk ticks are capturing in the background.
Evaluates:
- 09:15-09:45 Opening Shock Range
- VWAP & Rejection Wicks
- Dynamic Slippage Veto Gate
- Real-time CE/PE paper triggers
"""

import time
import json
import urllib.request
from datetime import datetime, time as dtime
from pathlib import Path
import pandas as pd

from core.model_manifest_generator import SentinelManifestLock
from core.model_manifest_generator import SentinelManifestLock
from core.dynamic_slippage_model import DynamicOptionSlippageModel
from core.expiry_calendar import get_days_to_expiry, is_holiday

class SentinelLiveFeedAdvisor:
    def __init__(self, artifacts_dir: str = "artifacts", ticker: str = "NIFTY"):
        self.lock_mgr = SentinelManifestLock(artifact_directory=artifacts_dir)
        if not self.lock_mgr.verify_manifest_or_fail_closed():
            raise SystemExit("ABORT: Model manifest verification failed.")

        with open(Path(artifacts_dir) / "calibrated_regime_matrix.json") as f:
            self.calib = json.load(f)

        self.ticker = ticker.upper()
        self.slippage = DynamicOptionSlippageModel(base_brokerage_pts=0.40)
        self.spread_threshold = 0.04
        self.or_high = -1e9
        self.or_low = 1e9
        self.shock_active = True
        self.last_evaluated_bar = None
        self.position = None

        # Expiry Calendar State Check:
        # TUESDAY = NIFTY (0-DTE), THURSDAY = SENSEX (0-DTE)
        now_dt = datetime.now()
        self.dte = get_days_to_expiry(now_dt, self.ticker)
        self.is_expiry_day = (self.dte == 0)
        print(f"📅 [EXPIRY CALENDAR AUDIT] Asset: {self.ticker} | DTE: {self.dte} | Is Expiry Day (0-DTE): {self.is_expiry_day}")
        print(f"   (Schedule Rules: Tuesday = NIFTY Expiry, Thursday = SENSEX Expiry)")

    def fetch_live_1m_candles(self) -> list:
        url = "https://api.upstox.com/v2/historical-candle/intraday/NSE_INDEX%7CNifty%2050/1minute"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "TradeBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            candles = data.get("data", {}).get("candles", [])
            return sorted(candles, key=lambda x: x[0])

    def calibrate_morning_range(self, candles: list):
        """Processes historical morning bars (09:15-09:45) to calibrate Opening Range."""
        for c in candles:
            b_dt = datetime.fromisoformat(c[0])
            btime = b_dt.time()
            h, l = float(c[2]), float(c[3])
            if btime <= dtime(9, 45, 0):
                self.or_high = max(self.or_high, h)
                self.or_low = min(self.or_low, l)
        
        if self.or_high > -1e8 and self.or_low < 1e8:
            self.shock_active = False
            or_width = self.or_high - self.or_low
            print(f"🔓 [OPENING RANGE CALIBRATED] OR High: {self.or_high:.2f} | OR Low: {self.or_low:.2f} | Width: {or_width:.2f} pts")
            
            # Query Institutional Session Memory Bank for matching historical days
            try:
                from core.session_regime_memory import find_similar_sessions
                # Approximate morning efficiency ratio
                disp = abs(float(candles[-1][4]) - float(candles[0][1]))
                tot_p = sum(abs(float(candles[k][4]) - float(candles[k-1][4])) for k in range(1, len(candles)))
                approx_ker = disp / max(0.1, tot_p)
                matches = find_similar_sessions(current_ker=approx_ker, current_or_width=or_width, top_k=1)
                if matches:
                    m = matches[0]
                    print(f"🧠 [REGIME MEMORY RETRIEVAL] Matching Historical Session: {m['date']} (Regime: {m['classified_regime']}, KER: {m['ker_efficiency_ratio']})")
                    print(f"   💡 Historical Lesson: {m['key_lesson']}")
            except Exception as e:
                pass

    def run_loop(self):
        print("🛰️ [SENTINEL LIVE FEED ADVISOR ONLINE] Polling live completed 1m candles...")
        print("🛡️ [SLIPPAGE GATE ENGAGED] Spread Veto Threshold: 4.0%")

        # Initial calibration pass
        init_candles = self.fetch_live_1m_candles()
        if init_candles:
            self.calibrate_morning_range(init_candles)

        while True:
            try:
                candles = self.fetch_live_1m_candles()
                if not candles:
                    time.sleep(2.0)
                    continue

                # The endpoint only publishes closed 1m intervals; candles[-1] is the most recently completed minute bar
                closed_bar = candles[-1]
                bar_time_str = closed_bar[0]

                if bar_time_str == self.last_evaluated_bar:
                    time.sleep(1.0)
                    continue

                self.last_evaluated_bar = bar_time_str
                bar_dt = datetime.fromisoformat(bar_time_str)
                btime = bar_dt.time()
                o, h, l, c = float(closed_bar[1]), float(closed_bar[2]), float(closed_bar[3]), float(closed_bar[4])

                # Opening Shock Stand-Aside: 09:15 - 09:45
                if btime < dtime(9, 45, 0):
                    self.or_high = max(self.or_high, h)
                    self.or_low = min(self.or_low, l)
                    print(f"⏳ [OPENING SHOCK] [{btime.strftime('%H:%M:%S')}] Bar Close: {c:.2f} | OR High: {self.or_high:.2f} | OR Low: {self.or_low:.2f}")
                    time.sleep(3.0)
                    continue

                if self.shock_active:
                    print(f"🔓 [OPENING SHOCK CLEARED] OR High: {self.or_high:.2f} | OR Low: {self.or_low:.2f} | Width: {self.or_high - self.or_low:.2f} pts")
                    self.shock_active = False

                # Friction & Slippage calculation conditioned on Expiry Calendar
                premium_est = max(20.0, c * 0.005)
                # On 0-DTE expiry days, gamma is ~3x higher near ATM (0.0035 vs 0.0012)
                effective_gamma = 0.0035 if self.is_expiry_day else 0.0012
                now_t = datetime.combine(datetime.today(), btime)
                market_close_t = datetime.combine(datetime.today(), dtime(15, 30, 0))
                mins_to_close = max(0.0, (market_close_t - now_t).total_seconds() / 60.0)

                fric = self.slippage.compute_drag(
                    premium=premium_est,
                    bid=premium_est * 0.985,
                    ask=premium_est * 1.015,
                    minutes_to_close=mins_to_close,
                    gamma=effective_gamma
                )
                spread_ratio = fric.bid_ask_spread / premium_est

                # Causal Setup Detection
                # Wick calculation
                total_range = max(0.1, h - l)
                upper_wick = h - max(o, c)
                lower_wick = min(o, c) - l

                # Concrete Option Strike Contract Resolver (50 pt intervals for Nifty)
                atm_strike = int(round(c / 50.0) * 50)
                ce_contract = f"NIFTY {atm_strike} CE"
                pe_contract = f"NIFTY {atm_strike} PE"

                signal_display = "WAIT"
                target_pts = 18.0
                sl_pts = 12.0

                if c > self.or_high:
                    signal_display = f"🎯 [BUY {ce_contract}] @ Breakout > {self.or_high:.1f} | Target: +{target_pts}pts | SL: -{sl_pts}pts"
                elif c < self.or_low:
                    signal_display = f"🎯 [BUY {pe_contract}] @ Breakdown < {self.or_low:.1f} | Target: +{target_pts}pts | SL: -{sl_pts}pts"
                elif lower_wick >= 6.0 and (lower_wick / total_range) >= 0.40:
                    signal_display = f"🎯 [BUY {ce_contract}] @ Bullish Wick Rejection | Target: +{target_pts}pts | SL: -{sl_pts}pts"
                elif upper_wick >= 6.0 and (upper_wick / total_range) >= 0.40:
                    signal_display = f"🎯 [BUY {pe_contract}] @ Bearish Wick Rejection | Target: +{target_pts}pts | SL: -{sl_pts}pts"

                if spread_ratio > self.spread_threshold:
                    signal_display = f"🚨 [SPREAD VETO] {signal_display} -> SUPPRESSED (>4.0% spread)"

                print(f"📊 [{btime.strftime('%H:%M:%S')}] Spot: {c:.2f} (H:{h:.2f} L:{l:.2f}) | Drag: {fric.total_drag_pts:.2f}pts ({spread_ratio*100:.1f}%)")
                if "BUY" in signal_display:
                    print(f"   {signal_display}")
                else:
                    print(f"   Status: SCALP_MONITORING | Setup: WAIT")

                time.sleep(3.0)

            except Exception as e:
                print(f"Polling loop exception: {e}")
                time.sleep(3.0)

if __name__ == "__main__":
    advisor = SentinelLiveFeedAdvisor()
    advisor.run_loop()
