from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

CAMPAIGN = "autonomous_structural_edge_exhaustion_v1"
SCHEMA_VERSION = 1
TZ = "Asia/Kolkata"
CAS_START = pd.Timestamp("2026-08-03").date()
INDEX_SYMBOL = "NIFTY"
SOURCE_SHA256 = "ae9645a83cb555899145e04ebe5a961fd130df25cba88a8fc8fd43b986bbfad0"
SOURCE_SIZE = 47_788_672
SOURCE_BASENAME = "constituent_index_5m.parquet"
RANDOM_STATE = 20260807
MIN_CONSTITUENTS = 40
INDEX_LIKE_MARKERS = ("NIFTY", "SENSEX", "FINNIFTY", "BANKNIFTY", "BANK NIFTY")
MIN_OBS_SYMBOL_SESSION_COVERAGE = 0.80
HORIZONS = (3, 6, 12)
MAX_MOTIFS_PER_FAMILY = 12
MAX_FINAL_CANDIDATES = 3
K_CANDIDATES = (4, 5, 6, 7, 8)

TS_CANDIDATES = (
    "event_timestamp", "timestamp", "datetime", "date_time", "exchange_timestamp",
    "candle_timestamp", "time",
)
SESSION_CANDIDATES = ("session_id", "session", "trade_date", "date", "session_date")
SYMBOL_CANDIDATES = (
    "instrument_family", "tradingsymbol", "trading_symbol", "symbol",
    "instrument_key", "underlying",
)
CLOSE_CANDIDATES = ("close", "ltp", "last_price", "price")
VOLUME_CANDIDATES = ("volume", "volume_sum", "last_traded_quantity", "ltq")
QUALITY_FALSE = ("fallback", "mock", "synthetic", "is_stale", "stale_price_flag")
QUALITY_TRUE = ("is_completed_bar", "underlying_completed_bar", "certified_for_replay")

FAMILY_FEATURES: dict[str, tuple[str, ...]] = {
    "PARTICIPATION_LEADERSHIP": (
        "breadth_imbalance", "sign_entropy", "top5_abs_share", "leader_churn",
        "participation_ratio", "mean_abs_ret",
    ),
    "DISPERSION_COHESION": (
        "dispersion_std", "dispersion_mad", "cross_section_spread", "coherence",
        "sign_entropy", "mean_abs_ret",
    ),
    "INDEX_CONSTITUENT_DISAGREEMENT": (
        "index_eqw_divergence", "index_median_divergence", "breadth_imbalance",
        "index_ret1", "constituent_mean_ret", "constituent_median_ret",
    ),
    "DIFFUSION_DYNAMICS": (
        "breadth_delta1", "breadth_delta3", "dispersion_delta1", "dispersion_delta3",
        "concentration_delta1", "leader_churn",
    ),
    "CROSS_SCALE_ALIGNMENT": (
        "breadth_gap_3_6", "dispersion_gap_3_6", "concentration_gap_3_6",
        "divergence_gap_3_6", "index_ret3", "index_ret6",
    ),
    "NORMALIZED_VOLUME_SHOCK": (
        "median_volume_ratio", "volume_shock_share", "high_volume_signed_mean",
        "breadth_imbalance", "dispersion_std", "index_eqw_divergence",
    ),
}


def load_pattern_atlas_helpers():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_observation_first_pattern_atlas_full_certification_v1.py"
    spec = importlib.util.spec_from_file_location("pattern_atlas_cert_helpers_for_exhaustion_v1", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load Pattern Atlas helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PA = load_pattern_atlas_helpers()
COST_BPS = float(PA.COST_BPS)
ROBUST_COST_BPS = float(PA.ROBUST_COST_BPS)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def stable_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def first(columns: Sequence[str], candidates: Sequence[str]) -> str | None:
    lookup = {str(c).lower(): str(c) for c in columns}
    return next((lookup[c.lower()] for c in candidates if c.lower() in lookup), None)


def _normalize_timestamp(series: pd.Series) -> pd.Series:
    values: list[pd.Timestamp | pd.NaT] = []
    for raw in series:
        try:
            ts = pd.Timestamp(raw)
            if pd.isna(ts):
                raise ValueError
            if ts.tzinfo is None:
                ts = ts.tz_localize(TZ, ambiguous="NaT", nonexistent="NaT")
            else:
                ts = ts.tz_convert(TZ)
            values.append(ts)
        except Exception:
            values.append(pd.NaT)
    return pd.Series(values, index=series.index, dtype=f"datetime64[ns, {TZ}]")


def verify_source(path: Path) -> dict[str, Any]:
    if path.name != SOURCE_BASENAME:
        raise ValueError(f"source basename mismatch: {path.name}")
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    sha = file_sha256(path)
    if size != SOURCE_SIZE:
        raise ValueError(f"source size mismatch expected={SOURCE_SIZE} actual={size}")
    if sha != SOURCE_SHA256:
        raise ValueError(f"source sha mismatch expected={SOURCE_SHA256} actual={sha}")
    return {"path": str(path), "basename": path.name, "size": size, "sha256": sha}


def canonicalize_source(path: Path) -> pd.DataFrame:
    import pyarrow.parquet as pq
    columns = list(pq.ParquetFile(path).schema.names)
    ts_col = first(columns, TS_CANDIDATES)
    session_col = first(columns, SESSION_CANDIDATES)
    symbol_col = first(columns, SYMBOL_CANDIDATES)
    close_col = first(columns, CLOSE_CANDIDATES)
    volume_col = first(columns, VOLUME_CANDIDATES)
    if ts_col is None or symbol_col is None or close_col is None:
        raise ValueError(
            f"required columns missing ts={ts_col} symbol={symbol_col} close={close_col} columns={columns}"
        )
    selected = [ts_col, symbol_col, close_col]
    if session_col and session_col not in selected:
        selected.append(session_col)
    if volume_col and volume_col not in selected:
        selected.append(volume_col)
    for name in (*QUALITY_FALSE, *QUALITY_TRUE):
        match = first(columns, (name,))
        if match and match not in selected:
            selected.append(match)
    frame = pd.read_parquet(path, columns=selected)
    out = pd.DataFrame(index=frame.index)
    out["timestamp"] = _normalize_timestamp(frame[ts_col])
    out["symbol"] = frame[symbol_col].astype(str).str.strip().str.upper()
    out["close"] = pd.to_numeric(frame[close_col], errors="coerce")
    out["volume"] = (
        pd.to_numeric(frame[volume_col], errors="coerce").clip(lower=0)
        if volume_col else np.nan
    )
    if session_col:
        session_values = pd.to_datetime(frame[session_col], errors="coerce")
        out["session_date"] = session_values.dt.date
        out["session_date"] = out["session_date"].where(out["session_date"].notna(), out["timestamp"].dt.date)
    else:
        out["session_date"] = out["timestamp"].dt.date

    mask = out["timestamp"].notna() & out["session_date"].notna() & out["close"].gt(0)
    lookup = {str(c).lower(): str(c) for c in frame.columns}
    for name in QUALITY_TRUE:
        col = lookup.get(name.lower())
        if col:
            mask &= frame[col].fillna(False).astype(bool)
    for name in QUALITY_FALSE:
        col = lookup.get(name.lower())
        if col:
            mask &= ~frame[col].fillna(True).astype(bool)
    out = out.loc[mask].copy()
    local_time = out["timestamp"].dt.time
    start = pd.Timestamp("09:15").time()
    end = pd.Timestamp("15:30").time()
    out = out.loc[local_time.between(start, end, inclusive="both")].copy()
    out = out.loc[pd.Series(out["session_date"]).map(lambda d: d < CAS_START).to_numpy()].copy()
    out = (
        out.sort_values(["symbol", "session_date", "timestamp"], kind="mergesort")
        .drop_duplicates(["symbol", "session_date", "timestamp"], keep="last")
        .reset_index(drop=True)
    )
    return out


def accepted_index_sessions(frame: pd.DataFrame, index_symbol: str = INDEX_SYMBOL) -> tuple[pd.DataFrame, list[str]]:
    idx = frame.loc[frame["symbol"].eq(index_symbol)].copy()
    if idx.empty:
        raise ValueError(f"index symbol {index_symbol} absent")
    accepted: list[str] = []
    parts: list[pd.DataFrame] = []
    for session_date, group in idx.groupby("session_date", sort=True):
        ordered = group.sort_values("timestamp", kind="mergesort").drop_duplicates("timestamp")
        if len(ordered) < 70:
            continue
        first_time = ordered["timestamp"].iloc[0].time()
        last_time = ordered["timestamp"].iloc[-1].time()
        if first_time > pd.Timestamp("09:20").time() or last_time < pd.Timestamp("15:25").time():
            continue
        deltas = ordered["timestamp"].diff().dt.total_seconds().div(60.0).dropna()
        if deltas.empty or float(deltas.median()) < 4.5 or float(deltas.median()) > 5.5:
            continue
        accepted.append(str(session_date))
        parts.append(ordered)
    if len(accepted) < 200:
        raise ValueError(f"too few accepted index sessions: {len(accepted)}")
    result = pd.concat(parts, ignore_index=True)
    return result, accepted


def split_sessions(sessions: Sequence[str]) -> dict[str, list[str]]:
    ordered = sorted(dict.fromkeys(map(str, sessions)))
    n = len(ordered)
    n_obs = int(math.floor(n * 0.50))
    n_rep = int(math.floor(n * 0.20))
    n_val = int(math.floor(n * 0.15))
    if min(n_obs, n_rep, n_val) < 20 or n - n_obs - n_rep - n_val < 20:
        raise ValueError(f"insufficient sessions for four-way split: {n}")
    return {
        "observation": ordered[:n_obs],
        "replication": ordered[n_obs:n_obs + n_rep],
        "validation": ordered[n_obs + n_rep:n_obs + n_rep + n_val],
        "unopened": ordered[n_obs + n_rep + n_val:],
    }


def select_observation_universe(frame: pd.DataFrame, index_rows: pd.DataFrame, splits: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    obs = set(map(str, splits["observation"]))
    index_obs = index_rows.loc[index_rows["session_date"].astype(str).isin(obs)]
    expected_by_session = index_obs.groupby(index_obs["session_date"].astype(str))["timestamp"].nunique().to_dict()
    symbol_text = frame["symbol"].astype(str).str.upper()
    index_like = pd.Series(False, index=frame.index)
    for marker in INDEX_LIKE_MARKERS:
        index_like |= symbol_text.str.contains(marker, regex=False)
    constituents = frame.loc[
        ~frame["symbol"].eq(INDEX_SYMBOL)
        & ~index_like
        & frame["session_date"].astype(str).isin(obs)
    ].copy()
    per_symbol_session = (
        constituents.groupby(["symbol", constituents["session_date"].astype(str)], observed=True)["timestamp"]
        .nunique()
        .rename("bars")
        .reset_index()
        .rename(columns={"session_date": "session_key"})
    )
    rows = []
    for symbol, group in per_symbol_session.groupby("symbol", sort=True):
        good = 0
        ratios = []
        for row in group.itertuples(index=False):
            session_key = str(getattr(row, "session_key"))
            expected = int(expected_by_session.get(session_key, 0))
            if expected <= 0:
                continue
            ratio = float(getattr(row, "bars")) / expected
            ratios.append(min(1.0, ratio))
            if ratio >= 0.80:
                good += 1
        coverage = good / max(1, len(obs))
        rows.append({
            "symbol": str(symbol),
            "good_observation_sessions": good,
            "observation_sessions": len(obs),
            "session_coverage": coverage,
            "median_bar_coverage": float(np.median(ratios)) if ratios else 0.0,
        })
    table = pd.DataFrame(rows).sort_values(["session_coverage", "median_bar_coverage", "symbol"], ascending=[False, False, True])
    selected = table.loc[
        table["session_coverage"].ge(MIN_OBS_SYMBOL_SESSION_COVERAGE)
        & table["median_bar_coverage"].ge(0.80), "symbol"
    ].astype(str).tolist()
    if len(selected) < MIN_CONSTITUENTS:
        raise ValueError(f"observation-selected constituent universe too small: {len(selected)}")
    authority = {
        "selection_scope": "observation_sessions_only",
        "minimum_symbol_session_coverage": MIN_OBS_SYMBOL_SESSION_COVERAGE,
        "minimum_constituents": MIN_CONSTITUENTS,
        "selected_count": len(selected),
        "selected_symbols": selected,
        "coverage_table": table.to_dict("records"),
        "index_like_symbol_markers_excluded": list(INDEX_LIKE_MARKERS),
        "point_in_time_membership_available": False,
        "survivorship_risk": "UNRESOLVED_POINT_IN_TIME_MEMBERSHIP",
    }
    authority["semantic_sha256"] = digest(authority)
    return authority


def _binary_entropy(p: float) -> float:
    if not math.isfinite(p) or p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p)))


def build_cross_sectional_frame(
    frame: pd.DataFrame,
    index_rows: pd.DataFrame,
    universe: Sequence[str],
    accepted_sessions: Sequence[str],
) -> pd.DataFrame:
    allowed_sessions = set(map(str, accepted_sessions))
    selected = frame.loc[
        frame["symbol"].isin([*universe, INDEX_SYMBOL])
        & frame["session_date"].astype(str).isin(allowed_sessions)
    ].copy()
    selected = selected.sort_values(["symbol", "session_date", "timestamp"], kind="mergesort")
    group = selected.groupby(["symbol", "session_date"], observed=True, sort=False)
    selected["log_ret1"] = group["close"].transform(lambda v: np.log(v).diff())
    if selected["volume"].notna().any():
        prior_median = group["volume"].transform(lambda v: v.shift(1).rolling(12, min_periods=4).median())
        selected["volume_ratio"] = selected["volume"].div(prior_median.replace(0, np.nan))
    else:
        selected["volume_ratio"] = np.nan

    constituents = selected.loc[selected["symbol"].isin(universe)].copy()
    rows: list[dict[str, Any]] = []
    for (session_date, timestamp), g in constituents.groupby(["session_date", "timestamp"], sort=True):
        returns = pd.to_numeric(g["log_ret1"], errors="coerce")
        valid = g.loc[np.isfinite(returns)].copy()
        returns = pd.to_numeric(valid["log_ret1"], errors="coerce").to_numpy(float)
        if len(returns) < MIN_CONSTITUENTS:
            continue
        symbols = valid["symbol"].astype(str).tolist()
        up = float(np.mean(returns > 0))
        down = float(np.mean(returns < 0))
        mean_ret = float(np.mean(returns))
        median_ret = float(np.median(returns))
        abs_ret = np.abs(returns)
        mean_abs = float(np.mean(abs_ret))
        dispersion = float(np.std(returns, ddof=0))
        mad = float(np.median(np.abs(returns - median_ret)))
        q10, q90 = np.quantile(returns, [0.10, 0.90])
        order = np.argsort(abs_ret)[::-1]
        top_symbols = tuple(symbols[i] for i in order[:5])
        abs_total = float(abs_ret.sum())
        top5_abs_share = float(abs_ret[order[:5]].sum() / abs_total) if abs_total > 0 else 1.0
        coherence = float(abs(mean_ret) / max(mean_abs, 1e-12))
        volume_ratio = pd.to_numeric(valid["volume_ratio"], errors="coerce").to_numpy(float)
        finite_v = volume_ratio[np.isfinite(volume_ratio) & (volume_ratio > 0)]
        if len(finite_v):
            median_volume_ratio = float(np.median(finite_v))
            volume_shock_share = float(np.mean(finite_v >= 2.0))
            mask_high = np.isfinite(volume_ratio) & (volume_ratio >= 2.0)
            high_volume_signed_mean = float(np.mean(returns[mask_high])) if mask_high.any() else 0.0
        else:
            median_volume_ratio = 1.0
            volume_shock_share = 0.0
            high_volume_signed_mean = 0.0
        rows.append({
            "session_date": str(session_date),
            "timestamp": pd.Timestamp(timestamp),
            "constituent_count": int(len(returns)),
            "participation_ratio": float(len(returns) / len(universe)),
            "breadth_up": up,
            "breadth_down": down,
            "breadth_imbalance": up - down,
            "sign_entropy": _binary_entropy(up / max(up + down, 1e-12)),
            "constituent_mean_ret": mean_ret,
            "constituent_median_ret": median_ret,
            "mean_abs_ret": mean_abs,
            "dispersion_std": dispersion,
            "dispersion_mad": mad,
            "cross_section_spread": float(q90 - q10),
            "coherence": coherence,
            "top5_abs_share": top5_abs_share,
            "top5_symbols": top_symbols,
            "median_volume_ratio": median_volume_ratio,
            "volume_shock_share": volume_shock_share,
            "high_volume_signed_mean": high_volume_signed_mean,
        })
    cross = pd.DataFrame(rows)
    if cross.empty:
        raise ValueError("no cross-sectional rows passed constituent gate")

    idx = selected.loc[selected["symbol"].eq(INDEX_SYMBOL), ["session_date", "timestamp", "close", "log_ret1"]].copy()
    idx["session_date"] = idx["session_date"].astype(str)
    idx = idx.rename(columns={"close": "index_close", "log_ret1": "index_ret1"})
    cross = cross.merge(idx, on=["session_date", "timestamp"], how="inner", validate="one_to_one")
    cross["index_eqw_divergence"] = cross["index_ret1"] - cross["constituent_mean_ret"]
    cross["index_median_divergence"] = cross["index_ret1"] - cross["constituent_median_ret"]

    parts: list[pd.DataFrame] = []
    for session_date, g in cross.groupby("session_date", sort=True):
        x = g.sort_values("timestamp", kind="mergesort").reset_index(drop=True).copy()
        previous_top: tuple[str, ...] | None = None
        churn = []
        for top in x["top5_symbols"]:
            current = set(top)
            if previous_top is None:
                churn.append(np.nan)
            else:
                prev = set(previous_top)
                union = current | prev
                churn.append(1.0 - (len(current & prev) / len(union) if union else 1.0))
            previous_top = top
        x["leader_churn"] = churn
        for feature, prefix in (
            ("breadth_imbalance", "breadth"),
            ("dispersion_std", "dispersion"),
            ("top5_abs_share", "concentration"),
            ("index_eqw_divergence", "divergence"),
        ):
            x[f"{prefix}_delta1"] = x[feature].diff(1)
            x[f"{prefix}_delta3"] = x[feature] - x[feature].shift(3)
            short = x[feature].rolling(3, min_periods=3).mean()
            long = x[feature].rolling(6, min_periods=6).mean()
            x[f"{prefix}_gap_3_6"] = short - long
        x["index_ret3"] = x["index_ret1"].rolling(3, min_periods=3).sum()
        x["index_ret6"] = x["index_ret1"].rolling(6, min_periods=6).sum()
        x["index_vol6"] = x["index_ret1"].rolling(6, min_periods=4).std(ddof=0)
        first_ts = x["timestamp"].iloc[0]
        last_ts = x["timestamp"].iloc[-1]
        duration = max(1.0, (last_ts - first_ts).total_seconds())
        x["session_progress"] = (x["timestamp"] - first_ts).dt.total_seconds() / duration
        parts.append(x)
    result = pd.concat(parts, ignore_index=True).sort_values(["session_date", "timestamp"], kind="mergesort")
    return result.reset_index(drop=True)


def split_name_for_date(session_date: str, splits: Mapping[str, Sequence[str]]) -> str:
    for name, values in splits.items():
        if session_date in set(map(str, values)):
            return name
    return "excluded"


def add_split_column(frame: pd.DataFrame, splits: Mapping[str, Sequence[str]]) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    for name, dates in splits.items():
        mapping.update({str(d): name for d in dates})
    out = frame.copy()
    out["split"] = out["session_date"].astype(str).map(mapping).fillna("excluded")
    return out
