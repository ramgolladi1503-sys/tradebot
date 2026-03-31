import argparse

from core.historical_data import load_market_data
from core.replay_backtest_v2 import ReplayBacktestEngineV2, BacktestConfigV2
from core.trade_builder_backtest_adapter_v2 import TradeBuilderBacktestAdapterV2

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    args = parser.parse_args()

    df = load_market_data(args.data)
    strategy = TradeBuilderBacktestAdapterV2()

    engine = ReplayBacktestEngineV2(
        df,
        strategy_fn=strategy,
        config=BacktestConfigV2()
    )

    res = engine.run()
    print(res.tail())
