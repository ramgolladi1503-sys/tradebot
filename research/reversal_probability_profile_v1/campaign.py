from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence
import hashlib
import json

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"
CAMPAIGN_ID = "RPP_NIFTY_REVERSAL_STRUCTURE_V1"
SPEC_VERSION = "1.0.0"


@dataclass(frozen=True)
class CampaignConfig:
    pivot_left: int = 5
    pivot_right: int = 5
    calculation_lookback_bars: int = 1170  # ~3 regular NSE sessions
    pivot_memory: int = 120
    profile_bins: int = 64
    smoothing_radius_bins: int = 2
    min_profile_pivots: int = 20
    atr_window: int = 30
    momentum_minutes: int = 5
    touch_radius_atr: float = 0.20
    reclaim_margin_atr: float = 0.05
    breakout_margin_atr: float = 0.10
    approach_momentum_atr: float = 0.20
    zone_search_distance_atr: float = 2.0
    primary_horizon_minutes: int = 15
    secondary_horizons_minutes: tuple[int, ...] = (20, 30)
    round_trip_cost_bps: float = 5.0
    train_sessions: int = 189
    test_sessions: int = 63
    step_sessions: int = 63
    min_train_events: int = 40
    min_oos_events: int = 100
    min_oos_sessions: int = 50
    min_oos_folds: int = 4
    min_positive_fold_fraction: float = 0.60
    min_hit_rate: float = 0.52
    min_incremental_bps_vs_momentum: float = 0.50
    min_incremental_bps_vs_shifted_control: float = 0.50
    min_shifted_control_events: int = 50
    max_single_fold_positive_profit_share: float = 0.60
    bootstrap_repetitions: int = 2000
    bootstrap_seed: int = 20260906
    negative_control_shift_minutes: int = 30
    session_open: str = "09:15"
    session_close: str = "15:30"

    def digest(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    mode: str  # REVERSAL or BREAKOUT
    min_density: float


CANDIDATES: tuple[CandidateSpec, ...] = (
    CandidateSpec("RPP_REVERSAL_D65", "REVERSAL", 0.65),
    CandidateSpec("RPP_REVERSAL_D80", "REVERSAL", 0.80),
    CandidateSpec("RPP_BREAKOUT_D65", "BREAKOUT", 0.65),
    CandidateSpec("RPP_BREAKOUT_D80", "BREAKOUT", 0.80),
)


def _find_col(df: pd.DataFrame, names: Sequence[str]) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for name in names:
        if name.lower() in lower:
            return str(lower[name.lower()])
    return None


def _read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    if p.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(p)
    raise ValueError(f"unsupported_table_format:{p.suffix}")


def sha256_path(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_ts(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.isna().any():
        raise ValueError("timestamp_parse_failure")
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize(IST)
    else:
        ts = ts.dt.tz_convert(IST)
    return ts


def load_index_ohlc(path: str | Path) -> pd.DataFrame:
    raw = _read_table(path).copy()
    ts_col = _find_col(raw, ("timestamp", "datetime", "date", "ts"))
    aliases = {
        "open": ("open", "spot_open", "o"),
        "high": ("high", "spot_high", "h"),
        "low": ("low", "spot_low", "l"),
        "close": ("close", "spot_close", "c"),
    }
    cols = {k: _find_col(raw, v) for k, v in aliases.items()}
    if ts_col is None or any(v is None for v in cols.values()):
        raise ValueError("index_table_requires_timestamp_ohlc")
    out = pd.DataFrame({"timestamp": _canonical_ts(raw[ts_col])})
    for k, c in cols.items():
        out[k] = pd.to_numeric(raw[c], errors="coerce")
    out = out.dropna().sort_values("timestamp").reset_index(drop=True)
    if out.duplicated("timestamp").any():
        raise ValueError("duplicate_timestamps")
    if ((out["high"] < out[["open", "close", "low"]].max(axis=1)) |
            (out["low"] > out[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("invalid_ohlc")
    local_time = out["timestamp"].dt.strftime("%H:%M")
    mask = (local_time >= "09:15") & (local_time <= "15:30")
    out = out.loc[mask].copy()
    out["session"] = out["timestamp"].dt.date
    return out.reset_index(drop=True)


def _causal_atr_and_momentum(df: pd.DataFrame, cfg: CampaignConfig) -> pd.DataFrame:
    out = df.copy()
    out["prev_close"] = out.groupby("session", sort=False)["close"].shift(1)
    tr = pd.concat([
        out["high"] - out["low"],
        (out["high"] - out["prev_close"]).abs(),
        (out["low"] - out["prev_close"]).abs(),
    ], axis=1).max(axis=1)
    out["atr"] = tr.groupby(out["session"]).transform(
        lambda s: s.rolling(cfg.atr_window, min_periods=max(10, cfg.atr_window // 3)).mean()
    )
    lag = out.groupby("session", sort=False)["close"].shift(cfg.momentum_minutes)
    out["momentum_atr"] = (out["close"] - lag) / out["atr"]
    return out


def _pivot_confirmations(df: pd.DataFrame, cfg: CampaignConfig) -> dict[int, list[tuple[str, float, int]]]:
    confirmations: dict[int, list[tuple[str, float, int]]] = {}
    left, right = cfg.pivot_left, cfg.pivot_right
    for _, day in df.groupby("session", sort=True):
        idx = day.index.to_numpy()
        highs = day["high"].to_numpy(float)
        lows = day["low"].to_numpy(float)
        n = len(day)
        for c in range(left, n - right):
            hi_window = highs[c-left:c+right+1]
            lo_window = lows[c-left:c+right+1]
            confirm_idx = int(idx[c + right])
            pivot_idx = int(idx[c])
            if np.isfinite(highs[c]) and highs[c] == np.max(hi_window) and np.sum(hi_window == highs[c]) == 1:
                confirmations.setdefault(confirm_idx, []).append(("HIGH", float(highs[c]), pivot_idx))
            if np.isfinite(lows[c]) and lows[c] == np.min(lo_window) and np.sum(lo_window == lows[c]) == 1:
                confirmations.setdefault(confirm_idx, []).append(("LOW", float(lows[c]), pivot_idx))
    return confirmations


def _smooth(counts: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return counts.astype(float)
    offsets = np.arange(-radius, radius + 1)
    kernel = (radius + 1 - np.abs(offsets)).astype(float)
    return np.convolve(counts.astype(float), kernel, mode="same")


def _local_peak_indices(x: np.ndarray) -> np.ndarray:
    if len(x) == 0:
        return np.array([], dtype=int)
    peaks = []
    for i, value in enumerate(x):
        if value <= 0:
            continue
        left = x[i - 1] if i > 0 else -np.inf
        right = x[i + 1] if i + 1 < len(x) else -np.inf
        if value >= left and value >= right and (value > left or value > right):
            peaks.append(i)
    return np.asarray(peaks, dtype=int)


def _build_profile(pivots: Iterable[tuple[str, float, int, int]], cfg: CampaignConfig):
    piv = list(pivots)
    if len(piv) < cfg.min_profile_pivots:
        return None
    prices = np.asarray([p[1] for p in piv], dtype=float)
    lo, hi = float(np.min(prices)), float(np.max(prices))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return None
    edges = np.linspace(lo, hi, cfg.profile_bins + 1)
    bin_idx = np.clip(np.searchsorted(edges, prices, side="right") - 1, 0, cfg.profile_bins - 1)
    high_counts = np.zeros(cfg.profile_bins, dtype=float)
    low_counts = np.zeros(cfg.profile_bins, dtype=float)
    for (kind, _, _, _), b in zip(piv, bin_idx):
        (high_counts if kind == "HIGH" else low_counts)[b] += 1.0
    high_s = _smooth(high_counts, cfg.smoothing_radius_bins)
    low_s = _smooth(low_counts, cfg.smoothing_radius_bins)
    total = high_s + low_s
    max_density = float(np.max(total))
    if max_density <= 0:
        return None
    centers = (edges[:-1] + edges[1:]) / 2.0
    return {
        "centers": centers,
        "high": high_s,
        "low": low_s,
        "total": total,
        "norm": total / max_density,
        "support_peaks": _local_peak_indices(low_s),
        "resistance_peaks": _local_peak_indices(high_s),
        "max_idx": int(np.argmax(total)),
    }


def build_causal_profile_features(index: pd.DataFrame, cfg: CampaignConfig = CampaignConfig()) -> pd.DataFrame:
    if cfg.pivot_left < 1 or cfg.pivot_right < 1:
        raise ValueError("pivot_left_right_must_be_positive")
    base = _causal_atr_and_momentum(index.reset_index(drop=True), cfg)
    confirmations = _pivot_confirmations(base, cfg)
    memory: deque[tuple[str, float, int, int]] = deque()
    profile = None
    rows: list[dict] = []

    for i, row in base.iterrows():
        changed = False
        for kind, price, pivot_idx in confirmations.get(i, []):
            memory.append((kind, price, pivot_idx, i))
            changed = True
        cutoff = i - cfg.calculation_lookback_bars
        while memory and memory[0][3] < cutoff:
            memory.popleft()
            changed = True
        while len(memory) > cfg.pivot_memory:
            memory.popleft()
            changed = True
        if changed:
            profile = _build_profile(memory, cfg)

        atr = float(row["atr"]) if pd.notna(row["atr"]) else np.nan
        if profile is None or not np.isfinite(atr) or atr <= 0:
            continue
        price = float(row["close"])
        centers = profile["centers"]
        norm = profile["norm"]
        support_idx = profile["support_peaks"]
        resistance_idx = profile["resistance_peaks"]

        support_candidates = support_idx[centers[support_idx] <= price]
        resistance_candidates = resistance_idx[centers[resistance_idx] >= price]
        support = np.nan
        support_density = np.nan
        resistance = np.nan
        resistance_density = np.nan
        if len(support_candidates):
            distances = price - centers[support_candidates]
            valid = distances <= cfg.zone_search_distance_atr * atr
            if valid.any():
                k = int(support_candidates[np.argmin(np.where(valid, distances, np.inf))])
                support = float(centers[k])
                support_density = float(norm[k])
        if len(resistance_candidates):
            distances = centers[resistance_candidates] - price
            valid = distances <= cfg.zone_search_distance_atr * atr
            if valid.any():
                k = int(resistance_candidates[np.argmin(np.where(valid, distances, np.inf))])
                resistance = float(centers[k])
                resistance_density = float(norm[k])
        max_idx = profile["max_idx"]
        rows.append({
            "timestamp": row["timestamp"],
            "session": row["session"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": price,
            "prev_close": float(row["prev_close"]) if pd.notna(row["prev_close"]) else np.nan,
            "atr": atr,
            "momentum_atr": float(row["momentum_atr"]) if pd.notna(row["momentum_atr"]) else np.nan,
            "confirmed_pivot_count": len(memory),
            "support": support,
            "support_density": support_density,
            "support_distance_atr": (price - support) / atr if np.isfinite(support) else np.nan,
            "resistance": resistance,
            "resistance_density": resistance_density,
            "resistance_distance_atr": (resistance - price) / atr if np.isfinite(resistance) else np.nan,
            "max_reversal_zone": float(centers[max_idx]),
            "max_zone_distance_atr": (price - float(centers[max_idx])) / atr,
        })
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def build_candidate_events(features: pd.DataFrame, spec: CandidateSpec, cfg: CampaignConfig) -> pd.DataFrame:
    f = features.copy()
    mom = f["momentum_atr"]
    if spec.mode == "REVERSAL":
        long_mask = (
            f["support"].notna()
            & (f["support_density"] >= spec.min_density)
            & (mom <= -cfg.approach_momentum_atr)
            & (f["low"] <= f["support"] + cfg.touch_radius_atr * f["atr"])
            & (f["close"] >= f["support"] + cfg.reclaim_margin_atr * f["atr"])
        )
        short_mask = (
            f["resistance"].notna()
            & (f["resistance_density"] >= spec.min_density)
            & (mom >= cfg.approach_momentum_atr)
            & (f["high"] >= f["resistance"] - cfg.touch_radius_atr * f["atr"])
            & (f["close"] <= f["resistance"] - cfg.reclaim_margin_atr * f["atr"])
        )
    elif spec.mode == "BREAKOUT":
        prior_resistance = f.groupby("session", sort=False)["resistance"].shift(1)
        prior_resistance_density = f.groupby("session", sort=False)["resistance_density"].shift(1)
        prior_support = f.groupby("session", sort=False)["support"].shift(1)
        prior_support_density = f.groupby("session", sort=False)["support_density"].shift(1)
        long_mask = (
            prior_resistance.notna()
            & (prior_resistance_density >= spec.min_density)
            & (mom >= cfg.approach_momentum_atr)
            & (f["prev_close"] <= prior_resistance + cfg.reclaim_margin_atr * f["atr"])
            & (f["close"] >= prior_resistance + cfg.breakout_margin_atr * f["atr"])
        )
        short_mask = (
            prior_support.notna()
            & (prior_support_density >= spec.min_density)
            & (mom <= -cfg.approach_momentum_atr)
            & (f["prev_close"] >= prior_support - cfg.reclaim_margin_atr * f["atr"])
            & (f["close"] <= prior_support - cfg.breakout_margin_atr * f["atr"])
        )
    else:
        raise ValueError(f"unknown_candidate_mode:{spec.mode}")

    out = f.loc[long_mask | short_mask].copy()
    out["signal"] = np.where(long_mask.loc[out.index], 1, -1)
    if spec.mode == "BREAKOUT":
        out["breakout_reference_zone"] = np.where(
            out["signal"] > 0, prior_resistance.loc[out.index], prior_support.loc[out.index]
        )
        out["breakout_reference_density"] = np.where(
            out["signal"] > 0, prior_resistance_density.loc[out.index], prior_support_density.loc[out.index]
        )
    out["candidate_id"] = spec.candidate_id
    out["mode"] = spec.mode
    out["min_density"] = spec.min_density
    return out.reset_index(drop=True)


def _deoverlap(events: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    kept = []
    for _, day in events.sort_values("timestamp").groupby("session", sort=True):
        last = None
        for idx, row in day.iterrows():
            ts = row["timestamp"]
            if last is None or (ts - last) >= pd.Timedelta(minutes=minutes):
                kept.append(idx)
                last = ts
    return events.loc[kept].sort_values("timestamp").reset_index(drop=True)


def attach_forward_outcomes(events: pd.DataFrame, prices: pd.DataFrame, cfg: CampaignConfig) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    p = prices.set_index("timestamp", drop=False)
    rows = []
    horizons = (cfg.primary_horizon_minutes,) + tuple(cfg.secondary_horizons_minutes)
    for _, e in events.iterrows():
        decision = e["timestamp"]
        entry_ts = decision + pd.Timedelta(minutes=1)
        if entry_ts not in p.index:
            continue
        entry = p.loc[entry_ts]
        if entry["session"] != e["session"]:
            continue
        item = e.to_dict()
        item["entry_timestamp"] = entry_ts
        item["entry_open"] = float(entry["open"])
        valid_primary = True
        for h in horizons:
            exit_ts = decision + pd.Timedelta(minutes=int(h))
            if exit_ts not in p.index or p.loc[exit_ts]["session"] != e["session"]:
                if h == cfg.primary_horizon_minutes:
                    valid_primary = False
                item[f"raw_{h}m_bps"] = np.nan
                item[f"signed_{h}m_gross_bps"] = np.nan
                item[f"signed_{h}m_net_bps"] = np.nan
                continue
            exit_close = float(p.loc[exit_ts]["close"])
            raw_bps = float(np.log(exit_close / float(entry["open"])) * 10000.0)
            gross = float(e["signal"] * raw_bps)
            item[f"raw_{h}m_bps"] = raw_bps
            item[f"signed_{h}m_gross_bps"] = gross
            item[f"signed_{h}m_net_bps"] = gross - cfg.round_trip_cost_bps
        if valid_primary:
            momentum_signal = int(np.sign(float(e["momentum_atr"])))
            raw_primary = item[f"raw_{cfg.primary_horizon_minutes}m_bps"]
            item["momentum_baseline_net_bps"] = momentum_signal * raw_primary - cfg.round_trip_cost_bps
            rows.append(item)
    return pd.DataFrame(rows)


def attach_shifted_time_control(events: pd.DataFrame, prices: pd.DataFrame, cfg: CampaignConfig) -> pd.DataFrame:
    """Move each event clock forward as a negative control while preserving signal sign."""
    if events.empty:
        return events.copy()
    p = prices.set_index("timestamp", drop=False)
    rows = []
    for _, e in events.iterrows():
        item = e.to_dict()
        shifted_decision = e["timestamp"] + pd.Timedelta(minutes=cfg.negative_control_shift_minutes)
        shifted_entry = shifted_decision + pd.Timedelta(minutes=1)
        shifted_exit = shifted_decision + pd.Timedelta(minutes=cfg.primary_horizon_minutes)
        item["shifted_control_decision_timestamp"] = shifted_decision
        item["shifted_control_entry_timestamp"] = shifted_entry
        item["shifted_control_gross_bps"] = np.nan
        item["shifted_control_net_bps"] = np.nan
        if shifted_entry in p.index and shifted_exit in p.index:
            entry = p.loc[shifted_entry]
            exit_row = p.loc[shifted_exit]
            if entry["session"] == e["session"] and exit_row["session"] == e["session"]:
                raw_bps = float(np.log(float(exit_row["close"]) / float(entry["open"])) * 10000.0)
                gross = float(int(e["signal"]) * raw_bps)
                item["shifted_control_gross_bps"] = gross
                item["shifted_control_net_bps"] = gross - cfg.round_trip_cost_bps
        rows.append(item)
    return pd.DataFrame(rows)


def _session_bootstrap_ci(events: pd.DataFrame, metric: str, cfg: CampaignConfig) -> tuple[float, float]:
    if events.empty:
        return (np.nan, np.nan)
    session_means = events.groupby("session")[metric].mean().dropna().to_numpy(float)
    if len(session_means) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(cfg.bootstrap_seed)
    samples = rng.choice(session_means, size=(cfg.bootstrap_repetitions, len(session_means)), replace=True).mean(axis=1)
    return tuple(float(x) for x in np.quantile(samples, [0.025, 0.975]))


def _candidate_train_score(events: pd.DataFrame, cfg: CampaignConfig) -> tuple[float, int, int]:
    metric = f"signed_{cfg.primary_horizon_minutes}m_net_bps"
    if events.empty:
        return (-np.inf, 0, 0)
    n = len(events)
    s = events["session"].nunique()
    if n < cfg.min_train_events or s < 20:
        return (-np.inf, n, s)
    sm = events.groupby("session")[metric].mean()
    score = float(sm.mean() - 0.25 * sm.std(ddof=0) / max(np.sqrt(len(sm)), 1.0))
    return (score, n, s)


def run_walk_forward(prices: pd.DataFrame, features: pd.DataFrame, cfg: CampaignConfig = CampaignConfig()) -> dict:
    sessions = sorted(prices["session"].unique())
    if len(sessions) < cfg.train_sessions + cfg.test_sessions:
        return {
            "campaign_id": CAMPAIGN_ID,
            "config_sha256": cfg.digest(),
            "verdict": "INSUFFICIENT_SESSIONS_FOR_WFA",
            "session_count": len(sessions),
            "required_sessions": cfg.train_sessions + cfg.test_sessions,
            "folds": [],
        }

    event_cache: dict[str, pd.DataFrame] = {}
    for spec in CANDIDATES:
        ev = build_candidate_events(features, spec, cfg)
        ev = _deoverlap(ev, cfg.primary_horizon_minutes)
        ev = attach_forward_outcomes(ev, prices, cfg)
        event_cache[spec.candidate_id] = attach_shifted_time_control(ev, prices, cfg)

    folds = []
    oos_parts = []
    start = 0
    fold_id = 0
    while start + cfg.train_sessions + cfg.test_sessions <= len(sessions):
        train_s = set(sessions[start:start + cfg.train_sessions])
        test_s = set(sessions[start + cfg.train_sessions:start + cfg.train_sessions + cfg.test_sessions])
        ranking = []
        for spec in CANDIDATES:
            train_events = event_cache[spec.candidate_id]
            train_events = train_events[train_events["session"].isin(train_s)]
            score, n, s = _candidate_train_score(train_events, cfg)
            ranking.append((score, spec.candidate_id, n, s))
        ranking.sort(key=lambda x: (-x[0], x[1]))
        best_score, best_id, train_n, train_session_n = ranking[0]
        if not np.isfinite(best_score):
            selected = None
            test_events = pd.DataFrame()
        else:
            selected = best_id
            test_events = event_cache[best_id]
            test_events = test_events[test_events["session"].isin(test_s)].copy()
            if not test_events.empty:
                test_events["fold_id"] = fold_id
                oos_parts.append(test_events)
        metric = f"signed_{cfg.primary_horizon_minutes}m_net_bps"
        folds.append({
            "fold_id": fold_id,
            "train_start": str(min(train_s)),
            "train_end": str(max(train_s)),
            "test_start": str(min(test_s)),
            "test_end": str(max(test_s)),
            "selected_candidate": selected,
            "train_score": None if not np.isfinite(best_score) else float(best_score),
            "train_events": int(train_n),
            "train_sessions_with_events": int(train_session_n),
            "test_events": int(len(test_events)),
            "test_sessions_with_events": int(test_events["session"].nunique()) if not test_events.empty else 0,
            "test_mean_net_bps": float(test_events[metric].mean()) if not test_events.empty else None,
            "test_hit_rate": float((test_events[f"signed_{cfg.primary_horizon_minutes}m_gross_bps"] > 0).mean()) if not test_events.empty else None,
        })
        fold_id += 1
        start += cfg.step_sessions

    oos = pd.concat(oos_parts, ignore_index=True) if oos_parts else pd.DataFrame()
    metric = f"signed_{cfg.primary_horizon_minutes}m_net_bps"
    gross_metric = f"signed_{cfg.primary_horizon_minutes}m_gross_bps"
    if oos.empty:
        return {
            "campaign_id": CAMPAIGN_ID,
            "config_sha256": cfg.digest(),
            "verdict": "NO_OOS_EVENTS",
            "session_count": len(sessions),
            "folds": folds,
        }

    ci_low, ci_high = _session_bootstrap_ci(oos, metric, cfg)
    fold_means = oos.groupby("fold_id")[metric].mean()
    positive_fold_fraction = float((fold_means > 0).mean()) if len(fold_means) else 0.0
    positive_pnl = oos.groupby("fold_id")[metric].sum().clip(lower=0)
    positive_total = float(positive_pnl.sum())
    max_profit_share = float(positive_pnl.max() / positive_total) if positive_total > 0 else 1.0
    baseline_mean = float(oos["momentum_baseline_net_bps"].mean())
    mean_net = float(oos[metric].mean())
    mean_gross = float(oos[gross_metric].mean())
    hit_rate_gross = float((oos[gross_metric] > 0).mean())
    incremental = mean_net - baseline_mean
    shifted_control = oos["shifted_control_net_bps"].dropna() if "shifted_control_net_bps" in oos else pd.Series(dtype=float)
    shifted_control_events = int(len(shifted_control))
    shifted_control_mean = float(shifted_control.mean()) if shifted_control_events else np.nan
    incremental_vs_shifted = mean_net - shifted_control_mean if np.isfinite(shifted_control_mean) else np.nan

    blockers = []
    if len(fold_means) < cfg.min_oos_folds:
        blockers.append("INSUFFICIENT_OOS_FOLDS")
    if len(oos) < cfg.min_oos_events:
        blockers.append("INSUFFICIENT_OOS_EVENTS")
    if oos["session"].nunique() < cfg.min_oos_sessions:
        blockers.append("INSUFFICIENT_OOS_SESSIONS")
    if not np.isfinite(ci_low) or ci_low <= 0:
        blockers.append("SESSION_BOOTSTRAP_CI_NOT_POSITIVE")
    if positive_fold_fraction < cfg.min_positive_fold_fraction:
        blockers.append("FOLD_STABILITY_FAIL")
    if hit_rate_gross < cfg.min_hit_rate:
        blockers.append("HIT_RATE_FAIL")
    if incremental < cfg.min_incremental_bps_vs_momentum:
        blockers.append("NO_INCREMENTAL_VALUE_VS_MOMENTUM")
    if shifted_control_events < cfg.min_shifted_control_events:
        blockers.append("INSUFFICIENT_SHIFTED_CONTROL_EVENTS")
    elif not np.isfinite(incremental_vs_shifted) or incremental_vs_shifted < cfg.min_incremental_bps_vs_shifted_control:
        blockers.append("NO_INCREMENTAL_VALUE_VS_SHIFTED_TIME_CONTROL")
    if max_profit_share > cfg.max_single_fold_positive_profit_share:
        blockers.append("FOLD_PROFIT_CONCENTRATION_FAIL")
    if mean_net <= 0:
        blockers.append("MEAN_AFTER_COST_PROXY_NOT_POSITIVE")

    summary = {
        "campaign_id": CAMPAIGN_ID,
        "spec_version": SPEC_VERSION,
        "config_sha256": cfg.digest(),
        "verdict": "ROBUST_DIRECTIONAL_EDGE_AFTER_COST_PROXY" if not blockers else "NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE",
        "blockers": blockers,
        "session_count": len(sessions),
        "oos_folds": int(len(fold_means)),
        "oos_events": int(len(oos)),
        "oos_sessions": int(oos["session"].nunique()),
        "mean_gross_bps": mean_gross,
        "mean_net_bps": mean_net,
        "gross_hit_rate": hit_rate_gross,
        "session_bootstrap_95_ci_net_bps": [ci_low, ci_high],
        "positive_fold_fraction": positive_fold_fraction,
        "max_single_fold_positive_profit_share": max_profit_share,
        "momentum_baseline_mean_net_bps": baseline_mean,
        "incremental_bps_vs_momentum": incremental,
        "shifted_time_control_minutes": cfg.negative_control_shift_minutes,
        "shifted_control_events": shifted_control_events,
        "shifted_control_mean_net_bps": None if not np.isfinite(shifted_control_mean) else shifted_control_mean,
        "incremental_bps_vs_shifted_control": None if not np.isfinite(incremental_vs_shifted) else incremental_vs_shifted,
        "round_trip_cost_proxy_bps": cfg.round_trip_cost_bps,
        "folds": folds,
        "selected_candidate_counts": {str(k): int(v) for k, v in oos.groupby("fold_id")["candidate_id"].first().value_counts().items()},
        "holdout_evaluated": False,
        "option_pnl_claimed": False,
        "live_or_broker_authority": False,
    }
    for h in cfg.secondary_horizons_minutes:
        col = f"signed_{h}m_net_bps"
        summary[f"mean_net_{h}m_bps"] = float(oos[col].mean()) if col in oos and oos[col].notna().any() else None
    return summary


def run_campaign(input_path: str | Path, output_dir: str | Path, cfg: CampaignConfig = CampaignConfig()) -> dict:
    prices = load_index_ohlc(input_path)
    features = build_causal_profile_features(prices, cfg)
    report = run_walk_forward(prices, features, cfg)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report["input_path"] = str(Path(input_path))
    report["input_sha256"] = sha256_path(input_path)
    report["price_rows"] = int(len(prices))
    report["feature_rows"] = int(len(features))
    report["first_session"] = str(prices["session"].min()) if len(prices) else None
    report["last_session"] = str(prices["session"].max()) if len(prices) else None
    feature_path = out / "causal_profile_features.parquet"
    try:
        features.to_parquet(feature_path, index=False)
        report["feature_artifact"] = feature_path.name
        report["feature_artifact_format"] = "parquet"
    except ImportError:
        feature_path = out / "causal_profile_features.csv"
        features.to_csv(feature_path, index=False)
        report["feature_artifact"] = feature_path.name
        report["feature_artifact_format"] = "csv_fallback_no_parquet_engine"
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
