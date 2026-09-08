from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

SCHEMA_VERSION = "MACD_FUTURES_PARTICIPATION_REGIME_V1_FULL_GATES"
DEFAULT_SEED = 20260908
DEFAULT_REPS = 10000
MIN_ACTIVE_SIGNAL_SESSIONS = 30
MIN_POSITIVE_FOLDS = 3
FDR_Q = 0.05


class FullGateBlocked(RuntimeError):
    """Raised when a required full-gate input cannot be evaluated truthfully."""


@dataclass(frozen=True)
class GateThresholds:
    min_active_signal_sessions: int = MIN_ACTIVE_SIGNAL_SESSIONS
    min_positive_folds: int = MIN_POSITIVE_FOLDS
    fdr_q: float = FDR_Q
    concentration_top5_abs_share_max: float = 0.60


def _require(df: pd.DataFrame, cols: Iterable[str], label: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise FullGateBlocked(f"{label}_SCHEMA_MISSING:{','.join(missing)}")


def canonicalize_per_signal(per_signal: pd.DataFrame) -> pd.DataFrame:
    _require(
        per_signal,
        [
            "signal_trade_id", "signal_origin", "signal_session_date", "signal_state",
            "signal_net_6bps", "placebo_mean_net_6bps", "delta_net_6bps",
            "compatible_placebo_n",
        ],
        "PER_SIGNAL",
    )
    out = per_signal.copy()
    out["signal_trade_id"] = out["signal_trade_id"].astype(str)
    if out["signal_trade_id"].duplicated().any():
        raise FullGateBlocked("PER_SIGNAL_DUPLICATE_SIGNAL_TRADE_ID")
    out["signal_session_date"] = out["signal_session_date"].astype(str)
    out["signal_origin"] = pd.to_datetime(out["signal_origin"], errors="coerce", utc=True)
    if out["signal_origin"].isna().any():
        raise FullGateBlocked("PER_SIGNAL_INVALID_SIGNAL_ORIGIN")
    if out["signal_state"].isna().any():
        raise FullGateBlocked("PER_SIGNAL_UNKNOWN_SIGNAL_STATE")
    out["signal_state"] = out["signal_state"].astype(bool)
    for col in ["signal_net_6bps", "placebo_mean_net_6bps", "delta_net_6bps", "compatible_placebo_n"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
        if out[col].isna().any():
            raise FullGateBlocked(f"PER_SIGNAL_NON_NUMERIC:{col}")
    if (out["compatible_placebo_n"] <= 0).any():
        raise FullGateBlocked("PER_SIGNAL_NONPOSITIVE_COMPATIBLE_PLACEBO_COUNT")
    calc = out["signal_net_6bps"] - out["placebo_mean_net_6bps"]
    if not np.allclose(calc.to_numpy(float), out["delta_net_6bps"].to_numpy(float), atol=1e-10, rtol=0):
        raise FullGateBlocked("PER_SIGNAL_DELTA_IDENTITY_FAIL")
    return out.sort_values(["signal_origin", "signal_trade_id"], kind="stable").reset_index(drop=True)


def _mean_or_none(values: pd.Series) -> float | None:
    if len(values) == 0:
        return None
    value = float(values.mean())
    return value if np.isfinite(value) else None


def _session_means(df: pd.DataFrame, value_col: str = "delta_net_6bps") -> pd.DataFrame:
    return (
        df.groupby("signal_session_date", as_index=False)
        .agg(value=(value_col, "mean"), n=("signal_trade_id", "size"))
        .sort_values("signal_session_date", kind="stable")
        .reset_index(drop=True)
    )


def interaction_summary(per_signal: pd.DataFrame) -> dict:
    x = canonicalize_per_signal(per_signal)
    active = x[x["signal_state"]]
    inactive = x[~x["signal_state"]]
    ad = _mean_or_none(active["delta_net_6bps"])
    bd = _mean_or_none(inactive["delta_net_6bps"])
    return {
        "active_signal_trades": int(len(active)),
        "active_signal_sessions": int(active["signal_session_date"].nunique()),
        "inactive_signal_trades": int(len(inactive)),
        "inactive_signal_sessions": int(inactive["signal_session_date"].nunique()),
        "active_signal_mean_net_6bps": _mean_or_none(active["signal_net_6bps"]),
        "active_placebo_mean_net_6bps": _mean_or_none(active["placebo_mean_net_6bps"]),
        "active_delta_net_6bps": ad,
        "inactive_signal_mean_net_6bps": _mean_or_none(inactive["signal_net_6bps"]),
        "inactive_placebo_mean_net_6bps": _mean_or_none(inactive["placebo_mean_net_6bps"]),
        "inactive_delta_net_6bps": bd,
        "interaction_lift_bps": float(ad - bd) if ad is not None and bd is not None else None,
        "overall_delta_net_6bps": _mean_or_none(x["delta_net_6bps"]),
        "median_compatible_placebos_per_signal": float(x["compatible_placebo_n"].median()),
        "min_compatible_placebos_per_signal": int(x["compatible_placebo_n"].min()),
    }


def session_block_bootstrap_ci(
    per_signal: pd.DataFrame,
    *,
    state: bool | None = None,
    reps: int = 5000,
    seed: int = DEFAULT_SEED,
) -> list[float] | None:
    x = canonicalize_per_signal(per_signal)
    if state is not None:
        x = x[x["signal_state"] == bool(state)]
    vals = _session_means(x)["value"].to_numpy(float)
    if len(vals) < 2:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(vals), size=(reps, len(vals)))
    boot = vals[idx].mean(axis=1)
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return [float(lo), float(hi)]


def session_signflip_pvalue(
    per_signal: pd.DataFrame,
    *,
    state: bool | None = None,
    reps: int = DEFAULT_REPS,
    seed: int = DEFAULT_SEED,
) -> float | None:
    x = canonicalize_per_signal(per_signal)
    if state is not None:
        x = x[x["signal_state"] == bool(state)]
    vals = _session_means(x)["value"].to_numpy(float)
    if len(vals) < 2:
        return None
    observed = float(vals.mean())
    rng = np.random.default_rng(seed)
    signs = rng.choice(np.array([-1.0, 1.0]), size=(reps, len(vals)), replace=True)
    null = (signs * vals).mean(axis=1)
    return float((1 + np.count_nonzero(null >= observed)) / (reps + 1))


def state_label_permutation_pvalue(
    per_signal: pd.DataFrame,
    *,
    reps: int = DEFAULT_REPS,
    seed: int = DEFAULT_SEED,
) -> float | None:
    x = canonicalize_per_signal(per_signal)
    session = (
        x.groupby("signal_session_date", as_index=False)
        .agg(delta=("delta_net_6bps", "mean"), state=("signal_state", "first"))
    )
    if session["state"].nunique() < 2:
        return None
    vals = session["delta"].to_numpy(float)
    states = session["state"].to_numpy(bool)
    observed = float(vals[states].mean() - vals[~states].mean())
    rng = np.random.default_rng(seed)
    exceed = 0
    valid = 0
    for _ in range(reps):
        perm = rng.permutation(states)
        if perm.all() or (~perm).all():
            continue
        lift = float(vals[perm].mean() - vals[~perm].mean())
        exceed += int(lift >= observed)
        valid += 1
    return float((1 + exceed) / (valid + 1)) if valid else None


def chronological_fold_results(per_signal: pd.DataFrame, folds: int = 4) -> pd.DataFrame:
    x = canonicalize_per_signal(per_signal)
    sessions = pd.DataFrame({"signal_session_date": sorted(x["signal_session_date"].unique())})
    if len(sessions) < folds:
        raise FullGateBlocked("INSUFFICIENT_SESSIONS_FOR_CHRONOLOGICAL_FOLDS")
    sessions["fold"] = (
        pd.qcut(np.arange(len(sessions)), q=folds, labels=False, duplicates="drop").astype(int) + 1
    )
    x = x.merge(sessions, on="signal_session_date", how="left", validate="many_to_one")
    rows = []
    for fold, g in x.groupby("fold", sort=True):
        active = g[g["signal_state"]]
        inactive = g[~g["signal_state"]]
        ad = _mean_or_none(active["delta_net_6bps"])
        bd = _mean_or_none(inactive["delta_net_6bps"])
        rows.append({
            "fold": int(fold),
            "start_session": str(g["signal_session_date"].min()),
            "end_session": str(g["signal_session_date"].max()),
            "signal_trades": int(len(g)),
            "active_signal_trades": int(len(active)),
            "active_signal_sessions": int(active["signal_session_date"].nunique()),
            "active_delta_net_6bps": ad,
            "inactive_delta_net_6bps": bd,
            "interaction_lift_bps": float(ad - bd) if ad is not None and bd is not None else None,
        })
    return pd.DataFrame(rows)


def concentration_report(per_signal: pd.DataFrame) -> dict:
    x = canonicalize_per_signal(per_signal)
    active = x[x["signal_state"]]
    if active.empty:
        raise FullGateBlocked("NO_ACTIVE_SIGNALS_FOR_CONCENTRATION")
    ses = _session_means(active)
    vals = ses["value"].to_numpy(float)
    denom = float(np.abs(vals).sum())
    ordered = np.sort(np.abs(vals))[::-1]
    top1 = float(ordered[:1].sum() / denom) if denom else 0.0
    top5 = float(ordered[:5].sum() / denom) if denom else 0.0
    return {
        "active_sessions": int(len(ses)),
        "top1_absolute_contribution_share": top1,
        "top5_absolute_contribution_share": top5,
        "max_session_delta_bps": float(ses["value"].max()),
        "min_session_delta_bps": float(ses["value"].min()),
    }


def top_five_session_removal(per_signal: pd.DataFrame) -> dict:
    x = canonicalize_per_signal(per_signal)
    active = x[x["signal_state"]]
    ses = _session_means(active)
    if len(ses) <= 5:
        raise FullGateBlocked("TOO_FEW_ACTIVE_SESSIONS_FOR_TOP5_REMOVAL")
    top = set(ses.nlargest(5, "value")["signal_session_date"].astype(str))
    kept = active[~active["signal_session_date"].astype(str).isin(top)]
    return {
        "removed_sessions": sorted(top),
        "remaining_active_sessions": int(kept["signal_session_date"].nunique()),
        "remaining_active_delta_net_6bps": _mean_or_none(kept["delta_net_6bps"]),
    }


def leave_one_quarter_out(per_signal: pd.DataFrame) -> pd.DataFrame:
    x = canonicalize_per_signal(per_signal)
    ts = pd.to_datetime(x["signal_origin"], utc=True).dt.tz_convert("Asia/Kolkata")
    x["quarter"] = ts.dt.to_period("Q").astype(str)
    rows = []
    for quarter in sorted(x["quarter"].unique()):
        g = x[x["quarter"] != quarter]
        active = g[g["signal_state"]]
        inactive = g[~g["signal_state"]]
        ad = _mean_or_none(active["delta_net_6bps"])
        bd = _mean_or_none(inactive["delta_net_6bps"])
        rows.append({
            "left_out_quarter": quarter,
            "remaining_active_sessions": int(active["signal_session_date"].nunique()),
            "active_delta_net_6bps": ad,
            "inactive_delta_net_6bps": bd,
            "interaction_lift_bps": float(ad - bd) if ad is not None and bd is not None else None,
        })
    return pd.DataFrame(rows)


def validate_delay_ledger(primary: pd.DataFrame, delayed: pd.DataFrame, *, delay_bars: int) -> dict:
    p = canonicalize_per_signal(primary)
    d = canonicalize_per_signal(delayed)
    pids = set(p["signal_trade_id"])
    dids = set(d["signal_trade_id"])
    if pids != dids:
        raise FullGateBlocked(
            f"DELAY_{delay_bars}_SIGNAL_ID_SET_MISMATCH:"
            f"missing={len(pids-dids)}:extra={len(dids-pids)}"
        )
    summary = interaction_summary(d)
    return {
        "delay_bars": int(delay_bars),
        "active_delta_net_6bps": summary["active_delta_net_6bps"],
        "active_delta_block_bootstrap_95ci": session_block_bootstrap_ci(
            d, state=True, seed=DEFAULT_SEED + delay_bars
        ),
        "interaction_lift_bps": summary["interaction_lift_bps"],
        "signal_count": int(len(d)),
        "source_requirement": "canonical exact-rule delayed-entry replay",
    }


def benjamini_hochberg(pvalues: dict[str, float | None], q: float = FDR_Q) -> dict:
    valid = [(k, float(v)) for k, v in pvalues.items() if v is not None and np.isfinite(v)]
    valid.sort(key=lambda kv: kv[1])
    m = len(valid)
    if not m:
        return {"q": float(q), "m": 0, "tests": {}, "any_pass": False}
    adj = [min(1.0, p * m / rank) for rank, (_, p) in enumerate(valid, start=1)]
    for i in range(m - 2, -1, -1):
        adj[i] = min(adj[i], adj[i + 1])
    tests = {}
    for rank, ((name, p), pa) in enumerate(zip(valid, adj), start=1):
        tests[name] = {
            "p_value": p, "rank": rank, "bh_adjusted_p": float(pa), "pass": bool(pa <= q)
        }
    return {
        "q": float(q), "m": m, "tests": tests,
        "any_pass": any(v["pass"] for v in tests.values()),
    }


def semantic_hash(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate_full_gates(
    per_signal: pd.DataFrame,
    *,
    delay1: pd.DataFrame | None,
    delay2: pd.DataFrame | None,
    hypothesis_id: str,
    external_multiplicity_pvalues: dict[str, float] | None = None,
    thresholds: GateThresholds = GateThresholds(),
    seed: int = DEFAULT_SEED,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    x = canonicalize_per_signal(per_signal)
    summary = interaction_summary(x)
    ci = session_block_bootstrap_ci(x, state=True, seed=seed)
    signflip_p = session_signflip_pvalue(x, state=True, seed=seed + 1)
    state_perm_p = state_label_permutation_pvalue(x, seed=seed + 2)
    folds = chronological_fold_results(x, folds=4)
    conc = concentration_report(x)
    top5 = top_five_session_removal(x)
    loqo = leave_one_quarter_out(x)

    blockers = []
    delay_results = {}
    if delay1 is None:
        blockers.append("MISSING_CANONICAL_DELAY_1_LEDGER")
    else:
        delay_results["delay_1"] = validate_delay_ledger(x, delay1, delay_bars=1)
    if delay2 is None:
        blockers.append("MISSING_CANONICAL_DELAY_2_LEDGER")
    else:
        delay_results["delay_2"] = validate_delay_ledger(x, delay2, delay_bars=2)

    pvalues = {
        f"{hypothesis_id}:ACTIVE_DELTA_SIGNFLIP": signflip_p,
        f"{hypothesis_id}:STATE_INTERACTION_PERMUTATION": state_perm_p,
    }
    if external_multiplicity_pvalues is None:
        blockers.append("MISSING_GLOBAL_MULTIPLICITY_LEDGER")
    else:
        pvalues.update({str(k): float(v) for k, v in external_multiplicity_pvalues.items()})
    fdr = benjamini_hochberg(pvalues, q=thresholds.fdr_q)

    active_ci_lower = ci[0] if ci is not None else None
    active_folds = folds["active_delta_net_6bps"].dropna()
    positive_folds = int((active_folds > 0).sum())
    median_fold = float(active_folds.median()) if len(active_folds) else None
    loqo_active = loqo["active_delta_net_6bps"].dropna()
    primary_name = f"{hypothesis_id}:ACTIVE_DELTA_SIGNFLIP"
    primary_fdr_pass = bool(fdr.get("tests", {}).get(primary_name, {}).get("pass", False))
    d1 = delay_results.get("delay_1", {}).get("active_delta_net_6bps")
    d2 = delay_results.get("delay_2", {}).get("active_delta_net_6bps")

    gates = {
        "support_gate": summary["active_signal_sessions"] >= thresholds.min_active_signal_sessions,
        "active_delta_positive": summary["active_delta_net_6bps"] is not None and summary["active_delta_net_6bps"] > 0,
        "active_delta_ci_lower_positive": active_ci_lower is not None and active_ci_lower > 0,
        "interaction_lift_positive": summary["interaction_lift_bps"] is not None and summary["interaction_lift_bps"] > 0,
        "positive_fold_count": positive_folds >= thresholds.min_positive_folds,
        "median_fold_positive": median_fold is not None and median_fold > 0,
        "top5_concentration_acceptable": conc["top5_absolute_contribution_share"] <= thresholds.concentration_top5_abs_share_max,
        "top5_removal_active_delta_positive": (
            top5["remaining_active_delta_net_6bps"] is not None
            and top5["remaining_active_delta_net_6bps"] > 0
        ),
        "leave_one_quarter_out_all_positive": bool(len(loqo_active) and (loqo_active > 0).all()),
        "primary_fdr_pass": primary_fdr_pass,
        "one_bar_delay_active_delta_positive": d1 is not None and d1 > 0,
        "two_bar_delay_active_delta_positive": d2 is not None and d2 > 0,
    }
    core_names = [
        "support_gate", "active_delta_positive", "active_delta_ci_lower_positive",
        "interaction_lift_positive", "positive_fold_count", "median_fold_positive",
        "top5_concentration_acceptable", "top5_removal_active_delta_positive",
        "leave_one_quarter_out_all_positive", "primary_fdr_pass",
    ]
    statistical_core = all(gates[k] for k in core_names)
    full_numeric = statistical_core and not blockers and gates["one_bar_delay_active_delta_positive"] and gates["two_bar_delay_active_delta_positive"]

    result = {
        "schema_version": SCHEMA_VERSION,
        "hypothesis_id": hypothesis_id,
        "summary": summary,
        "active_delta_block_bootstrap_95ci": ci,
        "active_delta_session_signflip_p": signflip_p,
        "state_interaction_session_permutation_p": state_perm_p,
        "fdr": fdr,
        "fold_summary": {
            "fold_count": int(len(folds)),
            "positive_active_delta_folds": positive_folds,
            "median_fold_active_delta_bps": median_fold,
        },
        "concentration": conc,
        "top_five_session_removal": top5,
        "leave_one_quarter_out_all_positive": gates["leave_one_quarter_out_all_positive"],
        "delay_results": delay_results,
        "blockers": blockers,
        "gates": gates,
        "statistical_core_pass": statistical_core,
        "full_numeric_gates_pass": full_numeric,
        "retrospective_research_exposed": True,
        "structural_edge_certified": False,
        "execution_viable": "UNKNOWN",
    }
    result["semantic_hash"] = semantic_hash(result)
    return result, folds, loqo
