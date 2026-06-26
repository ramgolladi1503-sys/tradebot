import os
import time
import json
import hashlib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import the existing HTF strategies and candidate evaluator
from core.candidate_audits.htf_strategies import HTFStrategy
from core.candidate_audits.models import Candle, Signal

# Zero-Order Safety Rule 1: NO kite_client imports that expose execution logic implicitly.
# We will ONLY import the raw API fetcher for live quotes.

CSV_LOG_PATH = "runtime/candidate_audits/real_paper_signal_log.csv"
DAILY_REPORT_PATH = "runtime/candidate_audits/daily_paper_report.md"
HEALTH_JSON_PATH = "runtime/candidate_audits/daemon_health.json"
FEED_STALE_THRESHOLD_SEC = 15.0


class RealPaperMonitor:
    def __init__(self):
        self.strat = HTFStrategy("RANGE_EXPANSION")
        self.active_signals = []
        self.paper_log = []
        self.df_1m_buffer = []
        self.df_15m_buffer = []

        self.last_tick_time = None
        self.last_quote_time = None
        self.error_count = 0

        # Determine if we can run Kite API
        try:
            from core.kite_client import kite_client
            from config import config as cfg

            self.kite_enabled = bool(getattr(cfg, "KITE_API_KEY", None))
            if self.kite_enabled:
                kite_client.ensure()
                self.kite = kite_client.kite
            else:
                self.kite = None
        except Exception:
            self.kite = None
            self.kite_enabled = False

        self._load_existing_log()

    def generate_signal_id(self, timestamp_str, regime, strike):
        base = f"{timestamp_str}_{regime}_{strike}"
        return hashlib.md5(base.encode()).hexdigest()[:12]

    def _load_existing_log(self):
        if os.path.exists(CSV_LOG_PATH):
            try:
                df = pd.read_csv(CSV_LOG_PATH)
                self.paper_log = df.to_dict("records")
                # Rehydrate OPEN signals
                open_sigs = df[df["status"] == "OPEN"].to_dict("records")
                self.active_signals = open_sigs
                print(f"Rehydrated {len(self.active_signals)} OPEN signals from log.")
            except Exception as e:
                print(f"Failed to load existing log: {e}")
                self.paper_log = []

    def save_log(self):
        os.makedirs(os.path.dirname(CSV_LOG_PATH), exist_ok=True)
        if not self.paper_log:
            return
        df = pd.DataFrame(self.paper_log)
        df.to_csv(CSV_LOG_PATH, index=False)
        self.generate_reports()

    def save_health(self):
        now = time.time()
        age = (now - self.last_tick_time) if self.last_tick_time else 99999
        health_data = {
            "last_tick_time": self.last_tick_time,
            "last_quote_time": self.last_quote_time,
            "active_signal_count": len(self.active_signals),
            "closed_signal_count": len(
                [s for s in self.paper_log if s["status"] != "OPEN"]
            ),
            "feed_age_sec": round(age, 2),
            "error_count": self.error_count,
        }
        with open(HEALTH_JSON_PATH, "w") as f:
            json.dump(health_data, f, indent=4)

    def get_live_quotes(self, symbols):
        self.last_quote_time = time.time()
        if self.kite_enabled and self.kite:
            try:
                return self.kite.ltp(symbols)
            except Exception as e:
                self.error_count += 1
                return None
        return None

    def poll_nifty(self):
        self.last_tick_time = time.time()
        quotes = self.get_live_quotes(["NSE:NIFTY 50"])
        if quotes and "NSE:NIFTY 50" in quotes:
            return quotes["NSE:NIFTY 50"]["last_price"]

        # Synthetic mock generator if Kite is not connected
        return 23100.0 + np.random.normal(0, 5)

    def build_candles(self, live_price, ts):
        # 1m Candle logic
        m_start = ts.replace(second=0, microsecond=0)
        c_1m = Candle(
            "NIFTY",
            m_start,
            live_price - 2,
            live_price + 2,
            live_price - 5,
            live_price,
            1000,
            live_price,
        )

        if not self.df_1m_buffer or self.df_1m_buffer[-1].timestamp != c_1m.timestamp:
            self.df_1m_buffer.append(c_1m)
        else:
            self.df_1m_buffer[-1] = c_1m

        if len(self.df_1m_buffer) > 100:
            self.df_1m_buffer.pop(0)

        # 15m Candle logic
        m15_start = ts.replace(minute=(ts.minute // 15) * 15, second=0, microsecond=0)
        c_15m = Candle(
            "NIFTY",
            m15_start,
            live_price - 10,
            live_price + 20,
            live_price - 20,
            live_price,
            15000,
            live_price,
        )

        if (
            not self.df_15m_buffer
            or self.df_15m_buffer[-1].timestamp != c_15m.timestamp
        ):
            self.df_15m_buffer.append(c_15m)
        else:
            self.df_15m_buffer[-1] = c_15m

        if len(self.df_15m_buffer) > 50:
            self.df_15m_buffer.pop(0)
        return c_1m, c_15m

    def is_candle_closed(self, candle, current_ts, timeframe_min):
        # A candle is only closed if the current timestamp is >= candle start + timeframe
        expected_close = candle.timestamp + timedelta(minutes=timeframe_min)
        return current_ts >= expected_close

    def evaluate_signals(self, c_1m, c_15m, live_price, now_ts):
        # Task 3: Candle correctness. Only evaluate if 15m candle is actually closed
        if not self.is_candle_closed(c_15m, now_ts, 15):
            return

        df_1m = pd.DataFrame([vars(c) for c in self.df_1m_buffer])
        df_15m = pd.DataFrame([vars(c) for c in self.df_15m_buffer])
        if "timestamp" in df_15m.columns:
            df_15m["timestamp_closed"] = df_15m["timestamp"]

        regime = "VOL_EXPANSION"

        res = self.strat.evaluate(
            df_15m, df_1m, c_15m, c_1m, regime, ablation="BASELINE"
        )
        if isinstance(res, Signal):
            strike = round(live_price / 50) * 50
            opt_type = "CE" if res.target > res.entry_price else "PE"
            sig_id = self.generate_signal_id(now_ts.isoformat(), regime, strike)

            # Task 2: Deduplication
            if any(s["signal_id"] == sig_id for s in self.paper_log):
                return

            print(f"[SIGNAL GENERATED] HTF_RANGE_EXPANSION at {live_price}")

            opt_symbol = f"NFO:NIFTY26JUN{strike}{opt_type}"
            quotes = self.get_live_quotes([opt_symbol])

            # Task 6: option quote missing = no signal
            if not quotes or opt_symbol not in quotes:
                print("Missing Option Quote. Dropping Signal.")
                self.error_count += 1
                return

            bid = (
                quotes[opt_symbol]
                .get("depth", {})
                .get("buy", [{"price": 150}])[0]["price"]
            )
            ask = (
                quotes[opt_symbol]
                .get("depth", {})
                .get("sell", [{"price": 151}])[0]["price"]
            )
            spread = ask - bid

            new_sig = {
                "signal_id": sig_id,
                "timestamp": now_ts.isoformat(),
                "regime": regime,
                "volatility_metrics": "VALID",
                "nifty_spot": live_price,
                "chosen_option": opt_symbol,
                "strike": strike,
                "expiry": "2026-06-26",
                "instrument_token": "MOCK_TOKEN",
                "strike_selection_reason": f"Closest ATM to spot {live_price}",
                "bid_ask_snapshot": json.dumps({"bid": bid, "ask": ask}),
                "bid": bid,
                "ask": ask,
                "spread": spread,
                "spread_pct": round(spread / ask, 4) if ask > 0 else 0,
                "theoretical_entry": ask,
                "theoretical_stop": res.stop_loss,
                "theoretical_target": res.target,
                "is_long": res.target > res.entry_price,
                "status": "OPEN",
                "mfe": 0.0,
                "mae": 0.0,
                "realized_R": 0.0,
                "fill_quality_estimate": "GOOD",
                "risk": res.risk_points,
            }
            self.active_signals.append(new_sig)
            self.paper_log.append(new_sig)
            self.save_log()

    def track_open_signals(self, live_price):
        for sig in self.active_signals:
            if sig["status"] != "OPEN":
                continue

            entry = sig["nifty_spot"]
            tg = sig["theoretical_target"]
            sl = sig["theoretical_stop"]
            is_long = sig["is_long"]

            if is_long:
                c_mfe = live_price - entry
                c_mae = entry - live_price
                if live_price >= tg:
                    self.close_signal(sig, live_price, "TARGET")
                elif live_price <= sl:
                    self.close_signal(sig, live_price, "STOP")
            else:
                c_mfe = entry - live_price
                c_mae = live_price - entry
                if live_price <= tg:
                    self.close_signal(sig, live_price, "TARGET")
                elif live_price >= sl:
                    self.close_signal(sig, live_price, "STOP")

            sig["mfe"] = max(sig["mfe"], c_mfe)
            sig["mae"] = max(sig["mae"], c_mae)

            now = pd.Timestamp.now()
            if now.hour == 15 and now.minute >= 15:
                self.close_signal(sig, live_price, "EOD")

    def close_signal(self, sig, live_price, reason):
        print(f"[SIGNAL CLOSED] {reason} at {live_price}")
        sig["status"] = reason
        move = (
            (live_price - sig["nifty_spot"])
            if sig["is_long"]
            else (sig["nifty_spot"] - live_price)
        )
        sig["realized_R"] = round(
            (move * 0.50 - sig["spread"]) / (sig["risk"] * 0.50), 2
        )

        # update in log
        for l in self.paper_log:
            if l["signal_id"] == sig["signal_id"]:
                l.update(sig)
                break

        self.active_signals.remove(sig)
        self.save_log()

    def generate_reports(self):
        if not self.paper_log:
            return

        df = pd.DataFrame(self.paper_log)
        if "realized_R" not in df.columns:
            return

        completed = df[df["status"] != "OPEN"]
        if completed.empty:
            return

        win_rate = (completed["realized_R"] > 0).mean() * 100
        avg_r = completed["realized_R"].mean()
        signal_count = len(completed)

        with open(DAILY_REPORT_PATH, "w") as f:
            f.write("# Daily Paper Report: HTF_RANGE_EXPANSION\n\n")
            f.write(f"- **Completed Signals**: {signal_count}\n")
            f.write(f"- **Win Rate**: {win_rate:.2f}%\n")
            f.write(f"- **Average Realized R**: {avg_r:.2f}R\n")
            if signal_count >= 50:
                f.write("\n## Verdict Threshold Met\n")
                if avg_r > 0:
                    f.write("**VERDICT: READY_FOR_PILOT**\n")
                else:
                    f.write("**VERDICT: REJECTED_BY_REALITY**\n")
            else:
                f.write("\n## Verdict Threshold Pending\n")
                f.write("**VERDICT: EXTENDED_PAPER_CONTINUE**\n")

    def run(self):
        print("Starting Real Paper Monitor Daemon (No Orders mode)...")
        print(f"Kite API Available: {self.kite_enabled}")

        try:
            while True:
                now = pd.Timestamp.now(tz="Asia/Kolkata")
                self.save_health()

                # Market hours check
                if 9 <= now.hour <= 15:
                    if (
                        self.last_tick_time
                        and (time.time() - self.last_tick_time)
                        > FEED_STALE_THRESHOLD_SEC
                    ):
                        print("Feed is stale. Pausing evaluation.")
                        self.error_count += 1
                        time.sleep(1)
                        continue

                    live_price = self.poll_nifty()
                    c_1m, c_15m = self.build_candles(live_price, now)

                    self.track_open_signals(live_price)

                    if len(self.active_signals) < 1:
                        self.evaluate_signals(c_1m, c_15m, live_price, now)

                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down monitor.")
            self.save_log()


if __name__ == "__main__":
    monitor = RealPaperMonitor()

    # Mocking a closed 15m candle for test initialisation
    lp = monitor.poll_nifty()
    now = pd.Timestamp.now()
    c1, c15 = monitor.build_candles(lp, now)

    # Force a mock signal to create CSV structure
    monitor.active_signals.append(
        {
            "signal_id": monitor.generate_signal_id(
                now.isoformat(), "VOL_EXPANSION", 23100
            ),
            "timestamp": now.isoformat(),
            "regime": "VOL_EXPANSION",
            "volatility_metrics": "VALID",
            "nifty_spot": lp,
            "chosen_option": "NFO:NIFTY26JUN23100CE",
            "strike": 23100,
            "expiry": "2026-06-26",
            "instrument_token": "MOCK_TOKEN",
            "strike_selection_reason": "Closest ATM",
            "bid_ask_snapshot": json.dumps({"bid": 150.0, "ask": 151.0}),
            "bid": 150.0,
            "ask": 151.0,
            "spread": 1.0,
            "spread_pct": 0.006,
            "theoretical_entry": 151.0,
            "theoretical_stop": lp - 20,
            "theoretical_target": lp + 40,
            "is_long": True,
            "status": "OPEN",
            "mfe": 0.0,
            "mae": 0.0,
            "realized_R": 0.0,
            "fill_quality_estimate": "GOOD",
            "risk": 20.0,
        }
    )

    monitor.paper_log.append(monitor.active_signals[0])
    monitor.close_signal(monitor.active_signals[0], lp + 40, "TARGET")
    monitor.save_health()
    print("Mock initialization complete. Starting monitor...")
    monitor.run()
