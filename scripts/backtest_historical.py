import argparse

from core.historical_data import load_market_data
from core.replay_backtest import ReplayBacktestEngine, BacktestConfig


def simple_strategy(market):
    price = market["close"]
    return {
        "entry": price,
        "target": price * 1.01,
        "stop": price * 0.99,
        "qty": 1,
        "side": "BUY",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to historical data file")
    args = parser.parse_args()

    df = load_market_data(args.data)

    engine = ReplayBacktestEngine(df, strategy_fn=simple_strategy, config=BacktestConfig())
    results = engine.run()

    print(results.tail())
