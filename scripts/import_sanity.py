import sys

MODULES = [
    "core.market_data",
    "core.orchestrator",
    "core.trade_store",
    "core.decision_logger",
    "core.strategy_gatekeeper",
    "core.feed_health",
    "core.cross_asset",
]


def main():
    for mod in MODULES:
        __import__(mod)
    print("IMPORT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
