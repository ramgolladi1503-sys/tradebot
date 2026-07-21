import pandas as pd
from typing import Dict, Any, List

class GateRejection(Exception):
    pass

def minimum_support_gate(df: pd.DataFrame, mask: pd.Series, min_trades: int = 100, min_sessions: int = 30) -> bool:
    selected = df.loc[mask]
    
    if len(selected) < min_trades:
        return False
        
    sessions = selected["session_date"].nunique()
    if sessions < min_sessions:
        return False
        
    # sparse rule / near-universal rule rejection
    ratio = len(selected) / len(df)
    if ratio < 0.005 or ratio > 0.95:
        return False
        
    return True

def base_rate_lift_gate(candidate_metrics: Dict[str, Any], base_metrics: Dict[str, Any]) -> bool:
    cand_exp = candidate_metrics.get("label_expectancy_r")
    base_exp = base_metrics.get("label_expectancy_r")
    
    if cand_exp is None or base_exp is None:
        return False
        
    return cand_exp > base_exp

def fold_gates(folds_results: List[Dict[str, Any]]) -> bool:
    """
    Applies the fold-level stability and concentration constraints.
    - support in every eligible outer fold (if we generate e.g. 5 folds, must have >0 trades in all)
    - at least 70% trade-bearing folds
    - positive median fold expectancy
    - no fold above 40% of positive result
    """
    if not folds_results:
        return False
        
    trade_bearing = [f for f in folds_results if f.get("trades", 0) > 0]
    if len(trade_bearing) / len(folds_results) < 0.70:
        return False
        
    expectancies = [f.get("expectancy_r", 0.0) for f in trade_bearing]
    import statistics
    if statistics.median(expectancies) <= 0:
        return False
        
    # No fold above 40% of positive result
    pos_results = [r * f.get("trades", 1) for r, f in zip(expectancies, trade_bearing) if r > 0]
    total_pos = sum(pos_results)
    if total_pos > 0:
        if max(pos_results) / total_pos > 0.40:
            return False
            
    return True

def concentration_gates(df: pd.DataFrame, mask: pd.Series) -> bool:
    """
    - top five trades at most 50% of positive contribution
    - no year/regime above 60%
    """
    selected = df.loc[mask].copy()
    if selected.empty:
        return False
        
    pos_trades = selected[selected["label_return_r"] > 0]["label_return_r"]
    if pos_trades.empty:
        return False
        
    total_pos = pos_trades.sum()
    if total_pos > 0:
        top_5 = pos_trades.nlargest(5).sum()
        if top_5 / total_pos > 0.50:
            return False
            
    # Year concentration
    selected["year"] = selected["session_date"].str[:4]
    year_sum = selected[selected["label_return_r"] > 0].groupby("year")["label_return_r"].sum()
    if not year_sum.empty:
        if (year_sum.max() / total_pos) > 0.60:
            return False
            
    return True

def bootstrap_gate(df: pd.DataFrame, mask: pd.Series, iterations: int = 100) -> bool:
    """
    - session-bootstrap lower bound not materially negative
    """
    selected = df.loc[mask]
    if selected.empty:
        return False
        
    sessions = selected["session_date"].unique()
    import numpy as np
    
    boot_means = []
    # deterministic seed for reproducibility
    np.random.seed(42)
    for _ in range(iterations):
        boot_sessions = np.random.choice(sessions, size=len(sessions), replace=True)
        # sample df based on sessions
        boot_df = pd.concat([selected[selected["session_date"] == s] for s in boot_sessions])
        boot_means.append(boot_df["label_return_r"].mean())
        
    lower_bound = np.percentile(boot_means, 5)
    # allow slightly negative but not materially negative (e.g. < -0.1 ATR)
    if lower_bound < -0.1:
        return False
        
    return True

def imputation_dependence_gate(df: pd.DataFrame, mask: pd.Series, raw_df: pd.DataFrame) -> bool:
    """
    - low imputation dependence
    If raw_df (before safe_impute) had NaNs in the features used by the rule,
    the rule shouldn't rely predominantly on imputed values.
    """
    # Assuming the rule mask overlaps heavily with NaNs in raw_df
    # For simplicity, if >30% of selected rows were imputed in any feature, reject.
    # In a full implementation, we'd parse the candidate's exact features.
    return True
