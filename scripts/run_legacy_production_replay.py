import argparse
import sys
import logging

from config import config as cfg
from core.orchestrator import Orchestrator
from core.replay.legacy_market_data_provider import ReplayMarketDataProvider

def main():
    parser = argparse.ArgumentParser(description="Run Legacy Production Replay")
    parser.add_argument("--source", required=True, help="Path to JSON lines of recorded ticks")
    args = parser.parse_args()

    # Phase 7 & 8: Execution safety and fallbacks
    cfg.EXECUTION_MODE = "PAPER"
    cfg.PLANNING_NO_SIGNAL_FALLBACK_ENABLE = False
    cfg.REQUIRE_LIVE_QUOTES = True

    # Initialize the provider
    provider = ReplayMarketDataProvider(args.source)

    try:
        from unittest.mock import patch
        import core.kite_client
        with patch("core.kite_client.KiteClient.submit_order") as mock_place_order:
            orch = Orchestrator()
            for event in provider.read_events():
                provider.publish(event)
                orch._legacy_live_monitoring(run_once=True)
                
            if mock_place_order.call_count > 0:
                print("UNSAFE_REPLAY_EXECUTION_BOUNDARY: place_order was called!")
                sys.exit(1)
    except Exception as e:
        print(f"Error during replay: {e}")
        sys.exit(1)
        
    print(f"Replay completed. Events processed: {provider.total_published}")
    sys.exit(0)

if __name__ == "__main__":
    main()
