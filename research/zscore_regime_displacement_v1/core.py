from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from research.autonomous_structural_edge_exhaustion_v1 import common as A
from research.autonomous_structural_edge_exhaustion_v1.certification import (
    robustness,
    validation_and_wfa,
)
from research.autonomous_structural_edge_exhaustion_v1.outcomes import (
    _bin,
    _context_thresholds,
    baseline_table,
    build_outcome_lookup,
    summarize,
)

CAMPAIGN = "zscore_regime_displacement_v1"
SCHEMA_VERSION = 1
ZSCORE_WINDOW = 12
EXTREME_Z = 2.0
REENTRY_Z = 1.5
HORIZONS = (3, 6)
FAMILY = "ZSCORE_REGIME_DISPLACEMENT"

HYPOTHESIS_SPECS: tuple[dict[str, Any], ...] = (
    {
        "mechanism": "EXTREME_REENTRY_CROSS_SECTIONAL_DISAGREEMENT",
        "description": (
            "A >=2 sigma NIFTY displacement fails to persist, re-enters inside 1.5 sigma, "
            "and the extreme bar was not confirmed by constituent breadth."
        ),
    },
    {
        "mechanism": "EXTREME_CONTINUATION_PARTICIPATION_CONFIRMATION",
        "description": (
            "A >=2 sigma NIFTY displacement is confirmed by same-direction breadth and "
            "same-direction high-volume constituent participation."
        ),
    },
)


def structural_screen(outcomes: Mapping[str, Any]) -> dict[str, Any]:
    """Inherited PR806 screen with predeclared-direction observation gate."""
    rows: list[dict[str, Any]] = []
    pvalues: list[float] = []
    for record in outcomes.get("records", []):
        obs = record["stats"]["observation"]["directional_excess"]
        rep = record["stats"]["replication"]["directional_excess"]
        pvalues.append(float(rep["sign_p"]))
        rows.append(
            {
                "hypothesis_id": record["hypothesis"]["hypothesis_id"],
                "family": record["hypothesis"]["family"],
                "observation": obs,
                "replication": rep,
            }
        )
    qvalues = A.PA.bh_qvalues(pvalues)
    survivors: list[str] = []
    for row, q in zip(rows, qvalues):
        obs, rep = row["observation"], row["replication"]
        gates = {
            "observation_n_ge_20": obs["n"] >= 20,
            "observation_directional_mean_ge_2bps": float(obs["mean_bps"] or -1e9) >= 2.0,
            "replication_n_ge_10": rep["n"] >= 10,
            "replication_mean_ge_2bps": float(rep["mean_bps"] or -1e9) >= 2.0,
            "replication_hit_rate_ge_55pct": float(rep["hit_rate"] or 0.0) >= 0.55,
            "replication_ci90_lower_positive": (
                rep["ci90"][0] is not None and float(rep["ci90"][0]) > 0.0
            ),
            "global_bh_q_le_10pct": float(q) <= 0.10,
        }
        row["bh_q"] = float(q)
        row["gates"] = gates
        row["passed"] = all(gates.values())
        if row["passed"]:
            survivors.append(str(row["hypothesis_id"]))
    catalog = {
        "principal_verdict": (
            "ZSCORE_STRUCTURAL_SCREEN_SURVIVORS"
            if survivors
            else "NO_ZSCORE_STRUCTURAL_EDGE_CANDIDATE_SURVIVED_SCREEN"
        ),
        "global_hypothesis_count": len(rows),
        "survivor_hypothesis_ids": survivors,
        "results": rows,
        "policy": {
            "global_multiple_testing_correction": "BENJAMINI_HOCHBERG",
            "direction_predeclared": True,
            "unopened_sessions_scored": False,
        },
    }
    catalog["semantic_sha256"] = A.digest(catalog)
    return catalog


def _prior_window_z(values: pd.Series, window: int = ZSCORE_WINDOW) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    prior_mean = numeric.shift(1).rolling(window, min_periods=window).mean()
    prior_std = numeric.shift(1).rolling(window, min_periods=window).std(ddof=0)
    z = (numeric - prior_mean) / prior_std.replace(0.0, np.nan)
    return z.replace([np.inf, -np.inf], np.nan)


def add_causal_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    """Add a completed-bar z-score against only the prior 12 completed 5m closes."""
    parts: list[pd.DataFrame] = []
    for _, group in frame.groupby("session_date", sort=True):
        g = group.sort_values("timestamp", kind="mergesort").copy()
        g["price_z12"] = _prior_window_z(g["index_close"], ZSCORE_WINDOW)
        parts.append(g)
    if not parts:
        return frame.assign(price_z12=np.nan)
    return pd.concat(parts, ignore_index=True).sort_values(
        ["session_date", "timestamp"], kind="mergesort"
    ).reset_index(drop=True)


def freeze_hypotheses() -> dict[str, Any]:
    hypotheses: list[dict[str, Any]] = []
    for spec in HYPOTHESIS_SPECS:
        for horizon in HORIZONS:
            item = {
                "hypothesis_id": f"ZRDV1::{spec['mechanism']}::H{horizon}",
                "family": FAMILY,
                "mechanism": spec["mechanism"],
                "description": spec["description"],
                "zscore_window_bars": ZSCORE_WINDOW,
                "extreme_z": EXTREME_Z,
                "reentry_z": REENTRY_Z,
                "horizon_bars": int(horizon),
                "horizon_minutes": int(horizon * 5),
                "signal_definition": "first_chronological_completed_bar_event_per_session",
                "entry_delay_bars": 1,
                "direction_rule": (
                    "opposite_extreme_sign"
                    if spec["mechanism"] == "EXTREME_REENTRY_CROSS_SECTIONAL_DISAGREEMENT"
                    else "same_as_extreme_sign"
                ),
                "direction_selected_from_outcomes": False,
                "outcomes_seen_when_frozen": False,
                "unopened_sessions_scored": False,
            }
            item["semantic_sha256"] = A.digest(item)
            hypotheses.append(item)
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "campaign": CAMPAIGN,
        "principal_verdict": "ZSCORE_MECHANISM_HYPOTHESES_FROZEN_BEFORE_OUTCOMES",
        "hypothesis_count": len(hypotheses),
        "hypotheses": hypotheses,
        "policy": {
            "thresholds_predeclared": True,
            "direction_predeclared": True,
            "outcomes_seen_when_frozen": False,
            "future_returns_calculated": False,
            "unopened_sessions_scored": False,
            "post_result_threshold_tuning_authorized": False,
        },
    }
    catalog["semantic_sha256"] = A.digest(catalog)
    return catalog


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _reversal_event(previous: Any, current: Any) -> tuple[bool, int]:
    prior_z = float(previous.price_z12) if pd.notna(previous.price_z12) else float("nan")
    current_z = float(current.price_z12) if pd.notna(current.price_z12) else float("nan")
    breadth = (
        float(previous.breadth_imbalance)
        if pd.notna(previous.breadth_imbalance)
        else float("nan")
    )
    if not (math.isfinite(prior_z) and math.isfinite(current_z) and math.isfinite(breadth)):
        return False, 0
    extreme_sign = _sign(prior_z)
    if extreme_sign == 0 or abs(prior_z) < EXTREME_Z:
        return False, 0
    if abs(current_z) > REENTRY_Z:
        return False, 0
    if abs(current_z) >= abs(prior_z):
        return False, 0
    disagreement = extreme_sign * breadth <= 0.0
    return disagreement, -extreme_sign if disagreement else 0


def _continuation_event(current: Any) -> tuple[bool, int]:
    z = float(current.price_z12) if pd.notna(current.price_z12) else float("nan")
    breadth = (
        float(current.breadth_imbalance)
        if pd.notna(current.breadth_imbalance)
        else float("nan")
    )
    shock_share = (
        float(current.volume_shock_share)
        if pd.notna(current.volume_shock_share)
        else float("nan")
    )
    hv_signed = (
        float(current.high_volume_signed_mean)
        if pd.notna(current.high_volume_signed_mean)
        else float("nan")
    )
    if not all(map(math.isfinite, (z, breadth, shock_share, hv_signed))):
        return False, 0
    direction = _sign(z)
    if direction == 0 or abs(z) < EXTREME_Z:
        return False, 0
    aligned = direction * breadth > 0.0 and direction * hv_signed > 0.0
    participation = shock_share > 0.0
    return aligned and participation, direction if aligned and participation else 0


def signal_table(frame: pd.DataFrame) -> dict[str, dict[str, dict[str, Any]]]:
    """Return first causal signal per session for each frozen mechanism."""
    result: dict[str, dict[str, dict[str, Any]]] = {
        spec["mechanism"]: {} for spec in HYPOTHESIS_SPECS
    }
    for session_date, group in frame.groupby("session_date", sort=True):
        g = group.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        for idx in range(len(g)):
            current = g.iloc[idx]
            if str(session_date) not in result["EXTREME_CONTINUATION_PARTICIPATION_CONFIRMATION"]:
                ok, direction = _continuation_event(current)
                if ok:
                    result["EXTREME_CONTINUATION_PARTICIPATION_CONFIRMATION"][str(session_date)] = {
                        "timestamp": pd.Timestamp(current["timestamp"]),
                        "direction": int(direction),
                        "z": float(current["price_z12"]),
                    }
            if idx == 0:
                continue
            if str(session_date) not in result["EXTREME_REENTRY_CROSS_SECTIONAL_DISAGREEMENT"]:
                previous = g.iloc[idx - 1]
                ok, direction = _reversal_event(previous, current)
                if ok:
                    result["EXTREME_REENTRY_CROSS_SECTIONAL_DISAGREEMENT"][str(session_date)] = {
                        "timestamp": pd.Timestamp(current["timestamp"]),
                        "direction": int(direction),
                        "extreme_timestamp": str(pd.Timestamp(previous["timestamp"])),
                        "extreme_z": float(previous["price_z12"]),
                        "reentry_z": float(current["price_z12"]),
                    }
    return result


def attach_development_outcomes(
    hypotheses: Mapping[str, Any],
    frame: pd.DataFrame,
    splits: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Attach outcomes only for observation/replication/validation; unopened remains sealed."""
    allowed = {"observation", "replication", "validation"}
    lookup = build_outcome_lookup(frame, allowed)
    cuts = _context_thresholds(frame)
    baseline = baseline_table(frame, lookup, cuts)
    signals = signal_table(frame)
    split_map = {str(day): split for split, days in splits.items() for day in days}
    records: list[dict[str, Any]] = []

    for hypothesis in hypotheses.get("hypotheses", []):
        mechanism = str(hypothesis["mechanism"])
        horizon = int(hypothesis["horizon_bars"])
        events: list[dict[str, Any]] = []
        for session_date, signal in signals.get(mechanism, {}).items():
            split = split_map.get(str(session_date), "excluded")
            if split not in allowed:
                continue
            signal_ts = pd.Timestamp(signal["timestamp"])
            outcome = lookup.get((str(session_date), int(signal_ts.value), horizon))
            if outcome is None:
                continue
            progress_bin = int(
                np.clip(math.floor(float(outcome["session_progress"]) * 10), 0, 9)
            )
            mom_bin = _bin(float(outcome["index_ret3"]), cuts["index_ret3"])
            vol_bin = _bin(float(outcome["index_vol6"]), cuts["index_vol6"])
            baseline_value = baseline.get((horizon, progress_bin, mom_bin, vol_bin))
            if baseline_value is None:
                continue
            direction = int(signal["direction"])
            raw_return = float(outcome["raw_return_bps"])
            raw_excess = raw_return - float(baseline_value)
            event = {
                "session_date": str(session_date),
                "split": split,
                **dict(outcome),
                "direction": direction,
                "baseline_return_bps": float(baseline_value),
                "raw_excess_bps": raw_excess,
                "directional_excess_bps": direction * raw_excess,
                "directional_gross_bps": direction * raw_return,
                "net_proxy_bps": direction * raw_return - A.COST_BPS,
                "delayed_net_proxy_bps": (
                    direction * float(outcome["delayed_raw_return_bps"]) - A.COST_BPS
                    if outcome.get("delayed_raw_return_bps") is not None
                    else None
                ),
                "shorter_net_proxy_bps": (
                    direction * float(outcome["shorter_raw_return_bps"]) - A.COST_BPS
                    if outcome.get("shorter_raw_return_bps") is not None
                    else None
                ),
                "longer_net_proxy_bps": (
                    direction * float(outcome["longer_raw_return_bps"]) - A.COST_BPS
                    if outcome.get("longer_raw_return_bps") is not None
                    else None
                ),
                "signal_z": float(signal.get("z", signal.get("reentry_z", np.nan))),
            }
            events.append(event)

        by_split: dict[str, Any] = {}
        for split in ("observation", "replication", "validation"):
            split_events = [e for e in events if e["split"] == split]
            by_split[split] = {
                "directional_excess": summarize(
                    [e["directional_excess_bps"] for e in split_events]
                ),
                "net_proxy": summarize([e["net_proxy_bps"] for e in split_events]),
            }
        records.append(
            {
                "hypothesis": {
                    **dict(hypothesis),
                    "direction_selected_from_observation_only": 0,
                    "direction_is_event_mechanical": True,
                },
                "stats": by_split,
                "events": events,
            }
        )

    catalog = {
        "principal_verdict": "ZSCORE_DEVELOPMENT_OUTCOMES_ATTACHED_UNOPENED_SEALED",
        "records": records,
        "context_thresholds": cuts,
        "baseline_cell_count": len(baseline),
        "outcome_lookup_count": len(lookup),
        "policy": {
            "allowed_outcome_splits": sorted(allowed),
            "unopened_sessions_scored": False,
            "direction_fit_scope": "NOT_FIT_MECHANICAL_FROM_EVENT_SIGN",
            "baseline_fit_scope": "observation_only",
            "pre_post_cas_pooled": False,
        },
    }
    catalog["semantic_sha256"] = A.digest(
        {
            "records": [
                {"hypothesis": r["hypothesis"], "stats": r["stats"]} for r in records
            ],
            "context_thresholds": cuts,
        }
    )
    return catalog


def final_authority(
    hypotheses: Mapping[str, Any],
    outcomes: Mapping[str, Any],
    screen: Mapping[str, Any],
    wfa: Mapping[str, Any],
    robust: Mapping[str, Any],
) -> dict[str, Any]:
    robust_ids = list(map(str, robust.get("survivor_hypothesis_ids", [])))
    if robust_ids:
        verdict = "ZSCORE_ROBUSTNESS_SURVIVOR_UNOPENED_TAIL_STILL_SEALED"
    else:
        verdict = "NO_ZSCORE_HYPOTHESIS_SURVIVED_DEVELOPMENT_CERTIFICATION"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "campaign": CAMPAIGN,
        "principal_verdict": verdict,
        "hypothesis_count": int(hypotheses.get("hypothesis_count", 0)),
        "structural_screen_survivors": list(
            map(str, screen.get("survivor_hypothesis_ids", []))
        ),
        "validation_wfa_survivors": list(
            map(str, wfa.get("survivor_hypothesis_ids", []))
        ),
        "robustness_survivors": robust_ids,
        "unopened_sessions_scored": False,
        "unopened_tail_access_authorized": False,
        "post_result_threshold_tuning_authorized": False,
        "options_edge_certified": False,
        "shadow_authorized": False,
        "paper_authorized": False,
        "live_authorized": False,
        "order_authorized": False,
        "claim_boundary": (
            "Development evidence only. A robustness survivor requires an independent "
            "one-shot sealed-tail procedure before any structural-edge claim."
        ),
        "semantic_inputs": {
            "hypotheses": hypotheses.get("semantic_sha256"),
            "outcomes": outcomes.get("semantic_sha256"),
            "screen": screen.get("semantic_sha256"),
            "wfa": wfa.get("semantic_sha256"),
            "robustness": robust.get("semantic_sha256"),
        },
    }
    payload["semantic_sha256"] = A.digest(payload)
    return payload


def run_development(source_file: str) -> dict[str, Any]:
    from pathlib import Path

    path = Path(source_file)
    source = A.verify_source(path)
    raw = A.canonicalize_source(path)
    index_rows, accepted = A.accepted_index_sessions(raw)
    splits = A.split_sessions(accepted)
    universe = A.select_observation_universe(raw, index_rows, splits)
    cross = A.build_cross_sectional_frame(
        raw, index_rows, universe["selected_symbols"], accepted
    )
    cross = A.add_split_column(cross, splits)
    cross = add_causal_zscore(cross)

    hypotheses = freeze_hypotheses()
    outcomes = attach_development_outcomes(hypotheses, cross, splits)
    screen = structural_screen(outcomes)
    wfa = validation_and_wfa(outcomes, screen)
    robust = robustness(outcomes, wfa)
    authority = final_authority(hypotheses, outcomes, screen, wfa, robust)

    return {
        "stage0_source_authority": {
            "principal_verdict": "PINNED_PRE_CAS_SOURCE_VERIFIED",
            **source,
            "accepted_sessions": len(accepted),
            "splits": {k: len(v) for k, v in splits.items()},
            "unopened_sessions_scored": False,
        },
        "stage1_universe": universe,
        "stage2_hypotheses": hypotheses,
        "stage3_development_outcomes": outcomes,
        "stage4_structural_screen": screen,
        "stage5_validation_wfa": wfa,
        "stage6_robustness": robust,
        "final_authority": authority,
    }
