import argparse

from core.historical_data import load_market_data
from core.trade_builder_backtest_adapter_v2 import TradeBuilderBacktestAdapterV2
from core.live_safety import RetailLiveSafetyGate, RetailSafetyConfig


def fake_broker_health():
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    args = parser.parse_args()

    df = load_market_data(args.data)
    strategy = TradeBuilderBacktestAdapterV2()

    safety = RetailLiveSafetyGate(RetailSafetyConfig())

    for _, row in df.iterrows():
        market = row.to_dict()
        signal = strategy(market)
        if not signal:
            continue

        allowed, reason = safety.can_submit(
            order=signal,
            market=market,
            broker_ok=fake_broker_health(),
            mode="PAPER",
        )

        if not allowed:
            print(f"BLOCKED: {reason}")
            continue

        safety.acknowledge_signal(signal, market["timestamp"])

        # simulate result (placeholder)
        pl = 0.0
        safety.record_trade_result(
            signal.get("symbol", "UNKNOWN"), market["timestamp"], pl
        )

        print(f"EXECUTED: {signal.get('symbol')} | reason={reason}")
