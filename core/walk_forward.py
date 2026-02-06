import pandas as pd
from core.backtest_engine import BacktestEngine
from core.feature_builder import add_indicators

def _train_stats(df: pd.DataFrame):
    try:
        d = add_indicators(df).dropna()
        if d.empty:
            return {}
        ret_vol = d["return_1"].std()
        atr_norm = (d["atr_14"] / d["close"]).median()
        vol_target = ret_vol if ret_vol and ret_vol > 0 else atr_norm
        return {"vol_target": float(vol_target) if vol_target else None}
    except Exception:
        return {}

def walk_forward(historical_data: pd.DataFrame, train_size: float = 0.6, step: int = 200):
    """
    Walk-forward backtest: train on expanding window, test on next step.
    """
    all_results = []
    n = len(historical_data)
    start_train = int(n * train_size)
    for start in range(start_train, n - step, step):
        train_df = historical_data.iloc[:start]
        test_df = historical_data.iloc[start:start + step]
        stats = _train_stats(train_df)
        engine = BacktestEngine(test_df, train_stats=stats)
        results = engine.run()
        all_results.append(results)
    if not all_results:
        return pd.DataFrame()
    return pd.concat(all_results, ignore_index=True)
