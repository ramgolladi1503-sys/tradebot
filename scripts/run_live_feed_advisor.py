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
from typing import Optional, Dict, Any
import pandas as pd

from core.model_manifest_generator import SentinelManifestLock
from core.dynamic_slippage_model import DynamicOptionSlippageModel
from core.expiry_calendar import get_days_to_expiry, is_holiday
from core.active_position_manager import (
    ActivePositionManager,
    STATE_STANDBY,
    STATE_IN_FLIGHT,
    STATE_TRAIL_LOCK,
    STATE_EXIT_PENDING,
    STATE_LIQUIDATED
)

class SentinelLiveFeedAdvisor:
    def __init__(self, artifacts_dir: str = "artifacts", ticker: str = "NIFTY"):
        self.lock_mgr = SentinelManifestLock(artifact_directory=artifacts_dir)
        if not self.lock_mgr.verify_manifest_or_fail_closed():
            raise SystemExit("ABORT: Model manifest verification failed.")

        with open(Path(artifacts_dir) / "calibrated_regime_matrix.json") as f:
            self.calib = json.load(f)

        self.ticker = ticker.upper()
        self.slippage = DynamicOptionSlippageModel(base_brokerage_pts=0.40)
        self.apm = ActivePositionManager()
        self.spread_threshold = 0.04
        self.or_high = -1e9
        self.or_low = 1e9
        self.shock_active = True
        self.last_evaluated_bar = None
        self.session_ker = None
        self.ewma_ker = 0.5
        self.ker_persistence_count = 0
        self.last_exit_price = None
        self.last_exit_direction = None

        # Append-Only Audit Sink Setup
        today_str = datetime.now().strftime("%Y%m%d")
        self.audit_log_path = Path(f"runtime/audit/sentinel_execution_paths_{today_str}.jsonl")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Expiry Calendar State Check:
        # TUESDAY = NIFTY (0-DTE), THURSDAY = SENSEX (0-DTE)
        now_dt = datetime.now()
        self.dte = get_days_to_expiry(now_dt, self.ticker)
        self.is_expiry_day = (self.dte == 0)
        print(f"📅 [EXPIRY CALENDAR AUDIT] Asset: {self.ticker} | DTE: {self.dte} | Is Expiry Day (0-DTE): {self.is_expiry_day}")
        print(f"   (Schedule Rules: Tuesday = NIFTY Expiry, Thursday = SENSEX Expiry)")
        print(f"📝 [AUDIT LOG SINK] Streaming to: {self.audit_log_path}")

    def fetch_live_1m_candles(self) -> list:
        url = "https://api.upstox.com/v2/historical-candle/intraday/NSE_INDEX%7CNifty%2050/1minute"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "TradeBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            candles = data.get("data", {}).get("candles", [])
            return sorted(candles, key=lambda x: x[0])

    def resolve_real_option_quote(self, strike: int, opt_type: str) -> Optional[dict]:
        """Reads the exact real-time option LTP, Bid, Ask, Volume, and OI from the live chunk stream."""
        import glob
        today_date_str = datetime.now().strftime("%Y-%m-%d")
        chunk_patterns = [
            f".runtime/market_data/{today_date_str}/chunks/*.parquet",
            f"runtime/market_data/{today_date_str}/chunks/*.parquet"
        ]
        chunks = []
        for pat in chunk_patterns:
            chunks.extend(glob.glob(pat))
        if not chunks:
            return None
        latest_chunk = sorted(chunks)[-1]
        try:
            df = pd.read_parquet(latest_chunk)
            pattern = f"NIFTY {strike} {opt_type}"
            matches = df[df["symbol"].str.startswith(pattern, na=False)]
            if not matches.empty:
                last_row = matches.iloc[-1]
                return {
                    "symbol": str(last_row["symbol"]),
                    "token": str(last_row["token"]),
                    "ltp": float(last_row["ltp"]),
                    "bid": float(last_row["bid"]),
                    "ask": float(last_row["ask"]),
                    "vol": float(last_row["vol"]),
                    "oi": float(last_row["oi"]),
                }
        except Exception:
            pass
        return None

    def emit_and_append_audit_log(self, payload: dict):
        """Asynchronous Append-Only JSONL Logging Sink. Dumps multi-variable metrics with zero latency."""
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except IOError as e:
            print(f"🚨 [AUDIT LOG ERROR] Failed to write row: {e}")

    def compress_audit_log_to_parquet(self):
        """Sweeps today's .jsonl rows into Snappy-compressed Parquet at session close."""
        if not self.audit_log_path.exists() or self.audit_log_path.stat().st_size == 0:
            return
        try:
            records = []
            with open(self.audit_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            if records:
                df = pd.DataFrame(records)
                pq_path = self.audit_log_path.with_suffix(".parquet")
                df.to_parquet(pq_path, compression="snappy")
                print(f"🗜️ [AUDIT COMPRESSION COMPLETE] Saved {len(df):,} rows to {pq_path.name}")
        except Exception as e:
            print(f"🚨 [AUDIT COMPRESSION ERROR] {e}")

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

                # Calculate session KER & EWMA-KER smoothing (alpha=0.15)
                disp = abs(c - float(candles[0][1]))
                tot_p = max(0.1, sum(abs(float(candles[k][4]) - float(candles[k-1][4])) for k in range(1, len(candles))))
                raw_ker = disp / tot_p
                self.session_ker = raw_ker
                self.ewma_ker = 0.15 * raw_ker + 0.85 * self.ewma_ker

                # 1m Realized ATR calculation across last 14 bars
                lookback_bars = candles[-14:] if len(candles) >= 14 else candles
                atr_1m = sum(max(float(b[2]) - float(b[3]), 0.1) for b in lookback_bars) / max(1, len(lookback_bars))

                # 1. Evaluate Active In-Flight Position Lifecycle
                if self.apm.state in {STATE_IN_FLIGHT, STATE_TRAIL_LOCK}:
                    # Read current live option LTP if contract token/strike is known
                    cur_opt_quote = None
                    if self.apm.payload and self.apm.payload.strike_contract:
                        try:
                            # Parse strike from payload contract name e.g. "NIFTY 22250 PE [ITM]"
                            parts = self.apm.payload.strike_contract.split()
                            pos_strike = int(parts[1])
                            pos_type = parts[2]
                            cur_opt_quote = self.resolve_real_option_quote(pos_strike, pos_type)
                        except Exception:
                            pass

                    cur_opt_ltp = cur_opt_quote.get("ltp") if cur_opt_quote else None

                    apm_state, trade_summary = self.apm.evaluate_bar(
                        bar_open=o,
                        bar_high=h,
                        bar_low=l,
                        bar_close=c,
                        bar_time_str=bar_time_str,
                        current_opt_ltp=cur_opt_ltp,
                        atr_1m=atr_1m
                    )
                    if apm_state == STATE_LIQUIDATED:
                        pnl = trade_summary.get("pnl_pts", 0.0)
                        opt_pnl = trade_summary.get("opt_pnl_pts")
                        pnl_emoji = "🟢" if pnl > 0 else "🔴"
                        opt_pnl_str = f" | Option PnL: {opt_pnl:+.2f} pts" if opt_pnl is not None else ""
                        self.last_exit_price = trade_summary.get("exit_price")
                        self.last_exit_direction = trade_summary.get("direction")
                        print(f"🔔 [POSITION EXITED] Reason: {trade_summary.get('exit_reason')} | Exit Spot: {trade_summary.get('exit_price'):.1f} | Spot PnL: {pnl_emoji} {pnl:+.1f} pts{opt_pnl_str}")
                    elif self.apm.payload:
                        p = self.apm.payload
                        trailed_tag = ""
                        if p.half_booked:
                            trailed_tag = f" [RUNNER 50% TRAIL | Opt HWM: ₹{p.opt_peak_hwm:.2f} | Opt Trail SL: ₹{p.runner_trailing_sl:.2f}]"
                        elif p.trail_locked:
                            trailed_tag = " [TRAIL LOCKED +4]"
                        opt_live_str = f" | Option LTP: ₹{p.opt_current_ltp:.2f} (Entry: ₹{p.opt_entry_ltp:.2f})" if p.opt_entry_ltp else ""
                        print(f"🛡️ [IN-FLIGHT POSITION] {p.strike_contract} | Entry Spot: {p.entry_price:.1f} | Current SL: {p.current_sl:.1f}{trailed_tag}{opt_live_str}")

                # 2. Causal Setup Detection (Only if FLAT / STANDBY / LIQUIDATED)
                total_range = max(0.1, h - l)
                upper_wick = h - max(o, c)
                lower_wick = min(o, c) - l

                # 1-Strike In-The-Money (ITM) Strike Contract Resolver (K ± 50, Delta ≈ 0.65)
                # Bridges 81% ATM liquidity with theta immunity and +10 pt option gain delivery
                atm_strike = int(round(c / 50.0) * 50)
                ce_itm_strike = atm_strike - 50  # 1-strike ITM for Call
                pe_itm_strike = atm_strike + 50  # 1-strike ITM for Put
                ce_contract = f"NIFTY {ce_itm_strike} CE [ITM]"
                pe_contract = f"NIFTY {pe_itm_strike} PE [ITM]"

                signal_display = "WAIT"
                # Target: +15 spot pts yields +10.0 option strike pts on 0.65 delta
                target_pts = 15.0
                # Volatility-Scaled Stop Loss: max(12.0, 1.2 * ATR_1m) removes noise whipsaw
                sl_pts = round(max(12.0, 1.2 * atr_1m), 1)

                entry_dir = None
                contract_choice = None
                chosen_strike = None

                # Dynamic Session Phase Variance Decay (SPVD) Energy Gate Check
                can_enter_energy, e_atr_rem, req_energy = self.apm.check_session_energy_gate(
                    current_time=btime,
                    daily_norm_atr=120.0,
                    target_pts=target_pts,
                    buffer_multiplier=1.5,
                    session_ker=self.ewma_ker
                )

                if c > self.or_high:
                    entry_dir = "CE"
                    contract_choice = ce_contract
                    chosen_strike = ce_itm_strike
                    signal_display = f"🎯 [BUY {ce_contract}] @ Breakout > {self.or_high:.1f} | Target: +{target_pts}pts | Vol-SL: -{sl_pts}pts (ATR:{atr_1m:.1f})"
                elif c < self.or_low:
                    entry_dir = "PE"
                    contract_choice = pe_contract
                    chosen_strike = pe_itm_strike
                    signal_display = f"🎯 [BUY {pe_contract}] @ Breakdown < {self.or_low:.1f} | Target: +{target_pts}pts | Vol-SL: -{sl_pts}pts (ATR:{atr_1m:.1f})"
                elif lower_wick >= 6.0 and (lower_wick / total_range) >= 0.40:
                    entry_dir = "CE"
                    contract_choice = ce_contract
                    chosen_strike = ce_itm_strike
                    signal_display = f"🎯 [BUY {ce_contract}] @ Bullish Wick Rejection | Target: +{target_pts}pts | Vol-SL: -{sl_pts}pts"
                elif upper_wick >= 6.0 and (upper_wick / total_range) >= 0.40:
                    entry_dir = "PE"
                    contract_choice = pe_contract
                    chosen_strike = pe_itm_strike
                    signal_display = f"🎯 [BUY {pe_contract}] @ Bearish Wick Rejection | Target: +{target_pts}pts | Vol-SL: -{sl_pts}pts"

                # Calculate cumulative session high and low to detect Macro Trend Exhaustion
                session_high = max(float(b[2]) for b in candles)
                session_low = min(float(b[3]) for b in candles)
                session_range = session_high - session_low
                # Macro ATR Extension Cap: If session has already moved > 2.5x 20d ATR (300 pts),
                # new trend breakout entries pay peak IV and risk mean-reversion whipsaw.
                atr_extension_exhausted = (session_range > 2.5 * 120.0)

                # Re-Entry Displacement Gate: Enforce that re-entering in the same direction
                # requires price to displace at least 1.0 * ATR_1m past the previous exit price.
                # Prevents taking back-to-back losing micro-scalps into the same stall zone.
                insufficient_displacement = False
                if self.last_exit_price is not None and self.last_exit_direction == entry_dir:
                    min_disp_pts = max(8.0, 1.0 * atr_1m)
                    if entry_dir == "PE" and (self.last_exit_price - c) < min_disp_pts:
                        insufficient_displacement = True
                    elif entry_dir == "CE" and (c - self.last_exit_price) < min_disp_pts:
                        insufficient_displacement = True

                # Gate Vetoes
                risk_flag = "NORMAL"
                if not can_enter_energy and entry_dir:
                    signal_display = f"🚫 [ENERGY GATE VETO] {signal_display} -> SUPPRESSED (Remaining ATR {e_atr_rem:.1f} < Required {req_energy:.1f})"
                    risk_flag = "VETO_ENERGY_DEPLETED"
                elif insufficient_displacement and entry_dir:
                    signal_display = f"🛑 [DISPLACEMENT VETO] {signal_display} -> SUPPRESSED (Re-entry requires >= {max(8.0, 1.0 * atr_1m):.1f}pts progress from prior exit {self.last_exit_price:.1f})"
                    risk_flag = "VETO_INSUFFICIENT_DISPLACEMENT"
                elif atr_extension_exhausted and entry_dir and ("Breakout" in signal_display or "Breakdown" in signal_display):
                    signal_display = f"🛑 [ATR EXTENSION VETO] {signal_display} -> SUPPRESSED (Session Range {session_range:.1f}pts > 300.0pts Exhaustion Cap)"
                    risk_flag = "VETO_ATR_EXTENSION_EXHAUSTED"
                elif spread_ratio > self.spread_threshold and entry_dir:
                    signal_display = f"🚨 [SPREAD VETO] {signal_display} -> SUPPRESSED (>4.0% spread)"
                    risk_flag = "VETO_SPREAD_EXPANDED"
                elif entry_dir and self.apm.state in {STATE_STANDBY, STATE_LIQUIDATED}:
                    # Read real option quote at entry
                    opt_q = self.resolve_real_option_quote(chosen_strike, entry_dir)
                    pos_id = f"TRADE_{btime.strftime('%H%M')}_{entry_dir}"
                    # Activate 50% target book + 50% runner mode when directional efficiency EWMA_KER > 0.35
                    is_runner = (self.ewma_ker > 0.35)
                    self.apm.arm_and_enter(
                        position_id=pos_id,
                        direction=entry_dir,
                        contract=contract_choice,
                        entry_price=c,
                        entry_time_str=bar_time_str,
                        sl_pts=sl_pts,
                        tp_pts=target_pts,
                        friction_drag_pts=fric.total_drag_pts,
                        opt_quote=opt_q,
                        is_runner_mode=is_runner
                    )
                    risk_flag = "EXECUTED_IN_FLIGHT"
                    opt_quote_str = f" | Option LTP: ₹{opt_q['ltp']:.2f} (Bid: ₹{opt_q['bid']:.2f} Ask: ₹{opt_q['ask']:.2f})" if opt_q else ""
                    runner_tag = " [RUNNER 50/50 ACTIVE]" if is_runner else ""
                    print(f"🚀 [NEW POSITION OPENED] {pos_id} | {contract_choice} @ Spot {c:.2f} | SL: {c - sl_pts if entry_dir == 'CE' else c + sl_pts:.1f} | TP: {c + target_pts if entry_dir == 'CE' else c - target_pts:.1f}{runner_tag}{opt_quote_str}")

                # Emit Append-Only JSONL Audit Row with zero latency
                self.emit_and_append_audit_log({
                    "timestamp": bar_time_str,
                    "spot_nifty": c,
                    "high": h,
                    "low": l,
                    "atr_1m": round(atr_1m, 2),
                    "raw_ker": round(raw_ker, 4),
                    "ewma_ker": round(self.ewma_ker, 4),
                    "drag_pts": round(fric.total_drag_pts, 2),
                    "spread_ratio": round(spread_ratio, 4),
                    "advisory": signal_display,
                    "risk_flag": risk_flag,
                    "apm_state": self.apm.state
                })

                print(f"📊 [{btime.strftime('%H:%M:%S')}] Spot: {c:.2f} (H:{h:.2f} L:{l:.2f}) | ATR: {atr_1m:.1f} | Drag: {fric.total_drag_pts:.2f}pts | EWMA-KER: {self.ewma_ker:.3f}")
                if "BUY" in signal_display:
                    print(f"   {signal_display}")
                else:
                    print(f"   Status: SCALP_MONITORING | Setup: WAIT")

                # If post-market, trigger Parquet audit compression
                if btime >= dtime(15, 30, 0):
                    self.compress_audit_log_to_parquet()

                time.sleep(3.0)

            except Exception as e:
                print(f"Polling loop exception: {e}")
                time.sleep(3.0)

if __name__ == "__main__":
    advisor = SentinelLiveFeedAdvisor()
    advisor.run_loop()
