import pandas as pd
import numpy as np
import itertools
from typing import List, Dict, Any, Optional
from core.backtest_elite import VectorizedBacktestEngine, EliteBacktestConfig

class WalkForwardAnalyzer:
    """
    Performs Walk-Forward Analysis (WFA) to prevent curve-fitting.
    
    Splits data into rolling train/test windows.
    Optimizes parameters on the train window, tests blindly on the test window.
    """
    
    def __init__(
        self, 
        data: pd.DataFrame, 
        train_years: int = 3, 
        test_years: int = 1,
        slippage_bps: float = 20.0,  # 0.2% slippage requirement
        spread_bps: float = 0.0
    ):
        self.data = data.copy()
        if not pd.api.types.is_datetime64_any_dtype(self.data.index):
            self.data.index = pd.to_datetime(self.data.index)
        self.data.sort_index(inplace=True)
        
        self.train_years = train_years
        self.test_years = test_years
        self.slippage_bps = slippage_bps
        self.spread_bps = spread_bps
        
        self.oos_results = []
        self.best_params_per_window = []

    def generate_windows(self):
        """Generates train/test date ranges based on available years."""
        years = sorted(self.data.index.year.unique())
        
        windows = []
        for i in range(len(years) - self.train_years - self.test_years + 1):
            train_start_year = years[i]
            train_end_year = years[i + self.train_years - 1]
            test_start_year = years[i + self.train_years]
            test_end_year = years[i + self.train_years + self.test_years - 1]
            
            train_mask = (self.data.index.year >= train_start_year) & (self.data.index.year <= train_end_year)
            test_mask = (self.data.index.year >= test_start_year) & (self.data.index.year <= test_end_year)
            
            windows.append({
                "train_start": str(train_start_year),
                "train_end": str(train_end_year),
                "test_start": str(test_start_year),
                "test_end": str(test_end_year),
                "train_df": self.data.loc[train_mask].copy(),
                "test_df": self.data.loc[test_mask].copy()
            })
        return windows

    def optimize(self, train_df: pd.DataFrame, param_grid: Dict[str, List[Any]]) -> Dict[str, Any]:
        """Runs a grid search over param_grid on the train_df."""
        keys, values = zip(*param_grid.items())
        permutations = [dict(zip(keys, v)) for v in itertools.product(*values)]
        
        best_pl = -float('inf')
        best_params = permutations[0]
        
        for params in permutations:
            config = EliteBacktestConfig(
                slippage_bps=self.slippage_bps,
                spread_bps=self.spread_bps,
                use_synth_chain=False, # Keep fast for optimization
                **params
            )
            
            engine = VectorizedBacktestEngine(train_df, config)
            res_df = engine.generate_signals_vectorized()
            
            total_pl = res_df["pl"].sum() if not res_df.empty else 0
            if total_pl > best_pl:
                best_pl = total_pl
                best_params = params
                
        return best_params

    def test(self, test_df: pd.DataFrame, params: Dict[str, Any]) -> pd.DataFrame:
        """Evaluates out-of-sample data with the best parameters."""
        config = EliteBacktestConfig(
            slippage_bps=self.slippage_bps,
            spread_bps=self.spread_bps,
            use_synth_chain=False,
            **params
        )
        
        engine = VectorizedBacktestEngine(test_df, config)
        res_df = engine.generate_signals_vectorized()
        return res_df

    def run(self, param_grid: Dict[str, List[Any]]) -> pd.DataFrame:
        """Executes the complete WFA process."""
        windows = self.generate_windows()
        
        all_oos_trades = []
        
        for i, window in enumerate(windows):
            print(f"Window {i+1}: Train {window['train_start']}-{window['train_end']} | Test {window['test_start']}-{window['test_end']}")
            
            # Train Phase
            best_params = self.optimize(window["train_df"], param_grid)
            self.best_params_per_window.append({
                "window": i+1,
                "train_years": f"{window['train_start']}-{window['train_end']}",
                "test_years": f"{window['test_start']}-{window['test_end']}",
                "best_params": best_params
            })
            print(f"  -> Best Params: {best_params}")
            
            # Test Phase (Out-of-Sample)
            oos_trades = self.test(window["test_df"], best_params)
            
            if not oos_trades.empty:
                oos_trades["wfa_window"] = i + 1
                oos_trades["test_year"] = window["test_start"]
                all_oos_trades.append(oos_trades)
                
        if all_oos_trades:
            self.oos_results = pd.concat(all_oos_trades, ignore_index=True)
        else:
            self.oos_results = pd.DataFrame()
            
        return self.oos_results
