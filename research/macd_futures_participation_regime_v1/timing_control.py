from __future__ import annotations

import numpy as np
import pandas as pd

from research.macd_futures_participation_regime_v1.analysis import CampaignBlocked
from research.macd_futures_participation_regime_v1.matching import (
    MIN_COMPATIBLE_PLACEBOS_PER_SIGNAL,
)

TIMING_CONTROL_SEED = 20260908
TIMING_CONTROL_REPS = 1000
MIN_VALID_REP_FRACTION = 0.80


def _to_ist(series: pd.Series, label: str) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.isna().any():
        raise CampaignBlocked(f"TIMING_CONTROL_INVALID_TIMESTAMP:{label}")
    if ts.dt.tz is None:
        return ts.dt.tz_localize(
            "Asia/Kolkata", ambiguous="raise", nonexistent="raise"
        )
    return ts.dt.tz_convert("Asia/Kolkata")


def _validate_primary(per_signal: pd.DataFrame) -> tuple[float, float]:
    required = {"signal_state", "delta_net_6bps"}
    missing = sorted(required - set(per_signal.columns))
    if missing:
        raise CampaignBlocked(
            f"TIMING_CONTROL_PRIMARY_SCHEMA_MISSING:{','.join(missing)}"
        )
    active = per_signal[per_signal["signal_state"] == True]  # noqa: E712
    inactive = per_signal[per_signal["signal_state"] == False]  # noqa: E712
    if active.empty or inactive.empty:
        raise CampaignBlocked("TIMING_CONTROL_REQUIRES_ACTIVE_AND_INACTIVE")
    active_delta = float(pd.to_numeric(active["delta_net_6bps"]).mean())
    inactive_delta = float(pd.to_numeric(inactive["delta_net_6bps"]).mean())
    return active_delta, float(active_delta - inactive_delta)


def _known_state_index(state: pd.DataFrame, state_col: str):
    required = {"timestamp", "session_date", state_col}
    missing = sorted(required - set(state.columns))
    if missing:
        raise CampaignBlocked(
            f"TIMING_CONTROL_STATE_SCHEMA_MISSING:{','.join(missing)}"
        )
    known = state[state[state_col].notna()][
        ["timestamp", "session_date", state_col]
    ].copy()
    if known.empty:
        raise CampaignBlocked("TIMING_CONTROL_NO_KNOWN_STATE_ROWS")
    known["timestamp"] = _to_ist(known["timestamp"], "STATE")
    known["session_date"] = known["session_date"].astype(str)
    known = known.sort_values(
        ["session_date", "timestamp"], kind="stable"
    ).reset_index(drop=True)
    if known.duplicated("timestamp").any():
        raise CampaignBlocked("TIMING_CONTROL_DUPLICATE_STATE_TIMESTAMPS")

    session_names = sorted(known["session_date"].unique())
    session_to_code = {s: i for i, s in enumerate(session_names)}
    known["session_code"] = known["session_date"].map(session_to_code).astype(int)
    known["position"] = known.groupby("session_code", sort=False).cumcount().astype(int)

    lengths = (
        known.groupby("session_code", sort=True).size().reindex(range(len(session_names))).to_numpy(dtype=int)
    )
    starts = np.zeros(len(lengths), dtype=int)
    if len(lengths) > 1:
        starts[1:] = np.cumsum(lengths[:-1])
    flat_state = known[state_col].astype(bool).to_numpy(dtype=bool)
    return known, lengths, starts, flat_state


def _attach_positions(
    origins: pd.DataFrame,
    origin_col: str,
    known: pd.DataFrame,
    label: str,
) -> pd.DataFrame:
    out = origins.copy()
    out[origin_col] = _to_ist(out[origin_col], label)
    lookup = known[["timestamp", "session_code", "position"]]
    out = out.merge(
        lookup,
        left_on=origin_col,
        right_on="timestamp",
        how="left",
        validate="many_to_one",
    )
    if out["timestamp"].isna().any():
        raise CampaignBlocked(
            f"TIMING_CONTROL_ORIGIN_STATE_UNAVAILABLE:{label}:"
            f"{int(out['timestamp'].isna().sum())}"
        )
    return out


def within_session_circular_state_shift_control(
    *,
    signals: pd.DataFrame,
    assigned: pd.DataFrame,
    state: pd.DataFrame,
    state_col: str,
    primary_per_signal: pd.DataFrame,
    reps: int = TIMING_CONTROL_REPS,
    seed: int = TIMING_CONTROL_SEED,
    minimum_compatible: int = MIN_COMPATIBLE_PLACEBOS_PER_SIGNAL,
) -> dict:
    """Break state-to-signal timing while preserving within-session state shape.

    Each session's known Boolean state sequence is circularly shifted by one
    random non-zero offset per replication. This preserves the exact number and
    run structure of active labels in the session, but changes their alignment
    to MACD and placebo timestamps. State-compatible placebo matching is then
    recomputed from scratch for every replication.
    """
    signal_required = {"signal_trade_id", "signal_origin", "net_6bps"}
    assigned_required = {
        "signal_trade_id",
        "matched_placebo_origin",
        "net_6bps",
    }
    if not signal_required.issubset(signals.columns):
        raise CampaignBlocked("TIMING_CONTROL_SIGNAL_SCHEMA_MISSING")
    if not assigned_required.issubset(assigned.columns):
        raise CampaignBlocked("TIMING_CONTROL_ASSIGNED_SCHEMA_MISSING")

    observed_active, observed_lift = _validate_primary(primary_per_signal)
    known, lengths, starts, flat_state = _known_state_index(state, state_col)

    sig = signals[["signal_trade_id", "signal_origin", "net_6bps"]].copy()
    sig["signal_trade_id"] = sig["signal_trade_id"].astype(str)
    if sig["signal_trade_id"].duplicated().any():
        raise CampaignBlocked("TIMING_CONTROL_DUPLICATE_SIGNAL_ID")
    sig = _attach_positions(sig, "signal_origin", known, "SIGNAL")
    sig = sig.reset_index(drop=True)
    sig["signal_index"] = np.arange(len(sig), dtype=int)

    ass = assigned[
        ["signal_trade_id", "matched_placebo_origin", "net_6bps"]
    ].copy()
    ass["signal_trade_id"] = ass["signal_trade_id"].astype(str)
    ass = _attach_positions(ass, "matched_placebo_origin", known, "PLACEBO")
    signal_index = sig[["signal_trade_id", "signal_index"]]
    ass = ass.merge(signal_index, on="signal_trade_id", how="left", validate="many_to_one")
    if ass["signal_index"].isna().any():
        raise CampaignBlocked("TIMING_CONTROL_ASSIGNMENT_SIGNAL_NOT_FOUND")

    sig_session = sig["session_code"].to_numpy(dtype=int)
    sig_pos = sig["position"].to_numpy(dtype=int)
    sig_net = pd.to_numeric(sig["net_6bps"], errors="coerce").to_numpy(dtype=float)
    ass_session = ass["session_code"].to_numpy(dtype=int)
    ass_pos = ass["position"].to_numpy(dtype=int)
    ass_signal_index = ass["signal_index"].to_numpy(dtype=int)
    ass_net = pd.to_numeric(ass["net_6bps"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(sig_net).any() or np.isnan(ass_net).any():
        raise CampaignBlocked("TIMING_CONTROL_INVALID_PAYOFF")

    rng = np.random.default_rng(seed)
    active_null: list[float] = []
    lift_null: list[float] = []
    invalid_thin_match = 0
    invalid_no_both_states = 0

    for _ in range(reps):
        offsets = np.array(
            [0 if length <= 1 else int(rng.integers(1, length)) for length in lengths],
            dtype=int,
        )
        sig_shift_idx = starts[sig_session] + (
            (sig_pos + offsets[sig_session]) % lengths[sig_session]
        )
        ass_shift_idx = starts[ass_session] + (
            (ass_pos + offsets[ass_session]) % lengths[ass_session]
        )
        sig_state = flat_state[sig_shift_idx]
        ass_state = flat_state[ass_shift_idx]
        compatible = ass_state == sig_state[ass_signal_index]

        compatible_signal_index = ass_signal_index[compatible]
        counts = np.bincount(
            compatible_signal_index, minlength=len(sig)
        ).astype(int)
        if len(counts) != len(sig) or (counts < minimum_compatible).any():
            invalid_thin_match += 1
            continue

        sums = np.bincount(
            compatible_signal_index,
            weights=ass_net[compatible],
            minlength=len(sig),
        )
        placebo_mean = sums / counts
        delta = sig_net - placebo_mean
        active_mask = sig_state.astype(bool)
        inactive_mask = ~active_mask
        if not active_mask.any() or not inactive_mask.any():
            invalid_no_both_states += 1
            continue

        active_delta = float(delta[active_mask].mean())
        inactive_delta = float(delta[inactive_mask].mean())
        active_null.append(active_delta)
        lift_null.append(float(active_delta - inactive_delta))

    valid = len(active_null)
    min_valid = int(np.ceil(reps * MIN_VALID_REP_FRACTION))
    if valid < min_valid:
        raise CampaignBlocked(
            "TIMING_CONTROL_INSUFFICIENT_VALID_REPS:"
            f"valid={valid}:required={min_valid}:requested={reps}"
        )

    active_arr = np.asarray(active_null, dtype=float)
    lift_arr = np.asarray(lift_null, dtype=float)
    p_active = float((1 + int((active_arr >= observed_active).sum())) / (valid + 1))
    p_lift = float((1 + int((lift_arr >= observed_lift).sum())) / (valid + 1))

    return {
        "control": "WITHIN_SESSION_CIRCULAR_FUTURES_STATE_TIMING_SHIFT",
        "state_col": state_col,
        "reps_requested": int(reps),
        "reps_valid": int(valid),
        "seed": int(seed),
        "minimum_compatible_placebos_per_signal": int(minimum_compatible),
        "invalid_thin_match_reps": int(invalid_thin_match),
        "invalid_no_both_states_reps": int(invalid_no_both_states),
        "observed_active_delta_bps": observed_active,
        "observed_interaction_lift_bps": observed_lift,
        "null_active_delta_mean_bps": float(active_arr.mean()),
        "null_interaction_lift_mean_bps": float(lift_arr.mean()),
        "null_active_delta_95pct": [
            float(x) for x in np.quantile(active_arr, [0.025, 0.975])
        ],
        "null_interaction_lift_95pct": [
            float(x) for x in np.quantile(lift_arr, [0.025, 0.975])
        ],
        "empirical_p_active_one_sided": p_active,
        "empirical_p_interaction_one_sided": p_lift,
        "passes_nominal_0_05": bool(p_active < 0.05 and p_lift < 0.05),
        "global_multiplicity_applied": False,
        "claim_boundary": (
            "timing-specific negative control; nominal p-values require global multiplicity correction before promotion"
        ),
        "structural_edge_certified": False,
    }
