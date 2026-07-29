#!/usr/bin/env python3
"""Underlying auction and option-response efficiency discovery V1.

This campaign adds an independent causal anchor that prior option-only campaigns lacked:
completed one-minute NIFTY auction behaviour. It joins manifest-approved, hash-verified
underlying candles to the preserved option event universe and tests eight frozen mechanisms.

Chronology:
- earliest 70% sessions: five expanding OOF folds;
- middle 15% sessions: validation for at most one frozen OOF survivor;
- latest 15% sessions: sealed master holdout, never read here.

Research only. No broker, order, paper, live, registry or production action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts import run_cross_strike_diffusion_discovery_v1 as metrics_mod
from scripts import run_cross_strike_diffusion_campaign_v2 as splitmod
from scripts import run_selective_option_leadership_campaign_v3 as leadership_mod
from scripts import run_option_surface_transition_discovery_v1 as surface_mod
from scripts import run_peer_reclaim_horizon_campaign_v5 as horizon_mod
from scripts import run_peer_reclaim_horizon_campaign_v5_1 as fixed_delay
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/underlying_auction_option_response_v1")
RESEARCH_REL = Path("research/underlying_auction_option_response_v1")
EVENT_FILE = "event_universe_5m.parquet"
SELECTED_MANIFEST_REL = Path(
    "research/local_evidence_consolidation_v1/worktrees/"
    "underlying-option-sequence-discovery-v1/research/"
    "unified_nifty_underlying_feature_warehouse_v1/selected_source_manifest.json"
)
EXIT_HORIZON_MINUTES = 10
MIN_OOF_TRADES = 80
MIN_OOF_SESSIONS = 60
MIN_VALIDATION_TRADES = 20
MIN_VALIDATION_SESSIONS = 15
MAX_SIGNALS_PER_SESSION = 2
MIN_SIGNAL_SEPARATION_MINUTES = 15
CUMULATIVE_MECHANISM_COUNT = 55
SEED = 20260729

MECHANISMS = (
    "accepted_up_displacement_ce",
    "accepted_down_displacement_pe",
    "failed_up_auction_pe",
    "failed_down_auction_ce",
    "second_up_push_efficiency_gain_ce",
    "second_down_push_efficiency_gain_pe",
    "compression_directional_release",
    "underlying_pause_option_lead",
)


def semantic_hash(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(body).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = _finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def _is_lfs_pointer(path: Path) -> bool:
    if not path.is_file():
        return True
    with path.open("rb") as handle:
        return handle.read(100).startswith(b"version https://git-lfs.github.com/spec")


def load_selected_manifest(root: Path) -> dict[str, Any]:
    path = root / SELECTED_MANIFEST_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("selected_count", 0)) < 390:
        raise RuntimeError("Selected NIFTY source manifest is unexpectedly small.")
    return payload


def discover_underlying_sources(root: Path, manifest: dict[str, Any]) -> tuple[list[Path], list[dict[str, Any]]]:
    expected = {
        str(row["sha256"]): {
            "date": str(row["date"]),
            "rows_in_target": int(row["rows_in_target"]),
            "source_path": str(row["path"]),
        }
        for row in manifest["selected_files"]
    }
    candidates = sorted(root.rglob("NIFTY_*.parquet"))
    matches: dict[str, list[Path]] = {}
    inspected: list[dict[str, Any]] = []
    for path in candidates:
        relative = str(path.relative_to(root))
        pointer = _is_lfs_pointer(path)
        record: dict[str, Any] = {
            "path": relative,
            "bytes": path.stat().st_size if path.exists() else 0,
            "lfs_pointer": pointer,
        }
        if not pointer:
            digest = sha256_file(path)
            record["sha256"] = digest
            if digest in expected:
                matches.setdefault(digest, []).append(path)
        inspected.append(record)
    missing = sorted(set(expected) - set(matches))
    if missing:
        raise RuntimeError(
            f"Missing {len(missing)} manifest-approved NIFTY parquet hashes after LFS materialization."
        )
    selected = [sorted(matches[digest], key=lambda item: str(item))[0] for digest in sorted(expected)]
    inventory = []
    for digest, path in zip(sorted(expected), selected):
        inventory.append(
            {
                **expected[digest],
                "selected_repository_path": str(path.relative_to(root)),
                "sha256": digest,
                "duplicate_repository_matches": len(matches[digest]),
                "bytes": path.stat().st_size,
            }
        )
    return selected, inventory


def _find_column(columns: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        if name in columns:
            return columns[name]
    raise RuntimeError(f"Required column missing. Tried: {names}")


def _normalize_timestamp(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="raise")
    if getattr(parsed.dt, "tz", None) is None:
        parsed = parsed.dt.tz_localize(
            "Asia/Kolkata", ambiguous="raise", nonexistent="raise"
        )
    return parsed.dt.tz_convert("UTC")


def load_underlying(paths: list[Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        raw = pd.read_parquet(path)
        normalized = {str(column).strip().lower(): str(column) for column in raw.columns}
        timestamp_column = _find_column(
            normalized, ("timestamp", "ts", "datetime", "date_time", "candle_time")
        )
        open_column = _find_column(normalized, ("open", "open_price"))
        high_column = _find_column(normalized, ("high", "high_price"))
        low_column = _find_column(normalized, ("low", "low_price"))
        close_column = _find_column(normalized, ("close", "close_price"))
        frame = pd.DataFrame(
            {
                "timestamp": _normalize_timestamp(raw[timestamp_column]),
                "u_open": _finite(raw[open_column]),
                "u_high": _finite(raw[high_column]),
                "u_low": _finite(raw[low_column]),
                "u_close": _finite(raw[close_column]),
            }
        )
        local = frame["timestamp"].dt.tz_convert("Asia/Kolkata")
        frame["session_id"] = local.dt.date.astype(str)
        frame["minute_of_day"] = local.dt.hour * 60 + local.dt.minute
        frame = frame.loc[frame["minute_of_day"].between(555, 930, inclusive="both")]
        frames.append(frame)
    underlying = pd.concat(frames, ignore_index=True, sort=False)
    underlying = underlying.dropna(subset=["timestamp", "u_open", "u_high", "u_low", "u_close"])
    underlying = underlying.sort_values(["session_id", "timestamp"], kind="mergesort")
    underlying = underlying.drop_duplicates(["session_id", "timestamp"], keep="first")
    invalid = (
        (underlying["u_high"] < underlying[["u_open", "u_close"]].max(axis=1))
        | (underlying["u_low"] > underlying[["u_open", "u_close"]].min(axis=1))
        | (underlying[["u_open", "u_high", "u_low", "u_close"]] <= 0).any(axis=1)
    )
    if invalid.any():
        raise RuntimeError(f"Underlying OHLC integrity failed for {int(invalid.sum())} rows.")
    return underlying.reset_index(drop=True)


def build_underlying_features(underlying: pd.DataFrame) -> pd.DataFrame:
    frame = underlying.copy()
    grouped = frame.groupby("session_id", sort=False, observed=True)
    frame["u_prev_close"] = grouped["u_close"].shift(1)
    frame["u_prev_open"] = grouped["u_open"].shift(1)
    frame["u_prev_high"] = grouped["u_high"].shift(1)
    frame["u_prev_low"] = grouped["u_low"].shift(1)
    frame["u_ret_1m_pct"] = (frame["u_close"] / frame["u_prev_close"] - 1.0) * 100.0
    frame["u_ret_3m_pct"] = (frame["u_close"] / grouped["u_close"].shift(3) - 1.0) * 100.0
    frame["u_ret_5m_pct"] = (frame["u_close"] / grouped["u_close"].shift(5) - 1.0) * 100.0
    frame["u_prev_ret_3m_pct"] = grouped["u_ret_3m_pct"].shift(3)
    frame["u_prev_ret_5m_pct"] = grouped["u_ret_5m_pct"].shift(1)
    frame["u_range_pct"] = (
        (frame["u_high"] - frame["u_low"]) / frame["u_prev_close"].replace(0, np.nan) * 100.0
    )
    frame["u_body_pct"] = (
        (frame["u_close"] - frame["u_open"]) / frame["u_open"].replace(0, np.nan) * 100.0
    )
    bar_range = (frame["u_high"] - frame["u_low"]).replace(0, np.nan)
    frame["u_close_location"] = (frame["u_close"] - frame["u_low"]) / bar_range
    overlap = (
        np.minimum(frame["u_high"], frame["u_prev_high"])
        - np.maximum(frame["u_low"], frame["u_prev_low"])
    ).clip(lower=0)
    denominator = np.minimum(
        frame["u_high"] - frame["u_low"],
        frame["u_prev_high"] - frame["u_prev_low"],
    ).replace(0, np.nan)
    frame["u_overlap_ratio"] = overlap / denominator
    frame["u_prior_high_10"] = grouped["u_high"].transform(
        lambda values: values.rolling(10, min_periods=5).max().shift(1)
    )
    frame["u_prior_low_10"] = grouped["u_low"].transform(
        lambda values: values.rolling(10, min_periods=5).min().shift(1)
    )
    rolling_high_5 = grouped["u_high"].transform(lambda values: values.rolling(5, min_periods=5).max())
    rolling_low_5 = grouped["u_low"].transform(lambda values: values.rolling(5, min_periods=5).min())
    rolling_high_15 = grouped["u_high"].transform(lambda values: values.rolling(15, min_periods=10).max())
    rolling_low_15 = grouped["u_low"].transform(lambda values: values.rolling(15, min_periods=10).min())
    frame["u_range_5m_pct"] = (rolling_high_5 - rolling_low_5) / frame["u_close"].replace(0, np.nan) * 100.0
    frame["u_range_15m_pct"] = (rolling_high_15 - rolling_low_15) / frame["u_close"].replace(0, np.nan) * 100.0
    frame["u_break_up"] = frame["u_close"] > frame["u_prior_high_10"]
    frame["u_break_down"] = frame["u_close"] < frame["u_prior_low_10"]
    frame["u_failed_up"] = (
        (frame["u_high"] > frame["u_prior_high_10"])
        & (frame["u_close"] < frame["u_prior_high_10"])
        & (frame["u_close_location"] < 0.50)
    )
    frame["u_failed_down"] = (
        (frame["u_low"] < frame["u_prior_low_10"])
        & (frame["u_close"] > frame["u_prior_low_10"])
        & (frame["u_close_location"] > 0.50)
    )
    absolute_moves = grouped["u_close"].transform(
        lambda values: values.diff().abs().rolling(5, min_periods=5).sum()
    )
    frame["u_efficiency_5"] = (
        (frame["u_close"] - grouped["u_close"].shift(5)).abs()
        / absolute_moves.replace(0, np.nan)
    )
    frame["u_accept_up"] = (
        frame["u_break_up"]
        & (frame["u_close_location"] >= 0.65)
        & (frame["u_overlap_ratio"] <= 0.55)
    )
    frame["u_accept_down"] = (
        frame["u_break_down"]
        & (frame["u_close_location"] <= 0.35)
        & (frame["u_overlap_ratio"] <= 0.55)
    )
    return frame


def prepare_option_causal(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=surface_mod.CAUSAL_COLUMNS)
    frame = surface_mod._surface_features(frame)
    frame = frame.loc[frame["minute_of_day"] >= 585].copy()
    return frame


def join_underlying_option(option: pd.DataFrame, underlying: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "timestamp", "session_id", "u_open", "u_high", "u_low", "u_close",
        "u_prev_close", "u_ret_1m_pct", "u_ret_3m_pct", "u_ret_5m_pct",
        "u_prev_ret_3m_pct", "u_prev_ret_5m_pct", "u_range_pct", "u_body_pct",
        "u_close_location", "u_overlap_ratio", "u_prior_high_10", "u_prior_low_10",
        "u_range_5m_pct", "u_range_15m_pct", "u_break_up", "u_break_down",
        "u_failed_up", "u_failed_down", "u_efficiency_5", "u_accept_up", "u_accept_down",
    ]
    joint = option.merge(
        underlying[keep], on=["timestamp", "session_id"], how="inner", validate="many_to_one"
    )
    side = np.where(joint["option_type"].eq("CE"), 1.0, -1.0)
    joint["directional_u_ret_1m_pct"] = joint["u_ret_1m_pct"] * side
    joint["directional_u_ret_3m_pct"] = joint["u_ret_3m_pct"] * side
    joint["directional_u_ret_5m_pct"] = joint["u_ret_5m_pct"] * side
    joint["previous_directional_u_ret_3m_pct"] = joint["u_prev_ret_3m_pct"] * side
    denominator = joint["directional_u_ret_5m_pct"].abs().clip(lower=0.005)
    previous_denominator = joint["u_prev_ret_5m_pct"].abs().clip(lower=0.005)
    joint["option_response_efficiency"] = joint["prior_5m_return_pct"] / denominator
    joint["previous_option_response_efficiency"] = joint["previous_return"] / previous_denominator
    joint["option_efficiency_delta"] = (
        joint["option_response_efficiency"] - joint["previous_option_response_efficiency"]
    )
    joint["directional_second_push"] = (
        (joint["directional_u_ret_3m_pct"] > 0)
        & (joint["previous_directional_u_ret_3m_pct"] > 0)
    )
    return joint


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    absolute_u_ret = _finite(training["u_ret_1m_pct"]).abs().dropna()
    return {
        "directional_u_ret_5_p65": _q(training, "directional_u_ret_5m_pct", 0.65),
        "directional_u_ret_5_p75": _q(training, "directional_u_ret_5m_pct", 0.75),
        "u_range_15_p30": _q(training, "u_range_15m_pct", 0.30),
        "u_range_5_p60": _q(training, "u_range_5m_pct", 0.60),
        "u_efficiency_p60": _q(training, "u_efficiency_5", 0.60),
        "option_return_p55": _q(training, "prior_5m_return_pct", 0.55),
        "option_accel_p60": _q(training, "return_acceleration", 0.60),
        "option_efficiency_p60": _q(training, "option_response_efficiency", 0.60),
        "option_efficiency_delta_p60": _q(training, "option_efficiency_delta", 0.60),
        "breadth_p55": _q(training, "breadth_positive", 0.55),
        "breadth_delta_p55": _q(training, "breadth_delta", 0.55),
        "volume_p55": _q(training, "prior_5m_volume_ratio", 0.55, 1.0),
        "u_abs_ret_1_p35": float(absolute_u_ret.quantile(0.35)) if not absolute_u_ret.empty else 0.0,
    }


def mechanism_masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    is_ce = frame["option_type"].eq("CE")
    is_pe = frame["option_type"].eq("PE")
    aligned_option = (
        (frame["prior_5m_return_pct"] >= cut["option_return_p55"])
        & (frame["option_response_efficiency"] >= cut["option_efficiency_p60"])
        & (frame["breadth_positive"] >= cut["breadth_p55"])
        & (frame["mirror_return"] <= 0)
    )
    return {
        "accepted_up_displacement_ce": (
            is_ce & frame["u_accept_up"].fillna(False)
            & (frame["directional_u_ret_5m_pct"] >= cut["directional_u_ret_5_p75"])
            & (frame["u_efficiency_5"] >= cut["u_efficiency_p60"]) & aligned_option
        ),
        "accepted_down_displacement_pe": (
            is_pe & frame["u_accept_down"].fillna(False)
            & (frame["directional_u_ret_5m_pct"] >= cut["directional_u_ret_5_p75"])
            & (frame["u_efficiency_5"] >= cut["u_efficiency_p60"]) & aligned_option
        ),
        "failed_up_auction_pe": (
            is_pe & frame["u_failed_up"].fillna(False)
            & (frame["return_acceleration"] >= cut["option_accel_p60"])
            & (frame["prior_5m_return_pct"] > 0) & (frame["mirror_return"] <= 0)
        ),
        "failed_down_auction_ce": (
            is_ce & frame["u_failed_down"].fillna(False)
            & (frame["return_acceleration"] >= cut["option_accel_p60"])
            & (frame["prior_5m_return_pct"] > 0) & (frame["mirror_return"] <= 0)
        ),
        "second_up_push_efficiency_gain_ce": (
            is_ce & frame["directional_second_push"].fillna(False)
            & (frame["directional_u_ret_5m_pct"] >= cut["directional_u_ret_5_p65"])
            & (frame["option_efficiency_delta"] >= cut["option_efficiency_delta_p60"])
            & aligned_option
        ),
        "second_down_push_efficiency_gain_pe": (
            is_pe & frame["directional_second_push"].fillna(False)
            & (frame["directional_u_ret_5m_pct"] >= cut["directional_u_ret_5_p65"])
            & (frame["option_efficiency_delta"] >= cut["option_efficiency_delta_p60"])
            & aligned_option
        ),
        "compression_directional_release": (
            (frame["u_range_15m_pct"] <= cut["u_range_15_p30"])
            & (frame["u_range_5m_pct"] >= cut["u_range_5_p60"])
            & (frame["directional_u_ret_5m_pct"] > 0)
            & (frame["return_acceleration"] >= cut["option_accel_p60"])
            & (frame["breadth_delta"] >= cut["breadth_delta_p55"])
            & (frame["mirror_return"] <= 0)
        ),
        "underlying_pause_option_lead": (
            (frame["u_ret_1m_pct"].abs() <= cut["u_abs_ret_1_p35"])
            & (frame["directional_u_ret_3m_pct"] >= 0)
            & (frame["prior_5m_return_pct"] >= cut["option_return_p55"])
            & (frame["return_acceleration"] >= cut["option_accel_p60"])
            & (frame["prior_5m_volume_ratio"] >= cut["volume_p55"])
            & (frame["mirror_return"] <= 0)
        ),
    }


def eligibility(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & frame["minute_of_day"].between(585, 875, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3) & (frame["volume"] > 0)
        & frame["u_prev_close"].notna() & frame["previous_return"].notna()
        & frame["mirror_return"].notna()
    )


def select_signals(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    candidates = frame.loc[mask & eligibility(frame) & frame["session_id"].isin(sessions)].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["premium_distance"] = (candidates["entry_price_next_open"] - 120.0).abs()
    candidates["auction_score"] = (
        candidates["directional_u_ret_5m_pct"].fillna(0)
        + candidates["u_efficiency_5"].fillna(0)
        + 0.25 * candidates["prior_5m_return_pct"].fillna(0)
        + 0.25 * candidates["return_acceleration"].fillna(0)
        + 0.50 * candidates["breadth_positive"].fillna(0)
        + 0.10 * candidates["option_efficiency_delta"].clip(-10, 10).fillna(0)
    )
    best = candidates.groupby(["session_id", "timestamp"], observed=True)["auction_score"].transform("max")
    candidates = candidates.loc[candidates["auction_score"].eq(best)]
    candidates = candidates.sort_values(
        ["session_id", "timestamp", "auction_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, True, False, True, True], kind="mergesort",
    ).drop_duplicates(["session_id", "timestamp"], keep="first")
    parts: list[pd.DataFrame] = []
    for _, group in candidates.groupby("session_id", sort=False, observed=True):
        selected: list[int] = []
        last_timestamp: pd.Timestamp | None = None
        for index, row in group.iterrows():
            timestamp = pd.Timestamp(row["timestamp"])
            if last_timestamp is not None:
                elapsed = (timestamp - last_timestamp).total_seconds() / 60.0
                if elapsed < MIN_SIGNAL_SEPARATION_MINUTES:
                    continue
            selected.append(index)
            last_timestamp = timestamp
            if len(selected) >= MAX_SIGNALS_PER_SESSION:
                break
        parts.append(group.loc[selected])
    return pd.concat(parts, ignore_index=False).sort_values(["session_id", "timestamp"], kind="mergesort") if parts else candidates.iloc[0:0]


def _mirror_lookup(frame: pd.DataFrame) -> pd.DataFrame:
    lookup = frame[[
        "session_id", "timestamp", "expiry_id", "strike", "option_type",
        "expired_instrument_key", "entry_price_next_open", "days_to_expiry", "minute_of_day",
    ]].copy()
    lookup = lookup.rename(columns={
        "option_type": "control_option_type",
        "expired_instrument_key": "control_expired_instrument_key",
        "entry_price_next_open": "control_entry_price_next_open",
        "days_to_expiry": "control_days_to_expiry",
        "minute_of_day": "control_minute_of_day",
    })
    return lookup.drop_duplicates(["session_id", "timestamp", "expiry_id", "strike", "control_option_type"])


def mirror_control_signals(signals: pd.DataFrame, frame: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    control = signals.copy()
    control["control_option_type"] = control["option_type"].map({"CE": "PE", "PE": "CE"})
    control = control.merge(
        _mirror_lookup(frame),
        on=["session_id", "timestamp", "expiry_id", "strike", "control_option_type"],
        how="inner", validate="many_to_one",
    )
    control = control.loc[control["control_entry_price_next_open"].between(30.0, 300.0, inclusive="both")].copy()
    control["expired_instrument_key"] = control["control_expired_instrument_key"]
    control["entry_price_next_open"] = control["control_entry_price_next_open"]
    control["option_type"] = control["control_option_type"]
    control["days_to_expiry"] = control["control_days_to_expiry"]
    control["minute_of_day"] = control["control_minute_of_day"]
    return control


def adjusted_ci_low(trades: pd.DataFrame, family_count: int) -> float | None:
    return leadership_mod.cluster_bootstrap_ci_low(trades, family_count)


def control_gate(primary: metrics_mod.Metrics, delayed: metrics_mod.Metrics, mirror: metrics_mod.Metrics) -> bool:
    if primary.mean_return_pct is None:
        return False
    delayed_ok = (
        delayed.trades >= max(10, int(primary.trades * 0.50))
        and delayed.mean_return_pct is not None
        and primary.mean_return_pct >= delayed.mean_return_pct + 0.20
    )
    mirror_ok = (
        mirror.trades >= max(10, int(primary.trades * 0.70))
        and mirror.mean_return_pct is not None
        and primary.mean_return_pct >= mirror.mean_return_pct + 0.50
    )
    return delayed_ok and mirror_ok


def oof_gate(metric: metrics_mod.Metrics, ci_low: float | None) -> bool:
    return bool(
        metric.trades >= MIN_OOF_TRADES and metric.sessions >= MIN_OOF_SESSIONS
        and metric.profit_factor is not None and metric.profit_factor >= 1.25
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.05
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00
        and ci_low is not None and ci_low > 0
        and metric.total_folds == 5 and metric.positive_folds >= 4
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.20)
        and (metric.top_five_session_profit_share is None or metric.top_five_session_profit_share <= 0.30)
    )


def validation_gate(metric: metrics_mod.Metrics, ci_low: float | None) -> bool:
    return bool(
        metric.trades >= MIN_VALIDATION_TRADES and metric.sessions >= MIN_VALIDATION_SESSIONS
        and metric.profit_factor is not None and metric.profit_factor >= 1.20
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct > 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.00
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00
        and ci_low is not None and ci_low > 0
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25)
        and (metric.top_five_session_profit_share is None or metric.top_five_session_profit_share <= 0.45)
    )


def _attach(signals: pd.DataFrame, option_causal: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    return horizon_mod.attach_exact_horizon(signals, option_causal, EXIT_HORIZON_MINUTES, fold_id)


def _write_ledger(frames: list[pd.DataFrame], path: Path) -> None:
    if not frames:
        return
    ledger = pd.concat(frames, ignore_index=True, sort=False)
    keep = [
        "partition", "control", "fold_id", "mechanism", "session_id", "timestamp", "exit_timestamp",
        "expired_instrument_key", "expiry_id", "option_type", "strike", "entry_price_next_open",
        "exit_close", "gross_return_pct", "net_return_pct", "stress_return_pct", "label_horizon_minutes",
        "u_open", "u_high", "u_low", "u_close", "u_ret_1m_pct", "u_ret_3m_pct", "u_ret_5m_pct",
        "u_range_5m_pct", "u_range_15m_pct", "u_efficiency_5", "u_accept_up", "u_accept_down",
        "u_failed_up", "u_failed_down", "directional_u_ret_5m_pct", "option_response_efficiency",
        "option_efficiency_delta", "prior_5m_return_pct", "return_acceleration", "mirror_return",
        "breadth_positive", "breadth_delta", "days_to_expiry", "minute_of_day",
    ]
    ledger[[column for column in keep if column in ledger.columns]].to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    out = root / OUT_REL
    research_dir = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_selected_manifest(root)
    paths, source_inventory = discover_underlying_sources(root, manifest)
    stable_json(out / "underlying_source_inventory.json", source_inventory)
    underlying_raw = load_underlying(paths)
    underlying = build_underlying_features(underlying_raw)
    option_causal = prepare_option_causal(root / PRIOR_REL / EVENT_FILE)
    joint = join_underlying_option(option_causal, underlying)
    if joint["session_id"].nunique() < 350:
        raise RuntimeError("Insufficient joint underlying-option session coverage.")
    partitions = splitmod.partition_sessions(joint)
    folds = splitmod.expanding_folds(partitions["research"])
    contract = {
        "schema_version": "underlying_auction_option_response_v1",
        "hypothesis": "underlying_auction_acceptance_or_failure_combined_with_option_response_efficiency_predicts_buy_side_option_moves",
        "mechanisms": list(MECHANISMS),
        "mechanism_count": len(MECHANISMS),
        "cumulative_mechanisms_in_all_adaptive_campaigns": CUMULATIVE_MECHANISM_COUNT,
        "multiplicity_policy": "session_cluster_bootstrap_lower_quantile_0_05_divided_by_2_times_55",
        "underlying_source_manifest_selected_count": int(manifest["selected_count"]),
        "underlying_loaded_sessions": int(underlying["session_id"].nunique()),
        "joint_rows": int(len(joint)),
        "joint_sessions": int(joint["session_id"].nunique()),
        "entry": "next_same_contract_option_open_after_completed_signal_candle",
        "exit_horizon_minutes": EXIT_HORIZON_MINUTES,
        "research_sessions": len(partitions["research"]),
        "validation_sessions": len(partitions["validation"]),
        "master_holdout_sessions": len(partitions["master_holdout"]),
        "master_holdout_policy": "latest_15pct_sessions_sealed_and_never_materialized",
        "normal_cost_pct": metrics_mod.NORMAL_COST_PCT,
        "stress_cost_pct": metrics_mod.STRESS_COST_PCT,
        "controls": ["same_strike_opposite_option", "target_entry_delayed_five_minutes"],
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)
    stable_json(out / "session_partitions.json", {
        "research": partitions["research"], "validation": partitions["validation"],
        "master_holdout_count": len(partitions["master_holdout"]),
        "master_holdout_sha256": semantic_hash(partitions["master_holdout"]),
        "master_holdout_sessions_redacted": True,
    })

    primary_ledgers = {name: [] for name in MECHANISMS}
    delayed_ledgers = {name: [] for name in MECHANISMS}
    mirror_ledgers = {name: [] for name in MECHANISMS}
    threshold_records: list[dict[str, Any]] = []
    evidence_frames: list[pd.DataFrame] = []
    for training_sessions, testing_sessions, fold_id in folds:
        training = joint.loc[joint["session_id"].isin(training_sessions)]
        testing = joint.loc[joint["session_id"].isin(testing_sessions)]
        cut = thresholds(training)
        threshold_records.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "thresholds": cut})
        masks = mechanism_masks(testing, cut)
        for mechanism in MECHANISMS:
            signals = select_signals(testing, masks[mechanism], mechanism, testing_sessions)
            delayed_signals = fixed_delay.shift_signal_entry(signals, option_causal, 5)
            mirror_signals = mirror_control_signals(signals, option_causal)
            primary = _attach(signals, option_causal, fold_id)
            delayed = _attach(delayed_signals, option_causal, fold_id)
            mirror = _attach(mirror_signals, option_causal, fold_id)
            if not primary.empty:
                primary["mechanism"] = mechanism
                primary_ledgers[mechanism].append(primary)
            if not delayed.empty:
                delayed["mechanism"] = mechanism + "__delayed_control"
                delayed_ledgers[mechanism].append(delayed)
            if not mirror.empty:
                mirror["mechanism"] = mechanism + "__mirror_control"
                mirror_ledgers[mechanism].append(mirror)
    stable_json(out / "fold_thresholds.json", threshold_records)

    oof_records: list[dict[str, Any]] = []
    survivors: list[tuple[str, metrics_mod.Metrics, float]] = []
    for mechanism in MECHANISMS:
        primary = pd.concat(primary_ledgers[mechanism], ignore_index=True, sort=False) if primary_ledgers[mechanism] else pd.DataFrame()
        delayed = pd.concat(delayed_ledgers[mechanism], ignore_index=True, sort=False) if delayed_ledgers[mechanism] else pd.DataFrame()
        mirror = pd.concat(mirror_ledgers[mechanism], ignore_index=True, sort=False) if mirror_ledgers[mechanism] else pd.DataFrame()
        primary_metric = metrics_mod.calculate_metrics(primary)
        delayed_metric = metrics_mod.calculate_metrics(delayed)
        mirror_metric = metrics_mod.calculate_metrics(mirror)
        ci_low = adjusted_ci_low(primary, CUMULATIVE_MECHANISM_COUNT)
        economic_pass = oof_gate(primary_metric, ci_low)
        controls_pass = control_gate(primary_metric, delayed_metric, mirror_metric) if economic_pass else False
        passed = economic_pass and controls_pass
        oof_records.append({
            "mechanism": mechanism, **asdict(primary_metric),
            "multiplicity_adjusted_cluster_bootstrap_ci_low": ci_low,
            "delayed_control": asdict(delayed_metric), "mirror_control": asdict(mirror_metric),
            "economic_gate": economic_pass, "control_gate": controls_pass, "oof_gate": passed,
        })
        if not primary.empty:
            evidence_frames.append(primary.assign(partition="research_oof", control="primary"))
        if not delayed.empty:
            evidence_frames.append(delayed.assign(partition="research_oof", control="delayed_5m"))
        if not mirror.empty:
            evidence_frames.append(mirror.assign(partition="research_oof", control="opposite_option"))
        if passed and ci_low is not None:
            survivors.append((mechanism, primary_metric, ci_low))
    survivors = sorted(survivors, key=lambda item: (
        item[2], item[1].remove_top_five_profit_factor or -math.inf, item[1].trades, item[0]
    ), reverse=True)[:1]
    survivor_names = [name for name, _, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "validation_survivors_frozen": survivor_names})

    validation_records: list[dict[str, Any]] = []
    validation_survivors: list[str] = []
    if survivor_names:
        final_cut = thresholds(joint.loc[joint["session_id"].isin(partitions["research"])])
        validation = joint.loc[joint["session_id"].isin(partitions["validation"])]
        masks = mechanism_masks(validation, final_cut)
        for mechanism in survivor_names:
            signals = select_signals(validation, masks[mechanism], mechanism, partitions["validation"])
            delayed_signals = fixed_delay.shift_signal_entry(signals, option_causal, 5)
            mirror_signals = mirror_control_signals(signals, option_causal)
            primary = _attach(signals, option_causal, "validation")
            delayed = _attach(delayed_signals, option_causal, "validation")
            mirror = _attach(mirror_signals, option_causal, "validation")
            primary_metric = metrics_mod.calculate_metrics(primary)
            delayed_metric = metrics_mod.calculate_metrics(delayed)
            mirror_metric = metrics_mod.calculate_metrics(mirror)
            ci_low = adjusted_ci_low(primary, 1)
            economic_pass = validation_gate(primary_metric, ci_low)
            controls_pass = control_gate(primary_metric, delayed_metric, mirror_metric) if economic_pass else False
            passed = economic_pass and controls_pass
            validation_records.append({
                "mechanism": mechanism, **asdict(primary_metric),
                "session_cluster_bootstrap_ci_low": ci_low,
                "delayed_control": asdict(delayed_metric), "mirror_control": asdict(mirror_metric),
                "economic_gate": economic_pass, "control_gate": controls_pass,
                "validation_gate": passed,
            })
            if not primary.empty:
                evidence_frames.append(primary.assign(partition="validation", control="primary"))
            if not delayed.empty:
                evidence_frames.append(delayed.assign(partition="validation", control="delayed_5m"))
            if not mirror.empty:
                evidence_frames.append(mirror.assign(partition="validation", control="opposite_option"))
            if passed:
                validation_survivors.append(mechanism)
    stable_json(out / "validation_screen.json", {
        "records": validation_records, "validation_survivors": validation_survivors,
        "master_holdout_outcomes_materialized": False,
    })
    _write_ledger(evidence_frames, out / "trade_ledger.csv")

    verdict = (
        "PROMISING_HIGH_OCCURRENCE_UNDERLYING_AUCTION_EDGE_MASTER_HOLDOUT_UNOPENED"
        if validation_survivors else (
            "NO_MULTIPLICITY_ADJUSTED_OOF_SURVIVOR_IN_UNDERLYING_AUCTION_FAMILY"
            if not survivor_names else "UNDERLYING_AUCTION_OOF_SURVIVOR_FAILED_VALIDATION"
        )
    )
    final = {
        "principal_verdict": verdict, "oof_survivors": survivor_names,
        "validation_survivors": validation_survivors,
        "cumulative_mechanisms_tested": CUMULATIVE_MECHANISM_COUNT,
        "master_holdout_outcomes_materialized": False,
        "master_holdout_status": "SEALED_FOR_CROSS_FAMILY_FINAL_CERTIFICATION",
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "contract_semantic_sha256": contract["semantic_sha256"], "research_only": True,
        "paper_or_live_authorized": False, "allowed_for_live_execution": False,
    }
    final["semantic_sha256"] = semantic_hash(final)
    stable_json(out / "final_decision.json", final)
    (research_dir / "RESULT.md").write_text(
        "# Underlying Auction and Option Response V1\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"OOF survivors: `{survivor_names}`\n\n"
        f"Validation survivors: `{validation_survivors}`\n\n"
        "Master holdout: `SEALED_AND_UNREAD`.\n\n"
        "No paper or live authorization is granted.\n",
        encoding="utf-8",
    )
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
