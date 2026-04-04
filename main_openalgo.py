from __future__ import annotations

from config import config as cfg
from core.orchestrator import Orchestrator
from core.brokers.openalgo_execution_router import OpenAlgoExecutionRouter


def main():
    orchestrator = Orchestrator(total_capital=getattr(cfg, "CAPITAL", 100000), poll_interval=30)

    # Swap router to OpenAlgo-backed router for LIVE mode
    orchestrator.execution_router = OpenAlgoExecutionRouter()

    orchestrator.live_monitoring()


if __name__ == "__main__":
    main()
