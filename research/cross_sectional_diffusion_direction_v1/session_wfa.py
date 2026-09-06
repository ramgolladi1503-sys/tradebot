from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

import numpy as np
import pandas as pd

from .campaign import (
    _choose_train_candidate,
    _fold_profit_concentration,
    _lagged_control,
    fit_index_only_baseline,
    score_index_only_baseline,
    score_signals,
    session_bootstrap_ci,
)


@dataclass(frozen=True)
class SessionCampaignConfig:
    lookback_minutes: int = 5
    primary_horizon_minutes: int = 15
    secondary_horizon_minutes: int = 30
    train_sessions: int = 252
    test_sessions: int = 63
    step_sessions: int = 63
    min_oos_folds: int = 4
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

    def digest(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def session_windows(
    frame: pd.DataFrame,
    train_sessions: int,
    test_sessions: int,
    step_sessions: int,
) -> list[tuple[list[object], list[object]]]:
    if min(train_sessions, test_sessions, step_sessions) <= 0:
        raise ValueError("session_window_sizes_must_be_positive")
    sessions = sorted(pd.Series(frame["session"]).dropna().unique().tolist())
    final_start = len(sessions) - train_sessions - test_sessions
    if final_start < 0:
        return []
    windows: list[tuple[list[object], list[object]]] = []
    for start in range(0, final_start + 1, step_sessions):
        train = sessions[start : start + train_sessions]
        test = sessions[start + train_sessions : start + train_sessions + test_sessions]
        windows.append((train, test))
    return windows


def run_session_walk_forward(
    features_with_returns: pd.DataFrame,
    *,
    horizon: int,
    cost_bps: float,
    cfg: SessionCampaignConfig,
) -> dict:
    frame = features_with_returns.copy()
    windows = session_windows(frame, cfg.train_sessions, cfg.test_sessions, cfg.step_sessions)
    if not windows:
        return {
            "status": "INSUFFICIENT_SESSIONS",
            "horizon": horizon,
            "folds": [],
            "events": pd.DataFrame(),
            "controls": pd.DataFrame(),
            "baselines": pd.DataFrame(),
        }

    event_frames: list[pd.DataFrame] = []
    control_frames: list[pd.DataFrame] = []
    baseline_frames: list[pd.DataFrame] = []
    folds: list[dict] = []

    for fold_id, (train_sessions, test_sessions) in enumerate(windows, start=1):
        train = frame[frame["session"].isin(train_sessions)].copy()
        test = frame[frame["session"].isin(test_sessions)].copy()
        thresholds, candidates = _choose_train_candidate(train, horizon, cost_bps, cfg)
        baseline_long, baseline_short, train_long_rate, train_short_rate = fit_index_only_baseline(train, thresholds)

        events = score_signals(test, thresholds, horizon, cost_bps)
        events["fold_id"] = fold_id
        control = score_signals(
            _lagged_control(test, cfg.negative_control_lag_minutes),
            thresholds,
            horizon,
            cost_bps,
        )
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
        folds.append(
            {
                "fold_id": fold_id,
                "train_session_start": str(train_sessions[0]),
                "train_session_end": str(train_sessions[-1]),
                "train_session_count": len(train_sessions),
                "test_session_start": str(test_sessions[0]),
                "test_session_end": str(test_sessions[-1]),
                "test_session_count": len(test_sessions),
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
            }
        )

    events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    controls = pd.concat(control_frames, ignore_index=True) if control_frames else pd.DataFrame()
    baselines = pd.concat(baseline_frames, ignore_index=True) if baseline_frames else pd.DataFrame()
    ci = session_bootstrap_ci(events, "net_bps", cfg.bootstrap_repetitions, cfg.bootstrap_seed)
    control_ci = session_bootstrap_ci(controls, "net_bps", cfg.bootstrap_repetitions, cfg.bootstrap_seed + 1)
    baseline_ci = session_bootstrap_ci(baselines, "net_bps", cfg.bootstrap_repetitions, cfg.bootstrap_seed + 2)
    fold_means = [f["oos_session_equal_net_bps"] for f in folds if f["oos_session_equal_net_bps"] is not None]
    positive_fold_fraction = float(np.mean(np.asarray(fold_means) > 0)) if fold_means else 0.0

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
        "max_single_fold_profit_share": _fold_profit_concentration(events),
    }


def assess_session_terminal_verdict(
    result: dict,
    *,
    cfg: SessionCampaignConfig,
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
    if len(result.get("folds", [])) < cfg.min_oos_folds:
        blockers.append("INSUFFICIENT_OOS_FOLDS")
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

    main_est = ci.get("estimate")
    control_est = result.get("lagged_control_bootstrap", {}).get("estimate")
    baseline_est = result.get("index_only_baseline_bootstrap", {}).get("estimate")
    if main_est is None:
        blockers.append("MAIN_EFFECT_UNAVAILABLE")
    elif control_est is not None and float(control_est) >= 0.5 * float(main_est):
        blockers.append("LAGGED_CONTROL_RETAINS_TOO_MUCH_EFFECT")
    if main_est is not None and baseline_est is not None and float(main_est) <= float(baseline_est):
        blockers.append("NO_INCREMENTAL_VALUE_OVER_INDEX_MOMENTUM")

    if blockers:
        return "NO_ROBUST_AFTER_COST_DIRECTIONAL_EDGE", blockers
    return "ROBUST_DIRECTIONAL_EDGE_AFTER_COST_PROXY", []
