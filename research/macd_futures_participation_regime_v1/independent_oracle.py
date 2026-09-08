from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

SCHEMA_VERSION = "MACD_FUTURES_PARTICIPATION_REGIME_V1_INDEPENDENT_ORACLE"


def _mean(values: pd.Series) -> float | None:
    if len(values) == 0:
        return None
    value = float(pd.to_numeric(values, errors="raise").mean())
    return value if np.isfinite(value) else None


def _semantic_hash(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_primary_ledger(
    per_signal: pd.DataFrame,
    reported: dict[str, Any],
    tol: float = 1e-9,
) -> dict:
    """Independent arithmetic oracle; deliberately imports no primary gate code."""
    required = {
        "signal_trade_id",
        "signal_session_date",
        "signal_state",
        "signal_net_6bps",
        "placebo_mean_net_6bps",
        "delta_net_6bps",
        "compatible_placebo_n",
    }
    missing = sorted(required - set(per_signal.columns))
    failures: list[str] = []
    if missing:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "FAIL",
            "failures": [f"MISSING_COLUMNS:{','.join(missing)}"],
        }

    x = per_signal.copy()
    if x["signal_trade_id"].astype(str).duplicated().any():
        failures.append("DUPLICATE_SIGNAL_TRADE_ID")
    if x["signal_state"].isna().any():
        failures.append("UNKNOWN_SIGNAL_STATE")

    compatible = pd.to_numeric(x["compatible_placebo_n"], errors="coerce")
    if compatible.isna().any() or (compatible <= 0).any():
        failures.append("INVALID_COMPATIBLE_PLACEBO_COUNT")

    sig = pd.to_numeric(x["signal_net_6bps"], errors="coerce")
    pla = pd.to_numeric(x["placebo_mean_net_6bps"], errors="coerce")
    delta = pd.to_numeric(x["delta_net_6bps"], errors="coerce")
    if sig.isna().any() or pla.isna().any() or delta.isna().any():
        failures.append("NON_NUMERIC_PAYOFF")
    elif not np.allclose((sig - pla).to_numpy(), delta.to_numpy(), atol=tol, rtol=0):
        failures.append("DELTA_IDENTITY_FAIL")

    state = x["signal_state"].astype(bool)
    active = x[state]
    inactive = x[~state]
    active_delta = _mean(active["delta_net_6bps"])
    inactive_delta = _mean(inactive["delta_net_6bps"])
    lift = (
        float(active_delta - inactive_delta)
        if active_delta is not None and inactive_delta is not None
        else None
    )
    active_sessions = int(active["signal_session_date"].astype(str).nunique())

    summary = reported.get("summary", {})
    checks = {
        "active_signal_sessions": (active_sessions, summary.get("active_signal_sessions")),
        "active_delta_net_6bps": (active_delta, summary.get("active_delta_net_6bps")),
        "inactive_delta_net_6bps": (inactive_delta, summary.get("inactive_delta_net_6bps")),
        "interaction_lift_bps": (lift, summary.get("interaction_lift_bps")),
    }
    for name, (actual, expected) in checks.items():
        if actual is None or expected is None:
            if actual != expected:
                failures.append(f"{name}:NULL_MISMATCH")
        elif isinstance(actual, (float, np.floating)):
            if not np.isclose(float(actual), float(expected), atol=tol, rtol=0):
                failures.append(f"{name}:MISMATCH:{actual}:{expected}")
        elif actual != expected:
            failures.append(f"{name}:MISMATCH:{actual}:{expected}")

    expected_hash = reported.get("semantic_hash")
    payload = {k: v for k, v in reported.items() if k != "semantic_hash"}
    recomputed_hash = _semantic_hash(payload)
    if expected_hash != recomputed_hash:
        failures.append("SEMANTIC_HASH_MISMATCH")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "checks": {
            "signal_trade_count": int(len(x)),
            "active_signal_sessions": active_sessions,
            "active_delta_net_6bps": active_delta,
            "inactive_delta_net_6bps": inactive_delta,
            "interaction_lift_bps": lift,
        },
        "reported_semantic_hash": expected_hash,
        "recomputed_semantic_hash": recomputed_hash,
    }
