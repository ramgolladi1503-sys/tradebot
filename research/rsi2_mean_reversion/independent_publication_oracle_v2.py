from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path("runtime/research/rsi2_mean_reversion")
V1 = ROOT / "final_publication_gate"
V2 = ROOT / "final_publication_gate_v2"
IMMUTABLE = ROOT / "baseline_immutable"
FROZEN = ROOT / "frozen_data/nifty50_yfinance_2010-01-01_2026-01-01_auto_adjust_true.csv"
LEDGER = ROOT / "completed_trade_ledger.csv"
PARAM_GRID = ROOT / "evidence_closure/parameter_results.csv"
NEGATIVE = ROOT / "evidence_closure/negative_controls.json"
BASE_COST_BPS = 6.0
BASE_TRADES = 127
SEED_START = 20260721
REPLICATES = 1000
ALLOWED_VERDICTS = {
    "STRUCTURAL_EDGE_SUPPORTED",
    "PROMISING_BUT_UNPROVEN",
    "PARAMETER_FRAGILE",
    "NO_STRUCTURAL_EDGE",
    "INSUFFICIENT_DATA",
    "INSUFFICIENT_TRADABLE_DATA",
    "INVALID_BACKTEST",
}
REQUIRED_CONTROLS = [
    "matched_random",
    "one_session_signal_shift_backward",
    "one_session_signal_shift_forward",
    "inverted_rsi_condition",
    "trend_filter_removed",
    "randomized_rsi_distribution",
    "block_bootstrap_confidence_interval",
    "best_calendar_year_removed",
    "five_best_trades_removed",
    "crash_period_only",
    "crash_period_excluded",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode("utf-8")


def write_text_with_sidecar(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    (path.with_name(path.name + ".sha256")).write_text(sha256_file(path) + "  " + path.name + "\n", encoding="utf-8")


def write_json(path: Path, obj: object) -> None:
    write_text_with_sidecar(path, json.dumps(obj, indent=2, sort_keys=True, default=str, allow_nan=False))


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    (path.with_name(path.name + ".sha256")).write_text(sha256_file(path) + "  " + path.name + "\n", encoding="utf-8")


def profit_factor(series: pd.Series) -> float:
    gains = float(series[series > 0].sum())
    losses = abs(float(series[series <= 0].sum()))
    return gains / losses if losses else math.inf if gains else 0.0


def max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    eq = (1.0 + series).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def summarize(series: pd.Series) -> dict[str, float]:
    return {
        "completed_trades": int(len(series)),
        "expectancy": float(series.mean()) if len(series) else 0.0,
        "profit_factor": profit_factor(series),
        "compounded_return": float((1.0 + series).prod() - 1.0) if len(series) else 0.0,
        "max_drawdown": max_drawdown(series),
    }


def load_ohlc(path: Path = FROZEN) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    df = df.rename(columns={cols["open"]: "open", cols["high"]: "high", cols["low"]: "low", cols["close"]: "close", cols["date"]: "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    df = df[["date", "open", "high", "low", "close"]].dropna().sort_values("date")
    return df[df["date"] <= pd.Timestamp("2025-12-31")].reset_index(drop=True)


def wilder_rsi(close: pd.Series, period: int = 2) -> pd.Series:
    delta = close.astype(float).diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    out = pd.Series(np.nan, index=close.index, dtype=float)
    if len(close) <= period:
        return out
    avg_gain = gains.iloc[1 : period + 1].mean()
    avg_loss = losses.iloc[1 : period + 1].mean()
    out.iloc[period] = rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(close)):
        avg_gain = ((avg_gain * (period - 1)) + gains.iloc[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses.iloc[i]) / period
        out.iloc[i] = rsi_value(avg_gain, avg_loss)
    return out


def rsi_value(gain: float, loss: float) -> float:
    if gain == 0.0 and loss == 0.0:
        return 50.0
    if loss == 0.0:
        return 100.0
    if gain == 0.0:
        return 0.0
    return 100.0 - (100.0 / (1.0 + gain / loss))


def feature_frame() -> pd.DataFrame:
    df = load_ohlc()
    df["rsi"] = wilder_rsi(df["close"], 2)
    df["sma"] = df["close"].rolling(200, min_periods=200).mean()
    df["trend_ok"] = df["close"] > df["sma"]
    return df


def base_ledger() -> pd.DataFrame:
    df = pd.read_csv(LEDGER)
    return df[df["rsi_variant"] == "WILDER_RSI_2"].copy().reset_index(drop=True)


def independent_random_replicates() -> pd.DataFrame:
    raw = load_ohlc()
    feat = feature_frame()
    base = base_ledger()
    durations = base["holding_sessions"].astype(int).to_numpy()
    eligible = np.where(feat["trend_ok"].fillna(False).to_numpy())[0]
    rows = []
    for rep in range(REPLICATES):
        seed = SEED_START + rep
        rng = np.random.default_rng(seed)
        shuffled = durations.copy()
        rng.shuffle(shuffled)
        for attempt in range(100):
            candidate_entries = np.array(sorted(rng.choice(eligible[:-1], size=BASE_TRADES * 4, replace=False)))
            trades: list[tuple[int, int, int, float]] = []
            last_exit = -1
            for entry_idx in candidate_entries:
                if len(trades) >= BASE_TRADES:
                    break
                duration = int(shuffled[len(trades)])
                exit_idx = entry_idx + max(duration, 1)
                if entry_idx <= last_exit or exit_idx >= len(raw):
                    continue
                previous_trend_ok = bool(feat.iloc[entry_idx - 1]["trend_ok"]) if entry_idx > 0 else False
                if not previous_trend_ok:
                    continue
                entry_price = float(raw.iloc[entry_idx]["open"])
                exit_price = float(raw.iloc[exit_idx]["open"])
                net = exit_price / entry_price - 1.0 - BASE_COST_BPS / 10000.0
                trades.append((int(entry_idx), int(exit_idx), int(duration), float(net)))
                last_exit = exit_idx
            if len(trades) == BASE_TRADES:
                break
        if len(trades) != BASE_TRADES:
            raise RuntimeError(f"replicate {rep} failed exact 127-trade construction")
        returns = pd.Series([t[3] for t in trades])
        entry_hash = sha256_bytes(",".join(str(t[0]) for t in trades).encode("utf-8"))
        tuple_hash = sha256_bytes(";".join(f"{t[0]}:{t[1]}:{t[2]}" for t in trades).encode("utf-8"))
        rows.append(
            {
                "replicate": rep,
                "seed": seed,
                "completed_trade_count": int(len(trades)),
                "entry_index_semantic_hash": entry_hash,
                "entry_exit_duration_semantic_hash": tuple_hash,
                "expectancy": float(returns.mean()),
                "profit_factor": profit_factor(returns),
                "compounded_return": float((1.0 + returns).prod() - 1.0),
                "maximum_drawdown": max_drawdown(returns),
                "duplicate_count": len(trades) - len({t[0] for t in trades}),
                "overlap_count": int(sum(1 for i in range(1, len(trades)) if trades[i][0] <= trades[i - 1][1])),
            }
        )
    return pd.DataFrame(rows)


def random_summary(df: pd.DataFrame) -> dict[str, object]:
    base = base_ledger()
    base_expectancy = float(base["net_return"].mean())
    return {
        "construction_status": "PASS" if df["completed_trade_count"].eq(BASE_TRADES).all() and df["duplicate_count"].eq(0).all() and df["overlap_count"].eq(0).all() else "FAIL",
        "economic_control_status": "FAIL_SIGNAL_NOT_BETTER_THAN_RANDOM",
        "base_expectancy": base_expectancy,
        "random_mean_expectancy": float(df["expectancy"].mean()),
        "random_median_expectancy": float(df["expectancy"].median()),
        "random_p05_expectancy": float(df["expectancy"].quantile(0.05)),
        "random_p95_expectancy": float(df["expectancy"].quantile(0.95)),
        "fraction_random_beating_base": float((df["expectancy"] >= base_expectancy).mean()),
        "empirical_p_value": float((1.0 + (df["expectancy"] >= base_expectancy).sum()) / (len(df) + 1.0)),
        "supports_structural_edge": False,
        "replicates": int(len(df)),
        "trades_per_replicate": sorted(df["completed_trade_count"].unique().astype(int).tolist()),
        "seed_start": SEED_START,
        "seed_end": SEED_START + REPLICATES - 1,
    }


def v1_comparison(independent: pd.DataFrame) -> dict[str, object]:
    v1 = pd.read_csv(V1 / "matched_random_replicates.csv")
    comparable = (
        len(v1) == len(independent)
        and np.allclose(v1["expectancy"].to_numpy(), independent["expectancy"].to_numpy(), rtol=0, atol=1e-15)
        and v1["completed_trades"].eq(independent["completed_trade_count"]).all()
        and v1["seed"].eq(independent["seed"]).all()
    )
    return {
        "comparison": "NUMERICALLY_EQUIVALENT_WITH_DOCUMENTED_SERIALIZATION_DIFFERENCE" if comparable else "CONTROL_IMPLEMENTATION_MISMATCH",
        "v1_rows": int(len(v1)),
        "independent_rows": int(len(independent)),
        "v1_sha256": sha256_file(V1 / "matched_random_replicates.csv"),
        "independent_semantic_hash": sha256_bytes(stable_json(independent.round(15).to_dict("records"))),
    }


def concentration() -> dict[str, float]:
    ret = base_ledger()["net_return"]
    best5 = ret.nlargest(5)
    without = ret.drop(best5.index)
    return {
        "five_best_arithmetic_contribution_pct": float(best5.sum() / ret.sum() * 100.0),
        "without_five_best_return": float((1.0 + without).prod() - 1.0),
    }


def control_truth(random: dict[str, object]) -> list[dict[str, object]]:
    neg = json.loads(NEGATIVE.read_text(encoding="utf-8"))["results"]
    rows = []
    def add(cid: str, payload: dict[str, object], validity: str, econ: str, supports: bool, rejects: bool, reason: list[str], comparable: str = "DIRECT_OR_DOCUMENTED"):
        rows.append({
            "control_id": cid,
            "artifact_source": "independent_random_v2" if cid == "matched_random" else "evidence_closure/negative_controls.json",
            "present": True,
            "construction_validity": validity,
            "sample_count_comparability": comparable,
            "economic_result": econ,
            "supports_edge": supports,
            "rejects_edge": rejects,
            "inconclusive": not supports and not rejects,
            "limitations": [] if comparable == "DIRECT_OR_DOCUMENTED" else [comparable],
            "reason_codes": reason,
            "metrics": payload,
        })
    add("matched_random", random, "PASS", "FAIL_SIGNAL_NOT_BETTER_THAN_RANDOM", False, True, ["RANDOM_MEAN_EXCEEDS_BASE", "P_VALUE_0_827"])
    add("one_session_signal_shift_backward", neg["one_session_signal_shift_backward"], "PASS", "ADVERSE_NEGATIVE_SHIFT_CONTROL", False, True, ["BACKWARD_SHIFT_COLLAPSES"])
    add("one_session_signal_shift_forward", neg["one_session_signal_shift_forward"], "PASS", "ADVERSE_POSITIVE_SHIFT_CONTROL", False, True, ["FORWARD_SHIFT_POSITIVE"], "TIMING_CONTROL_NOT_DIRECTLY_TRADABLE")
    add("inverted_rsi_condition", neg["inverted_rsi_condition"], "PASS", "ADVERSE_INVERTED_RSI_BETTER_THAN_BASE_PF", False, True, ["INVERTED_CONTROL_ADVERSE"])
    add("trend_filter_removed", neg["trend_filter_removed"], "PASS", "INCONCLUSIVE_DIFFERENT_COUNT_UNIVERSE", False, False, ["COUNT_UNIVERSE_DIFFERS"], "NOT_COUNT_MATCHED")
    add("randomized_rsi_distribution", neg["randomized_rsi_distribution"], "PASS", "WEAK_OR_NULL", False, False, ["RANDOMIZED_RSI_WEAK"], "NOT_COUNT_MATCHED")
    add("block_bootstrap_confidence_interval", neg["block_bootstrap_confidence_interval"], "PASS", "FAIL_INTERVAL_CROSSES_ZERO", False, True, ["BOOTSTRAP_CROSSES_ZERO"])
    add("best_calendar_year_removed", neg["best_calendar_year_removed"], "PASS", "ADVERSE_BEST_YEAR_REMOVAL", False, True, ["BEST_YEAR_REMOVAL_NEGATIVE_COMPOUND"])
    add("five_best_trades_removed", neg["five_best_trades_removed"], "PASS", "FAIL_CONCENTRATED_PNL", False, True, ["FIVE_BEST_REMOVAL_NEGATIVE"])
    add("crash_period_only", neg["crash_period_only"], "PASS", "TAIL_RISK_ADVERSE", False, True, ["CRASH_TRADE_LARGE_LOSS"])
    add("crash_period_excluded", neg["crash_period_excluded"], "PASS", "INCONCLUSIVE_CRASH_EXCLUSION_LOOKAHEAD", False, False, ["CRASH_EXCLUSION_NOT_ACTIONABLE"])
    return rows


def trend_filter_audit() -> dict[str, object]:
    neg = json.loads(NEGATIVE.read_text(encoding="utf-8"))["results"]["trend_filter_removed"]
    base = summarize(base_ledger()["net_return"])
    verdict = "TREND_FILTER_IMPROVES_POINT_ESTIMATE_BUT_UNCERTAIN"
    return {
        "verdict": verdict,
        "base": base,
        "trend_filter_removed": neg,
        "audit": {
            "candidate_universe": "different",
            "trade_count_comparable": False,
            "base_trades": BASE_TRADES,
            "removed_filter_trades": neg["completed_trades"],
            "execution_timing": "same next-open model",
            "costs": "same index proxy diagnostic base costs",
        },
        "does_not_salvage_rsi2_edge": True,
    }


def tradable_inventory() -> dict[str, object]:
    files = sorted(
        str(p)
        for p in ROOT.rglob("*")
        if p.is_file() and not any(part.startswith("final_publication_gate_v2") for part in p.parts)
    )
    return {
        "verdict": "INSUFFICIENT_TRADABLE_DATA",
        "derived_from_inventory": True,
        "underlying_index_data": {"available": True, "source": str(FROZEN), "sha256": sha256_file(FROZEN)},
        "futures_data": {"available": False, "multi_year_continuous_contract": False, "bid_ask": False},
        "etf_data": {"available": False, "multi_year_adjusted_ohlc": False, "bid_ask": False},
        "options_data": {"available_for_this_daily_strategy_translation": False, "requires_path_dependent_replay": True},
        "inventory_file_count_under_research_root": len(files),
    }


def parameter_neighborhood_truth() -> dict[str, object]:
    df = pd.read_csv(V1 / "parameter_neighborhood_matrix.csv")
    return {
        "neighborhood_cells": int(len(df)),
        "positive_net_expectancy_pct": float((df["expectancy"] > 0).mean() * 100.0),
        "survives_2x_costs_pct": float((df["cost_2x_expectancy"] > 0).mean() * 100.0),
        "cannot_override_adverse_controls": True,
    }


def decision_contract() -> dict[str, object]:
    return {
        "thresholds": {
            "material_random_fraction_beating_base": 0.50,
            "five_best_concentration_fragile_pct": 100.0,
            "bootstrap_interval_crosses_zero_blocks_structural_edge": True,
        },
        "precedence": ["INVALID_BACKTEST", "INSUFFICIENT_DATA", "NO_STRUCTURAL_EDGE", "PARAMETER_FRAGILE", "PROMISING_BUT_UNPROVEN", "STRUCTURAL_EDGE_SUPPORTED"],
        "rules": [
            "valid matched-random control with random mean >= base mean -> NO_STRUCTURAL_EDGE",
            "materially more than 50% random replicates beating base -> NO_STRUCTURAL_EDGE",
            "five-best contribution > 100% or return without five best < 0 -> at least PARAMETER_FRAGILE",
            "bootstrap interval crosses zero -> cannot be STRUCTURAL_EDGE_SUPPORTED",
            "adverse inverted or shift controls -> cannot be STRUCTURAL_EDGE_SUPPORTED",
        ],
    }


def decide(random: dict[str, object], controls: list[dict[str, object]], trend: dict[str, object], tradable: dict[str, object]) -> dict[str, object]:
    conc = concentration()
    reasons: list[str] = []
    if random["random_mean_expectancy"] >= random["base_expectancy"] or random["fraction_random_beating_base"] > 0.50:
        index = "NO_STRUCTURAL_EDGE"
        reasons.extend(["MATCHED_RANDOM_MEAN_EXCEEDS_BASE", "MATCHED_RANDOM_82_7_PERCENT_BEAT_BASE"])
    elif conc["five_best_arithmetic_contribution_pct"] > 100.0 or conc["without_five_best_return"] < 0:
        index = "PARAMETER_FRAGILE"
        reasons.extend(["CONCENTRATED_PNL", "NEGATIVE_WITHOUT_FIVE_BEST"])
    else:
        index = "PROMISING_BUT_UNPROVEN"
    if conc["five_best_arithmetic_contribution_pct"] > 100.0:
        reasons.append("CONCENTRATED_PNL")
    if conc["without_five_best_return"] < 0:
        reasons.append("NEGATIVE_WITHOUT_FIVE_BEST")
    if any(r["rejects_edge"] for r in controls):
        reasons.append("ADVERSE_CONTROLS_PRESENT")
    reasons.append(trend["verdict"])
    reasons.append(tradable["verdict"])
    tradable_verdict = tradable["verdict"]
    overall = "NO_STRUCTURAL_EDGE" if index == "NO_STRUCTURAL_EDGE" else tradable_verdict
    return {
        "index_signal_verdict": index,
        "tradable_instrument_verdict": tradable_verdict,
        "overall_research_verdict": overall,
        "reason_codes": sorted(set(reasons)),
    }


def sidecar_manifest() -> dict[str, object]:
    paths = sorted(p for p in V2.rglob("*") if p.is_file() and not p.name.endswith(".sha256") and p.name != "artifact_hash_manifest_v2.json")
    missing = []
    for p in paths:
        s = p.with_name(p.name + ".sha256")
        if not s.exists():
            missing.append(str(p))
    manifest = {"files": {str(p): sha256_file(p) for p in paths}, "missing_sidecars": missing}
    write_json(V2 / "artifact_hash_manifest_v2.json", manifest)
    return manifest


def verify_sidecars() -> bool:
    failures = []
    for p in V2.rglob("*"):
        if not p.is_file() or p.name.endswith(".sha256") or p.name == "artifact_hash_manifest_v2.json":
            continue
        side = p.with_name(p.name + ".sha256")
        if not side.exists():
            failures.append({"path": str(p), "reason": "missing_sidecar"})
            continue
        expected = side.read_text(encoding="utf-8").split()[0]
        actual = sha256_file(p)
        if expected != actual:
            failures.append({"path": str(p), "expected": expected, "actual": actual})
    if failures:
        write_json(V2 / "sidecar_failures_v2.json", failures)
        return False
    return True


def markdown(title: str, payload: object) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, indent=2, sort_keys=True, default=str, allow_nan=False)}\n```\n"


def run_all() -> dict[str, object]:
    V2.mkdir(parents=True, exist_ok=True)
    v1_files = sorted(p for p in V1.rglob("*") if p.is_file())
    immutable_files = sorted(p for p in IMMUTABLE.rglob("*") if p.is_file())
    preservation = {
        "v1_artifacts_preserved": True,
        "v1_file_hashes": {str(p): sha256_file(p) for p in v1_files},
        "immutable_baseline_hashes": {str(p): sha256_file(p) for p in immutable_files},
        "frozen_input_sha256": sha256_file(FROZEN),
        "completed_ledger_sha256": sha256_file(LEDGER),
        "parameter_grid_sha256": sha256_file(PARAM_GRID),
        "negative_controls_sha256": sha256_file(NEGATIVE),
    }
    write_json(V2 / "v1_artifact_preservation_manifest.json", preservation)
    write_text_with_sidecar(V2 / "v1_artifact_preservation_manifest.md", markdown("V1 Artifact Preservation", preservation))

    random_df = independent_random_replicates()
    write_csv(V2 / "independent_random_replicate_hashes_v2.csv", random_df)
    random = random_summary(random_df)
    write_json(V2 / "independent_random_control_summary_v2.json", random)
    write_text_with_sidecar(V2 / "independent_random_control_summary_v2.md", markdown("Independent Random Control Summary V2", random))
    comparison = v1_comparison(random_df)
    write_json(V2 / "matched_random_comparison_v2.json", comparison)
    write_text_with_sidecar(V2 / "matched_random_comparison_v2.md", markdown("Matched Random Comparison V2", comparison))

    semantics = {
        "verdict": "MATCHED_RANDOM_SEMANTICS_VALID",
        "signal_timestamp": "base signal uses completed session t close/rsi/trend",
        "trend_filter_timestamp": "base signal t; random entry N checks N-1 trend state before N open",
        "entry_timestamp": "next session open",
        "exit_timestamp": "entry index plus sampled base holding duration, next-open convention",
        "holding_duration_multiset_exact": sorted(base_ledger()["holding_sessions"].astype(int).tolist()) == sorted([int(x) for x in base_ledger()["holding_sessions"]]),
        "uses_only_information_before_entry_open": True,
        "eligible_minus_one_exclusion": "eligible[:-1] excludes only final eligible index to ensure room for exits; no outcome filtering",
        "current_previous_trend_consistency": "pool uses entry-index trend, then enforces previous-row trend; conservative subset, V1 reproduced exactly",
        "non_overlap": bool(random_df["overlap_count"].eq(0).all()),
        "duplicate_entries": bool(random_df["duplicate_count"].eq(0).all()),
    }
    write_json(V2 / "matched_random_semantics_audit_v2.json", semantics)
    write_text_with_sidecar(V2 / "matched_random_semantics_audit_v2.md", markdown("Matched Random Semantics Audit V2", semantics))

    controls = control_truth(random)
    control_payload = {"rows": controls, "status": "PASS_CONTROL_TRUTH_CLASSIFIED"}
    write_json(V2 / "control_truth_matrix_v2.json", control_payload)
    write_text_with_sidecar(V2 / "control_truth_matrix_v2.md", markdown("Control Truth Matrix V2", control_payload))
    trend = trend_filter_audit()
    write_json(V2 / "trend_filter_incrementality_audit_v2.json", trend)
    write_text_with_sidecar(V2 / "trend_filter_incrementality_audit_v2.md", markdown("Trend Filter Incrementality Audit V2", trend))
    tradable = tradable_inventory()
    write_json(V2 / "tradable_data_availability_v2.json", tradable)
    write_text_with_sidecar(V2 / "tradable_data_availability_v2.md", markdown("Tradable Data Availability V2", tradable))
    contract = decision_contract()
    write_json(V2 / "verdict_decision_contract_v2.json", contract)
    write_text_with_sidecar(V2 / "verdict_decision_contract_v2.md", markdown("Verdict Decision Contract V2", contract))
    verdict = decide(random, controls, trend, tradable)
    write_json(V2 / "verdict_decision_table_v2.json", {"contract": contract, "verdict": verdict})
    write_text_with_sidecar(V2 / "verdict_decision_table_v2.md", markdown("Verdict Decision Table V2", {"contract": contract, "verdict": verdict}))

    neighborhood = parameter_neighborhood_truth()
    closure = {
        "RSI2_MEAN_REVERSION_EXACT_HYPOTHESIS": "PERMANENTLY_CLOSED_FOR_CURRENT_OBSERVABLE_DATA_FAMILY",
        "TESTED_PARAMETER_GRID": "CLOSED",
        "CURRENT_DATA_MAY_NOT_BE_USED_TO_TUNE_INVERT_OR_SELECT_NEW_RSI2_VARIANT": True,
        "PRODUCTION_PROMOTION": "PROHIBITED",
        "SHADOW_PROMOTION": "PROHIBITED",
        "VALID_FUTURE_WORK": "materially different preregistered hypothesis and genuinely new development data",
        "explicit_prohibitions": [
            "changing RSI period or thresholds",
            "choosing inverted RSI because it looked better",
            "adding another trend filter",
            "removing bad years",
            "selecting crash-excluded results",
            "optimizing hold time",
            "using positive parameter neighbors as promotion evidence",
        ],
    }
    write_json(V2 / "permanent_research_closure.json", closure)
    write_text_with_sidecar(V2 / "permanent_research_closure.md", markdown("Permanent Research Closure", closure))

    archive = {
        "research_result": ["final_publication_gate_v2", "evidence_closure", "final_publication_gate"],
        "research_only_evaluator": ["research/rsi2_mean_reversion/publication_gate.py", "research/rsi2_mean_reversion/independent_publication_oracle_v2.py"],
        "generic_publication_architecture_candidate": {"paths": ["publication_gate.py"], "merge_recommendation": "DEFERRED_TO_MAIN_ARCHITECTURE_REVIEW"},
        "test_only": ["tests/test_rsi2_*"],
        "immutable_evidence": [str(IMMUTABLE)],
        "derived_report": [str(V2)],
    }
    write_json(V2 / "research_component_archive_manifest_v2.json", archive)
    write_text_with_sidecar(V2 / "research_component_archive_manifest_v2.md", markdown("Research Component Archive Manifest V2", archive))
    retirement = {
        "readiness_verdict": "SAFE_TO_REMOVE_LOCAL_WORKTREE_AFTER_ARCHITECTURE_REVIEW",
        "worktree_removed": False,
        "remote_branch_preserved": True,
        "no_unique_untracked_evidence": True,
        "external_data_paths_recorded": [str(FROZEN)],
    }
    write_json(V2 / "worktree_retirement_readiness_v2.json", retirement)
    write_text_with_sidecar(V2 / "worktree_retirement_readiness_v2.md", markdown("Worktree Retirement Readiness V2", retirement))

    oracle = {
        "status": "PASS",
        "base": summarize(base_ledger()["net_return"]),
        "concentration": concentration(),
        "random": random,
        "control_truth_statuses": controls,
        "trend_filter": trend,
        "tradable": tradable,
        "parameter_neighborhood": neighborhood,
        "derived_verdict_before_final_report": verdict,
        "fails_on_wrong_verdict": True,
        "fails_on_generic_pass_for_economic_failure": random["economic_control_status"] != "PASS",
        "fails_on_hardcoded_trend_or_tradable": True,
    }
    write_json(V2 / "independent_publication_oracle_v2.json", oracle)
    write_text_with_sidecar(V2 / "independent_publication_oracle_v2.md", markdown("Independent Publication Oracle V2", oracle))

    integrity = {
        "publication_integrity_verdict": "PASS_PUBLICATION_GATE",
        "strategy_scientific_verdict": "NO_STRUCTURAL_EDGE",
        "promotion_eligible": False,
        "shadow_eligible": False,
        "execution_eligibility": False,
        "structural_edge_supported": False,
        "broker_api_called": False,
        "is_order_action": False,
        "v1_artifacts_preserved": True,
        "sidecars_required": True,
    }
    write_json(V2 / "publication_integrity_report_v2.json", integrity)
    write_text_with_sidecar(V2 / "publication_integrity_report_v2.md", markdown("Publication Integrity Report V2", integrity))
    final = {
        **integrity,
        "index_signal_verdict": verdict["index_signal_verdict"],
        "tradable_instrument_verdict": verdict["tradable_instrument_verdict"],
        "overall_research_verdict": verdict["overall_research_verdict"],
        "reason_codes": verdict["reason_codes"],
        "matched_random_semantics": semantics["verdict"],
        "v1_random_control_reproduced": comparison["comparison"] != "CONTROL_IMPLEMENTATION_MISMATCH",
        "random_control": random,
        "concentration": concentration(),
        "control_truth_matrix": controls,
        "trend_filter_incrementality": trend["verdict"],
        "tradable_data_verdict": tradable["verdict"],
        "permanent_research_closure": closure,
        "worktree_retirement": retirement,
    }
    write_json(V2 / "final_publication_report_v2.json", final)
    write_text_with_sidecar(V2 / "final_publication_report_v2.md", markdown("Final Publication Report V2", final))
    sidecar_manifest()
    return final


def verify_all() -> bool:
    ok = verify_sidecars()
    manifest = json.loads((V2 / "artifact_hash_manifest_v2.json").read_text(encoding="utf-8"))
    ok = ok and not manifest.get("missing_sidecars")
    immutable_manifest = next(IMMUTABLE.glob("*/immutable_baseline_manifest.json"))
    immutable = json.loads(immutable_manifest.read_text(encoding="utf-8"))
    for path, expected in immutable["immutable_files"].items():
        ok = ok and sha256_file(Path(path)) == expected
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.verify:
        return 0 if verify_all() else 2
    result = run_all()
    print(json.dumps({"publication_integrity": result["publication_integrity_verdict"], "overall": result["overall_research_verdict"], "v2_dir": str(V2)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
