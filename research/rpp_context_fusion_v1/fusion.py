from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

from research.reversal_probability_profile_v2 import (
    RPPV2Config,
    attach_forward_outcomes,
    build_causal_location_map,
    build_confirmed_events,
    label_zone_interactions,
    load_nifty_ohlc,
)

IST = "Asia/Kolkata"
CAMPAIGN_ID = "RPP_CONTEXT_FUSION_V1"
SPEC_VERSION = "1.0.0"
EXPECTED_INPUT_SHA256 = "ae9645a83cb555899145e04ebe5a961fd130df25cba88a8fc8fd43b986bbfad0"
GOVERNED_SPECIAL_SESSIONS = {
    "2024-01-20",
    "2024-03-02",
    "2024-05-18",
    "2024-11-01",
    "2025-02-01",
}


@dataclass(frozen=True)
class FusionConfig:
    """Frozen, non-optimized context filter layered on causal RPP V2 events.

    The filter is deliberately small. It does not search thresholds or event
    subtypes. RPP supplies location/interaction; independent same-time market
    context decides whether that interaction is directionally supported.
    """

    context_lookback_minutes: int = 5
    breadth_abs_min: float = 0.40
    minimum_constituent_count: int = 40
    minimum_exact_return_coverage: float = 0.80
    require_breadth_alignment: bool = True
    require_index_momentum_alignment: bool = True

    round_trip_cost_bps: float = 5.0
    reserve_tail_sessions: int = 63
    warmup_sessions: int = 126
    test_sessions: int = 63
    step_sessions: int = 63

    min_oos_folds: int = 3
    min_oos_events: int = 90
    min_oos_sessions: int = 45
    min_positive_fold_fraction: float = 0.60
    min_hit_rate: float = 0.52
    max_single_fold_positive_profit_share: float = 0.65
    min_uplift_vs_parent_rpp_bps: float = 0.50
    lagged_context_minutes: int = 30
    min_lagged_control_events: int = 45
    min_uplift_vs_lagged_context_bps: float = 0.50

    bootstrap_repetitions: int = 2000
    bootstrap_seed: int = 20260906

    # RPP V2 remains structurally frozen. Only the cost proxy is synchronized.
    rpp: RPPV2Config = field(default_factory=RPPV2Config)

    def rpp_config(self) -> RPPV2Config:
        return replace(
            self.rpp,
            round_trip_cost_bps=self.round_trip_cost_bps,
            reserve_tail_sessions=self.reserve_tail_sessions,
            warmup_sessions=self.warmup_sessions,
            test_sessions=self.test_sessions,
            step_sessions=self.step_sessions,
        )

    def digest(self) -> str:
        raw = asdict(self)
        raw["rpp"] = asdict(self.rpp_config())
        return hashlib.sha256(json.dumps(raw, sort_keys=True).encode("utf-8")).hexdigest()


def sha256_path(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    if p.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(p)
    raise ValueError(f"unsupported_table_format:{p.suffix}")


def _canonical_ts(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.isna().any():
        raise ValueError("timestamp_parse_failure")
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize(IST)
    else:
        ts = ts.dt.tz_convert(IST)
    return ts


def _truthy(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    return series.fillna(False).astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def load_governed_panel(path: str | Path) -> pd.DataFrame:
    """Load the physical long panel and fail closed on synthetic/mock/fallback rows."""
    raw = _read_table(path).copy()
    lower = {str(c).lower(): c for c in raw.columns}
    ts_col = next((lower[k] for k in ("timestamp", "datetime", "ts") if k in lower), None)
    symbol_col = lower.get("symbol") or lower.get("instrument")
    close_col = lower.get("close")
    if ts_col is None or symbol_col is None or close_col is None:
        raise ValueError("panel_requires_timestamp_symbol_close")

    for flag in ("synthetic", "mock", "fallback"):
        col = lower.get(flag)
        if col is not None and _truthy(raw[col]).any():
            raise ValueError(f"governed_panel_contains_{flag}_rows")

    out = pd.DataFrame(
        {
            "timestamp": _canonical_ts(raw[ts_col]),
            "symbol": raw[symbol_col].astype(str).str.upper().str.strip(),
            "close": pd.to_numeric(raw[close_col], errors="coerce"),
        }
    ).dropna()
    out = out[out["close"] > 0].copy()
    hhmm = out["timestamp"].dt.strftime("%H:%M")
    out = out[(hhmm >= "09:15") & (hhmm <= "15:30")].copy()
    out["session"] = out["timestamp"].dt.date
    out = out[~out["session"].astype(str).isin(GOVERNED_SPECIAL_SESSIONS)].copy()
    if out.duplicated(["timestamp", "symbol"]).any():
        raise ValueError("duplicate_timestamp_symbol_rows")
    return out.sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _exact_return(group: pd.DataFrame, lookback_minutes: int) -> pd.Series:
    g = group.sort_values("timestamp")
    lag_close = g["close"].shift(1)
    lag_ts = g["timestamp"].shift(1)
    # The physical campaign is 5-minute. For a different requested lookback,
    # use an exact self-merge path rather than silently treating minutes as bars.
    if lookback_minutes != 5:
        lag = g[["timestamp", "close"]].copy()
        lag["timestamp"] = lag["timestamp"] + pd.Timedelta(minutes=lookback_minutes)
        lag = lag.rename(columns={"close": "lag_close"})
        m = g[["timestamp", "close"]].merge(lag, on="timestamp", how="left")
        ret = np.log(m["close"] / m["lag_close"])
        ret.index = g.index
        return ret
    exact = (g["timestamp"] - lag_ts) == pd.Timedelta(minutes=5)
    ret = np.log(g["close"] / lag_close).where(exact)
    ret.index = g.index
    return ret


def build_constituent_context(panel: pd.DataFrame, prices: pd.DataFrame, cfg: FusionConfig) -> pd.DataFrame:
    """Build exact-clock, same-session unweighted breadth with no future data."""
    p = panel.copy()
    nifty_mask = p["symbol"].eq("NIFTY")
    constituents = p.loc[~nifty_mask].copy()
    if constituents.empty:
        raise ValueError("no_constituent_rows")

    constituents["ret"] = constituents.groupby(["session", "symbol"], group_keys=False).apply(
        lambda g: _exact_return(g, cfg.context_lookback_minutes),
        include_groups=False,
    ).reset_index(level=[0, 1], drop=True)

    current_count = constituents.groupby("timestamp")["symbol"].nunique().rename("constituent_count")
    valid = constituents.dropna(subset=["ret"]).copy()
    agg = valid.groupby("timestamp").agg(
        exact_return_count=("symbol", "nunique"),
        breadth=("ret", lambda s: float(np.sign(s).mean())),
        constituent_median_return_bps=("ret", lambda s: float(np.median(s) * 10000.0)),
        constituent_dispersion_bps=("ret", lambda s: float(np.std(s, ddof=0) * 10000.0)),
    )
    context = current_count.to_frame().join(agg, how="left").reset_index()
    context["exact_return_count"] = context["exact_return_count"].fillna(0).astype(int)
    context["exact_return_coverage"] = context["exact_return_count"] / context["constituent_count"].clip(lower=1)

    # Exact-clock NIFTY momentum is independent directional context. It is not
    # sourced from the RPP state machine's approach-momentum field.
    n = prices[["timestamp", "session", "close"]].copy().sort_values("timestamp")
    n["lag_ts"] = n.groupby("session")["timestamp"].shift(1)
    n["lag_close"] = n.groupby("session")["close"].shift(1)
    if cfg.context_lookback_minutes == 5:
        exact = (n["timestamp"] - n["lag_ts"]) == pd.Timedelta(minutes=5)
        n["nifty_context_return_bps"] = np.log(n["close"] / n["lag_close"]).where(exact) * 10000.0
    else:
        lag = n[["timestamp", "session", "close"]].copy()
        lag["timestamp"] = lag["timestamp"] + pd.Timedelta(minutes=cfg.context_lookback_minutes)
        lag = lag.rename(columns={"close": "lag_exact_close"})
        n = n.merge(lag[["timestamp", "session", "lag_exact_close"]], on=["timestamp", "session"], how="left")
        n["nifty_context_return_bps"] = np.log(n["close"] / n["lag_exact_close"]) * 10000.0

    context = context.merge(n[["timestamp", "session", "nifty_context_return_bps"]], on="timestamp", how="left")
    return context.sort_values("timestamp").reset_index(drop=True)


def _alignment_mask(df: pd.DataFrame, cfg: FusionConfig, prefix: str = "") -> pd.Series:
    breadth = df[f"{prefix}breadth"]
    count = df[f"{prefix}constituent_count"]
    coverage = df[f"{prefix}exact_return_coverage"]
    nifty_ret = df[f"{prefix}nifty_context_return_bps"]
    signal = df["signal"]

    mask = count.ge(cfg.minimum_constituent_count)
    mask &= coverage.ge(cfg.minimum_exact_return_coverage)
    mask &= breadth.abs().ge(cfg.breadth_abs_min)
    if cfg.require_breadth_alignment:
        mask &= np.sign(breadth).eq(signal)
    if cfg.require_index_momentum_alignment:
        mask &= np.sign(nifty_ret).eq(signal)
    return mask.fillna(False)


def enrich_events_with_context(events: pd.DataFrame, context: pd.DataFrame, cfg: FusionConfig) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    base = events.merge(context, on=["timestamp", "session"], how="left", validate="many_to_one")
    base["fusion_eligible"] = _alignment_mask(base, cfg)

    # Negative control: use context known 30 minutes earlier. This preserves
    # causality while deliberately destroying contemporaneous alignment.
    lagged = context.copy()
    lagged["timestamp"] = lagged["timestamp"] + pd.Timedelta(minutes=cfg.lagged_context_minutes)
    rename = {
        c: f"lagged_{c}"
        for c in (
            "constituent_count",
            "exact_return_count",
            "breadth",
            "constituent_median_return_bps",
            "constituent_dispersion_bps",
            "exact_return_coverage",
            "nifty_context_return_bps",
        )
    }
    lagged = lagged.rename(columns=rename)
    base = base.merge(
        lagged[["timestamp", "session", *rename.values()]],
        on=["timestamp", "session"],
        how="left",
        validate="many_to_one",
    )
    base["lagged_context_control_eligible"] = _alignment_mask(base, cfg, prefix="lagged_")
    return base


def _session_bootstrap_ci(events: pd.DataFrame, metric: str, cfg: FusionConfig) -> tuple[float, float]:
    means = events.groupby("session")[metric].mean().dropna().to_numpy(float)
    if len(means) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(cfg.bootstrap_seed)
    samples = rng.choice(means, size=(cfg.bootstrap_repetitions, len(means)), replace=True).mean(axis=1)
    lo, hi = np.quantile(samples, [0.025, 0.975])
    return float(lo), float(hi)


def _assign_oos_folds(df: pd.DataFrame, usable_sessions: list, cfg: FusionConfig) -> tuple[pd.DataFrame, list[dict]]:
    parts: list[pd.DataFrame] = []
    folds: list[dict] = []
    start = cfg.warmup_sessions
    fold_id = 0
    while start + cfg.test_sessions <= len(usable_sessions):
        test_sessions = usable_sessions[start : start + cfg.test_sessions]
        test = set(test_sessions)
        part = df[df["session"].isin(test)].copy() if not df.empty else pd.DataFrame()
        if not part.empty:
            part["fold_id"] = fold_id
            parts.append(part)
        folds.append(
            {
                "fold_id": fold_id,
                "test_start": str(test_sessions[0]),
                "test_end": str(test_sessions[-1]),
                "events": int(len(part)),
                "sessions_with_events": int(part["session"].nunique()) if not part.empty else 0,
            }
        )
        fold_id += 1
        start += cfg.step_sessions
    return (pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(), folds)


def evaluate_fusion(enriched_outcomes: pd.DataFrame, usable_sessions: list, cfg: FusionConfig) -> dict:
    primary = cfg.rpp_config().primary_horizon_minutes
    net_col = f"signed_{primary}m_net_bps"
    gross_col = f"signed_{primary}m_gross_bps"

    parent_oos, fold_geometry = _assign_oos_folds(enriched_outcomes, usable_sessions, cfg)
    if parent_oos.empty:
        return {"verdict": "NO_OOS_EVENTS", "blockers": ["NO_OOS_EVENTS"], "folds": fold_geometry}

    fused = parent_oos[parent_oos["fusion_eligible"]].copy()
    lagged = parent_oos[parent_oos["lagged_context_control_eligible"]].copy()
    if fused.empty:
        return {
            "verdict": "NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE",
            "blockers": ["NO_FUSED_OOS_EVENTS"],
            "parent_rpp_oos_events": int(len(parent_oos)),
            "folds": fold_geometry,
        }

    ci_low, ci_high = _session_bootstrap_ci(fused, net_col, cfg)
    fold_means = fused.groupby("fold_id")[net_col].mean()
    positive_fold_fraction = float((fold_means > 0).mean()) if len(fold_means) else 0.0
    positive_pnl = fused.groupby("fold_id")[net_col].sum().clip(lower=0)
    positive_total = float(positive_pnl.sum())
    max_profit_share = float(positive_pnl.max() / positive_total) if positive_total > 0 else 1.0

    mean_net = float(fused[net_col].mean())
    mean_gross = float(fused[gross_col].mean())
    hit_rate = float((fused[gross_col] > 0).mean())
    parent_mean = float(parent_oos[net_col].mean())
    uplift_parent = mean_net - parent_mean
    lagged_mean = float(lagged[net_col].mean()) if len(lagged) else np.nan
    uplift_lagged = mean_net - lagged_mean if np.isfinite(lagged_mean) else np.nan

    blockers: list[str] = []
    if len(fold_means) < cfg.min_oos_folds:
        blockers.append("INSUFFICIENT_OOS_FOLDS")
    if len(fused) < cfg.min_oos_events:
        blockers.append("INSUFFICIENT_OOS_EVENTS")
    if fused["session"].nunique() < cfg.min_oos_sessions:
        blockers.append("INSUFFICIENT_OOS_SESSIONS")
    if not np.isfinite(ci_low) or ci_low <= 0:
        blockers.append("SESSION_BOOTSTRAP_CI_NOT_POSITIVE")
    if positive_fold_fraction < cfg.min_positive_fold_fraction:
        blockers.append("FOLD_STABILITY_FAIL")
    if hit_rate < cfg.min_hit_rate:
        blockers.append("HIT_RATE_FAIL")
    if max_profit_share > cfg.max_single_fold_positive_profit_share:
        blockers.append("FOLD_PROFIT_CONCENTRATION_FAIL")
    if mean_net <= 0:
        blockers.append("MEAN_AFTER_COST_PROXY_NOT_POSITIVE")
    if uplift_parent < cfg.min_uplift_vs_parent_rpp_bps:
        blockers.append("NO_MATERIAL_UPLIFT_VS_PARENT_RPP")
    if len(lagged) < cfg.min_lagged_control_events:
        blockers.append("INSUFFICIENT_LAGGED_CONTEXT_CONTROL_EVENTS")
    elif not np.isfinite(uplift_lagged) or uplift_lagged < cfg.min_uplift_vs_lagged_context_bps:
        blockers.append("NO_MATERIAL_UPLIFT_VS_LAGGED_CONTEXT_CONTROL")

    by_state = {}
    for state, g in fused.groupby("event_type"):
        by_state[str(state)] = {
            "events": int(len(g)),
            "sessions": int(g["session"].nunique()),
            "mean_gross_bps": float(g[gross_col].mean()),
            "mean_net_bps": float(g[net_col].mean()),
            "gross_hit_rate": float((g[gross_col] > 0).mean()),
            "mean_breadth": float(g["breadth"].mean()),
        }

    folds = []
    for item in fold_geometry:
        fid = item["fold_id"]
        fg = fused[fused["fold_id"] == fid]
        pg = parent_oos[parent_oos["fold_id"] == fid]
        row = dict(item)
        row.update(
            {
                "fused_events": int(len(fg)),
                "fused_mean_net_bps": float(fg[net_col].mean()) if len(fg) else None,
                "fused_hit_rate": float((fg[gross_col] > 0).mean()) if len(fg) else None,
                "parent_rpp_mean_net_bps": float(pg[net_col].mean()) if len(pg) else None,
            }
        )
        folds.append(row)

    return {
        "verdict": "ROBUST_DIRECTIONAL_EDGE_AFTER_COST_PROXY" if not blockers else "NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE",
        "blockers": blockers,
        "oos_folds": int(len(fold_means)),
        "parent_rpp_oos_events": int(len(parent_oos)),
        "fused_oos_events": int(len(fused)),
        "fused_oos_sessions": int(fused["session"].nunique()),
        "fused_selection_rate": float(len(fused) / len(parent_oos)),
        "mean_gross_bps": mean_gross,
        "mean_net_bps": mean_net,
        "gross_hit_rate": hit_rate,
        "session_bootstrap_95_ci_net_bps": [ci_low, ci_high],
        "positive_fold_fraction": positive_fold_fraction,
        "max_single_fold_positive_profit_share": max_profit_share,
        "parent_rpp_mean_net_bps": parent_mean,
        "uplift_bps_vs_parent_rpp": uplift_parent,
        "lagged_context_control_events": int(len(lagged)),
        "lagged_context_control_mean_net_bps": None if not np.isfinite(lagged_mean) else lagged_mean,
        "uplift_bps_vs_lagged_context_control": None if not np.isfinite(uplift_lagged) else uplift_lagged,
        "event_type_diagnostics": by_state,
        "folds": folds,
    }


def run_experiment(input_path: str | Path, output_dir: str | Path, cfg: FusionConfig = FusionConfig()) -> dict:
    input_sha = sha256_path(input_path)
    if input_sha != EXPECTED_INPUT_SHA256:
        raise ValueError(f"input_sha256_mismatch:{input_sha}")

    panel_all = load_governed_panel(input_path)
    prices_all = load_nifty_ohlc(input_path)
    prices_all = prices_all[~prices_all["session"].astype(str).isin(GOVERNED_SPECIAL_SESSIONS)].copy()
    sessions_all = sorted(prices_all["session"].unique())
    if len(sessions_all) <= cfg.reserve_tail_sessions + cfg.warmup_sessions + cfg.test_sessions:
        raise ValueError("insufficient_sessions_for_frozen_fusion_evaluation")

    # Seal before ANY RPP feature, breadth, momentum, or outcome construction.
    usable_sessions = sessions_all[:-cfg.reserve_tail_sessions]
    sealed_sessions = sessions_all[-cfg.reserve_tail_sessions:]
    usable = set(usable_sessions)
    prices = prices_all[prices_all["session"].isin(usable)].copy().reset_index(drop=True)
    panel = panel_all[panel_all["session"].isin(usable)].copy().reset_index(drop=True)

    rpp_cfg = cfg.rpp_config()
    location = build_causal_location_map(prices, rpp_cfg)
    states = label_zone_interactions(location, rpp_cfg)
    parent_events = build_confirmed_events(states, rpp_cfg)
    parent_outcomes = attach_forward_outcomes(parent_events, prices, rpp_cfg)

    context = build_constituent_context(panel, prices, cfg)
    enriched = enrich_events_with_context(parent_outcomes, context, cfg)
    evaluation = evaluate_fusion(enriched, usable_sessions, cfg)

    report = {
        "campaign_id": CAMPAIGN_ID,
        "spec_version": SPEC_VERSION,
        "config_sha256": cfg.digest(),
        "input_path": str(Path(input_path)),
        "input_sha256": input_sha,
        "governed_special_sessions": sorted(GOVERNED_SPECIAL_SESSIONS),
        "all_regular_sessions_count": int(len(sessions_all)),
        "usable_sessions_count": int(len(usable_sessions)),
        "sealed_tail_sessions_count": int(len(sealed_sessions)),
        "sealed_tail_start": str(sealed_sessions[0]),
        "sealed_tail_end": str(sealed_sessions[-1]),
        "sealed_tail_rpp_feature_rows_processed": 0,
        "sealed_tail_context_rows_processed": 0,
        "sealed_tail_outcomes_processed": 0,
        "parent_rpp_confirmed_events": int(len(parent_events)),
        "parent_rpp_outcomes": int(len(parent_outcomes)),
        "context_rows": int(len(context)),
        "parameter_search_performed": False,
        "event_subtype_selected_after_outcomes": False,
        "relative_density_is_calibrated_probability": False,
        "context_uses_future_bars": False,
        "official_constituent_weights_claimed": False,
        "holdout_evaluated": False,
        "option_pnl_claimed": False,
        "live_or_broker_authority": False,
        **evaluation,
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    context.to_csv(out / "constituent_context.csv", index=False)
    enriched.to_csv(out / "rpp_events_with_context.csv", index=False)
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return report
