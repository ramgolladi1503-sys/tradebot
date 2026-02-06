import json
import time
import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

AB_PATH = Path("logs/model_ab_trials.jsonl")
AB_SUMMARY_PATH = Path("logs/model_ab_summary.json")


def file_hash(path: str | Path | None) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def training_window(df: pd.DataFrame, ts_col: str = "timestamp") -> dict:
    if df is None or df.empty or ts_col not in df.columns:
        return {"start": None, "end": None, "rows": int(len(df) if df is not None else 0)}
    try:
        ts = pd.to_datetime(df[ts_col], errors="coerce")
        ts = ts.dropna()
        if ts.empty:
            return {"start": None, "end": None, "rows": int(len(df))}
        return {
            "start": str(ts.min()),
            "end": str(ts.max()),
            "rows": int(len(df)),
        }
    except Exception:
        return {"start": None, "end": None, "rows": int(len(df))}


def regime_coverage(df: pd.DataFrame, regime_col: str = "seg_regime") -> dict:
    if df is None or df.empty or regime_col not in df.columns:
        return {}
    try:
        dist = df[regime_col].astype(str).value_counts(normalize=True).to_dict()
        return {k: float(v) for k, v in dist.items()}
    except Exception:
        return {}


def calibration_curve(proba, actual, bins: int = 10) -> list[dict]:
    try:
        proba = np.asarray(proba, dtype=float)
        actual = np.asarray(actual, dtype=float)
    except Exception:
        return []
    if proba.size == 0 or actual.size == 0:
        return []
    proba = np.clip(proba, 0, 1)
    bins = max(2, int(bins))
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (proba >= lo) & (proba < hi) if i < bins - 1 else (proba >= lo) & (proba <= hi)
        if not np.any(mask):
            out.append({"bin_low": float(lo), "bin_high": float(hi), "count": 0, "avg_conf": None, "win_rate": None})
            continue
        p = proba[mask]
        y = actual[mask]
        out.append({
            "bin_low": float(lo),
            "bin_high": float(hi),
            "count": int(p.size),
            "avg_conf": float(np.mean(p)),
            "win_rate": float(np.mean(y)),
        })
    return out


def build_governance(train_df: pd.DataFrame,
                     feature_list: Optional[list] = None,
                     regime_col: str = "seg_regime",
                     ts_col: str = "timestamp",
                     calibration: Optional[list] = None,
                     extra: Optional[dict] = None) -> dict:
    gov = {
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "training_window": training_window(train_df, ts_col=ts_col),
        "feature_list": list(feature_list) if feature_list else [],
        "regime_coverage": regime_coverage(train_df, regime_col=regime_col),
        "calibration_curve": calibration or [],
    }
    if extra:
        gov.update(extra)
    return gov


def log_ab_trial(trade_id: str,
                 symbol: str,
                 timestamp: str,
                 champion_conf: Optional[float],
                 shadow_conf: Optional[float],
                 champion_version: Optional[str],
                 shadow_version: Optional[str],
                 mode: str = "PAPER",
                 extra: Optional[dict] = None) -> None:
    entry = {
        "trade_id": trade_id,
        "timestamp": timestamp,
        "symbol": symbol,
        "mode": mode,
        "champion_conf": champion_conf,
        "shadow_conf": shadow_conf,
        "champion_version": champion_version,
        "shadow_version": shadow_version,
        "actual": None,
    }
    if extra:
        entry.update(extra)
    try:
        AB_PATH.parent.mkdir(exist_ok=True)
        with AB_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def attach_outcomes(trade_log_path: str = "data/trade_log.json", ab_path: Path | None = None) -> Path | None:
    ab_path = ab_path or AB_PATH
    if not ab_path.exists():
        return None
    trade_map = {}
    try:
        with open(trade_log_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                tid = obj.get("trade_id")
                if tid and obj.get("actual") is not None:
                    trade_map[tid] = obj.get("actual")
    except Exception:
        trade_map = {}

    out_path = ab_path.with_name("model_ab_trials_enriched.jsonl")
    try:
        with ab_path.open("r") as f_in, out_path.open("w") as f_out:
            for line in f_in:
                if not line.strip():
                    continue
                obj = json.loads(line)
                tid = obj.get("trade_id")
                if tid in trade_map:
                    obj["actual"] = trade_map[tid]
                f_out.write(json.dumps(obj) + "\n")
    except Exception:
        return None
    return out_path


def bootstrap_pvalue(y, champ, chall, metric: str = "brier", n: int = 500, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    y = np.asarray(y, dtype=float)
    champ = np.asarray(champ, dtype=float)
    chall = np.asarray(chall, dtype=float)
    if y.size == 0 or champ.size == 0 or chall.size == 0 or y.size != champ.size or y.size != chall.size:
        return {"p_value": None, "effect": None}

    if metric == "brier":
        loss_champ = (champ - y) ** 2
        loss_chall = (chall - y) ** 2
        diff = loss_champ - loss_chall  # positive means challenger better
    else:
        acc_champ = (champ >= 0.5) == y
        acc_chall = (chall >= 0.5) == y
        diff = acc_chall.astype(float) - acc_champ.astype(float)

    if diff.size < 5:
        return {"p_value": None, "effect": float(np.mean(diff))}

    boot = []
    for _ in range(n):
        idx = rng.integers(0, diff.size, size=diff.size)
        boot.append(float(np.mean(diff[idx])))
    boot = np.asarray(boot, dtype=float)
    p_value = float(np.mean(boot <= 0.0))
    effect = float(np.mean(diff))
    return {"p_value": p_value, "effect": effect}

