from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from .common import *
from .discovery import precompute_motif_signals


def build_outcome_lookup(
    frame: pd.DataFrame,
    allowed_splits: set[str] | None = None,
) -> dict[tuple[str, int, int], dict[str, Any]]:
    """Precompute fixed-horizon outcomes only for explicitly authorized splits."""
    lookup: dict[tuple[str, int, int], dict[str, Any]] = {}
    source = frame if allowed_splits is None else frame.loc[frame["split"].isin(sorted(allowed_splits))]
    base = source[[
        "session_date", "timestamp", "session_progress", "index_close",
        "index_ret3", "index_vol6", "split",
    ]].drop_duplicates(["session_date", "timestamp"])
    for session_date, group in base.groupby("session_date", sort=True):
        session = group.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        timestamps = pd.to_datetime(session["timestamp"])
        prices = pd.to_numeric(session["index_close"], errors="coerce").to_numpy(float)
        progress = pd.to_numeric(session["session_progress"], errors="coerce").to_numpy(float)
        mom = pd.to_numeric(session["index_ret3"], errors="coerce").to_numpy(float)
        vol = pd.to_numeric(session["index_vol6"], errors="coerce").to_numpy(float)
        for signal_idx in range(len(session)):
            signal_ts = pd.Timestamp(timestamps.iloc[signal_idx])
            for horizon in HORIZONS:
                entry_idx = signal_idx + 1
                exit_idx = entry_idx + int(horizon)
                if exit_idx >= len(session):
                    continue
                expected_entry = signal_ts + pd.Timedelta(minutes=5)
                expected_exit = expected_entry + pd.Timedelta(minutes=5 * int(horizon))
                if timestamps.iloc[entry_idx] != expected_entry or timestamps.iloc[exit_idx] != expected_exit:
                    continue
                if not (
                    math.isfinite(prices[entry_idx]) and math.isfinite(prices[exit_idx])
                    and prices[entry_idx] > 0 and prices[exit_idx] > 0
                ):
                    continue
                raw_bps = float(math.log(prices[exit_idx] / prices[entry_idx]) * 10000.0)
                shorter_idx = entry_idx + max(1, int(horizon) // 2)
                shorter_bps = (
                    float(math.log(prices[shorter_idx] / prices[entry_idx]) * 10000.0)
                    if shorter_idx < len(session) else None
                )
                delayed_entry_idx = signal_idx + 2
                delayed_exit_idx = delayed_entry_idx + int(horizon)
                delayed_bps = None
                if delayed_exit_idx < len(session):
                    if (
                        timestamps.iloc[delayed_entry_idx] == signal_ts + pd.Timedelta(minutes=10)
                        and timestamps.iloc[delayed_exit_idx] == signal_ts + pd.Timedelta(minutes=10 + 5 * int(horizon))
                    ):
                        delayed_bps = float(math.log(prices[delayed_exit_idx] / prices[delayed_entry_idx]) * 10000.0)
                longer_idx = entry_idx + int(horizon) + max(1, int(horizon) // 2)
                longer_bps = (
                    float(math.log(prices[longer_idx] / prices[entry_idx]) * 10000.0)
                    if longer_idx < len(session) else None
                )
                lookup[(str(session_date), int(signal_ts.value), int(horizon))] = {
                    "signal_timestamp": str(signal_ts),
                    "entry_timestamp": str(timestamps.iloc[entry_idx]),
                    "exit_timestamp": str(timestamps.iloc[exit_idx]),
                    "raw_return_bps": raw_bps,
                    "shorter_raw_return_bps": shorter_bps,
                    "delayed_raw_return_bps": delayed_bps,
                    "longer_raw_return_bps": longer_bps,
                    "session_progress": float(progress[signal_idx]),
                    "index_ret3": float(mom[signal_idx]) if math.isfinite(mom[signal_idx]) else float("nan"),
                    "index_vol6": float(vol[signal_idx]) if math.isfinite(vol[signal_idx]) else float("nan"),
                }
    return lookup


def _context_thresholds(frame: pd.DataFrame) -> dict[str, list[float]]:
    obs = frame.loc[frame["split"].eq("observation")]
    result: dict[str, list[float]] = {}
    for feature in ("index_ret3", "index_vol6"):
        values = pd.to_numeric(obs[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
        if len(values) < 100:
            result[feature] = [0.0, 0.0]
        else:
            result[feature] = [float(np.quantile(values, 1/3)), float(np.quantile(values, 2/3))]
    return result


def _bin(value: float, cuts: Sequence[float]) -> int:
    if not math.isfinite(value):
        return 1
    return int(np.digitize([value], np.asarray(cuts, dtype=float), right=False)[0])


def baseline_table(
    frame: pd.DataFrame,
    outcome_lookup: Mapping[tuple[str, int, int], Mapping[str, Any]],
    context_cuts: Mapping[str, Sequence[float]],
) -> dict[tuple[int, int, int, int], float]:
    values: dict[tuple[int, int, int, int], list[float]] = defaultdict(list)
    observation = frame.loc[frame["split"].eq("observation")].drop_duplicates(["session_date", "timestamp"])
    for row in observation.itertuples(index=False):
        session_date = str(getattr(row, "session_date"))
        signal_ts = pd.Timestamp(getattr(row, "timestamp"))
        progress_bin = int(np.clip(math.floor(float(getattr(row, "session_progress")) * 10), 0, 9))
        mom = float(getattr(row, "index_ret3")) if pd.notna(getattr(row, "index_ret3")) else float("nan")
        vol = float(getattr(row, "index_vol6")) if pd.notna(getattr(row, "index_vol6")) else float("nan")
        mom_bin = _bin(mom, context_cuts["index_ret3"])
        vol_bin = _bin(vol, context_cuts["index_vol6"])
        for horizon in HORIZONS:
            outcome = outcome_lookup.get((session_date, int(signal_ts.value), int(horizon)))
            if outcome is not None:
                values[(horizon, progress_bin, mom_bin, vol_bin)].append(float(outcome["raw_return_bps"]))
    table: dict[tuple[int, int, int, int], float] = {}
    progress_fallback: dict[tuple[int, int], list[float]] = defaultdict(list)
    for key, vals in values.items():
        if len(vals) >= 20:
            table[key] = float(np.median(vals))
        progress_fallback[(key[0], key[1])].extend(vals)
    for (horizon, progress_bin), vals in progress_fallback.items():
        if len(vals) >= 30:
            fallback = float(np.median(vals))
            for mom_bin in range(3):
                for vol_bin in range(3):
                    table.setdefault((horizon, progress_bin, mom_bin, vol_bin), fallback)
    return table


def summarize(values: Sequence[float]) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {"n": 0, "mean_bps": None, "median_bps": None, "hit_rate": None, "ci90": [None, None], "sign_p": 1.0}
    hits = int(np.sum(arr > 0))
    ci = PA.bootstrap_mean_ci(arr, confidence=0.90)
    return {
        "n": int(len(arr)),
        "mean_bps": float(np.mean(arr)),
        "median_bps": float(np.median(arr)),
        "hit_rate": float(hits / len(arr)),
        "ci90": [float(ci[0]), float(ci[1])],
        "sign_p": float(binomtest(hits, len(arr), 0.5, alternative="greater").pvalue),
    }


def attach_development_outcomes(
    hypotheses: Mapping[str, Any],
    discovery: Mapping[str, Any],
    assignments: Mapping[str, pd.DataFrame],
    frame: pd.DataFrame,
    splits: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    cuts = _context_thresholds(frame)
    outcome_lookup = build_outcome_lookup(frame, {"observation", "replication", "validation"})
    baseline = baseline_table(frame, outcome_lookup, cuts)
    signal_table = precompute_motif_signals(discovery, assignments)
    split_map = {str(d): split for split, dates in splits.items() for d in dates}
    records: list[dict[str, Any]] = []
    for hypothesis in hypotheses.get("hypotheses", []):
        motif_id = str(hypothesis["motif_id"])
        horizon = int(hypothesis["horizon_bars"])
        events: list[dict[str, Any]] = []
        for session_date, signal in signal_table.get(motif_id, {}).items():
            split = split_map.get(str(session_date), "excluded")
            if split not in {"observation", "replication", "validation"}:
                continue
            outcome = outcome_lookup.get((str(session_date), int(pd.Timestamp(signal).value), horizon))
            if outcome is None:
                continue
            progress_bin = int(np.clip(math.floor(outcome["session_progress"] * 10), 0, 9))
            mom_bin = _bin(outcome["index_ret3"], cuts["index_ret3"])
            vol_bin = _bin(outcome["index_vol6"], cuts["index_vol6"])
            baseline_value = baseline.get((horizon, progress_bin, mom_bin, vol_bin))
            if baseline_value is None:
                continue
            events.append({
                "session_date": str(session_date),
                "split": split,
                **dict(outcome),
                "baseline_return_bps": float(baseline_value),
                "raw_excess_bps": float(outcome["raw_return_bps"] - baseline_value),
            })
        obs_excess = [e["raw_excess_bps"] for e in events if e["split"] == "observation"]
        direction = 1 if (np.mean(obs_excess) if obs_excess else 0.0) >= 0 else -1
        for event in events:
            event["direction"] = direction
            event["directional_excess_bps"] = direction * float(event["raw_excess_bps"])
            event["directional_gross_bps"] = direction * float(event["raw_return_bps"])
            event["net_proxy_bps"] = event["directional_gross_bps"] - COST_BPS
            event["delayed_net_proxy_bps"] = (
                direction * float(event["delayed_raw_return_bps"]) - COST_BPS
                if event.get("delayed_raw_return_bps") is not None else None
            )
            event["shorter_net_proxy_bps"] = (
                direction * float(event["shorter_raw_return_bps"]) - COST_BPS
                if event.get("shorter_raw_return_bps") is not None else None
            )
            event["longer_net_proxy_bps"] = (
                direction * float(event["longer_raw_return_bps"]) - COST_BPS
                if event.get("longer_raw_return_bps") is not None else None
            )
        by_split = {}
        for split in ("observation", "replication", "validation"):
            split_events = [e for e in events if e["split"] == split]
            by_split[split] = {
                "directional_excess": summarize([e["directional_excess_bps"] for e in split_events]),
                "net_proxy": summarize([e["net_proxy_bps"] for e in split_events]),
            }
        records.append({
            "hypothesis": {**dict(hypothesis), "direction_selected_from_observation_only": int(direction)},
            "stats": by_split,
            "events": events,
        })
    return {
        "principal_verdict": "DEVELOPMENT_OUTCOMES_ATTACHED_WITH_OBSERVATION_ONLY_DIRECTION",
        "records": records,
        "context_thresholds": cuts,
        "baseline_cell_count": len(baseline),
        "outcome_lookup_count": len(outcome_lookup),
        "policy": {
            "unopened_sessions_scored": False,
            "direction_fit_scope": "observation_only",
            "baseline_fit_scope": "observation_only",
            "pre_post_cas_pooled": False,
        },
        "semantic_sha256": digest({"records": [{"hypothesis": r["hypothesis"], "stats": r["stats"]} for r in records], "context_thresholds": cuts}),
    }
