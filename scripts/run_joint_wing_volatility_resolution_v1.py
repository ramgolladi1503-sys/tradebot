#!/usr/bin/env python3
"""Joint-wing volatility shock resolution discovery V1.

Hypothesis: CE and PE can expand together during an uncertainty/volatility shock.
The structural opportunity is not the initial joint expansion, but its directional
resolution: one same-strike wing retains or accelerates while the other rolls over.
Buy the persistent wing at its next one-minute open and exit ten minutes later.

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
from scripts import run_surface_exhaustion_mirror_reversal_v1 as previous_campaign
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/joint_wing_volatility_resolution_v1")
RESEARCH_REL = Path("research/joint_wing_volatility_resolution_v1")
EVENT_FILE = "event_universe_5m.parquet"
EXIT_HORIZON_MINUTES = 10
MIN_OOF_TRADES = 80
MIN_OOF_SESSIONS = 60
MIN_VALIDATION_TRADES = 20
MIN_VALIDATION_SESSIONS = 15
MAX_SIGNALS_PER_SESSION = 2
MIN_SIGNAL_SEPARATION_MINUTES = 15
CUMULATIVE_MECHANISM_COUNT = 47
SEED = 20260729

MECHANISMS = (
    "joint_lift_directional_resolution",
    "persistent_joint_lift_leader",
    "mirror_rollover_target_persistence",
    "volume_confirmed_joint_resolution",
    "low_dispersion_joint_resolution",
    "oi_backed_joint_resolution",
    "near_expiry_joint_resolution",
    "late_session_joint_resolution",
)


def semantic_hash(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(body).hexdigest()


def _finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = _finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def prepare_causal(event_path: Path) -> pd.DataFrame:
    frame = previous_campaign.prepare_causal(event_path)
    frame["joint_wing_return"] = frame["prior_5m_return_pct"] + frame["mirror_return"]
    frame["joint_wing_floor"] = frame[["prior_5m_return_pct", "mirror_return"]].min(axis=1)
    frame["dominance"] = frame["option_asymmetry"]
    frame["dominance_delta"] = frame["option_asymmetry"] - frame["previous_option_asymmetry"]
    frame["joint_wing_acceleration"] = frame["return_acceleration"] + frame["mirror_acceleration"]
    frame["target_vs_mirror_volume"] = frame["prior_5m_volume_ratio"] - frame["mirror_volume_ratio"]
    return frame


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    return {
        "return_p55": _q(training, "prior_5m_return_pct", 0.55),
        "return_p65": _q(training, "prior_5m_return_pct", 0.65),
        "joint_p65": _q(training, "joint_wing_return", 0.65),
        "joint_p75": _q(training, "joint_wing_return", 0.75),
        "dominance_p65": _q(training, "dominance", 0.65),
        "dominance_p75": _q(training, "dominance", 0.75),
        "dominance_delta_p60": _q(training, "dominance_delta", 0.60),
        "breadth_p60": _q(training, "breadth_positive", 0.60),
        "dispersion_p40": _q(training, "surface_return_dispersion", 0.40),
        "volume_p60": _q(training, "prior_5m_volume_ratio", 0.60, 1.0),
        "volume_advantage_p60": _q(training, "target_vs_mirror_volume", 0.60),
        "oi_p60": _q(training, "oi_change_ratio", 0.60),
        "mirror_rollover_p40": _q(training, "mirror_turn", 0.40),
    }


def mechanism_masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    target = frame["prior_5m_return_pct"]
    mirror = frame["mirror_return"]
    both_positive = (target > 0) & (mirror > 0)
    target_leads = frame["dominance"] >= cut["dominance_p65"]
    joint_shock = frame["joint_wing_return"] >= cut["joint_p65"]
    broad_target = frame["breadth_positive"] >= cut["breadth_p60"]
    return {
        "joint_lift_directional_resolution": (
            both_positive
            & joint_shock
            & target_leads
            & (frame["dominance_delta"] >= cut["dominance_delta_p60"])
            & broad_target
        ),
        "persistent_joint_lift_leader": (
            (frame["previous_return"] > 0)
            & (frame["previous_mirror_return"] > 0)
            & both_positive
            & target_leads
            & (frame["return_acceleration"] >= 0)
            & (frame["dominance_delta"] > 0)
        ),
        "mirror_rollover_target_persistence": (
            (frame["previous_mirror_return"] > 0)
            & (target >= cut["return_p55"])
            & (frame["return_acceleration"] >= 0)
            & (frame["mirror_turn"] <= cut["mirror_rollover_p40"])
            & target_leads
            & broad_target
        ),
        "volume_confirmed_joint_resolution": (
            both_positive
            & joint_shock
            & target_leads
            & (frame["prior_5m_volume_ratio"] >= cut["volume_p60"])
            & (frame["target_vs_mirror_volume"] >= cut["volume_advantage_p60"])
            & broad_target
        ),
        "low_dispersion_joint_resolution": (
            both_positive
            & joint_shock
            & target_leads
            & (frame["surface_return_dispersion"] <= cut["dispersion_p40"])
            & broad_target
        ),
        "oi_backed_joint_resolution": (
            both_positive
            & joint_shock
            & target_leads
            & (frame["oi_change_ratio"] >= cut["oi_p60"])
            & (frame["prior_5m_volume_ratio"] >= cut["volume_p60"])
        ),
        "near_expiry_joint_resolution": (
            frame["days_to_expiry"].between(0, 2, inclusive="both")
            & both_positive
            & (frame["joint_wing_return"] >= cut["joint_p75"])
            & (frame["dominance"] >= cut["dominance_p75"])
            & broad_target
        ),
        "late_session_joint_resolution": (
            frame["minute_of_day"].between(780, 875, inclusive="both")
            & both_positive
            & joint_shock
            & target_leads
            & (frame["dominance_delta"] > 0)
        ),
    }


def eligibility(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & frame["minute_of_day"].between(585, 875, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
        & frame["mirror_return"].notna()
        & frame["mirror_volume_ratio"].notna()
    )


def _mirror_contract_lookup(frame: pd.DataFrame) -> pd.DataFrame:
    lookup = frame[
        [
            "session_id",
            "timestamp",
            "expiry_id",
            "strike",
            "option_type",
            "expired_instrument_key",
            "entry_price_next_open",
            "days_to_expiry",
            "minute_of_day",
            "volume",
        ]
    ].copy()
    lookup = lookup.rename(
        columns={
            "option_type": "control_option_type",
            "expired_instrument_key": "control_expired_instrument_key",
            "entry_price_next_open": "control_entry_price_next_open",
            "days_to_expiry": "control_days_to_expiry",
            "minute_of_day": "control_minute_of_day",
            "volume": "control_volume",
        }
    )
    return lookup.drop_duplicates(
        ["session_id", "timestamp", "expiry_id", "strike", "control_option_type"]
    )


def build_candidates(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    columns = [
        "session_id",
        "timestamp",
        "expiry_id",
        "strike",
        "option_type",
        "expired_instrument_key",
        "entry_price_next_open",
        "days_to_expiry",
        "minute_of_day",
        "prior_5m_return_pct",
        "previous_return",
        "return_acceleration",
        "mirror_return",
        "previous_mirror_return",
        "mirror_acceleration",
        "mirror_turn",
        "prior_5m_volume_ratio",
        "mirror_volume_ratio",
        "target_vs_mirror_volume",
        "open_interest",
        "oi_change_ratio",
        "breadth_positive",
        "breadth_delta",
        "surface_return_dispersion",
        "joint_wing_return",
        "joint_wing_floor",
        "dominance",
        "dominance_delta",
    ]
    candidates = frame.loc[
        mask & eligibility(frame) & frame["session_id"].isin(sessions),
        columns,
    ].copy()
    if candidates.empty:
        return candidates
    candidates["control_option_type"] = candidates["option_type"].map({"CE": "PE", "PE": "CE"})
    candidates = candidates.merge(
        _mirror_contract_lookup(frame),
        on=["session_id", "timestamp", "expiry_id", "strike", "control_option_type"],
        how="inner",
        validate="many_to_one",
    )
    candidates = candidates.loc[
        candidates["control_entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & (candidates["control_volume"] > 0)
    ].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["premium_distance"] = (candidates["entry_price_next_open"] - 120.0).abs()
    candidates["resolution_score"] = (
        candidates["joint_wing_return"].fillna(0)
        + candidates["dominance"].fillna(0)
        + candidates["dominance_delta"].fillna(0)
        + 0.25 * candidates["prior_5m_volume_ratio"].fillna(0)
        + candidates["breadth_positive"].fillna(0)
    )
    best = candidates.groupby(["session_id", "timestamp"], observed=True)["resolution_score"].transform("max")
    candidates = candidates.loc[candidates["resolution_score"].eq(best)]
    candidates = candidates.sort_values(
        ["session_id", "timestamp", "resolution_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
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
    if not parts:
        return candidates.iloc[0:0]
    return pd.concat(parts, ignore_index=False).sort_values(["session_id", "timestamp"], kind="mergesort")


def mirror_control_signals(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    control = candidates.copy()
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
        metric.trades >= MIN_OOF_TRADES
        and metric.sessions >= MIN_OOF_SESSIONS
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.25
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None
        and metric.remove_top_five_profit_factor >= 1.05
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.00
        and ci_low is not None
        and ci_low > 0
        and metric.total_folds == 5
        and metric.positive_folds >= 4
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.20)
        and (metric.top_five_session_profit_share is None or metric.top_five_session_profit_share <= 0.30)
    )


def validation_gate(metric: metrics_mod.Metrics, ci_low: float | None) -> bool:
    return bool(
        metric.trades >= MIN_VALIDATION_TRADES
        and metric.sessions >= MIN_VALIDATION_SESSIONS
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.20
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct > 0
        and metric.remove_top_five_profit_factor is not None
        and metric.remove_top_five_profit_factor >= 1.00
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.00
        and ci_low is not None
        and ci_low > 0
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25)
        and (metric.top_five_session_profit_share is None or metric.top_five_session_profit_share <= 0.45)
    )


def _attach(signals: pd.DataFrame, causal: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    return horizon_mod.attach_exact_horizon(signals, causal, EXIT_HORIZON_MINUTES, fold_id)


def _write_ledger(frames: list[pd.DataFrame], path: Path) -> None:
    if not frames:
        return
    ledger = pd.concat(frames, ignore_index=True, sort=False)
    keep = [
        "partition",
        "control",
        "fold_id",
        "mechanism",
        "session_id",
        "timestamp",
        "exit_timestamp",
        "expired_instrument_key",
        "expiry_id",
        "option_type",
        "strike",
        "entry_price_next_open",
        "exit_close",
        "gross_return_pct",
        "net_return_pct",
        "stress_return_pct",
        "label_horizon_minutes",
        "control_option_type",
        "control_expired_instrument_key",
        "prior_5m_return_pct",
        "mirror_return",
        "return_acceleration",
        "mirror_acceleration",
        "mirror_turn",
        "joint_wing_return",
        "dominance",
        "dominance_delta",
        "prior_5m_volume_ratio",
        "mirror_volume_ratio",
        "oi_change_ratio",
        "breadth_positive",
        "surface_return_dispersion",
        "days_to_expiry",
        "minute_of_day",
    ]
    ledger[[column for column in keep if column in ledger.columns]].to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    event_path = root / PRIOR_REL / EVENT_FILE
    out = root / OUT_REL
    research_dir = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)

    causal = prepare_causal(event_path)
    partitions = splitmod.partition_sessions(causal)
    folds = splitmod.expanding_folds(partitions["research"])
    contract = {
        "schema_version": "joint_wing_volatility_resolution_v1",
        "hypothesis": "joint_ce_pe_expansion_resolves_into_a_persistent_directional_wing",
        "mechanisms": list(MECHANISMS),
        "mechanism_count": len(MECHANISMS),
        "cumulative_mechanisms_in_all_adaptive_campaigns": CUMULATIVE_MECHANISM_COUNT,
        "multiplicity_policy": "session_cluster_bootstrap_lower_quantile_0_05_divided_by_2_times_47",
        "entry": "next_same_contract_open_of_persistent_wing_after_completed_signal_candle",
        "exit_horizon_minutes": EXIT_HORIZON_MINUTES,
        "research_sessions": len(partitions["research"]),
        "validation_sessions": len(partitions["validation"]),
        "master_holdout_sessions": len(partitions["master_holdout"]),
        "master_holdout_policy": "latest_15pct_sessions_sealed_and_never_materialized",
        "normal_cost_pct": metrics_mod.NORMAL_COST_PCT,
        "stress_cost_pct": metrics_mod.STRESS_COST_PCT,
        "controls": ["same_strike_opposite_wing", "target_entry_delayed_five_minutes"],
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)
    stable_json(
        out / "session_partitions.json",
        {
            "research": partitions["research"],
            "validation": partitions["validation"],
            "master_holdout_count": len(partitions["master_holdout"]),
            "master_holdout_sha256": semantic_hash(partitions["master_holdout"]),
            "master_holdout_sessions_redacted": True,
        },
    )

    primary_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    delayed_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    mirror_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    fold_thresholds: list[dict[str, Any]] = []
    evidence_frames: list[pd.DataFrame] = []

    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = thresholds(training)
        fold_thresholds.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "thresholds": cut})
        masks = mechanism_masks(testing, cut)
        for mechanism in MECHANISMS:
            candidates = build_candidates(testing, masks[mechanism], mechanism, testing_sessions)
            delayed_target = fixed_delay.shift_signal_entry(candidates, testing, 5)
            mirror_control = mirror_control_signals(candidates)
            primary = _attach(candidates, testing, fold_id)
            delayed = _attach(delayed_target, testing, fold_id)
            mirror = _attach(mirror_control, testing, fold_id)
            if not primary.empty:
                primary["mechanism"] = mechanism
                primary_ledgers[mechanism].append(primary)
            if not delayed.empty:
                delayed["mechanism"] = mechanism + "__delayed_target_control"
                delayed_ledgers[mechanism].append(delayed)
            if not mirror.empty:
                mirror["mechanism"] = mechanism + "__mirror_control"
                mirror_ledgers[mechanism].append(mirror)
    stable_json(out / "fold_thresholds.json", fold_thresholds)

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
        oof_records.append(
            {
                "mechanism": mechanism,
                **asdict(primary_metric),
                "multiplicity_adjusted_cluster_bootstrap_ci_low": ci_low,
                "delayed_target_control": asdict(delayed_metric),
                "mirror_control": asdict(mirror_metric),
                "economic_gate": economic_pass,
                "control_gate": controls_pass,
                "oof_gate": passed,
            }
        )
        if not primary.empty:
            evidence_frames.append(primary.assign(partition="research_oof", control="primary_persistent_wing"))
        if not delayed.empty:
            evidence_frames.append(delayed.assign(partition="research_oof", control="delayed_target_5m"))
        if not mirror.empty:
            evidence_frames.append(mirror.assign(partition="research_oof", control="same_strike_mirror"))
        if passed and ci_low is not None:
            survivors.append((mechanism, primary_metric, ci_low))

    survivors = sorted(
        survivors,
        key=lambda item: (
            item[2],
            item[1].remove_top_five_profit_factor or -math.inf,
            item[1].trades,
            item[0],
        ),
        reverse=True,
    )[:1]
    survivor_names = [name for name, _, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "validation_survivors_frozen": survivor_names})

    validation_records: list[dict[str, Any]] = []
    validation_survivors: list[str] = []
    if survivor_names:
        final_cut = thresholds(causal.loc[causal["session_id"].isin(partitions["research"])])
        validation = causal.loc[causal["session_id"].isin(partitions["validation"])]
        masks = mechanism_masks(validation, final_cut)
        for mechanism in survivor_names:
            candidates = build_candidates(validation, masks[mechanism], mechanism, partitions["validation"])
            delayed_target = fixed_delay.shift_signal_entry(candidates, validation, 5)
            mirror_control = mirror_control_signals(candidates)
            primary = _attach(candidates, validation, "validation")
            delayed = _attach(delayed_target, validation, "validation")
            mirror = _attach(mirror_control, validation, "validation")
            primary_metric = metrics_mod.calculate_metrics(primary)
            delayed_metric = metrics_mod.calculate_metrics(delayed)
            mirror_metric = metrics_mod.calculate_metrics(mirror)
            ci_low = adjusted_ci_low(primary, 1)
            economic_pass = validation_gate(primary_metric, ci_low)
            controls_pass = control_gate(primary_metric, delayed_metric, mirror_metric) if economic_pass else False
            passed = economic_pass and controls_pass
            validation_records.append(
                {
                    "mechanism": mechanism,
                    **asdict(primary_metric),
                    "session_cluster_bootstrap_ci_low": ci_low,
                    "delayed_target_control": asdict(delayed_metric),
                    "mirror_control": asdict(mirror_metric),
                    "economic_gate": economic_pass,
                    "control_gate": controls_pass,
                    "validation_gate": passed,
                }
            )
            if not primary.empty:
                evidence_frames.append(primary.assign(partition="validation", control="primary_persistent_wing"))
            if not delayed.empty:
                evidence_frames.append(delayed.assign(partition="validation", control="delayed_target_5m"))
            if not mirror.empty:
                evidence_frames.append(mirror.assign(partition="validation", control="same_strike_mirror"))
            if passed:
                validation_survivors.append(mechanism)
    stable_json(
        out / "validation_screen.json",
        {
            "records": validation_records,
            "validation_survivors": validation_survivors,
            "master_holdout_outcomes_materialized": False,
        },
    )
    _write_ledger(evidence_frames, out / "trade_ledger.csv")

    verdict = (
        "PROMISING_HIGH_OCCURRENCE_JOINT_WING_RESOLUTION_MASTER_HOLDOUT_UNOPENED"
        if validation_survivors
        else (
            "NO_MULTIPLICITY_ADJUSTED_OOF_SURVIVOR_IN_JOINT_WING_RESOLUTION_FAMILY"
            if not survivor_names
            else "JOINT_WING_RESOLUTION_OOF_SURVIVOR_FAILED_VALIDATION"
        )
    )
    final = {
        "principal_verdict": verdict,
        "oof_survivors": survivor_names,
        "validation_survivors": validation_survivors,
        "cumulative_mechanisms_tested": CUMULATIVE_MECHANISM_COUNT,
        "master_holdout_outcomes_materialized": False,
        "master_holdout_status": "SEALED_FOR_CROSS_FAMILY_FINAL_CERTIFICATION",
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "contract_semantic_sha256": contract["semantic_sha256"],
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    final["semantic_sha256"] = semantic_hash(final)
    stable_json(out / "final_decision.json", final)
    (research_dir / "RESULT.md").write_text(
        "# Joint-Wing Volatility Resolution V1\n\n"
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
