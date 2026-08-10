#!/usr/bin/env python3
"""
Trader Observation Micro Features Generator V12
Extracts microscopic bar-by-bar features based on frozen trader observations.
"""
import os
import glob
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any

def load_and_align_v12_data(
    constituent_dir: str, 
    nifty_csv_path: str
) -> pd.DataFrame:
    nifty_df = pd.read_csv(nifty_csv_path)
    ts_col_nifty = [c for c in nifty_df.columns if 'date' in c.lower() or 'time' in c.lower() or 'timestamp' in c.lower()][0]
    nifty_df['dt'] = pd.to_datetime(nifty_df[ts_col_nifty]).dt.floor('5min')
    nifty_df = nifty_df.sort_values('dt').drop_duplicates('dt').set_index('dt')
    
    nifty_df['nifty_ret1'] = nifty_df['close'].pct_change() * 10000.0
    nifty_df['nifty_ret6'] = nifty_df['close'].pct_change(6) * 10000.0
    nifty_df['body_bps'] = (nifty_df['close'] - nifty_df['open']) / nifty_df['open'] * 10000.0
    nifty_df['range_bps'] = (nifty_df['high'] - nifty_df['low']) / nifty_df['low'] * 10000.0
    nifty_df['upper_wick_bps'] = (nifty_df['high'] - nifty_df[['open', 'close']].max(axis=1)) / nifty_df['open'] * 10000.0
    nifty_df['lower_wick_bps'] = (nifty_df[['open', 'close']].min(axis=1) - nifty_df['low']) / nifty_df['open'] * 10000.0

    core_syms = ['BEL', 'INDIGO', 'JIOFIN', 'TRENT', 'ZOMATO']
    sym_dfs = {}
    
    for f in glob.glob(os.path.join(constituent_dir, '**', '*.parquet'), recursive=True):
        parts = f.split(os.sep)
        sym = [p.replace('symbol=', '') for p in parts if p.startswith('symbol=')][0]
        if sym in core_syms:
            df = pd.read_parquet(f)
            ts_col = [c for c in df.columns if 'date' in c.lower() or 'time' in c.lower() or 'timestamp' in c.lower()][0]
            df['dt'] = pd.to_datetime(df[ts_col]).dt.floor('5min')
            df = df.sort_values('dt').drop_duplicates('dt').set_index('dt')
            col_close = 'close' if 'close' in df.columns else 'Close'
            df[f'{sym}_ret1'] = df[col_close].pct_change() * 10000.0
            if sym not in sym_dfs:
                sym_dfs[sym] = df[[f'{sym}_ret1']]
            else:
                sym_dfs[sym] = pd.concat([sym_dfs[sym], df[[f'{sym}_ret1']]]).sort_index()
                sym_dfs[sym] = sym_dfs[sym][~sym_dfs[sym].index.duplicated(keep='first')]

    combined = nifty_df[['open', 'high', 'low', 'close', 'nifty_ret1', 'nifty_ret6', 'body_bps', 'range_bps', 'upper_wick_bps', 'lower_wick_bps']].copy()
    for sym in core_syms:
        if sym in sym_dfs:
            combined = combined.join(sym_dfs[sym], how='inner')

    ret_cols = [f'{sym}_ret1' for sym in core_syms if f'{sym}_ret1' in combined.columns]
    combined['selective_breadth_up'] = (combined[ret_cols] > 0).mean(axis=1)
    combined['selective_dispersion_bps'] = combined[ret_cols].std(axis=1)

    return combined.dropna()

def generate_v12_frozen_candidate_specs() -> List[Dict[str, Any]]:
    return [
        {
            "candidate_id": "H1_TRAPPED_PUSH_SNAPBACK",
            "family": "TRAPPED_PUSH_SNAPBACK",
            "predicate": lambda df: (df['range_bps'].shift(1) > 12.0) & (df['upper_wick_bps'].shift(1) > 4.0) & (df['body_bps'] < -2.0),
            "target_direction": "DOWN",
            "economic_rationale": "Buyers fail at upper wick and get trapped; immediate snapback selling follow-through."
        },
        {
            "candidate_id": "H2_ABSORPTION_AFTER_WIDE_CANDLE",
            "family": "ABSORPTION_AFTER_WIDE_CANDLE",
            "predicate": lambda df: (df['range_bps'].shift(1) > 15.0) & (df['range_bps'] < 5.0) & (df['selective_dispersion_bps'] > 10.0),
            "target_direction": "UP",
            "economic_rationale": "Impulse bar halts into tight absorption before continuation."
        },
        {
            "candidate_id": "H3_CONSTITUENT_DISAGREEMENT_INDEX_HOLD",
            "family": "CONSTITUENT_DISAGREEMENT_INDEX_HOLD",
            "predicate": lambda df: (df['body_bps'].abs() < 2.0) & (df['selective_breadth_up'] >= 0.8),
            "target_direction": "UP",
            "economic_rationale": "Constituent breadth leads while index body hesitates."
        }
    ]
