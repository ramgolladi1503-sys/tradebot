import argparse

from core.historical_data import load_market_data
from tools.legacy.adaptive_portfolio import (
    AdaptivePortfolioEngine,
    AdaptiveStrategyAdapter,
)
from core.trade_builder_backtest_adapter_v2 import TradeBuilderBacktestAdapterV2


def build_strategies():
    tb = TradeBuilderBacktestAdapterV2()
    strat1 = AdaptiveStrategyAdapter("tb_trend", tb, allowed_regimes=("trend",))
    strat2 = AdaptiveStrategyAdapter("tb_sideways", tb, allowed_regimes=("sideways",))
    return [strat1, strat2]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    args = parser.parse_args()

    df = load_market_data(args.data)
    strategies = build_strategies()

    engine = AdaptivePortfolioEngine(df, strategies)
    res = engine.run()

    print(res.tail())
