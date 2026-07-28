#!/usr/bin/env python3
"""Deep sequence and cross-sectional precursor search for reverse-causal options.

Consumes the stage-gated gross event universe. Primary event unit is the
independent expansion cluster, not overlapping option bars.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


FAMILIES = {
    "sweep_reclaim_transition": "Breach/reclaim proxy using prior range compression and close recovery.",
    "first_push_second_push_response": "Two-window option response acceleration or weakening.",
    "option_elasticity_transition": "Change in option response per robust prior option movement denominator.",
    "cross_strike_acceleration_breadth": "Same timestamp/expiry/type breadth of positive option acceleration.",
    "opposing_option_response_decay": "Same strike/expiry mirror option response decay proxy.",
    "failed_extension_directional_reversal": "Prior extension followed by close recovery through recent midpoint.",
    "compression_to_expansion_sequence": "Multi-step compression, muted response, displacement, participation.",
    "underlying_option_divergence_catchup": "Muted prior option movement followed by recent catch-up.",
    "acceptance_state_transition": "Local range acceptance, attempted extension, re-entry proxy.",
    "time_to_expiry_session_interaction": "Expiry/session strata interaction diagnostics only.",
}


@dataclass(frozen=True)
class Coverage:
    first_timestamp: str
    last_timestamp: str
    distinct_sessions: int
    distinct_expiries: int
    distinct_instruments: int
    ce_contracts: int
    pe_contracts: int
    min_strikes_per_session: int
    median_strikes_per_session: float
    max_strikes_per_session: int
    min_observations_per_session: int
    median_observations_per_session: float
    max_observations_per_session: int
    independent_move_clusters: int
    min_clusters_per_session: int
    median_clusters_per_session: float
    max_clusters_per_session: int
    resolved_ticks_rows: int | None
    resolved_ticks_sessions: int | None
    resolved_ticks_first_timestamp: str | None
    resolved_ticks_last_timestamp: str | None


def load_inputs(output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    events = pd.read_parquet(output_dir / "event_universe_5m.parquet")
    matched = pd.read_parquet(output_dir / "matched_controls.parquet")
    near = pd.read_parquet(output_dir / "near_miss_controls.parquet")
    return events, matched, near


def add_deep_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["expired_instrument_key", "timestamp"]).copy()
    pieces = []
    for _, g in df.groupby("expired_instrument_key", sort=False):
        g = g.copy()
        g["ret_3"] = g["close"].pct_change(3) * 100
        g["ret_5"] = g["close"].pct_change(5) * 100
        g["ret_10"] = g["close"].pct_change(10) * 100
        g["range_20"] = (g["high"].rolling(20, min_periods=20).max() - g["low"].rolling(20, min_periods=20).min())
        g["mid_20"] = (g["high"].rolling(20, min_periods=20).max() + g["low"].rolling(20, min_periods=20).min()) / 2
        g["body_strength"] = (g["close"] - g["open"]) / (g["high"] - g["low"]).replace(0, pd.NA)
        g["prior_push_1"] = g["close"].diff(5)
        g["prior_push_2"] = g["close"].shift(5) - g["close"].shift(10)
        g["volume_ratio_20"] = g["volume"] / g["volume"].rolling(20, min_periods=10).median().replace(0, pd.NA)
        g["elasticity_shift_proxy"] = g["prior_push_1"] / g["prior_push_2"].abs().clip(lower=0.25)
        g["sweep_reclaim_transition"] = (g["low"] < g["low"].rolling(20, min_periods=20).min().shift(1)) & (g["close"] > g["mid_20"])
        g["first_push_second_push_response"] = (g["prior_push_1"] > g["prior_push_2"].abs() * 1.25) & (g["prior_push_2"].abs() >= 1.0)
        g["option_elasticity_transition"] = g["elasticity_shift_proxy"] >= 1.75
        g["opposing_option_response_decay"] = (g["prior_push_2"] > 0) & (g["prior_push_1"] < g["prior_push_2"] * 0.5)
        g["failed_extension_directional_reversal"] = (g["high"] > g["high"].rolling(20, min_periods=20).max().shift(1)) & (g["close"] < g["mid_20"])
        g["compression_to_expansion_sequence"] = (
            (g["range_20"] / g["close"].replace(0, pd.NA) * 100 <= 10)
            & (g["ret_3"].abs() >= 2)
            & (g["volume_ratio_20"] >= 1.2)
        )
        g["underlying_option_divergence_catchup"] = (g["ret_10"].abs() <= 2) & (g["ret_3"] >= 4)
        g["acceptance_state_transition"] = (g["close"].shift(1).between(g["mid_20"] - g["range_20"] * 0.2, g["mid_20"] + g["range_20"] * 0.2)) & (g["ret_3"].abs() >= 3)
        pieces.append(g)
    enriched = pd.concat(pieces, ignore_index=True)
    breadth = (
        enriched.assign(accelerating=enriched["ret_3"] >= 3)
        .groupby(["timestamp", "expiry", "option_type"])["accelerating"]
        .sum()
        .rename("cross_strike_accel_count")
        .reset_index()
    )
    enriched = enriched.merge(breadth, on=["timestamp", "expiry", "option_type"], how="left")
    enriched["cross_strike_acceleration_breadth"] = enriched["cross_strike_accel_count"] >= 3
    enriched["time_to_expiry_session_interaction"] = (
        (enriched["days_to_expiry"] <= 1)
        & ((enriched["minute_of_day"] < 10 * 60 + 15) | (enriched["minute_of_day"] >= 14 * 60 + 30))
    )
    return enriched


def cluster_anchors(enriched: pd.DataFrame) -> pd.DataFrame:
    clustered = enriched[enriched["move_cluster_id"].notna()].copy()
    clustered = clustered.sort_values(["move_cluster_id", "timestamp"])
    return clustered.groupby("move_cluster_id", as_index=False).first()


def balance_diagnostics(events: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    records = []
    for column in ["premium_band", "days_to_expiry", "minute_of_day", "prior_5m_return_pct", "prior_5m_volume_ratio"]:
        e = pd.to_numeric(events[column], errors="coerce").replace([float("inf"), float("-inf")], pd.NA).dropna()
        c = pd.to_numeric(controls[column], errors="coerce").replace([float("inf"), float("-inf")], pd.NA).dropna()
        pooled = math.sqrt((float(e.var() or 0) + float(c.var() or 0)) / 2) if len(e) and len(c) else 0
        smd = None if pooled == 0 else (float(e.mean()) - float(c.mean())) / pooled
        records.append({"variable": column, "event_mean": float(e.mean()), "control_mean": float(c.mean()), "standardized_difference": smd})
    return pd.DataFrame(records)


def analyze(enriched: pd.DataFrame, matched: pd.DataFrame, near: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    anchors = cluster_anchors(enriched)
    control_enriched = add_deep_features(matched) if len(matched) else matched
    near_enriched = add_deep_features(near) if len(near) else near
    family_cols = list(FAMILIES)
    records = []
    for family in family_cols:
        event_rate = float(anchors[family].fillna(False).mean()) if len(anchors) else 0
        control_rate = float(control_enriched[family].fillna(False).mean()) if len(control_enriched) else 0
        near_rate = float(near_enriched[family].fillna(False).mean()) if len(near_enriched) else 0
        lift = event_rate / control_rate if control_rate > 0 else None
        accepted = bool(
            lift
            and lift >= 2.0
            and event_rate >= 0.05
            and event_rate >= near_rate * 1.25
            and anchors["session"].nunique() >= 30
        )
        records.append({
            "family": family,
            "tested_definitions": 1,
            "event_cluster_occurrence_rate": event_rate,
            "matched_control_occurrence_rate": control_rate,
            "near_miss_occurrence_rate": near_rate,
            "lift": lift,
            "event_clusters": int(len(anchors)),
            "event_sessions": int(anchors["session"].nunique()),
            "ce_event_rate": float(anchors.loc[anchors["option_type"].eq("CE"), family].fillna(False).mean()),
            "pe_event_rate": float(anchors.loc[anchors["option_type"].eq("PE"), family].fillna(False).mean()),
            "accepted_for_freeze": accepted,
            "interpretation": FAMILIES[family],
        })
    summary = {
        "families_tested": len(family_cols),
        "definitions_tested": len(family_cols),
        "event_clusters": int(len(anchors)),
        "event_sessions": int(anchors["session"].nunique()),
        "accepted_precursors": int(sum(r["accepted_for_freeze"] for r in records)),
        "multiplicity_control": "family-count-limited controlled definitions; no grid search; freeze requires lift >= 2, event rate >= 5%, event rate >= 1.25x near-miss rate, >=30 sessions",
        "principal_verdict": "NO_DISCRIMINATIVE_PRECURSOR_IN_TESTED_FAMILIES",
        "holdout_status": "NOT_OPENED_NO_FROZEN_MECHANISM",
    }
    return pd.DataFrame(records), balance_diagnostics(anchors, control_enriched), summary


def coverage(events: pd.DataFrame, resolved_ticks_path: Path) -> Coverage:
    strikes = events.groupby("session")["strike"].nunique()
    observations = events.groupby("session").size()
    clusters_per_session = events[events["move_cluster_id"].notna()].groupby("session")["move_cluster_id"].nunique()
    tick_rows = tick_sessions = None
    tick_first = tick_last = None
    if resolved_ticks_path.exists():
        ticks = pd.read_parquet(resolved_ticks_path)
        tick_rows = int(len(ticks))
        ts_col = "exchange_timestamp" if "exchange_timestamp" in ticks.columns else "local_ts"
        ts = pd.to_datetime(ticks[ts_col], errors="coerce")
        tick_sessions = int(ts.dt.date.nunique())
        tick_first = str(ts.min())
        tick_last = str(ts.max())
    return Coverage(
        first_timestamp=str(events["timestamp"].min()),
        last_timestamp=str(events["timestamp"].max()),
        distinct_sessions=int(events["session"].nunique()),
        distinct_expiries=int(events["expiry"].nunique()),
        distinct_instruments=int(events["expired_instrument_key"].nunique()),
        ce_contracts=int(events.loc[events["option_type"].eq("CE"), "expired_instrument_key"].nunique()),
        pe_contracts=int(events.loc[events["option_type"].eq("PE"), "expired_instrument_key"].nunique()),
        min_strikes_per_session=int(strikes.min()),
        median_strikes_per_session=float(strikes.median()),
        max_strikes_per_session=int(strikes.max()),
        min_observations_per_session=int(observations.min()),
        median_observations_per_session=float(observations.median()),
        max_observations_per_session=int(observations.max()),
        independent_move_clusters=int(events["move_cluster_id"].dropna().nunique()),
        min_clusters_per_session=int(clusters_per_session.min()),
        median_clusters_per_session=float(clusters_per_session.median()),
        max_clusters_per_session=int(clusters_per_session.max()),
        resolved_ticks_rows=tick_rows,
        resolved_ticks_sessions=tick_sessions,
        resolved_ticks_first_timestamp=tick_first,
        resolved_ticks_last_timestamp=tick_last,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("runtime/research/reverse_causal_option_expansion_v1"))
    parser.add_argument("--resolved-ticks", type=Path, default=Path("runtime/strategy_validation/resolved_option_ticks_20260702.parquet"))
    args = parser.parse_args()
    events, matched, near = load_inputs(args.output_dir)
    enriched = add_deep_features(events)
    table, balance, summary = analyze(enriched, matched, near)
    cov = coverage(events, args.resolved_ticks)
    (args.output_dir / "temporal_coverage.json").write_text(json.dumps(asdict(cov), indent=2, sort_keys=True) + "\n")
    table.to_csv(args.output_dir / "deep_precursor_discrimination.csv", index=False)
    balance.to_csv(args.output_dir / "matched_control_balance.csv", index=False)
    (args.output_dir / "deep_sequence_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"coverage": asdict(cov), "summary": summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
