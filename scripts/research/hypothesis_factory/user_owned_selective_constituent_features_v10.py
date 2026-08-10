#!/usr/bin/env python3
"""
Selective Constituent Feature Generator V10
Computes lead-lag momentum, dispersion shock, and selective breadth divergence 
features from user-owned selective constituent parquet files + NIFTY index OHLCV.
"""
import os
import glob
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any

def load_and_align_pilot_data(
    constituent_dir: str, 
    nifty_csv_path: str
) -> pd.DataFrame:
    # 1. Load NIFTY index
    nifty_df = pd.read_csv(nifty_csv_path)
    ts_col_nifty = [c for c in nifty_df.columns if 'date' in c.lower() or 'time' in c.lower() or 'timestamp' in c.lower()][0]
    nifty_df['dt'] = pd.to_datetime(nifty_df[ts_col_nifty]).dt.floor('5min')
    nifty_df = nifty_df.sort_values('dt').drop_duplicates('dt').set_index('dt')
    nifty_df['nifty_ret1'] = nifty_df['close'].pct_change() * 10000.0
    nifty_df['nifty_ret6'] = nifty_df['close'].pct_change(6) * 10000.0

    # 2. Load selective constituent files
    files = glob.glob(os.path.join(constituent_dir, '**', '*.parquet'), recursive=True)
    sym_dfs = {}
    
    for f in files:
        parts = f.split(os.sep)
        sym_part = [p for p in parts if p.startswith('symbol=')]
        sym = sym_part[0].replace('symbol=', '') if sym_part else 'UNKNOWN'
        
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

    # Focus on core 5 high-overlap symbols
    core_syms = ['BEL', 'INDIGO', 'JIOFIN', 'TRENT', 'ZOMATO']
    combined = nifty_df[['close', 'nifty_ret1', 'nifty_ret6']].copy()
    
    for sym in core_syms:
        if sym in sym_dfs:
            combined = combined.join(sym_dfs[sym], how='inner')

    # Compute constituent breadth & dispersion
    ret_cols = [f'{sym}_ret1' for sym in core_syms if f'{sym}_ret1' in combined.columns]
    
    # 1. Breadth: fraction of constituents with positive 1-bar return
    combined['selective_breadth_up'] = (combined[ret_cols] > 0).mean(axis=1)
    
    # 2. Dispersion: cross-sectional std dev of constituent returns
    combined['selective_dispersion_bps'] = combined[ret_cols].std(axis=1)
    
    # 3. Lead-lag momentum: mean return of constituents minus index return
    combined['selective_lead_lag_diff'] = combined[ret_cols].mean(axis=1) - combined['nifty_ret1']

    return combined.dropna()

def generate_v10_candidate_specs() -> List[Dict[str, Any]]:
    candidates = [
        # Lead-lag momentum candidate
        {
            "candidate_id": "V10_SELECTIVE_LEAD_LAG_MOMENTUM_UP",
            "family": "SELECTIVE_CONSTITUENT_MOMENTUM_LEAD_LAG",
            "predicate": lambda df: (df['selective_lead_lag_diff'] > 5.0) & (df['selective_breadth_up'] >= 0.8),
            "target_direction": "UP",
            "pilot_scope": "SELECTIVE_9_SYMBOLS_ONLY",
            "not_full_nifty_breadth": True,
            "execution_viability": False,
            "edge_claimed": False,
            "structural_edge_certified": False
        },
        {
            "candidate_id": "V10_SELECTIVE_LEAD_LAG_MOMENTUM_DOWN",
            "family": "SELECTIVE_CONSTITUENT_MOMENTUM_LEAD_LAG",
            "predicate": lambda df: (df['selective_lead_lag_diff'] < -5.0) & (df['selective_breadth_up'] <= 0.2),
            "target_direction": "DOWN",
            "pilot_scope": "SELECTIVE_9_SYMBOLS_ONLY",
            "not_full_nifty_breadth": True,
            "execution_viability": False,
            "edge_claimed": False,
            "structural_edge_certified": False
        },
        # Dispersion shock candidate
        {
            "candidate_id": "V10_SELECTIVE_DISPERSION_SHOCK_EXPANSION",
            "family": "SELECTIVE_CONSTITUENT_DISPERSION_SHOCK",
            "predicate": lambda df: (df['selective_dispersion_bps'] > df['selective_dispersion_bps'].rolling(20).mean() * 1.8),
            "target_direction": "UP",
            "pilot_scope": "SELECTIVE_9_SYMBOLS_ONLY",
            "not_full_nifty_breadth": True,
            "execution_viability": False,
            "edge_claimed": False,
            "structural_edge_certified": False
        },
        # Breadth divergence candidate
        {
            "candidate_id": "V10_SELECTIVE_BREADTH_DIVERGENCE_BULLISH",
            "family": "SELECTIVE_CONSTITUENT_BREADTH_DIVERGENCE",
            "predicate": lambda df: (df['nifty_ret1'] < -2.0) & (df['selective_breadth_up'] >= 0.6),
            "target_direction": "UP",
            "pilot_scope": "SELECTIVE_9_SYMBOLS_ONLY",
            "not_full_nifty_breadth": True,
            "execution_viability": False,
            "edge_claimed": False,
            "structural_edge_certified": False
        }
    ]
    return candidates
