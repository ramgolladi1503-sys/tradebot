from __future__ import annotations

import numpy as np
import pandas as pd

from research.macd_futures_participation_regime_v1.analysis import CampaignBlocked

CONTROL_SCHEMA = "MACD_FUTURES_PARTICIPATION_REGIME_V1_CONTROLS"
CONTROL_SEED = 20260908
SIGN_FLIP_REPS = 20000


def _validate(per_signal: pd.DataFrame) -> pd.DataFrame:
    required = {
        "signal_trade_id",
        "signal_session_date",
        "signal_state",
        "delta_net_6bps",
    }
    missing = sorted(required - set(per_signal.columns))
    if missing:
        raise CampaignBlocked(f"CONTROL_SCHEMA_MISSING:{','.join(missing)}")
    if per_signal.empty:
        raise CampaignBlocked("CONTROL_EMPTY_PER_SIGNAL")
    df = per_signal.copy()
    df["signal_session_date"] = df["signal_session_date"].astype(str)
    df["delta_net_6bps"] = pd.to_numeric(df["delta_net_6bps"], errors="coerce")
    if df["delta_net_6bps"].isna().any():
        raise CampaignBlocked("CONTROL_INVALID_DELTA")
    return df


def condition_removal_control(per_signal: pd.DataFrame) -> dict:
    """Compare state-conditioned delta with the unconditional MACD delta.

    This is a mechanism ablation, not a new optimization. A state that does not
    improve signal-specific separation over the unconditional candidate should
    not be credited merely because MACD itself is positive.
    """
    df = _validate(per_signal)
    active = df[df["signal_state"] == True]  # noqa: E712
    inactive = df[df["signal_state"] == False]  # noqa: E712
    if active.empty or inactive.empty:
        raise CampaignBlocked("CONTROL_REQUIRES_ACTIVE_AND_INACTIVE_SIGNALS")

    unconditional = float(df["delta_net_6bps"].mean())
    active_delta = float(active["delta_net_6bps"].mean())
    inactive_delta = float(inactive["delta_net_6bps"].mean())
    return {
        "control": "CONDITION_REMOVAL",
        "signal_trades": int(len(df)),
        "active_signal_trades": int(len(active)),
        "inactive_signal_trades": int(len(inactive)),
        "unconditional_delta_net_6bps": unconditional,
        "active_delta_net_6bps": active_delta,
        "inactive_delta_net_6bps": inactive_delta,
        "active_minus_unconditional_bps": float(active_delta - unconditional),
        "interaction_lift_bps": float(active_delta - inactive_delta),
        "condition_adds_point_estimate_information": bool(
            active_delta > unconditional and active_delta > inactive_delta
        ),
        "claim_boundary": "descriptive ablation; not standalone significance proof",
    }


def session_cluster_sign_flip_control(
    per_signal: pd.DataFrame,
    *,
    reps: int = SIGN_FLIP_REPS,
    seed: int = CONTROL_SEED,
) -> dict:
    """One-sided session-cluster randomization test for active-state delta > 0.

    All active trades in a session are first reduced to one session mean. Random
    signs are then applied at the session level, avoiding row-level IID claims.
    """
    df = _validate(per_signal)
    active = df[df["signal_state"] == True].copy()  # noqa: E712
    if active.empty:
        raise CampaignBlocked("CONTROL_NO_ACTIVE_SIGNALS")
    session_means = (
        active.groupby("signal_session_date", as_index=False)["delta_net_6bps"]
        .mean()["delta_net_6bps"]
        .to_numpy(dtype=float)
    )
    if len(session_means) < 2:
        raise CampaignBlocked("CONTROL_INSUFFICIENT_ACTIVE_SESSIONS")

    observed = float(session_means.mean())
    rng = np.random.default_rng(seed)
    # Chunk to avoid allocating reps x sessions for unusually large campaigns.
    exceed = 0
    generated = 0
    chunk = 2000
    while generated < reps:
        n = min(chunk, reps - generated)
        signs = rng.choice(np.array([-1.0, 1.0]), size=(n, len(session_means)))
        null_means = (signs * session_means).mean(axis=1)
        exceed += int((null_means >= observed).sum())
        generated += n
    p_one_sided = float((exceed + 1) / (reps + 1))

    return {
        "control": "SESSION_CLUSTER_SIGN_FLIP_ACTIVE_DELTA",
        "active_signal_sessions": int(len(session_means)),
        "observed_active_session_mean_delta_bps": observed,
        "reps": int(reps),
        "seed": int(seed),
        "null_exceedances": int(exceed),
        "empirical_p_one_sided": p_one_sided,
        "passes_nominal_0_05": bool(observed > 0 and p_one_sided < 0.05),
        "claim_boundary": (
            "session-cluster symmetry randomization control; global multiplicity/FDR remains separate"
        ),
    }


def controls_bundle(per_signal: pd.DataFrame) -> dict:
    return {
        "schema": CONTROL_SCHEMA,
        "condition_removal": condition_removal_control(per_signal),
        "session_cluster_sign_flip": session_cluster_sign_flip_control(per_signal),
        "global_multiplicity_applied": False,
        "basis_timing_permutation_applied": False,
        "delay_sensitivity_applied": False,
        "structural_edge_certified": False,
    }
