from __future__ import annotations

import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import (
    FRICTIONS, HORIZONS, VARIANTS, DataContractError, Metrics, calculate_metrics,
    forward_gate, oof_gate, semantic_hash, sha256_file, split_sessions, stable_json,
    time_bucket, training_thresholds, variant_mask,
)
from .data import build_features, load_constituent_bars, resolve_sources
from .options import OptionPairStore, replay_frame


def expanding_folds(sessions: list[str]) -> list[tuple[list[str], list[str]]]:
    blocks = [part.tolist() for part in np.array_split(np.asarray(sessions, dtype=object), 6) if len(part)]
    return [([s for block in blocks[:pos] for s in block], blocks[pos]) for pos in range(1, len(blocks))]


def oof_signals(features: pd.DataFrame, sessions: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    ledgers, freeze_folds = [], []
    for fold, (train_sessions, test_sessions) in enumerate(expanding_folds(sessions), start=1):
        train = features[features["session"].isin(train_sessions)]
        test = features[features["session"].isin(test_sessions)].copy()
        thresholds = training_thresholds(train)
        freeze_folds.append({
            "fold": fold, "train_start": train_sessions[0], "train_end": train_sessions[-1],
            "test_start": test_sessions[0], "test_end": test_sessions[-1], "thresholds": thresholds,
        })
        for variant in VARIANTS:
            selected = test[variant_mask(test, thresholds, variant)].copy()
            selected["variant"], selected["fold"] = variant, fold
            ledgers.append(selected)
    signals = pd.concat(ledgers, ignore_index=False) if ledgers else pd.DataFrame()
    freeze = {"variants": list(VARIANTS), "folds": freeze_folds}
    return signals, freeze


def matched_controls(features: pd.DataFrame, signals: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    pool = features.loc[~features.index.isin(signals.index)].copy()
    pool["time_bucket"] = time_bucket(pool["minute_of_day"])
    selected = signals.copy()
    selected["time_bucket"] = time_bucket(selected["minute_of_day"])
    used, rows = set(), []
    for _, signal in selected.sort_values(["session", "signal_timestamp"]).iterrows():
        candidates = pool[(pool["time_bucket"] == signal["time_bucket"]) & (~pool.index.isin(used))].copy()
        if candidates.empty:
            continue
        candidates["distance"] = (
            (candidates["index_expression_ratio"] - signal["index_expression_ratio"]).abs()
            + (candidates["dispersion_mad"] - signal["dispersion_mad"]).abs()
            / max(float(signal["dispersion_mad"]), 1e-8)
        )
        chosen = candidates.sort_values(["distance", "session", "signal_timestamp"], kind="mergesort").iloc[0]
        used.add(int(chosen.name))
        rows.append({
            "signal_session": signal["session"], "control_session": chosen["session"],
            "signal_timestamp": signal["signal_timestamp"], "control_timestamp": chosen["signal_timestamp"],
            "signal_future_range": signal[f"future_range_{horizon}"],
            "control_future_range": chosen[f"future_range_{horizon}"],
        })
    return pd.DataFrame(rows)


def choose_horizon(ledger: pd.DataFrame, variant: str) -> tuple[int, Metrics] | None:
    candidates = []
    if ledger.empty:
        return None
    for horizon in HORIZONS:
        subset = ledger[(ledger["variant"] == variant) & (ledger["horizon"] == horizon) & (~ledger["prior_zero_volume"])]
        metrics = calculate_metrics(subset)
        candidates.append((metrics.mean_return if metrics.mean_return is not None else -math.inf, horizon, metrics))
    candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return None if not candidates or not np.isfinite(candidates[0][0]) else (candidates[0][1], candidates[0][2])


def _bounded_features(features: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    first = pd.to_datetime(inventory.get("first_candle"), errors="coerce").min()
    last = pd.to_datetime(inventory.get("last_candle"), errors="coerce").max()
    if pd.isna(first) or pd.isna(last):
        raise DataContractError("inventory lacks usable first/last candle timestamps")
    return features[(features["signal_timestamp"].dt.date >= first.date()) & (features["signal_timestamp"].dt.date <= last.date())].copy()


def _pair_count(inventory: pd.DataFrame) -> int:
    required = ["expiry", "strike", "option_type"]
    if any(column not in inventory for column in required):
        return 0
    return int(inventory.dropna(subset=required).groupby(["expiry", "strike"])["option_type"].nunique().ge(2).sum())


def _terminal_no_survivor(signals: pd.DataFrame, ledger: pd.DataFrame, screens: list[dict[str, Any]]) -> str:
    signal_max = max((int((signals["variant"] == v).sum()) for v in VARIANTS), default=0) if not signals.empty else 0
    replay_max = max((int(((ledger["variant"] == v) & (~ledger["prior_zero_volume"])).sum()) for v in VARIANTS), default=0) if not ledger.empty else 0
    if signal_max < 80:
        return "INSUFFICIENT_EVENT_OCCURRENCE"
    if replay_max < 80:
        return "INSUFFICIENT_CE_PE_PAIR_COVERAGE"
    return "UNDERLYING_RANGE_EDGE_ONLY_OPTION_TRANSLATION_FAILED" if any((s.get("matched_range_lift") or 0) > 0 for s in screens) else "NO_DISPERSION_IGNITION_STRUCTURAL_EDGE"


def run_campaign(repo_root: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = resolve_sources(repo_root)
    bars, index_symbol = load_constituent_bars(paths.constituent_bars)
    features = build_features(bars, index_symbol)
    inventory = pd.read_parquet(paths.contract_inventory)
    bounded = _bounded_features(features, inventory)
    split = split_sessions(bounded["session"].unique())

    contract = {
        "constituent_path": str(paths.constituent_bars.relative_to(repo_root)),
        "constituent_sha256": sha256_file(paths.constituent_bars),
        "constituent_rows": len(bars), "constituent_sessions": int(bars["session"].nunique()),
        "feature_rows": len(features), "index_symbol": index_symbol,
        "contract_inventory_path": str(paths.contract_inventory.relative_to(repo_root)),
        "contract_inventory_sha256": sha256_file(paths.contract_inventory),
        "contract_inventory_rows": len(inventory), "same_strike_pair_count": _pair_count(inventory),
        "bounded_overlap_start": min(split["research"]), "bounded_overlap_end": max(split["holdout"]),
        "split_counts": {key: len(value) for key, value in split.items()},
        "historical_bid_ask_available": False, "historical_iv_available": False,
        "read_only": True, "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(output_dir / "data_contract_report.json", contract)
    stable_json(output_dir / "session_split_manifest.json", split)

    signals, freeze = oof_signals(bounded, split["research"])
    freeze.update({
        "entry": "same-strike nearest-expiry ATM CE+PE at exact next one-minute open",
        "exit_horizons_minutes": list(HORIZONS), "frictions": FRICTIONS,
        "maximum_atm_distance": 100.0, "membership_uses_future_entry_price": False,
        "holdout_access": "sealed_until_oof_and_validation_gates_pass",
        "campaign_wide_variants": len(VARIANTS), "campaign_wide_tests": len(VARIANTS) * len(HORIZONS),
        "research_only": True, "allowed_for_live_execution": False,
    })
    freeze["semantic_sha256"] = semantic_hash(freeze)
    stable_json(output_dir / "pre_outcome_freeze.json", freeze)
    signals.to_csv(output_dir / "oof_signal_ledger.csv", index=False)

    store = OptionPairStore(paths.contract_inventory, paths.option_root)
    ledger, delayed = replay_frame(store, signals), replay_frame(store, signals, 1)
    ledger.to_csv(output_dir / "oof_straddle_ledger.csv", index=False)
    delayed.to_csv(output_dir / "delayed_entry_ledger.csv", index=False)

    screens, survivors = [], []
    research_features = bounded[bounded["session"].isin(split["research"])]
    for variant in VARIANTS:
        choice = choose_horizon(ledger, variant)
        if choice is None:
            screens.append({"variant": variant, "passed": False, "reason": "no_replayable_pairs"})
            continue
        horizon, metrics = choice
        controls = matched_controls(research_features, signals[signals["variant"] == variant], horizon)
        lift = float((controls["signal_future_range"] - controls["control_future_range"]).mean()) if not controls.empty else None
        delayed_metrics = calculate_metrics(delayed[(delayed["variant"] == variant) & (delayed["horizon"] == horizon) & (~delayed["prior_zero_volume"])])
        passed = oof_gate(metrics, lift, delayed_metrics.mean_return)
        screens.append({"variant": variant, "horizon": horizon, "metrics": asdict(metrics), "matched_range_lift": lift, "delayed_metrics": asdict(delayed_metrics), "passed": passed})
        if passed:
            survivors.append((variant, horizon, metrics))
    stable_json(output_dir / "oof_screen.json", {"variants": screens})

    if not survivors:
        verdict = _terminal_no_survivor(signals, ledger, screens)
        result = {"principal_verdict": verdict, "oof_survivors": 0, "validation_opened": False, "holdout_opened": False, "limitations": ["historical bid-ask unavailable", "historical IV unavailable"]}
        stable_json(output_dir / "final_decision.json", result)
        return result

    survivors.sort(key=lambda item: (item[2].mean_return or -math.inf, item[2].trades), reverse=True)
    variant, horizon, _ = survivors[0]
    frozen_thresholds = training_thresholds(research_features)
    validation_features = bounded[bounded["session"].isin(split["validation"])]
    validation_signals = validation_features[variant_mask(validation_features, frozen_thresholds, variant)].copy()
    validation_signals["variant"], validation_signals["fold"] = variant, 100
    validation = replay_frame(store, validation_signals)
    validation = validation[(validation["horizon"] == horizon) & (~validation["prior_zero_volume"])] if not validation.empty else validation
    validation.to_csv(output_dir / "validation_ledger.csv", index=False)
    validation_metrics = calculate_metrics(validation)
    validation_passed = forward_gate(validation_metrics)
    stable_json(output_dir / "validation_screen.json", {"variant": variant, "horizon": horizon, "metrics": asdict(validation_metrics), "passed": validation_passed})
    if not validation_passed:
        result = {"principal_verdict": "UNDERLYING_RANGE_EDGE_ONLY_OPTION_TRANSLATION_FAILED", "selected_variant": variant, "selected_horizon": horizon, "validation_opened": True, "validation_passed": False, "holdout_opened": False}
        stable_json(output_dir / "final_decision.json", result)
        return result

    holdout_features = bounded[bounded["session"].isin(split["holdout"])]
    holdout_signals = holdout_features[variant_mask(holdout_features, frozen_thresholds, variant)].copy()
    holdout_signals["variant"], holdout_signals["fold"] = variant, 200
    holdout = replay_frame(store, holdout_signals)
    holdout = holdout[(holdout["horizon"] == horizon) & (~holdout["prior_zero_volume"])] if not holdout.empty else holdout
    holdout.to_csv(output_dir / "holdout_ledger.csv", index=False)
    holdout_metrics = calculate_metrics(holdout)
    holdout_passed = forward_gate(holdout_metrics)
    stable_json(output_dir / "holdout_screen.json", {"variant": variant, "horizon": horizon, "metrics": asdict(holdout_metrics), "passed": holdout_passed})
    result = {
        "principal_verdict": "VALIDATED_DISPERSION_IGNITION_STRADDLE_EDGE" if holdout_passed else "UNDERLYING_RANGE_EDGE_ONLY_OPTION_TRANSLATION_FAILED",
        "selected_variant": variant, "selected_horizon": horizon,
        "validation_opened": True, "validation_passed": True, "holdout_opened": True,
        "holdout_passed": holdout_passed, "holdout_metrics": asdict(holdout_metrics),
        "limitations": ["historical bid-ask unavailable", "historical IV unavailable"],
    }
    stable_json(output_dir / "final_decision.json", result)
    return result
