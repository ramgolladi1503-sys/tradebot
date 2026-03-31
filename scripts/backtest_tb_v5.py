import argparse

from core.historical_data import load_market_data
from core.replay_backtest_v3 import ReplayBacktestEngineV3, BacktestConfigV3
from core.trade_builder_backtest_adapter_v2 import TradeBuilderBacktestAdapterV2

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    args = parser.parse_args()

    df = load_market_data(args.data)
    strategy = TradeBuilderBacktestAdapterV2()

    engine = ReplayBacktestEngineV3(
        df,
        strategy_fn=strategy,
        config=BacktestConfigV3()
    )

    res = engine.run()
    print(res.tail())
