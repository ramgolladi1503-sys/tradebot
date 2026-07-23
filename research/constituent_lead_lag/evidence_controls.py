"""Causal controls and sensitivity calculations for lead-lag evidence."""

from __future__ import annotations

from collections import Counter
from typing import Sequence

import numpy as np
import pandas as pd

from .model import SignalState, StrategyThresholds, TradeOutcome, evaluate_signals_with_entry_delay, summarize_outcomes

CONTROL_SPEC_VERSION = "causal_matched_no_lead_v1"
DELAY_SPEC_VERSION = "additional_one_bar_delay_v1"
CONCENTRATION_SPEC_VERSION = "absolute_net_contribution_v1"


def _volatility_buckets(states: pd.DataFrame) -> pd.Series:
    source = pd.to_numeric(states.get("rolling_median_30m_move_bps", states.get("dispersion_bps", 0.0)), errors="coerce").fillna(0.0)
    unique = int(source.nunique())
    if unique <= 1:
        return pd.Series(["Q1"] * len(states), index=states.index, dtype="object")
    q = min(4, unique)
    ranked = source.rank(method="first")
    return pd.qcut(ranked, q=q, labels=[f"Q{i + 1}" for i in range(q)]).astype(str)


def build_matched_no_lead_control(states: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    frame = states.copy().reset_index(drop=True)
    if "side" not in frame or "decision_timestamp" not in frame:
        raise ValueError("states require side and decision_timestamp")
    signals = frame[frame["side"].isin(["LONG", "SHORT"])].copy()
    if signals.empty:
        return pd.DataFrame(columns=["status"]), {
            "result": "NOT_APPLICABLE_ZERO_SIGNALS",
            "control_spec": CONTROL_SPEC_VERSION,
            "signal_count": 0,
            "control_count": 0,
        }
    candidates = frame[frame["side"].eq("NONE")].copy()
    if len(candidates) < len(signals):
        raise ValueError("insufficient non-signal states for matched control")
    frame["volatility_bucket"] = _volatility_buckets(frame)
    signals = frame.loc[signals.index].copy()
    candidates = frame.loc[candidates.index].copy()
    used: set[int] = set()
    rows: list[dict[str, object]] = []
    for signal in signals.sort_values(["decision_timestamp", "session"]).itertuples():
        pool = candidates[
            (~candidates.index.isin(used))
            & candidates["decision_time"].eq(signal.decision_time)
            & candidates["volatility_bucket"].eq(signal.volatility_bucket)
        ]
        if pool.empty:
            pool = candidates[(~candidates.index.isin(used)) & candidates["decision_time"].eq(signal.decision_time)]
        if pool.empty:
            pool = candidates[~candidates.index.isin(used)]
        if pool.empty:
            raise ValueError("unable to construct unique causal control")
        ordered = pool.assign(_distance=(pd.to_datetime(pool["decision_timestamp"], utc=True) - pd.Timestamp(signal.decision_timestamp)).abs())
        ordered = ordered.sort_values(["_distance", "session", "decision_timestamp"])
        chosen_index = int(ordered.index[0])
        chosen = candidates.loc[chosen_index]
        used.add(chosen_index)
        if str(chosen["decision_timestamp"]) == str(signal.decision_timestamp):
            raise ValueError("control reused signal state identity")
        rows.append({
            "status": "MATCHED_CAUSAL_NO_LEAD_CONTROL",
            "control_spec": CONTROL_SPEC_VERSION,
            "matched_signal_session": str(signal.session),
            "matched_signal_decision_timestamp": str(signal.decision_timestamp),
            "matched_signal_side": str(signal.side),
            "control_session": str(chosen["session"]),
            "control_decision_time": str(chosen["decision_time"]),
            "control_decision_timestamp": str(chosen["decision_timestamp"]),
            "control_original_side": str(chosen["side"]),
            "control_side": str(signal.side),
            "volatility_bucket": str(chosen["volatility_bucket"]),
            "control_reason": str(chosen.get("reason", "")),
        })
    control = pd.DataFrame(rows)
    signal_side_counts = Counter(signals["side"].astype(str))
    control_side_counts = Counter(control["control_side"].astype(str))
    signal_time_counts = Counter(signals["decision_time"].astype(str))
    control_time_counts = Counter(control["control_decision_time"].astype(str))
    if signal_side_counts != control_side_counts or signal_time_counts != control_time_counts:
        raise ValueError("matched control distribution mismatch")
    return control, {
        "result": "MATCHED_CONTROL_CONSTRUCTED",
        "control_spec": CONTROL_SPEC_VERSION,
        "signal_count": int(len(signals)),
        "control_count": int(len(control)),
        "side_distribution_preserved": True,
        "decision_time_distribution_preserved": True,
        "unique_control_identities": int(control["control_decision_timestamp"].nunique()) == len(control),
    }


def delayed_entry_summary(states: Sequence[SignalState], bars: pd.DataFrame,
                          thresholds: StrategyThresholds = StrategyThresholds()) -> tuple[list[TradeOutcome], dict[str, object]]:
    signals = [state for state in states if state.side in {"LONG", "SHORT"}]
    if not signals:
        return [], {"result": "NOT_APPLICABLE_ZERO_SIGNALS", "delay_spec": DELAY_SPEC_VERSION, "signal_count": 0}
    outcomes = evaluate_signals_with_entry_delay(states, bars, thresholds, entry_delay_bars=2)
    summary = summarize_outcomes(outcomes)
    summary.update({
        "result": "COMPUTED",
        "delay_spec": DELAY_SPEC_VERSION,
        "original_signal_count": len({(state.session, state.index_symbol) for state in signals}),
        "delayed_outcome_count": len(outcomes),
        "excluded_missing_delayed_entry": len({(state.session, state.index_symbol) for state in signals}) - len(outcomes),
    })
    return outcomes, summary


def concentration_summary(outcomes: Sequence[TradeOutcome]) -> dict[str, object]:
    valid = [outcome for outcome in outcomes if outcome.exit_reason != "AMBIGUOUS_SAME_BAR"]
    if not valid:
        return {"result": "NOT_APPLICABLE_ZERO_SIGNALS", "concentration_spec": CONCENTRATION_SPEC_VERSION, "signals": 0}
    frame = pd.DataFrame([outcome.to_payload() for outcome in valid])
    frame["month"] = frame["session"].astype(str).str.slice(0, 7)
    absolute = frame["net_return_bps"].abs()
    denominator = float(absolute.sum())
    if denominator <= 1e-12:
        contribution = pd.Series(np.repeat(1.0 / len(frame), len(frame)), index=frame.index)
    else:
        contribution = absolute / denominator
    frame["absolute_contribution"] = contribution
    month_share = frame.groupby("month")["absolute_contribution"].sum().sort_values(ascending=False)
    session_share = frame.groupby("session")["absolute_contribution"].sum().sort_values(ascending=False)
    decision_share = frame.groupby("decision_time").size().div(len(frame)).sort_values(ascending=False)
    side_share = frame.groupby("side").size().div(len(frame)).sort_values(ascending=False)
    return {
        "result": "COMPUTED",
        "concentration_spec": CONCENTRATION_SPEC_VERSION,
        "signals": int(len(frame)),
        "monthly_absolute_pnl_share_max": float(month_share.iloc[0]),
        "monthly_absolute_pnl_share": {str(k): float(v) for k, v in month_share.items()},
        "top_session_absolute_pnl_share": float(session_share.iloc[0]),
        "top_five_session_absolute_pnl_share": float(session_share.head(5).sum()),
        "decision_time_signal_share_max": float(decision_share.iloc[0]),
        "side_signal_share_max": float(side_share.iloc[0]),
    }
