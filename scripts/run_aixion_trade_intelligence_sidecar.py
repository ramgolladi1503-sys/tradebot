#!/usr/bin/env python3
from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from aixion_trade_intelligence.live_sidecar import LiveSidecar, SidecarConfig
from aixion_trade_intelligence.publisher import FileEventPublisher
from aixion_trade_intelligence.safe_publish import NonBlockingPublisher


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the read-only Aixion Trade Intelligence JSONL sidecar."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    config = SidecarConfig.from_json(args.config)
    publisher = NonBlockingPublisher(FileEventPublisher(args.evidence_root, fsync=True))
    sidecar = LiveSidecar(config, publisher)
    if args.once:
        sidecar.start()
        result = sidecar.poll_once()
        sidecar.stop()
        return 0 if result["failed"] == 0 else 3

    stop = False

    def request_stop(_signum, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    sidecar.run_forever(lambda: stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
