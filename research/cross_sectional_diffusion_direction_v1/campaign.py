from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence
import hashlib
import json

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"
CAMPAIGN_ID = "HYP_CROSS_SECTIONAL_DIFFUSION_DIRECTION_V1"
SPEC_VERSION = "1.0.0"


@dataclass(frozen=True)
class CampaignConfig:
    lookback_minutes: int = 5
    primary_horizon_minutes: int = 15
    secondary_horizon_minutes: int = 30
    train_years: int = 3
    test_years: int = 1
    breadth_quantiles: tuple[float, ...] = (0.80, 0.90)
    gap_quantiles: tuple[float, ...] = (0.75, 0.90)
    min_coverage: float = 0.80
    min_oos_events: int = 100
    min_oos_sessions: int = 50
    min_positive_fold_fraction: float = 0.60
    bootstrap_repetitions: int = 2000
    bootstrap_seed: int = 20260906
    negative_control_lag_minutes: int = 30
    max_single_fold_profit_share: float = 0.50
    session_open: str = "09:15"
    session_close: str = "15:30"

    def digest(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Thresholds:
    breadth_q: float
    gap_q: float
    breadth_long: float
    breadth_short: float
    gap_long: float
    gap_short: float


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
    if p.is_dir():
        files = sorted(
            x for x in p.rglob("*")
            if x.is_file() and x.suffix.lower() in {".csv", ".parquet", ".pq"}
        )
        if not files:
            raise ValueError("directory_contains_no_supported_tables")
        return pd.concat([_read_table(x) for x in files], ignore_index=True)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    if p.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(p)
    raise ValueError(f"unsupported_table_format:{p.suffix}")


def sha256_path(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.is_file():
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    files = sorted(
        x for x in p.rglob("*")
        if x.is_file() and x.suffix.lower() in {".csv", ".parquet", ".pq"}
    )
    if not files:
        raise ValueError("directory_contains_no_supported_tables")
    h = hashlib.sha256()
    for file_path in files:
        rel = file_path.relative_to(p).as_posix().encode("utf-8")
        h.update(rel)
        h.update(bytes.fromhex(sha256_path(file_path)))
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


def load_price_table(path: str | Path, *, require_symbol: bool = False) -> pd.DataFrame:
    raw = _read_table(path).copy()
    ts_col = _find_col(raw, ("timestamp", "datetime", "date", "ts"))
    close_col = _find_col(raw, ("close", "c"))
    open_col = _find_col(raw, ("open", "o"))
    symbol_col = _find_col(raw, ("symbol", "ticker", "tradingsymbol"))
    if ts_col is None or close_col is None:
        raise ValueError("price_table_requires_timestamp_and_close")
    if require_symbol and symbol_col is None:
        raise ValueError("constituent_table_requires_symbol")
    out = pd.DataFrame({
        "timestamp": _canonical_ts(raw[ts_col]),
        "close": pd.to_numeric(raw[close_col], errors="coerce"),
    })
    if open_col is not None:
        out["open"] = pd.to_numeric(raw[open_col], errors="coerce")
    else:
        out["open"] = out["close"]
    if symbol_col is not None:
        out["symbol"] = raw[symbol_col].astype(str).str.upper().str.strip()
    out = out.dropna(subset=["timestamp", "open", "close"])
    keys = ["timestamp", "symbol"] if "symbol" in out.columns else ["timestamp"]
    if out.duplicated(keys).any():
        raise ValueError("duplicate_price_rows")
    return out.sort_values(keys).reset_index(drop=True)


def load_membership(path: str | Path) -> pd.DataFrame:
    raw = _read_table(path).copy()
    symbol_col = _find_col(raw, ("symbol", "ticker", "tradingsymbol"))
    start_col = _find_col(raw, ("effective_from", "start", "start_date", "from"))
    end_col = _find_col(raw, ("effective_to", "end", "end_date", "to"))
    weight_col = _find_col(raw, ("weight", "index_weight", "free_float_weight"))
    if symbol_col is None or start_col is None:
        raise ValueError("membership_requires_symbol_and_effective_from")
    out = pd.DataFrame({
        "symbol": raw[symbol_col].astype(str).str.upper().str.strip(),
        "effective_from": pd.to_datetime(raw[start_col], errors="coerce").dt.date,
    })
    if end_col is None:
        out["effective_to"] = pd.NaT
    else:
        out["effective_to"] = pd.to_datetime(raw[end_col], errors="coerce").dt.date
    if weight_col is None:
        out["weight"] = np.nan
    else:
        out["weight"] = pd.to_numeric(raw[weight_col], errors="coerce")
    if out["effective_from"].isna().any():
        raise ValueError("membership_date_parse_failure")
    return out.sort_values(["effective_from", "symbol"]).reset_index(drop=True)


def _session_key(ts: pd.Series) -> pd.Series:
    return ts.dt.tz_convert(IST).dt.date


def _within_session_lag(series: pd.Series, session: pd.Series, periods: int) -> pd.Series:
    return series.groupby(session, sort=False).shift(periods)


def _eligible_members(membership: pd.DataFrame, date_value) -> pd.DataFrame:
    target = pd.Timestamp(date_value).normalize()
    start = pd.to_datetime(membership["effective_from"], errors="coerce").dt.normalize()
    end = pd.to_datetime(membership["effective_to"], errors="coerce").dt.normalize()
    active = membership[
        (start <= target)
        & (end.isna() | (end >= target))
    ].copy()
    if active.empty:
        return active
    active = active.drop_duplicates("symbol", keep="last")
    weights = pd.to_numeric(active["weight"], errors="coerce")
    if weights.notna().all() and float(weights.clip(lower=0).sum()) > 0:
        active["normalized_weight"] = weights.clip(lower=0) / float(weights.clip(lower=0).sum())
        active["weight_authority"] = "HISTORICAL_WEIGHTED"
    else:
        active["normalized_weight"] = 1.0 / len(active)
        active["weight_authority"] = "HISTORICAL_MEMBERSHIP_EQUAL_WEIGHT"
    return active[["symbol", "normalized_weight", "weight_authority"]]


def build_feature_frame(
    index: pd.DataFrame,
    constituents: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    lookback_minutes: int = 5,
    min_coverage: float = 0.80,
) -> pd.DataFrame:
    if lookback_minutes <= 0:
        raise ValueError("lookback_must_be_positive")
    idx = index.copy().sort_values("timestamp")
    con = constituents.copy().sort_values(["symbol", "timestamp"])
    idx["session"] = _session_key(idx["timestamp"])
    idx["index_lag_close"] = _within_session_lag(idx["close"], idx["session"], lookback_minutes)
    idx["index_r"] = np.log(idx["close"] / idx["index_lag_close"])
    idx["next_open"] = idx.groupby("session", sort=False)["open"].shift(-1)

    con["session"] = _session_key(con["timestamp"])
    con["lag_close"] = con.groupby(["symbol", "session"], sort=False)["close"].shift(lookback_minutes)
    con["ret"] = np.log(con["close"] / con["lag_close"])
    con = con.dropna(subset=["ret"])

    rows: list[dict] = []
    for date_value, idx_day in idx.groupby("session", sort=True):
        members = _eligible_members(membership, date_value)
        if members.empty:
            continue
        day_con = con[con["session"] == date_value].merge(members, on="symbol", how="inner")
        if day_con.empty:
            continue
        member_count = int(len(members))
        weight_authority = str(members["weight_authority"].iloc[0])
        for ts, group in day_con.groupby("timestamp", sort=True):
            observed = group.dropna(subset=["ret", "normalized_weight"]).copy()
            if observed.empty:
                continue
            coverage = observed["symbol"].nunique() / member_count
            if coverage < min_coverage:
                continue
            w = observed["normalized_weight"].to_numpy(float)
            w = w / w.sum()
            r = observed["ret"].to_numpy(float)
            breadth = float(np.dot(w, np.sign(r)))
            impulse = float(np.dot(w, r))
            rows.append({
                "timestamp": ts,
                "session": date_value,
                "breadth": breadth,
                "impulse": impulse,
                "coverage": float(coverage),
                "eligible_members": member_count,
                "observed_members": int(observed["symbol"].nunique()),
                "weight_authority": weight_authority,
            })
    if not rows:
        raise ValueError("no_feature_rows_after_membership_and_coverage")
    feat = pd.DataFrame(rows)
    out = idx.merge(feat, on=["timestamp", "session"], how="inner")
    out["gap"] = out["impulse"] - out["index_r"]
    out = out.dropna(subset=["index_r", "breadth", "impulse", "gap", "next_open"]).copy()
    return out.sort_values("timestamp").reset_index(drop=True)


def add_forward_returns(features: pd.DataFrame, execution: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    base = features.copy()
    exe = execution.copy().sort_values("timestamp")
    exe["session"] = _session_key(exe["timestamp"])
    exe["entry_open"] = exe.groupby("session", sort=False)["open"].shift(-1)
    result = base.merge(exe[["timestamp", "entry_open", "session"]], on=["timestamp", "session"], how="left")
    for h in sorted(set(int(x) for x in horizons)):
        if h <= 0:
            raise ValueError("horizon_must_be_positive")
        exe[f"exit_close_{h}"] = exe.groupby("session", sort=False)["close"].shift(-h)
        result = result.merge(exe[["timestamp", f"exit_close_{h}"]], on="timestamp", how="left")
        result[f"long_gross_bps_{h}"] = np.log(result[f"exit_close_{h}"] / result["entry_open"]) * 10000.0
    return result


def fit_thresholds(train: pd.DataFrame, breadth_q: float, gap_q: float) -> Thresholds:
    if not (0.5 < breadth_q < 1.0 and 0.5 < gap_q < 1.0):
        raise ValueError("quantiles_must_be_above_half_and_below_one")
    return Thresholds(
        breadth_q=float(breadth_q),
        gap_q=float(gap_q),
        breadth_long=float(train["breadth"].quantile(breadth_q)),
        breadth_short=float(train["breadth"].quantile(1.0 - breadth_q)),
        gap_long=float(train["gap"].quantile(gap_q)),
        gap_short=float(train["gap"].quantile(1.0 - gap_q)),
    )


def apply_signal(frame: pd.DataFrame, thresholds: Thresholds) -> pd.Series:
    long = (
        (frame["breadth"] >= thresholds.breadth_long)
        & (frame["impulse"] > 0)
        & (frame["gap"] >= thresholds.gap_long)
    )
    short = (
        (frame["breadth"] <= thresholds.breadth_short)
        & (frame["impulse"] < 0)
        & (frame["gap"] <= thresholds.gap_short)
    )
    return pd.Series(np.select([long, short], [1, -1], default=0), index=frame.index, dtype=int)


def _deoverlap_events(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    kept: list[int] = []
    last_by_session: dict[object, pd.Timestamp] = {}
    delta = pd.Timedelta(minutes=horizon)
    for idx, row in frame.sort_values("timestamp").iterrows():
        ts = pd.Timestamp(row["timestamp"])
        session = row["session"]
        last = last_by_session.get(session)
        if last is None or ts - last >= delta:
            kept.append(idx)
            last_by_session[session] = ts
    return frame.loc[kept].sort_values("timestamp").copy()


def score_signals(frame: pd.DataFrame, thresholds: Thresholds, horizon: int, cost_bps: float) -> pd.DataFrame:
    scored = frame.copy()
    scored["signal"] = apply_signal(scored, thresholds)
    scored = scored[scored["signal"] != 0].copy()
    scored = scored.dropna(subset=[f"long_gross_bps_{horizon}"])
    scored = _deoverlap_events(scored, horizon)
    scored["gross_bps"] = scored["signal"] * scored[f"long_gross_bps_{horizon}"]
    scored["net_bps"] = scored["gross_bps"] - float(cost_bps)
    return scored


def session_bootstrap_ci(events: pd.DataFrame, value_col: str, repetitions: int, seed: int) -> dict:
    if events.empty:
        return {"estimate": None, "ci_lower": None, "ci_upper": None, "sessions": 0}
    by_session = events.groupby("session", sort=True)[value_col].mean().astype(float).to_numpy()
    rng = np.random.default_rng(seed)
    samples = rng.choice(by_session, size=(repetitions, len(by_session)), replace=True).mean(axis=1)
    return {
        "estimate": float(by_session.mean()),
        "ci_lower": float(np.quantile(samples, 0.025)),
        "ci_upper": float(np.quantile(samples, 0.975)),
        "sessions": int(len(by_session)),
    }


def _annual_windows(frame: pd.DataFrame, train_years: int, test_years: int) -> list[tuple[list[int], list[int]]]:
    years = sorted(set(pd.DatetimeIndex(frame["timestamp"]).year))
    windows: list[tuple[list[int], list[int]]] = []
    for i in range(len(years) - train_years - test_years + 1):
        train = years[i:i + train_years]
        test = years[i + train_years:i + train_years + test_years]
        windows.append((train, test))
    return windows


def _candidate_grid(cfg: CampaignConfig) -> list[tuple[float, float]]:
    return [(float(bq), float(gq)) for bq in cfg.breadth_quantiles for gq in cfg.gap_quantiles]


def _choose_train_candidate(train: pd.DataFrame, horizon: int, cost_bps: float, cfg: CampaignConfig) -> tuple[Thresholds, list[dict]]:
    candidates: list[dict] = []
    best: tuple[float, Thresholds] | None = None
    for bq, gq in _candidate_grid(cfg):
        t = fit_thresholds(train, bq, gq)
        events = score_signals(train, t, horizon, cost_bps)
        score = float(events.groupby("session")["net_bps"].mean().mean()) if not events.empty else -np.inf
        candidates.append({
            "breadth_q": bq,
            "gap_q": gq,
            "train_events": int(len(events)),
            "train_sessions": int(events["session"].nunique()) if not events.empty else 0,
            "train_session_equal_net_bps": None if not np.isfinite(score) else score,
        })
        if best is None or score > best[0]:
            best = (score, t)
    if best is None:
        raise ValueError("candidate_selection_failed")
    return best[1], candidates


def fit_index_only_baseline(train: pd.DataFrame, thresholds: Thresholds) -> tuple[float, float, float, float]:
    signal = apply_signal(train, thresholds)
    long_rate = float((signal == 1).mean())
    short_rate = float((signal == -1).mean())
    if long_rate <= 0 or short_rate <= 0:
        raise ValueError("diffusion_signal_rate_zero_in_train")
    long_q = min(max(1.0 - long_rate, 0.50), 0.999)
    short_q = min(max(short_rate, 0.001), 0.50)
    return (
        float(train["index_r"].quantile(long_q)),
        float(train["index_r"].quantile(short_q)),
        long_rate,
        short_rate,
    )


def score_index_only_baseline(
    frame: pd.DataFrame,
    *,
    long_threshold: float,
    short_threshold: float,
    horizon: int,
    cost_bps: float,
) -> pd.DataFrame:
    scored = frame.copy()
    scored["signal"] = np.select(
        [scored["index_r"] >= long_threshold, scored["index_r"] <= short_threshold],
        [1, -1],
        default=0,
    ).astype(int)
    scored = scored[scored["signal"] != 0].copy()
    scored = scored.dropna(subset=[f"long_gross_bps_{horizon}"])
    scored = _deoverlap_events(scored, horizon)
    scored["gross_bps"] = scored["signal"] * scored[f"long_gross_bps_{horizon}"]
    scored["net_bps"] = scored["gross_bps"] - float(cost_bps)
    return scored


def _lagged_control(frame: pd.DataFrame, lag_minutes: int) -> pd.DataFrame:
    out = frame.copy().sort_values("timestamp")
    for col in ("breadth", "impulse", "gap"):
        out[col] = out.groupby("session", sort=False)[col].shift(lag_minutes)
    return out.dropna(subset=["breadth", "impulse", "gap"]).copy()


def _fold_profit_concentration(events: pd.DataFrame) -> float | None:
    if events.empty or "fold_id" not in events:
        return None
    fold = events.groupby("fold_id", sort=True)["net_bps"].sum()
    positive = fold.clip(lower=0)
    total = float(positive.sum())
    if total <= 0:
        return None
    return float(positive.max() / total)


def run_walk_forward(
    features_with_returns: pd.DataFrame,
    *,
    horizon: int,
    cost_bps: float,
    cfg: CampaignConfig,
) -> dict:
    frame = features_with_returns.copy()
    windows = _annual_windows(frame, cfg.train_years, cfg.test_years)
    if not windows:
        return {"status": "INSUFFICIENT_YEARS", "horizon": horizon, "folds": [], "events": pd.DataFrame()}
    event_frames: list[pd.DataFrame] = []
    control_frames: list[pd.DataFrame] = []
    baseline_frames: list[pd.DataFrame] = []
    folds: list[dict] = []
    for fold_id, (train_years, test_years) in enumerate(windows, start=1):
        years = pd.DatetimeIndex(frame["timestamp"]).year
        train = frame[years.isin(train_years)].copy()
        test = frame[years.isin(test_years)].copy()
        thresholds, candidates = _choose_train_candidate(train, horizon, cost_bps, cfg)
        baseline_long, baseline_short, train_long_rate, train_short_rate = fit_index_only_baseline(train, thresholds)
        events = score_signals(test, thresholds, horizon, cost_bps)
        events["fold_id"] = fold_id
        control = score_signals(_lagged_control(test, cfg.negative_control_lag_minutes), thresholds, horizon, cost_bps)
        control["fold_id"] = fold_id
        baseline = score_index_only_baseline(
            test,
            long_threshold=baseline_long,
            short_threshold=baseline_short,
            horizon=horizon,
            cost_bps=cost_bps,
        )
        baseline["fold_id"] = fold_id
        if not events.empty:
            event_frames.append(events)
        if not control.empty:
            control_frames.append(control)
        if not baseline.empty:
            baseline_frames.append(baseline)
        fold_mean = float(events.groupby("session")["net_bps"].mean().mean()) if not events.empty else None
        control_mean = float(control.groupby("session")["net_bps"].mean().mean()) if not control.empty else None
        baseline_mean = float(baseline.groupby("session")["net_bps"].mean().mean()) if not baseline.empty else None
        folds.append({
            "fold_id": fold_id,
            "train_years": train_years,
            "test_years": test_years,
            "thresholds": asdict(thresholds),
            "train_candidates": candidates,
            "oos_events": int(len(events)),
            "oos_sessions": int(events["session"].nunique()) if not events.empty else 0,
            "oos_session_equal_net_bps": fold_mean,
            "lagged_control_session_equal_net_bps": control_mean,
            "index_only_baseline_session_equal_net_bps": baseline_mean,
            "index_only_baseline_long_threshold": baseline_long,
            "index_only_baseline_short_threshold": baseline_short,
            "train_diffusion_long_rate": train_long_rate,
            "train_diffusion_short_rate": train_short_rate,
        })
    events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    controls = pd.concat(control_frames, ignore_index=True) if control_frames else pd.DataFrame()
    baselines = pd.concat(baseline_frames, ignore_index=True) if baseline_frames else pd.DataFrame()
    ci = session_bootstrap_ci(events, "net_bps", cfg.bootstrap_repetitions, cfg.bootstrap_seed)
    control_ci = session_bootstrap_ci(controls, "net_bps", cfg.bootstrap_repetitions, cfg.bootstrap_seed + 1)
    baseline_ci = session_bootstrap_ci(baselines, "net_bps", cfg.bootstrap_repetitions, cfg.bootstrap_seed + 2)
    fold_means = [f["oos_session_equal_net_bps"] for f in folds if f["oos_session_equal_net_bps"] is not None]
    positive_fold_fraction = float(np.mean(np.array(fold_means) > 0)) if fold_means else 0.0
    concentration = _fold_profit_concentration(events)
    return {
        "status": "COMPLETE",
        "horizon": horizon,
        "cost_bps": float(cost_bps),
        "folds": folds,
        "events": events,
        "controls": controls,
        "baselines": baselines,
        "oos_event_count": int(len(events)),
        "oos_session_count": int(events["session"].nunique()) if not events.empty else 0,
        "session_bootstrap": ci,
        "lagged_control_bootstrap": control_ci,
        "index_only_baseline_bootstrap": baseline_ci,
        "positive_fold_fraction": positive_fold_fraction,
        "max_single_fold_profit_share": concentration,
    }


def assess_terminal_verdict(
    result: dict,
    *,
    cfg: CampaignConfig,
    membership_authoritative: bool,
    execution_authoritative: bool,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if result.get("status") != "COMPLETE":
        blockers.append("WFA_INCOMPLETE")
    if not membership_authoritative:
        blockers.append("HISTORICAL_MEMBERSHIP_NOT_AUTHORITATIVE")
    if not execution_authoritative:
        blockers.append("EXECUTION_SERIES_NOT_AUTHORITATIVE")
    if result.get("oos_event_count", 0) < cfg.min_oos_events:
        blockers.append("INSUFFICIENT_OOS_EVENTS")
    if result.get("oos_session_count", 0) < cfg.min_oos_sessions:
        blockers.append("INSUFFICIENT_OOS_SESSIONS")
    ci = result.get("session_bootstrap", {})
    if ci.get("ci_lower") is None or float(ci["ci_lower"]) <= 0:
        blockers.append("AFTER_COST_CI_NOT_POSITIVE")
    if float(result.get("positive_fold_fraction", 0.0)) < cfg.min_positive_fold_fraction:
        blockers.append("FOLD_STABILITY_NOT_MET")
    concentration = result.get("max_single_fold_profit_share")
    if concentration is not None and float(concentration) > cfg.max_single_fold_profit_share:
        blockers.append("PROFIT_CONCENTRATION_TOO_HIGH")
    control = result.get("lagged_control_bootstrap", {})
    baseline = result.get("index_only_baseline_bootstrap", {})
    main_est = ci.get("estimate")
    control_est = control.get("estimate")
    baseline_est = baseline.get("estimate")
    if main_est is None:
        blockers.append("MAIN_EFFECT_UNAVAILABLE")
    elif control_est is not None and float(control_est) >= 0.5 * float(main_est):
        blockers.append("LAGGED_CONTROL_RETAINS_TOO_MUCH_EFFECT")
    if main_est is not None and baseline_est is not None and float(main_est) <= float(baseline_est):
        blockers.append("NO_INCREMENTAL_VALUE_OVER_INDEX_MOMENTUM")
    if blockers:
        return "NO_CERTIFIED_TRADABLE_EDGE", blockers
    return "CERTIFIED_DIRECTIONAL_EXECUTION_EDGE", []


def summarize_result(result: dict) -> dict:
    out = {k: v for k, v in result.items() if k not in {"events", "controls", "baselines"}}
    return out
