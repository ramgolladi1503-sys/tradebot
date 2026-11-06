"""Offline Multi-Session Regime Simulation & Replay Engine for Sentinel.

Replays actual historical session bars through the calibrated SentinelRegimeRouter
to verify how the 5-regime supervisory gates (ORB green-lighting, Chop drag protection,
and Reversal setup arming) performed across recent live captured sessions.

Preserves trading safety invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
- edge_certification_status = "NO_CERTIFIED_EDGE"
"""
from __future__ import annotations

import json
import os
import glob
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import numpy as np
import pandas as pd

from core.sentinel_regime_router import (
    SentinelRegimeRouter,
    REGIME_RUNAWAY_EXPANSION,
    REGIME_ROTATIONAL_CHOP,
    REGIME_EXHAUSTION_REVERSAL,
    REGIME_VOLATILITY_COMPRESSION,
)

CORE_REGIMES = [
    REGIME_RUNAWAY_EXPANSION,
    REGIME_ROTATIONAL_CHOP,
    REGIME_EXHAUSTION_REVERSAL,
    REGIME_VOLATILITY_COMPRESSION,
]


class SentinelMultiSessionSimulator:
    """Simulates Sentinel Regime Router supervisory decisions across historical sessions."""

    def __init__(self, capture_base_dir: str = "/Volumes/TradeBot/live market capture"):
        self.capture_base_dir = capture_base_dir
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False
        self.allowed_for_live_execution = False
        self.edge_certification_status = "NO_CERTIFIED_EDGE"

    def discover_sessions(self, max_sessions: int = 10) -> List[str]:
        """Discovers valid captured sessions with 1-minute index data."""
        pattern = os.path.join(self.capture_base_dir, "2026-*")
        dirs = sorted([d for d in glob.glob(pattern) if os.path.isdir(d)])
        valid = []
        for d in dirs:
            date_str = os.path.basename(d)
            clean_date = date_str.replace("-", "")
            fpath = os.path.join(d, f"indices_1m_{clean_date}.parquet")
            if os.path.exists(fpath):
                valid.append(d)
        return valid[-max_sessions:]

    def replay_session(self, session_dir: str, symbol: str = "NIFTY 50") -> Dict[str, Any]:
        """Replays a single session through SentinelRegimeRouter."""
        date_str = os.path.basename(session_dir)
        clean_date = date_str.replace("-", "")
        fpath = os.path.join(session_dir, f"indices_1m_{clean_date}.parquet")
        
        df = pd.read_parquet(fpath)
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol].copy()
        
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        router = SentinelRegimeRouter(
            enable_wal=False
        )
        
        timeline: List[Dict[str, Any]] = []
        regime_dwell_counts: Dict[str, int] = {r: 0 for r in CORE_REGIMES}
        regime_dwell_counts["OPENING_DISCOVERY_LOCKOUT"] = 0
        regime_dwell_counts["AMBIGUOUS_NO_TRADE"] = 0
        
        orb_green_bars = 0
        reversal_armed_bars = 0
        capital_defense_bars = 0
        
        for idx, row in df.iterrows():
            ts = row["timestamp"]
            price = float(row["close"])
            vol = float(row["volume"]) if "volume" in row and row["volume"] > 0 else 50000.0
            
            # Synthetic proxy for resting depth
            depth_bid = vol * 2.5
            depth_ask = vol * 2.4
            
            ts_ms = int(ts.timestamp() * 1000)
            b_time = ts.time()
            
            state = router.on_bar_close(
                bar_close=price,
                bar_volume=vol,
                cvd_delta=0.0,
                timestamp_ms=ts_ms,
                bar_time=b_time,
                tick_staleness_sec=0.2,
                depth_bid=depth_bid,
                depth_ask=depth_ask,
                depth_persistence_sec=4.0,
                circuit_lower=price * 0.90,
                circuit_upper=price * 1.10,
                tick_vol_sigma=1.0
            )
            
            dominant = state.dominant_regime
            if dominant in regime_dwell_counts:
                regime_dwell_counts[dominant] += 1
            else:
                regime_dwell_counts[dominant] = 1
                
            if state.permissions.get("ORB", False):
                orb_green_bars += 1
            if state.permissions.get("REVERSAL", False):
                reversal_armed_bars += 1
            if not state.is_trading_permitted:
                capital_defense_bars += 1
                
            timeline.append({
                "timestamp": ts.strftime("%H:%M"),
                "price": price,
                "dominant_regime": dominant,
                "probabilities": state.probabilities,
                "entropy": state.entropy,
                "is_trading_permitted": state.is_trading_permitted,
                "permissions": state.permissions,
                "fail_closed_reason": state.fail_closed_reason
            })
            
        total_bars = len(df)
        dominant_session_regime = max(regime_dwell_counts.items(), key=lambda x: x[1])[0]
        
        return {
            "date": date_str,
            "symbol": symbol,
            "total_bars": total_bars,
            "open": float(df["open"].iloc[0]),
            "high": float(df["high"].max()),
            "low": float(df["low"].min()),
            "close": float(df["close"].iloc[-1]),
            "day_range": float(df["high"].max() - df["low"].min()),
            "dominant_session_regime": dominant_session_regime,
            "regime_dwell_counts": regime_dwell_counts,
            "orb_green_bars": orb_green_bars,
            "reversal_armed_bars": reversal_armed_bars,
            "capital_defense_bars": capital_defense_bars,
            "regime_switches": router.session_switch_count,
            "timeline": timeline
        }

    def run_multi_session_simulation(self, max_sessions: int = 10, output_path: str = "reports/research/sentinel_regime_simulation_latest.json") -> Dict[str, Any]:
        """Runs the multi-session simulation across discovered sessions and persists the report."""
        sessions = self.discover_sessions(max_sessions=max_sessions)
        results = []
        for s in sessions:
            res = self.replay_session(s, symbol="NIFTY 50")
            results.append(res)
            
        summary = {
            "generated_at": datetime.now().isoformat(),
            "safety": {
                "read_only": self.read_only,
                "is_order_action": self.is_order_action,
                "broker_api_called": self.broker_api_called,
                "allowed_for_live_execution": self.allowed_for_live_execution,
                "edge_certification_status": self.edge_certification_status
            },
            "total_sessions": len(results),
            "sessions": results
        }
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2)
            
        return summary


if __name__ == "__main__":
    sim = SentinelMultiSessionSimulator()
    print("Running Sentinel Multi-Session Simulation...")
    report = sim.run_multi_session_simulation(max_sessions=10)
    print(f"Simulation completed for {report['total_sessions']} sessions.")
    for s in report["sessions"]:
        print(f"  {s['date']} | Range: {s['day_range']:.1f} pts | Dominant: {s['dominant_session_regime']} | ORB Green: {s['orb_green_bars']} bars | Defense: {s['capital_defense_bars']} bars")
