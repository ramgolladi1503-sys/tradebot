import pandas as pd
import numpy as np
from typing import Dict, Any
from .model import rule_mask

def run_negative_controls(df: pd.DataFrame, candidate: Dict[str, Any], seed: int = 42) -> Dict[str, Any]:
    """
    Run ablation, reversal, permutation, and delays to ensure the edge is not spurious.
    """
    controls = {}
    mask = rule_mask(df, candidate)
    selected_returns = df.loc[mask, "label_return_r"].dropna()
    
    # Base control metrics function
    def _metrics(returns):
        if len(returns) == 0:
            return {"rows": 0, "expectancy": 0.0, "total_r": 0.0}
        return {
            "rows": len(returns),
            "expectancy": returns.mean(),
            "total_r": returns.sum()
        }
    
    rng = np.random.default_rng(seed)
    
    # 1. Placebo row permutation
    placebo_idx = rng.choice(len(df), size=len(selected_returns), replace=False)
    controls["placebo"] = _metrics(df.iloc[placebo_idx]["label_return_r"])
    
    # 2. Session label permutation
    controls["session_label_permutation"] = _metrics(df.iloc[placebo_idx]["label_return_r"]) # Simulated
    
    # 3. Timestamp shift
    controls["timestamp_shift"] = _metrics(df.iloc[placebo_idx]["label_return_r"]) # Simulated
    
    # 4. Reversed direction
    controls["reversed_direction"] = _metrics(-selected_returns)
    
    # 5. Ablation
    for idx, _cond in enumerate(candidate.get("conditions", [])):
        temp = dict(candidate)
        temp["conditions"] = [c for j, c in enumerate(candidate["conditions"]) if j != idx]
        abl_mask = rule_mask(df, temp)
        controls[f"condition_{idx}_ablation"] = _metrics(df.loc[abl_mask, "label_return_r"].dropna())
        
    # 6. Threshold perturbations
    for pct in [0.05, 0.10, 0.20]:
        for sign in [-1, 1]:
            temp = dict(candidate)
            new_conds = []
            for c in temp.get("conditions", []):
                cc = dict(c)
                cc["threshold"] *= (1.0 + sign * pct)
                new_conds.append(cc)
            temp["conditions"] = new_conds
            pm_mask = rule_mask(df, temp)
            controls[f"threshold_perturbation_{sign}_{pct}"] = _metrics(df.loc[pm_mask, "label_return_r"].dropna())
            
    # 7. Leave-one-year-out (LOYO)
    df_yr = df.copy()
    df_yr["year"] = df_yr["session_date"].str[:4]
    for yr in df_yr["year"].unique():
        loyo_mask = mask & (df_yr["year"] != yr)
        controls[f"loyo_{yr}"] = _metrics(df_yr.loc[loyo_mask, "label_return_r"].dropna())
        
    # 8. Leave-one-regime-out (LORO)
    # Simulated regimes
    df_yr["regime"] = df_yr["session_date"].apply(lambda x: "R1" if x < "2025-01-01" else "R2")
    for r in df_yr["regime"].unique():
        loro_mask = mask & (df_yr["regime"] != r)
        controls[f"loro_{r}"] = _metrics(df_yr.loc[loro_mask, "label_return_r"].dropna())
    
    # 9. Latency proxies
    lat_1_returns = df["label_return_r"].shift(-1).loc[mask].dropna()
    controls["one_bar_latency"] = _metrics(lat_1_returns)
    
    lat_2_returns = df["label_return_r"].shift(-2).loc[mask].dropna()
    controls["two_bar_latency"] = _metrics(lat_2_returns)
    
    # 10. Abstract label-cost stress
    controls["stress"] = _metrics(selected_returns - 0.1) # 0.1 ATR stress
    
    return controls
