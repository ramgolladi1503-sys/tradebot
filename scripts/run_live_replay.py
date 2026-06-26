#!/usr/bin/env python3
import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("live_replay")

# Mock the current time globally
_MOCK_TIME = None
import core.time_utils

original_now_ist = core.time_utils.now_ist


def mock_now_ist():
    global _MOCK_TIME
    if _MOCK_TIME:
        return _MOCK_TIME
    return original_now_ist()


core.time_utils.now_ist = mock_now_ist

from core.v2_pipeline import run_v2_pipeline
from core.pro_strategy_pipeline import run_pro_strategy_pipeline
from core.pairs_candidate_generator import build_pairs_candidate_intents
from core.cross_asset import CrossAsset
from core.pairs_execution_coordinator import PairsExecutionCoordinator


class MockExecutionRouter:
    def __init__(self):
        self.executions = []
        self.pnl = 0.0

    def execute(self, trade, bid, ask, volume, **kwargs):
        self.executions.append(trade)
        return {"status": "FILLED"}


def main():
    print("--- Starting Event-Driven Live Replay Engine ---")
    data_path = ROOT / "data" / "active_options_replay.json"
    if not data_path.exists():
        print(f"ERROR: {data_path} not found.")
        return

    with open(data_path, "r") as f:
        ticks = json.load(f)

    print(f"Loaded {len(ticks)} synchronous ticks.")

    # Initialize state
    cross_asset = CrossAsset()
    router = MockExecutionRouter()

    class DummyRiskEngine:
        def evaluate(self, req):
            class R:
                passed = True
                allowed = True

            return R()

    pairs_coordinator = PairsExecutionCoordinator(router, risk_engine=DummyRiskEngine())

    stats = {
        "v2_signals": 0,
        "pro_signals": 0,
        "pairs_signals": 0,
        "ticks_processed": 0,
    }

    for i, tick in enumerate(ticks):
        global _MOCK_TIME
        _MOCK_TIME = datetime.fromisoformat(tick["timestamp"])

        # 1. Update Cross Asset
        ca_features = {}
        for symbol, price in tick.items():
            if symbol == "timestamp":
                continue
            # Only update indices for cross asset
            if symbol in ["NIFTY_INDEX", "BANKNIFTY_INDEX"]:
                f = cross_asset.update(symbol, price)
                if f:
                    ca_features = f

        if not ca_features:
            continue

        # We need to construct a market_data dict
        # market_data needs spot, ltp, ohlc, etc. For our simplified replay:
        market_data = {
            "spot": tick.get("NIFTY_INDEX", 0.0),
            "banknifty_spot": tick.get("BANKNIFTY_INDEX", 0.0),
            "vix": tick.get("INDIA_VIX", 15.0),
            "cross_asset_features": ca_features,
            "ltp": tick,
        }

        # 2. Run V2 Pipeline
        try:
            v2_cands, _ = run_v2_pipeline(market_data, None)
            if v2_cands:
                stats["v2_signals"] += len(v2_cands)
        except Exception as e:
            pass  # ignore missing dependencies in mock

        # 3. Run Pro Pipeline
        try:
            pro_cands, _ = run_pro_strategy_pipeline(market_data, None)
            if pro_cands:
                stats["pro_signals"] += len(pro_cands)
        except Exception as e:
            pass

        # 4. Run Pairs Pipeline
        try:
            pairs_report = build_pairs_candidate_intents(ca_features)
            if pairs_report.valid and pairs_report.generated_intents:
                for intent in pairs_report.generated_intents:
                    stats["pairs_signals"] += 1
                    current_prices = {
                        "NIFTY_INDEX": tick.get("NIFTY_INDEX"),
                        "BANKNIFTY_INDEX": tick.get("BANKNIFTY_INDEX"),
                    }
                    pairs_coordinator.route_pair(intent, current_prices)
        except Exception as e:
            pass

        stats["ticks_processed"] += 1

        if i % 250 == 0:
            print(f"Processed {i}/{len(ticks)} ticks...")

    print("\n--- Replay Summary ---")
    print(json.dumps(stats, indent=2))
    print(f"Total pairs legs executed: {len(router.executions)}")


if __name__ == "__main__":
    main()
