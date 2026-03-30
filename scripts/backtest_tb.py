import argparse

from core.historical_data import load_market_data
from core.replay_backtest import ReplayBacktestEngine, BacktestConfig
from core.trade_builder_backtest_adapter import TradeBuilderBacktestAdapter

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    args = parser.parse_args()

    df = load_market_data(args.data)
    strategy = TradeBuilderBacktestAdapter()
    engine = ReplayBacktestEngine(df, strategy_fn=strategy, config=BacktestConfig())
    results = engine.run()
    print(results.tail())
