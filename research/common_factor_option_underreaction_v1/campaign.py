from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.dispersion_ignition_straddle_v1.common import (
    DataContractError,
    calculate_metrics,
    semantic_hash,
    sha256_file,
    split_sessions,
    stable_json,
    time_bucket,
)
from research.dispersion_ignition_straddle_v1.data import (
    build_features,
    load_constituent_bars,
    resolve_sources,
)
from research.dispersion_ignition_straddle_v1.options import OptionPairStore, stale_at_signal

HORIZONS = (5, 10, 15, 20)
FRICTIONS = {"base": 0.005, "stress": 0.010, "severe": 0.015}
VARIANTS = (
    "coherent_common_shock_index_lag_wing_underreaction",
    "broad_common_shock_low_concentration_low_premium_burden",
    "common_shock_mirror_decay_wing_underreaction",
)


@dataclass(frozen=True)
class Screen:
    variant: str
    horizon: int | None
    passed: bool
    reason: str
    metrics: dict[str, Any] | None
    directional_lift: float | None
    mirror_mean: float | None
    delayed_mean: float | None


def _future_index_returns(features: pd.DataFrame, bars: pd.DataFrame, index_symbol: str) -> pd.DataFrame:
    index = bars[bars["symbol"] == index_symbol].copy()
    index = index.sort_values(["session", "timestamp"], kind="mergesort")
    for horizon in HORIZONS:
        steps = horizon // 5
        future = index.groupby("session", sort=False)["close"].shift(-steps)
        index[f"future_index_return_{horizon}"] = future / index["close"] - 1.0
    keep = ["session", "timestamp", *[f"future_index_return_{h}" for h in HORIZONS]]
    return features.merge(
        index[keep].rename(columns={"timestamp": "bar_timestamp"}),
        on=["session", "bar_timestamp"],
        how="left",
        validate="one_to_one",
    )


def _option_state(store: OptionPairStore, row: pd.Series) -> dict[str, Any] | None:
    direction = 1 if float(row["median_return"]) > 0 else -1 if float(row["median_return"]) < 0 else 0
    if direction == 0:
        return None
    pair = store.select(str(row["session"]), row["signal_timestamp"], float(row["index_close"]))
    if pair is None:
        return None
    ce, pe, prior = pair["ce"], pair["pe"], pair["prior"]
    previous = prior - pd.Timedelta(minutes=5)
    if previous not in ce.index or previous not in pe.index:
        return None
    if stale_at_signal(ce, prior) or stale_at_signal(pe, prior):
        return None
    selected, mirror = (ce, pe) if direction > 0 else (pe, ce)
    selected_type, mirror_type = ("CE", "PE") if direction > 0 else ("PE", "CE")
    selected_close = float(selected.loc[prior, "close"])
    mirror_close = float(mirror.loc[prior, "close"])
    selected_previous = float(selected.loc[previous, "close"])
    mirror_previous = float(mirror.loc[previous, "close"])
    if min(selected_close, mirror_close, selected_previous, mirror_previous) <= 0:
        return None
    expiry = pd.Timestamp(pair["expiry"]).date()
    session = pd.Timestamp(row["session"]).date()
    return {
        "direction": direction,
        "selected_option_type": selected_type,
        "mirror_option_type": mirror_type,
        "pair_expiry": str(expiry),
        "pair_strike": float(pair["strike"]),
        "days_to_expiry": (expiry - session).days,
        "selected_signal_close": selected_close,
        "mirror_signal_close": mirror_close,
        "selected_return_5m": selected_close / selected_previous - 1.0,
        "mirror_return_5m": mirror_close / mirror_previous - 1.0,
        "selected_premium_burden": selected_close / float(row["index_close"]),
        "straddle_premium_burden": (selected_close + mirror_close) / float(row["index_close"]),
        "selected_signal_volume": float(selected.loc[prior, "volume"]),
        "mirror_signal_volume": float(mirror.loc[prior, "volume"]),
    }


def build_causal_state(features: pd.DataFrame, store: OptionPairStore) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, row in features.sort_values(["session", "signal_timestamp"], kind="mergesort").iterrows():
        option = _option_state(store, row)
        if option is None:
            continue
        payload = row.to_dict()
        payload.update(option)
        payload["source_feature_index"] = int(index)
        payload["coherence_score"] = float(row["median_abs_return"]) / max(float(row["dispersion_mad"]), 1e-8)
        payload["common_shock_strength"] = (
            abs(float(row["median_return"]))
            * float(row["absolute_participation"])
            * payload["coherence_score"]
        )
        payload["index_lag"] = abs(float(row["median_return"])) - abs(float(row["index_ret_1"]))
        payload["wing_underreaction_gap"] = abs(float(row["median_return"])) - max(option["selected_return_5m"], 0.0)
        payload["minute_of_day"] = int(row["minute_of_day"])
        payload["threshold_bucket"] = f"{payload['minute_of_day'] // 30}|{min(max(option['days_to_expiry'], 0), 7)}"
        rows.append(payload)
    state = pd.DataFrame(rows)
    if state.empty:
        raise DataContractError("no causal option-pair states available")
    return state.sort_values(["session", "signal_timestamp"], kind="mergesort").reset_index(drop=True)


def _cuts(frame: pd.DataFrame) -> dict[str, float]:
    return {
        "strength_high": float(frame["common_shock_strength"].quantile(0.75)),
        "coherence_high": float(frame["coherence_score"].quantile(0.70)),
        "participation_high": float(frame["absolute_participation"].quantile(0.70)),
        "index_lag_high": float(frame["index_lag"].quantile(0.65)),
        "wing_response_low": float(frame["selected_return_5m"].quantile(0.35)),
        "premium_burden_low": float(frame["selected_premium_burden"].quantile(0.50)),
        "top5_broad": float(frame["top5_abs_share"].quantile(0.50)),
        "mirror_decay": float(frame["mirror_return_5m"].quantile(0.50)),
    }


def training_thresholds(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        raise DataContractError("empty threshold frame")
    global_cuts = _cuts(frame)
    grouped: dict[str, dict[str, float]] = {}
    for bucket, group in frame.groupby("threshold_bucket", sort=True):
        grouped[str(bucket)] = _cuts(group) if len(group) >= 40 else global_cuts
    return {"global": global_cuts, "by_bucket": grouped}


def _series(frame: pd.DataFrame, thresholds: dict[str, Any], key: str) -> pd.Series:
    return frame["threshold_bucket"].map(
        lambda bucket: thresholds["by_bucket"].get(str(bucket), thresholds["global"])[key]
    ).astype(float)


def variant_mask(frame: pd.DataFrame, thresholds: dict[str, Any], variant: str) -> pd.Series:
    coherent = frame["coherence_score"] >= _series(frame, thresholds, "coherence_high")
    participating = frame["absolute_participation"] >= _series(frame, thresholds, "participation_high")
    lagging = frame["index_lag"] >= _series(frame, thresholds, "index_lag_high")
    underreacting = frame["selected_return_5m"] <= _series(frame, thresholds, "wing_response_low")
    strength = frame["common_shock_strength"] >= _series(frame, thresholds, "strength_high")
    liquid = (frame["selected_signal_volume"] > 0) & (frame["mirror_signal_volume"] > 0)
    if variant == VARIANTS[0]:
        return liquid & coherent & participating & lagging & underreacting & strength
    if variant == VARIANTS[1]:
        return (
            liquid & coherent & participating & lagging & strength
            & (frame["top5_abs_share"] <= _series(frame, thresholds, "top5_broad"))
            & (frame["selected_premium_burden"] <= _series(frame, thresholds, "premium_burden_low"))
        )
    if variant == VARIANTS[2]:
        return (
            liquid & coherent & participating & lagging & underreacting & strength
            & (frame["mirror_return_5m"] <= _series(frame, thresholds, "mirror_decay"))
        )
    raise ValueError(variant)


def expanding_folds(sessions: list[str]) -> list[tuple[list[str], list[str]]]:
    blocks = [part.tolist() for part in np.array_split(np.asarray(sessions, dtype=object), 6) if len(part)]
    return [([item for block in blocks[:position] for item in block], blocks[position]) for position in range(1, len(blocks))]


def generate_oof(state: pd.DataFrame, sessions: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    ledgers, freezes = [], []
    for fold, (training_sessions, testing_sessions) in enumerate(expanding_folds(sessions), start=1):
        training = state[state["session"].isin(training_sessions)]
        testing = state[state["session"].isin(testing_sessions)]
        thresholds = training_thresholds(training)
        freezes.append({
            "fold": fold,
            "training_start": training_sessions[0],
            "training_end": training_sessions[-1],
            "testing_start": testing_sessions[0],
            "testing_end": testing_sessions[-1],
            "thresholds": thresholds,
        })
        for variant in VARIANTS:
            chosen = testing[variant_mask(testing, thresholds, variant)].copy()
            chosen["variant"], chosen["fold"] = variant, fold
            ledgers.append(chosen)
    return (pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame()), {"folds": freezes}


def replay_signal(store: OptionPairStore, row: pd.Series, delay: int = 0) -> list[dict[str, Any]]:
    pair = store.select(str(row["session"]), row["signal_timestamp"], float(row["index_close"]))
    if pair is None or str(pair["expiry"]) != str(row["pair_expiry"]) or float(pair["strike"]) != float(row["pair_strike"]):
        return []
    selected, mirror = (pair["ce"], pair["pe"]) if int(row["direction"]) > 0 else (pair["pe"], pair["ce"])
    entry = row["signal_timestamp"] + pd.Timedelta(minutes=delay)
    if entry not in selected.index or entry not in mirror.index:
        return []
    selected_entry, mirror_entry = float(selected.loc[entry, "open"]), float(mirror.loc[entry, "open"])
    if min(selected_entry, mirror_entry) <= 0:
        return []
    output = []
    for horizon in HORIZONS:
        exit_timestamp = entry + pd.Timedelta(minutes=horizon - 1)
        if exit_timestamp not in selected.index or exit_timestamp not in mirror.index:
            continue
        selected_exit, mirror_exit = float(selected.loc[exit_timestamp, "close"]), float(mirror.loc[exit_timestamp, "close"])
        gross = selected_exit / selected_entry - 1.0
        mirror_gross = mirror_exit / mirror_entry - 1.0
        directional = float(row[f"future_index_return_{horizon}"]) * int(row["direction"])
        output.append({
            "session": str(row["session"]),
            "signal_timestamp": row["signal_timestamp"],
            "entry_timestamp": entry,
            "exit_timestamp": exit_timestamp,
            "variant": row["variant"],
            "fold": int(row["fold"]),
            "horizon": horizon,
            "direction": int(row["direction"]),
            "selected_option_type": row["selected_option_type"],
            "mirror_option_type": row["mirror_option_type"],
            "expiry": row["pair_expiry"],
            "strike": float(row["pair_strike"]),
            "selected_entry": selected_entry,
            "selected_exit": selected_exit,
            "mirror_entry": mirror_entry,
            "mirror_exit": mirror_exit,
            "gross_return": gross,
            "stress_return": gross - FRICTIONS["stress"],
            "severe_return": gross - FRICTIONS["severe"],
            "mirror_stress_return": mirror_gross - FRICTIONS["stress"],
            "directional_index_return": directional,
            "extra_entry_delay": delay,
            "days_to_expiry": int(row["days_to_expiry"]),
            "selected_premium_burden": float(row["selected_premium_burden"]),
        })
    return output


def replay_frame(store: OptionPairStore, signals: pd.DataFrame, delay: int = 0) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for _, row in signals.sort_values(["session", "signal_timestamp", "variant"]).iterrows():
        records.extend(replay_signal(store, row, delay))
    return pd.DataFrame(records)


def matched_directional_lift(state: pd.DataFrame, signals: pd.DataFrame, horizon: int) -> float | None:
    if signals.empty:
        return None
    pool = state.loc[~state.index.isin(signals.index)].copy()
    pool["time_bucket"] = time_bucket(pool["minute_of_day"])
    selected = signals.copy()
    selected["time_bucket"] = time_bucket(selected["minute_of_day"])
    used, differences = set(), []
    for _, signal in selected.sort_values(["session", "signal_timestamp"]).iterrows():
        candidates = pool[
            (pool["direction"] == signal["direction"])
            & (pool["time_bucket"] == signal["time_bucket"])
            & (~pool.index.isin(used))
        ].copy()
        if candidates.empty:
            continue
        candidates["distance"] = (
            (candidates["selected_premium_burden"] - signal["selected_premium_burden"]).abs()
            + 0.1 * (candidates["days_to_expiry"] - signal["days_to_expiry"]).abs()
        )
        control = candidates.sort_values(["distance", "session", "signal_timestamp"], kind="mergesort").iloc[0]
        used.add(int(control.name))
        signal_return = float(signal[f"future_index_return_{horizon}"]) * int(signal["direction"])
        control_return = float(control[f"future_index_return_{horizon}"]) * int(control["direction"])
        if np.isfinite(signal_return) and np.isfinite(control_return):
            differences.append(signal_return - control_return)
    return float(np.mean(differences)) if differences else None


def _oof_gate(metrics: Any, directional_lift: float | None, mirror_mean: float | None, delayed_mean: float | None) -> bool:
    return bool(
        metrics.trades >= 80
        and metrics.sessions >= 50
        and (metrics.mean_return or 0) > 0
        and (metrics.bootstrap_ci_low or -1) > 0
        and (metrics.remove_top_five_mean or -1) > 0
        and (metrics.profit_factor or 0) > 1.10
        and metrics.total_folds >= 5
        and metrics.positive_folds >= 4
        and (metrics.largest_winner_share is None or metrics.largest_winner_share < 0.18)
        and (metrics.largest_session_share is None or metrics.largest_session_share < 0.20)
        and directional_lift is not None
        and directional_lift > 0
        and mirror_mean is not None
        and metrics.mean_return is not None
        and metrics.mean_return > mirror_mean
        and delayed_mean is not None
        and metrics.mean_return > delayed_mean
    )


def _forward_gate(metrics: Any) -> bool:
    return bool(
        metrics.trades >= 20
        and metrics.sessions >= 15
        and (metrics.mean_return or 0) > 0
        and (metrics.bootstrap_ci_low or -1) > 0
        and (metrics.remove_top_five_mean or -1) > 0
        and (metrics.profit_factor or 0) > 1.05
        and (metrics.largest_winner_share is None or metrics.largest_winner_share < 0.24)
        and (metrics.largest_session_share is None or metrics.largest_session_share < 0.25)
    )


def run_campaign(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = resolve_sources(repo_root)
    bars, index_symbol = load_constituent_bars(sources.constituent_bars)
    features = _future_index_returns(build_features(bars, index_symbol), bars, index_symbol)
    inventory = pd.read_parquet(sources.contract_inventory)
    first = pd.to_datetime(inventory.get("first_candle"), errors="coerce").min()
    last = pd.to_datetime(inventory.get("last_candle"), errors="coerce").max()
    if pd.isna(first) or pd.isna(last):
        raise DataContractError("inventory has no usable time boundary")
    features = features[
        (features["signal_timestamp"].dt.date >= first.date())
        & (features["signal_timestamp"].dt.date <= last.date())
    ].copy()
    store = OptionPairStore(sources.contract_inventory, sources.option_root)
    state = build_causal_state(features, store)
    split = split_sessions(state["session"].unique())

    data_contract = {
        "constituent_path": str(sources.constituent_bars.relative_to(repo_root)),
        "constituent_sha256": sha256_file(sources.constituent_bars),
        "contract_inventory_path": str(sources.contract_inventory.relative_to(repo_root)),
        "contract_inventory_sha256": sha256_file(sources.contract_inventory),
        "constituent_rows": len(bars),
        "feature_rows": len(features),
        "causal_pair_state_rows": len(state),
        "causal_pair_state_sessions": int(state["session"].nunique()),
        "split_counts": {key: len(value) for key, value in split.items()},
        "historical_bid_ask_available": False,
        "historical_iv_available": False,
        "read_only": True,
        "allowed_for_live_execution": False,
    }
    data_contract["semantic_sha256"] = semantic_hash(data_contract)
    stable_json(output_dir / "data_contract_report.json", data_contract)
    stable_json(output_dir / "session_split_manifest.json", split)

    oof_signals, fold_freeze = generate_oof(state, split["research"])
    freeze = {
        "variants": list(VARIANTS),
        "horizons": list(HORIZONS),
        "frictions": FRICTIONS,
        "folds": fold_freeze["folds"],
        "direction": "sign_of_completed_constituent_median_return",
        "pair_selection": "nearest_nonexpired_same_strike_atm_pair_within_100_points",
        "membership_uses_future_entry_price": False,
        "entry": "exact_next_one_minute_open",
        "campaign_wide_tests": len(VARIANTS) * len(HORIZONS),
        "validation_and_holdout_sealed": True,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    freeze["semantic_sha256"] = semantic_hash(freeze)
    stable_json(output_dir / "pre_outcome_freeze.json", freeze)
    oof_signals.to_csv(output_dir / "oof_signal_ledger.csv", index=False)

    oof = replay_frame(store, oof_signals)
    delayed = replay_frame(store, oof_signals, 1)
    oof.to_csv(output_dir / "oof_trade_ledger.csv", index=False)
    delayed.to_csv(output_dir / "delayed_entry_ledger.csv", index=False)

    screens: list[dict[str, Any]] = []
    survivors: list[tuple[str, int, Any]] = []
    research_state = state[state["session"].isin(split["research"])]
    for variant in VARIANTS:
        choices = []
        for horizon in HORIZONS:
            ledger = oof[(oof["variant"] == variant) & (oof["horizon"] == horizon)] if not oof.empty else pd.DataFrame()
            metrics = calculate_metrics(ledger)
            choices.append((metrics.mean_return if metrics.mean_return is not None else -math.inf, horizon, metrics))
        choices.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        if not choices or not np.isfinite(choices[0][0]):
            screens.append(asdict(Screen(variant, None, False, "no_replayable_trades", None, None, None, None)))
            continue
        _, horizon, metrics = choices[0]
        selected_signals = oof_signals[oof_signals["variant"] == variant]
        directional_lift = matched_directional_lift(research_state, selected_signals, horizon)
        ledger = oof[(oof["variant"] == variant) & (oof["horizon"] == horizon)]
        mirror_mean = float(ledger["mirror_stress_return"].mean()) if not ledger.empty else None
        delayed_ledger = delayed[(delayed["variant"] == variant) & (delayed["horizon"] == horizon)] if not delayed.empty else pd.DataFrame()
        delayed_mean = float(delayed_ledger["stress_return"].mean()) if not delayed_ledger.empty else None
        passed = _oof_gate(metrics, directional_lift, mirror_mean, delayed_mean)
        screens.append(asdict(Screen(variant, horizon, passed, "passed" if passed else "oof_gate_failed", asdict(metrics), directional_lift, mirror_mean, delayed_mean)))
        if passed:
            survivors.append((variant, horizon, metrics))
    stable_json(output_dir / "oof_screen.json", {"variants": screens})

    if not survivors:
        maximum_signals = max((int((oof_signals["variant"] == variant).sum()) for variant in VARIANTS), default=0)
        maximum_trades = max((int((oof["variant"] == variant).sum()) for variant in VARIANTS), default=0) if not oof.empty else 0
        if maximum_signals < 80:
            verdict = "INSUFFICIENT_COMMON_FACTOR_EVENT_OCCURRENCE"
        elif maximum_trades < 80:
            verdict = "INSUFFICIENT_DIRECTIONAL_OPTION_COVERAGE"
        elif any((screen.get("directional_lift") or 0) > 0 for screen in screens):
            verdict = "COMMON_FACTOR_DIRECTIONAL_EDGE_OPTION_TRANSLATION_FAILED"
        else:
            verdict = "NO_COMMON_FACTOR_OPTION_UNDERREACTION_EDGE"
        result = {
            "principal_verdict": verdict,
            "oof_survivors": 0,
            "validation_opened": False,
            "holdout_opened": False,
            "limitations": ["historical bid-ask unavailable", "historical IV unavailable"],
        }
        stable_json(output_dir / "final_decision.json", result)
        return result

    survivors.sort(key=lambda item: (item[2].mean_return or -math.inf, item[2].trades), reverse=True)
    variant, horizon, _ = survivors[0]
    full_thresholds = training_thresholds(research_state)
    validation_state = state[state["session"].isin(split["validation"])]
    validation_signals = validation_state[variant_mask(validation_state, full_thresholds, variant)].copy()
    validation_signals["variant"], validation_signals["fold"] = variant, 100
    validation = replay_frame(store, validation_signals)
    validation = validation[validation["horizon"] == horizon] if not validation.empty else validation
    validation.to_csv(output_dir / "validation_ledger.csv", index=False)
    validation_metrics = calculate_metrics(validation)
    validation_passed = _forward_gate(validation_metrics)
    stable_json(output_dir / "validation_screen.json", {"variant": variant, "horizon": horizon, "metrics": asdict(validation_metrics), "passed": validation_passed})
    if not validation_passed:
        result = {
            "principal_verdict": "COMMON_FACTOR_DIRECTIONAL_EDGE_OPTION_TRANSLATION_FAILED",
            "selected_variant": variant,
            "selected_horizon": horizon,
            "validation_opened": True,
            "validation_passed": False,
            "holdout_opened": False,
        }
        stable_json(output_dir / "final_decision.json", result)
        return result

    holdout_state = state[state["session"].isin(split["holdout"])]
    holdout_signals = holdout_state[variant_mask(holdout_state, full_thresholds, variant)].copy()
    holdout_signals["variant"], holdout_signals["fold"] = variant, 200
    holdout = replay_frame(store, holdout_signals)
    holdout = holdout[holdout["horizon"] == horizon] if not holdout.empty else holdout
    holdout.to_csv(output_dir / "holdout_ledger.csv", index=False)
    holdout_metrics = calculate_metrics(holdout)
    holdout_passed = _forward_gate(holdout_metrics)
    stable_json(output_dir / "holdout_screen.json", {"variant": variant, "horizon": horizon, "metrics": asdict(holdout_metrics), "passed": holdout_passed})
    result = {
        "principal_verdict": "VALIDATED_COMMON_FACTOR_OPTION_UNDERREACTION_EDGE" if holdout_passed else "COMMON_FACTOR_DIRECTIONAL_EDGE_OPTION_TRANSLATION_FAILED",
        "selected_variant": variant,
        "selected_horizon": horizon,
        "validation_opened": True,
        "validation_passed": True,
        "holdout_opened": True,
        "holdout_passed": holdout_passed,
        "holdout_metrics": asdict(holdout_metrics),
        "limitations": ["historical bid-ask unavailable", "historical IV unavailable"],
    }
    stable_json(output_dir / "final_decision.json", result)
    return result
