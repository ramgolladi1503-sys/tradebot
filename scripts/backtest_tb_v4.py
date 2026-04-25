from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.replay_contract import assert_deterministic_runtime_replay


DEPRECATION_MESSAGE = (
    "DEPRECATED: scripts/backtest_tb_v4.py is no longer a truth engine. "
    "Use scripts/validate_system.py or core.replay_engine.ReplayEngine."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deprecated compatibility wrapper for canonical replay validation")
    parser.add_argument("--data", default="")
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--runtime-root", default=None)
    args = parser.parse_args()

    result = assert_deterministic_runtime_replay(
        runtime_root=args.runtime_root,
        symbol=args.symbol,
        start=args.start,
        end=args.end,
    )
    print(DEPRECATION_MESSAGE)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
