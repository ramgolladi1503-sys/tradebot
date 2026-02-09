from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd

from config import config as cfg


DECISION_JSONL = Path(getattr(cfg, "DECISION_LOG_PATH", "logs/decision_events.jsonl"))
DEFAULT_WINDOW = int(getattr(cfg, "DECAY_WINDOW_TRADES", 50))
DEFAULT_DRAWNDOWN_THRESHOLD = float(getattr(cfg, "DECAY_DRAWDOWN_THRESHOLD", -100.0))


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _load_decision_events(decision_jsonl: Path, db_path: Path) -> pd.DataFrame:
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                df = pd.read_sql("SELECT * FROM decision_events", conn)
            if not df.empty:
                return df
        except Exception:
            pass
    rows = _load_jsonl(decision_jsonl)
    return pd.DataFrame(rows)


def _load_trade_risk_map(trade_log_path: Path) -> Dict[str, float]:
    if not trade_log_path.exists():
        return {}
    try:
        rows = json.loads(trade_log_path.read_text())
    except Exception:
        rows = _load_jsonl(trade_log_path)
    risk_map = {}
    for r in rows:
        tid = r.get("trade_id")
        if not tid:
            continue
        try:
            entry = float(r.get("entry", 0.0))
            stop = float(r.get("stop", 0.0))
        except Exception:
            continue
        risk = abs(entry - stop)
        if risk > 0:
            risk_map[tid] = risk
    return risk_map


def _js_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    keys = set(p) | set(q)
    if not keys:
        return 0.0
    m = {k: 0.5 * (p.get(k, 0.0) + q.get(k, 0.0)) for k in keys}
    def kl(a, b):
        s = 0.0
        for k in keys:
            av = max(a.get(k, 1e-9), 1e-9)
            bv = max(b.get(k, 1e-9), 1e-9)
            s += av * math.log(av / bv)
        return s
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def _psi(expected: Iterable[float], actual: Iterable[float], bins: int = 10) -> float:
    exp_vals = np.asarray(list(expected), dtype=float)
    act_vals = np.asarray(list(actual), dtype=float)
    if exp_vals.size == 0 or act_vals.size == 0:
        return 0.0
    edges = np.quantile(exp_vals, np.linspace(0, 1, bins + 1))
    exp_hist, _ = np.histogram(exp_vals, bins=edges)
    act_hist, _ = np.histogram(act_vals, bins=edges)
    exp_pct = np.maximum(exp_hist / max(exp_hist.sum(), 1), 1e-6)
    act_pct = np.maximum(act_hist / max(act_hist.sum(), 1), 1e-6)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def _drawdown(pnls: Iterable[float]) -> float:
    pnl = np.asarray(list(pnls), dtype=float)
    if pnl.size == 0:
        return 0.0
    equity = pnl.cumsum()
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    return float(dd.min())


def _worst_run(pnls: Iterable[float]) -> int:
    worst = 0
    streak = 0
    for p in pnls:
        if p < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return int(worst)


def _sharpe_proxy(pnls: Iterable[float]) -> float:
    pnls = np.asarray(list(pnls), dtype=float)
    if pnls.size < 2:
        return 0.0
    mean = pnls.mean()
    std = pnls.std()
    if std <= 0:
        return 0.0
    return float(mean / std)


def _dist(series: pd.Series) -> Dict[str, float]:
    counts = series.value_counts(dropna=False).to_dict()
    total = max(len(series), 1)
    return {str(k): v / total for k, v in counts.items()}


def _brier(proba: pd.Series, y: pd.Series) -> float:
    if proba.empty or y.empty:
        return 0.0
    p = proba.astype(float)
    t = y.astype(float)
    return float(((p - t) ** 2).mean())


def build_decay_dataset(
    decision_jsonl: Path = DECISION_JSONL,
    db_path: Path = Path(getattr(cfg, "TRADE_DB_PATH", "data/trades.db")),
    trade_log_path: Path = Path("data/trade_log.json"),
    window: int = DEFAULT_WINDOW,
    drawdown_threshold: float = DEFAULT_DRAWNDOWN_THRESHOLD,
    shock_threshold: float = 0.6,
    out_path: Path = Path("data/decay_features.parquet"),
) -> pd.DataFrame:
    df = _load_decision_events(decision_jsonl, db_path)
    if df.empty:
        out_path.parent.mkdir(exist_ok=True)
        pd.DataFrame().to_parquet(out_path, index=False)
        return pd.DataFrame()

    if "ts" not in df.columns:
        if "timestamp" in df.columns:
            df["ts"] = df["timestamp"]
        else:
            df["ts"] = pd.Timestamp.utcnow().isoformat()

    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df.dropna(subset=["ts"])
    df["filled_bool"] = pd.to_numeric(df.get("filled_bool"), errors="coerce")
    df["ensemble_proba"] = pd.to_numeric(df.get("ensemble_proba"), errors="coerce")
    df["xgb_proba"] = pd.to_numeric(df.get("xgb_proba"), errors="coerce")
    df["score_0_100"] = pd.to_numeric(df.get("score_0_100"), errors="coerce")
    df["spread_pct"] = pd.to_numeric(df.get("spread_pct"), errors="coerce")
    df["depth_imbalance"] = pd.to_numeric(df.get("depth_imbalance"), errors="coerce")
    df["shock_score"] = pd.to_numeric(df.get("shock_score"), errors="coerce")
    df["slippage_vs_mid"] = pd.to_numeric(df.get("slippage_vs_mid"), errors="coerce")

    risk_map = _load_trade_risk_map(trade_log_path)

    rows = []
    for strat, sdf in df.groupby("strategy_id"):
        sdf = sdf.sort_values("ts").reset_index(drop=True)
        if len(sdf) < window:
            continue
        for i in range(window - 1, len(sdf)):
            win = sdf.iloc[i - window + 1:i + 1]
            prev = sdf.iloc[i - 2 * window + 1:i - window + 1] if i + 1 >= 2 * window else sdf.iloc[0:0]

            executed = win[win["filled_bool"] == 1]
            pnl15 = executed["pnl_horizon_15m"] if "pnl_horizon_15m" in executed.columns else pd.Series(dtype=float)
            pnl5 = executed["pnl_horizon_5m"] if "pnl_horizon_5m" in executed.columns else pd.Series(dtype=float)
            pnls = pnl15.fillna(pnl5).dropna().astype(float)
            expectancy = float(pnls.mean()) if not pnls.empty else 0.0
            win_rate = float((pnls > 0).mean()) if not pnls.empty else 0.0
            sharpe_proxy = _sharpe_proxy(pnls.tolist())
            worst_run = _worst_run(pnls.tolist())
            dd = _drawdown(pnls.tolist())
            dd_slope = (dd - 0.0) / max(len(pnls), 1)

            # Avg R (use entry/stop risk if available)
            rs = []
            for tid, pnl in zip(executed.get("trade_id", []), pnls):
                risk = risk_map.get(tid)
                if risk:
                    rs.append(pnl / risk)
            avg_r = float(np.mean(rs)) if rs else 0.0

            attempted = win[(win.get("gatekeeper_allowed") == 1) & (win.get("risk_allowed") == 1) & (win.get("exec_guard_allowed") == 1)]
            fill_rate = float(attempted["filled_bool"].mean()) if not attempted.empty else 0.0
            cancel_rate = float(1.0 - fill_rate) if not attempted.empty else 0.0

            avg_spread = float(win["spread_pct"].dropna().mean()) if win["spread_pct"].notna().any() else 0.0
            avg_slip = float(executed["slippage_vs_mid"].dropna().mean()) if executed["slippage_vs_mid"].notna().any() else 0.0
            stale_quote_rate = float(((win["bid"].isna()) | (win["ask"].isna())).mean()) if "bid" in win.columns and "ask" in win.columns else 0.0

            reg_dist = _dist(win.get("regime", pd.Series(dtype=str)))
            prev_reg_dist = _dist(prev.get("regime", pd.Series(dtype=str))) if not prev.empty else {}
            reg_js = _js_divergence(reg_dist, prev_reg_dist) if prev_reg_dist else 0.0

            shock_freq = float((win["shock_score"].fillna(0) >= shock_threshold).mean()) if "shock_score" in win.columns else 0.0

            # PSI for key features
            key_features = ["ensemble_proba", "xgb_proba", "score_0_100", "spread_pct", "depth_imbalance", "shock_score"]
            psi_vals = []
            if not prev.empty:
                for col in key_features:
                    if col in win.columns:
                        psi_vals.append(_psi(prev[col].dropna(), win[col].dropna()))
            psi_max = float(max(psi_vals)) if psi_vals else 0.0

            # Calibration error trend
            proba_col = "ensemble_proba" if win["ensemble_proba"].notna().any() else "xgb_proba"
            cur_y = (pnls > 0).astype(int) if not pnls.empty else pd.Series(dtype=int)
            cur_proba = executed[proba_col].dropna() if proba_col in executed.columns else pd.Series(dtype=float)
            brier_cur = _brier(cur_proba, cur_y[:len(cur_proba)])
            if not prev.empty:
                prev_exec = prev[prev["filled_bool"] == 1]
                prev_pnl15 = prev_exec["pnl_horizon_15m"] if "pnl_horizon_15m" in prev_exec.columns else pd.Series(dtype=float)
                prev_pnl5 = prev_exec["pnl_horizon_5m"] if "pnl_horizon_5m" in prev_exec.columns else pd.Series(dtype=float)
                prev_pnls = prev_pnl15.fillna(prev_pnl5).dropna().astype(float)
                prev_y = (prev_pnls > 0).astype(int) if not prev_pnls.empty else pd.Series(dtype=int)
                prev_proba = prev_exec[proba_col].dropna() if proba_col in prev_exec.columns else pd.Series(dtype=float)
                brier_prev = _brier(prev_proba, prev_y[:len(prev_proba)])
                cal_trend = brier_cur - brier_prev
            else:
                cal_trend = 0.0

            # Label: decayed if next window expectancy < 0 and drawdown exceeds threshold
            decayed = None
            next_exp = None
            next_dd = None
            if i + window < len(sdf):
                next_win = sdf.iloc[i + 1:i + 1 + window]
                next_exec = next_win[next_win["filled_bool"] == 1]
                next_pnl15 = next_exec["pnl_horizon_15m"] if "pnl_horizon_15m" in next_exec.columns else pd.Series(dtype=float)
                next_pnl5 = next_exec["pnl_horizon_5m"] if "pnl_horizon_5m" in next_exec.columns else pd.Series(dtype=float)
                next_pnls = next_pnl15.fillna(next_pnl5).dropna().astype(float)
                next_exp = float(next_pnls.mean()) if not next_pnls.empty else 0.0
                next_dd = _drawdown(next_pnls.tolist())
                decayed = 1 if (next_exp < 0 and next_dd > drawdown_threshold) else 0

            rows.append({
                "strategy_id": strat,
                "window_end_ts": win["ts"].iloc[-1],
                "expectancy": expectancy,
                "win_rate": win_rate,
                "avg_R": avg_r,
                "sharpe_proxy": sharpe_proxy,
                "worst_run": worst_run,
                "drawdown": dd,
                "drawdown_slope": dd_slope,
                "fill_rate": fill_rate,
                "avg_spread_pct": avg_spread,
                "avg_slippage_vs_mid": avg_slip,
                "cancel_rate": cancel_rate,
                "stale_quote_rate": stale_quote_rate,
                "regime_dist": json.dumps(reg_dist),
                "regime_js": reg_js,
                "shock_score_freq": shock_freq,
                "psi_max": psi_max,
                "calibration_error_trend": cal_trend,
                "next_expectancy": next_exp,
                "next_drawdown": next_dd,
                "decayed": decayed,
            })

    out_df = pd.DataFrame(rows).sort_values(["strategy_id", "window_end_ts"]).reset_index(drop=True)

    # time_to_failure estimate: first future decayed window
    out_df["time_to_failure_sec"] = np.nan
    for strat, sdf in out_df.groupby("strategy_id"):
        sdf = sdf.sort_values("window_end_ts").reset_index()
        decayed_idx = sdf.index[sdf["decayed"] == 1].tolist()
        for i, row in sdf.iterrows():
            future = [d for d in decayed_idx if d > i]
            if not future:
                continue
            j = future[0]
            t0 = sdf.loc[i, "window_end_ts"]
            t1 = sdf.loc[j, "window_end_ts"]
            if pd.notna(t0) and pd.notna(t1):
                out_df.loc[sdf.loc[i, "index"], "time_to_failure_sec"] = (t1 - t0).total_seconds()

    out_path.parent.mkdir(exist_ok=True)
    out_df.to_parquet(out_path, index=False)
    return out_df


if __name__ == "__main__":
    build_decay_dataset()
