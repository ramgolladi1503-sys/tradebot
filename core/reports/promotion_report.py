import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd


def _brier(y, p) -> float | None:
    if y is None or p is None or len(y) == 0:
        return None
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    return float(np.mean((p - y) ** 2))


def _ece(y, p, bins: int = 10) -> float | None:
    if y is None or p is None or len(y) == 0:
        return None
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    p = np.clip(p, 0, 1)
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        if not np.any(mask):
            continue
        avg_conf = np.mean(p[mask])
        avg_acc = np.mean(y[mask])
        ece += (mask.sum() / len(p)) * abs(avg_conf - avg_acc)
    return float(ece)


def _tail_loss(pnl: pd.Series, k: int) -> float | None:
    if pnl is None or pnl.dropna().empty:
        return None
    vals = pnl.dropna().sort_values().head(k)
    if vals.empty:
        return None
    return float(vals.mean())


def _profitability_metrics(pnl: pd.Series) -> dict:
    if pnl is None:
        return {"expectancy": None, "profit_factor": None, "max_drawdown": None, "net_pnl": None, "win_rate": None}
    clean = pd.Series(pnl).dropna().astype(float)
    if clean.empty:
        return {"expectancy": None, "profit_factor": None, "max_drawdown": None, "net_pnl": None, "win_rate": None}

    wins = clean[clean > 0]
    losses = clean[clean < 0]
    net_pnl = float(clean.sum())
    expectancy = float(clean.mean())
    profit_factor = None if losses.empty or float(abs(losses.sum())) == 0.0 else float(wins.sum() / abs(losses.sum()))
    equity = clean.cumsum()
    running_peak = equity.cummax()
    drawdown = equity - running_peak
    max_drawdown = float(drawdown.min()) if not drawdown.empty else None
    win_rate = float((clean > 0).mean())
    return {
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "net_pnl": net_pnl,
        "win_rate": win_rate,
    }


def evaluate_promotion(df: pd.DataFrame, day: str, gates: dict) -> dict:
    if df is None or df.empty:
        raise ValueError("Truth dataset is empty.")
    df = df.copy()
    df["ts_dt"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df[df["ts_dt"].dt.date.astype(str) >= day]
    if df.empty:
        raise ValueError("No shadow data in window.")

    required = ["champion_proba", "challenger_proba"]
    for col in required:
        if col not in df.columns or df[col].dropna().empty:
            raise ValueError(f"Missing required column: {col}")

    if "pnl_15m" in df.columns and df["pnl_15m"].notna().any():
        pnl_col = "pnl_15m"
        y = (df[pnl_col].fillna(0) > 0).astype(float).values
    elif "realized_pnl" in df.columns and df["realized_pnl"].notna().any():
        pnl_col = "realized_pnl"
        y = (df[pnl_col].fillna(0) > 0).astype(float).values
    else:
        raise ValueError("Missing outcome labels (pnl_15m or realized_pnl).")
    champ = df["champion_proba"].astype(float).values
    chall = df["challenger_proba"].astype(float).values

    champ_brier = _brier(y, champ)
    chall_brier = _brier(y, chall)
    champ_ece = _ece(y, champ, bins=gates.get("ece_bins", 10))
    chall_ece = _ece(y, chall, bins=gates.get("ece_bins", 10))

    profitability = _profitability_metrics(df[pnl_col]) if pnl_col in df.columns else {}
    tail_k = int(gates.get("tail_k", 20))
    champ_tail = _tail_loss(df[pnl_col], tail_k) if pnl_col in df.columns else None
    chall_tail = champ_tail

    # Segment by regime
    seg = {}
    if "primary_regime" in df.columns:
        for reg, g in df.groupby("primary_regime"):
            if g.empty:
                continue
            y_r = g["filled_bool"].fillna(0).astype(float).values
            c_r = g["champion_proba"].astype(float).values
            h_r = g["challenger_proba"].astype(float).values
            seg[reg] = {
                "champ_brier": _brier(y_r, c_r),
                "chall_brier": _brier(y_r, h_r),
                "count": int(len(g)),
            }

    report = {
        "date": day,
        "champ_brier": champ_brier,
        "chall_brier": chall_brier,
        "champ_ece": champ_ece,
        "chall_ece": chall_ece,
        "champ_tail": champ_tail,
        "chall_tail": chall_tail,
        "profitability": profitability,
        "segments": seg,
    }
    return report


def write_promotion_report(report: dict, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report["generated_at"] = datetime.now().isoformat()
    out_path.write_text(json.dumps(report, indent=2, default=str))
    return out_path
