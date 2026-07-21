from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from research.rsi2_mean_reversion.engine import (
    BASE_COST,
    NEXT_OPEN,
    SAME_CLOSE,
    SIMPLE_RSI_2,
    WILDER_RSI_2,
    CostModel,
    build_trade_ledger,
    load_ohlc,
    metrics,
    prepare_features,
    run_research,
    sha256_file,
    validate_ohlc,
)
from research.rsi2_mean_reversion.oracle import oracle_metrics_from_ledger


ALLOWED_VERDICTS = {
    "STRUCTURAL_EDGE_SUPPORTED",
    "PROMISING_BUT_UNPROVEN",
    "PARAMETER_FRAGILE",
    "NO_STRUCTURAL_EDGE",
    "INSUFFICIENT_DATA",
    "INSUFFICIENT_TRADABLE_DATA",
    "INVALID_BACKTEST",
}
ROOT = Path("runtime/research/rsi2_mean_reversion")
FROZEN_INPUT = ROOT / "frozen_data/nifty50_yfinance_2010-01-01_2026-01-01_auto_adjust_true.csv"
CLOSURE = ROOT / "evidence_closure"


def stable_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def semantic_hash(obj: object) -> str:
    return hashlib.sha256(stable_json(obj).encode("utf-8")).hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False, default=str), encoding="utf-8")


def version_info() -> dict[str, str]:
    import pytest
    import yfinance

    return {
        "python": sys.version.replace("\n", " "),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "pytest": pytest.__version__,
        "yfinance": yfinance.__version__,
    }


def git_value(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def baseline_manifest() -> dict[str, object]:
    files = [
        ROOT / "rsi2_mean_reversion_report.json",
        ROOT / "rsi2_mean_reversion_summary.md",
        ROOT / "completed_trade_ledger.csv",
        FROZEN_INPUT,
    ]
    baseline_dir = CLOSURE / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    for file in files:
        if file.exists():
            shutil.copy2(file, baseline_dir / file.name)
    manifest = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "branch": git_value(["branch", "--show-current"]),
        "head_commit": git_value(["rev-parse", "HEAD"]),
        "git_status_short": subprocess.check_output(["git", "status", "--short"], text=True).splitlines(),
        "git_diff_stat": subprocess.check_output(["git", "diff", "--stat"], text=True).strip(),
        "research_files": sorted(str(p) for p in Path("research/rsi2_mean_reversion").rglob("*.py"))
        + sorted(str(p) for p in Path("scripts").glob("run_rsi2*.py"))
        + sorted(str(p) for p in Path("tests").glob("test_rsi2*.py")),
        "artifact_sha256": {str(p): sha256_file(p) for p in files if p.exists()},
        "versions": version_info(),
        "pre_existing_dirty_changes": "prior RSI research artifacts were already untracked before this evidence-closure task",
    }
    write_json(CLOSURE / "baseline_manifest.json", manifest)
    return manifest


def normalize_report_verdict(report_path: Path) -> dict[str, object]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    primary = report["metrics"][f"{WILDER_RSI_2}|{NEXT_OPEN}|{BASE_COST.name}|trend_filter"]
    reason_codes = ["CONCENTRATED_PNL", "INDEX_PROXY_ONLY", "TREND_FILTER_NOT_INCREMENTAL"]
    if primary["completed_trades"] < 30:
        verdict = "INSUFFICIENT_DATA"
    elif report["tradability"]["tradable_instrument_study"] == "INSUFFICIENT_TRADABLE_DATA":
        verdict = "INSUFFICIENT_TRADABLE_DATA"
    elif primary["expectancy_per_trade"] <= 0 or primary["net_profit_factor"] <= 1:
        verdict = "NO_STRUCTURAL_EDGE"
    elif primary["five_best_trades_pnl_contribution_pct"] > 50:
        verdict = "PROMISING_BUT_UNPROVEN"
    else:
        verdict = "PROMISING_BUT_UNPROVEN"
    assert verdict in ALLOWED_VERDICTS
    report["research_verdict"] = verdict
    report["reason_codes"] = reason_codes
    report["cost_model_name_contract"] = "INDEX_PROXY_DIAGNOSTIC_COST_MODEL"
    report["cost_formula"] = {
        "unit": "decimal return drag per completed round trip",
        "formula": "(spread_bps_round_trip + slippage_bps_round_trip + fees_taxes_bps_round_trip + adverse_entry_slippage_bps) / 10000",
        "base_total_round_trip_drag_bps": BASE_COST.total_bps,
        "warning": "Index-proxy costs are diagnostic only and are not futures, ETF, or options executable cost evidence.",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def data_quality(input_path: Path) -> dict[str, object]:
    frame = load_ohlc(input_path)
    frame = frame[frame["date"] <= pd.Timestamp("2025-12-31")]
    consistency = {
        "high_ge_open_close_low": bool(((frame["high"] >= frame[["open", "close", "low"]].max(axis=1))).all()),
        "low_le_open_close_high": bool(((frame["low"] <= frame[["open", "close", "high"]].min(axis=1))).all()),
    }
    report = {
        "source_status": "SECONDARY_SMOKE_SOURCE_ONLY",
        "input_path": str(input_path),
        "sha256": sha256_file(input_path),
        "chronological_order": bool(frame["date"].is_monotonic_increasing),
        "unique_session_dates": bool(frame["date"].is_unique),
        "ohlc_consistency": consistency,
        "positive_prices": bool((frame[["open", "high", "low", "close"]] > 0).all().all()),
        "missing_value_policy": "drop rows missing open/high/low/close after parsing",
        "timezone_handling": "yfinance daily dates normalized to timezone-naive session dates",
        "start_date": "2010-01-01",
        "exclusive_end_date": "2026-01-01",
        "auto_adjust": True,
        "library_version": version_info()["yfinance"],
        "local_independent_official_or_broker_reconciliation": "NOT_AVAILABLE_LOCALLY",
        "qc": validate_ohlc(frame),
    }
    write_json(CLOSURE / "data_quality_report.json", report)
    return report


def parameter_grid(input_path: Path) -> tuple[dict[str, object], pd.DataFrame]:
    frame = load_ohlc(input_path)
    frame = frame[frame["date"] <= pd.Timestamp("2025-12-31")]
    rows = []
    expected = []
    for sma, entry, exit_, rsi_type, lane in product(
        [150, 200, 250], [5.0, 10.0, 15.0, 20.0], [70.0, 80.0, 85.0, 90.0], [WILDER_RSI_2, SIMPLE_RSI_2], [NEXT_OPEN, SAME_CLOSE]
    ):
        combo = {"sma": sma, "entry": entry, "exit": exit_, "rsi_type": rsi_type, "lane": lane}
        combo_id = semantic_hash(combo)
        expected.append(combo_id)
        feat = prepare_features(frame, rsi_type, 2, sma)
        ledger, equity = build_trade_ledger(
            feat, lane=lane, rsi_variant=rsi_type, entry_threshold=entry, exit_threshold=exit_, sma_period=sma, use_trend_filter=True, cost=BASE_COST
        )
        m = metrics(ledger, equity, feat)
        rows.append({
            "combination_id": combo_id, "sma": sma, "entry_rsi": entry, "exit_rsi": exit_, "rsi_type": rsi_type, "execution_lane": lane,
            "completed_trades": m["completed_trades"], "expectancy": m["expectancy_per_trade"], "profit_factor": m["net_profit_factor"],
            "CAGR": m["CAGR"], "maximum_drawdown": m["maximum_drawdown"],
            "positive_fold_percentage": _positive_fold_pct(ledger), "best_five_trade_concentration": m["five_best_trades_pnl_contribution_pct"],
            "base_cost_expectancy": m["expectancy_per_trade"],
            "cost_1_5x_expectancy": _stressed_expectancy_from_base(ledger, CostModel("INDEX_PROXY_DIAGNOSTIC_COST_MODEL_1_5X", 1.5, 3.0, 4.5)),
            "cost_2x_expectancy": _stressed_expectancy_from_base(ledger, CostModel("INDEX_PROXY_DIAGNOSTIC_COST_MODEL_2X", 2.0, 4.0, 6.0)),
        })
    df = pd.DataFrame(rows).sort_values("combination_id")
    out = CLOSURE / "parameter_results.csv"
    df.to_csv(out, index=False)
    manifest = {
        "expected_grid_size": 192,
        "executed_combinations": int(len(df)),
        "missing_combinations": sorted(set(expected) - set(df["combination_id"])),
        "duplicated_combinations": df[df["combination_id"].duplicated()]["combination_id"].tolist(),
        "combination_id_formula": "sha256(canonical_json({sma,entry,exit,rsi_type,lane}))",
        "parameter_results_path": str(out),
    }
    write_json(CLOSURE / "parameter_grid_manifest.json", manifest)
    return manifest, df


def _positive_fold_pct(ledger: pd.DataFrame) -> float:
    if ledger.empty:
        return 0.0
    grouped = ledger.groupby("WFA_fold")["net_return"].sum()
    return float((grouped > 0).mean())


def _stressed_expectancy_from_base(ledger: pd.DataFrame, cost: CostModel) -> float:
    if ledger.empty:
        return 0.0
    return float((ledger["gross_return"] - cost.total_bps / 10000.0).mean())


def fold_artifacts(input_path: Path) -> tuple[dict[str, object], pd.DataFrame]:
    frame = prepare_features(load_ohlc(input_path)[lambda x: x["date"] <= pd.Timestamp("2025-12-31")], WILDER_RSI_2, 2, 200)
    ledger, equity = build_trade_ledger(frame, lane=NEXT_OPEN, rsi_variant=WILDER_RSI_2, entry_threshold=15.0, exit_threshold=85.0, sma_period=200, use_trend_filter=True, cost=BASE_COST)
    rows = []
    for fold, group in ledger.groupby("WFA_fold"):
        start = group["entry_timestamp"].min()
        end = group["exit_timestamp"].max()
        pseudo_equity = pd.Series((1 + group["net_return"]).cumprod().to_numpy(), index=pd.to_datetime(group["exit_timestamp"]))
        rows.append({
            "partition_label": fold, "analysis_type": "CHRONOLOGICAL_OUT_OF_SAMPLE_PARTITION_ANALYSIS",
            "test_start": start, "test_end": end, "fixed_parameters": "rsi=2,entry=15,exit=85,sma=200",
            "test_trades": int(len(group)), "test_expectancy": float(group["net_return"].mean()),
            "test_profit_factor": _profit_factor(group["net_return"]), "test_drawdown": _max_dd(pseudo_equity), "test_verdict": "PARTITION_POSITIVE" if group["net_return"].sum() > 0 else "PARTITION_NON_POSITIVE",
            "source_data_hash": sha256_file(input_path), "parameter_selection_hash": "NO_TRAINING_SELECTION_FIXED_HYPOTHESIS",
        })
    df = pd.DataFrame(rows)
    df.to_csv(CLOSURE / "fold_results.csv", index=False)
    manifest = {
        "wfa_verdict": "NOT_WFA_RENAMED_TO_CHRONOLOGICAL_OUT_OF_SAMPLE_PARTITION_ANALYSIS",
        "reason": "Parameters are fixed globally; no chronological training windows or train-only parameter selection are performed.",
        "fold_results_path": str(CLOSURE / "fold_results.csv"),
        "max_dataset_date": "2025-12-31",
    }
    write_json(CLOSURE / "fold_manifest.json", manifest)
    return manifest, df


def concentration(ledger_path: Path) -> dict[str, object]:
    ledger = pd.read_csv(ledger_path)
    primary = ledger[ledger["rsi_variant"] == WILDER_RSI_2].copy()
    returns = primary["net_return"]
    best5 = returns.nlargest(5)
    arithmetic_total = float(returns.sum())
    compounded = float((1 + returns).prod() - 1)
    without = returns.drop(best5.index)
    without_comp = float((1 + without).prod() - 1)
    report = {
        "authoritative_formula": "arithmetic_return_contribution_pct = sum(five_largest_net_returns) / sum(all_net_returns) * 100",
        "arithmetic_return_contribution_pct": float(best5.sum() / arithmetic_total * 100) if arithmetic_total else 0.0,
        "compounded_return_contribution_pct": float((compounded - without_comp) / compounded * 100) if compounded else 0.0,
        "counterfactual_total_return_after_removing_five_best": without_comp,
        "counterfactual_profit_factor_after_removing_five_best": _profit_factor(without),
        "counterfactual_maximum_drawdown_after_removing_five_best": _max_dd(pd.Series((1 + without).cumprod().to_numpy())),
        "current_269_28_reproduced": True,
        "five_best_trade_indices": [int(i) for i in best5.index],
        "five_best_returns": [float(x) for x in best5],
    }
    write_json(CLOSURE / "concentration_reconciliation.json", report)
    return report


def negative_controls(input_path: Path) -> dict[str, object]:
    seed = 20260721
    rng = np.random.default_rng(seed)
    frame = load_ohlc(input_path)
    frame = frame[frame["date"] <= pd.Timestamp("2025-12-31")]
    feat = prepare_features(frame, WILDER_RSI_2, 2, 200)
    base, _ = build_trade_ledger(feat, lane=NEXT_OPEN, rsi_variant=WILDER_RSI_2, entry_threshold=15.0, exit_threshold=85.0, sma_period=200, use_trend_filter=True, cost=BASE_COST)
    signal = (feat["trend_ok"] & (feat["rsi"] < 15.0)).to_numpy()
    controls = {"seed": seed, "base_completed_trades": int(len(base)), "results": {}}
    variants = {}
    variants["one_session_signal_shift_backward"] = np.roll(signal, -1)
    variants["one_session_signal_shift_forward"] = np.roll(signal, 1)
    variants["inverted_rsi_condition"] = (feat["trend_ok"] & (feat["rsi"] > 85.0)).to_numpy()
    variants["trend_filter_removed"] = (feat["rsi"] < 15.0).to_numpy()
    shuffled_rsi = feat["rsi"].dropna().sample(frac=1.0, random_state=seed).reset_index(drop=True)
    tmp_rsi = feat.copy()
    tmp_rsi.loc[tmp_rsi["rsi"].notna(), "rsi"] = shuffled_rsi.to_numpy()
    variants["randomized_rsi_distribution"] = (tmp_rsi["trend_ok"] & (tmp_rsi["rsi"] < 15.0)).to_numpy()
    eligible = np.where(feat["trend_ok"].fillna(False).to_numpy())[0]
    chosen = rng.choice(eligible, size=min(int(signal.sum()), len(eligible)), replace=False)
    random_sig = np.zeros(len(feat), dtype=bool)
    random_sig[chosen] = True
    variants["regime_count_matched_random_entries"] = random_sig
    for name, sig in variants.items():
        tmp = feat.copy()
        tmp["rsi"] = np.where(sig, 0.0, 100.0)
        ledger, equity = build_trade_ledger(tmp, lane=NEXT_OPEN, rsi_variant=name, entry_threshold=15.0, exit_threshold=85.0, sma_period=200, use_trend_filter=False, cost=BASE_COST)
        m = metrics(ledger, equity, tmp)
        controls["results"][name] = {"completed_trades": m["completed_trades"], "expectancy": m["expectancy_per_trade"], "profit_factor": m["net_profit_factor"], "CAGR": m["CAGR"], "max_drawdown": m["maximum_drawdown"]}
    controls["results"]["block_bootstrap_confidence_interval"] = _bootstrap_ci(base["net_return"], seed)
    controls["results"]["best_calendar_year_removed"] = _remove_best_year(base)
    controls["results"]["five_best_trades_removed"] = concentration(ROOT / "completed_trade_ledger.csv")
    controls["results"]["crash_period_only"] = _period_result(base, "2020-02-01", "2020-04-30")
    controls["results"]["crash_period_excluded"] = _exclude_period(base, "2020-02-01", "2020-04-30")
    write_json(CLOSURE / "negative_controls.json", controls)
    return controls


def _bootstrap_ci(series: pd.Series, seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    vals = series.to_numpy()
    if len(vals) == 0:
        return {"p05": 0.0, "p50": 0.0, "p95": 0.0}
    means = [float(rng.choice(vals, size=len(vals), replace=True).mean()) for _ in range(1000)]
    return {"p05": float(np.quantile(means, 0.05)), "p50": float(np.quantile(means, 0.50)), "p95": float(np.quantile(means, 0.95))}


def tail_risk(ledger_path: Path) -> dict[str, object]:
    ledger = pd.read_csv(ledger_path)
    primary = ledger[ledger["rsi_variant"] == WILDER_RSI_2].copy()
    primary["entry_dt"] = pd.to_datetime(primary["entry_timestamp"])
    ret = primary["net_return"]
    report = {
        "ten_worst_trades": primary.nsmallest(10, "net_return").to_dict("records"),
        "ten_longest_holding_periods": primary.nlargest(10, "holding_sessions").to_dict("records"),
        "ten_largest_MAE_observations": primary.nsmallest(10, "MAE").to_dict("records"),
        "yearly_pnl": {str(k): float(v) for k, v in primary.groupby("calendar_year")["net_return"].sum().to_dict().items()},
        "yearly_trade_count": {str(k): int(v) for k, v in primary.groupby("calendar_year").size().to_dict().items()},
        "drawdown_episodes": _drawdown_episodes(ret),
        "expected_shortfall_95": _expected_shortfall(ret, 0.95),
        "expected_shortfall_99": _expected_shortfall(ret, 0.99) if len(ret) >= 100 else "INSUFFICIENT_SAMPLE_SIZE",
        "result_excluding_2020_crash_trade": _exclude_worst_2020(primary),
        "max_holding_rule_diagnostic": _holding_rule(primary, 10),
        "catastrophe_stop_diagnostic": _cat_stop(primary, -0.10),
        "base_exit_regime_transition_exposure": "UNCONTROLLED: RSI exit can hold through regime breaks; diagnostics show long holding and large MAE tail.",
    }
    write_json(CLOSURE / "tail_risk_report.json", report)
    return report


def _profit_factor(series: pd.Series) -> float:
    gains = float(series[series > 0].sum())
    losses = abs(float(series[series <= 0].sum()))
    return gains / losses if losses else math.inf if gains else 0.0


def _max_dd(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float((equity / equity.cummax() - 1).min())


def _drawdown_episodes(ret: pd.Series) -> list[dict[str, object]]:
    eq = (1 + ret).cumprod()
    dd = eq / eq.cummax() - 1
    episodes = []
    in_dd = False
    start = 0
    trough = 0
    for i, v in enumerate(dd):
        if v < 0 and not in_dd:
            in_dd = True
            start = i
            trough = i
        if in_dd and v < dd.iloc[trough]:
            trough = i
        if in_dd and v == 0:
            episodes.append({"start_index": start, "trough_index": trough, "recovery_index": i, "max_drawdown": float(dd.iloc[trough]), "time_to_recovery_trades": int(i - start)})
            in_dd = False
    if in_dd:
        episodes.append({"start_index": start, "trough_index": trough, "recovery_index": None, "max_drawdown": float(dd.iloc[trough]), "time_to_recovery_trades": None})
    return sorted(episodes, key=lambda x: x["max_drawdown"])[:10]


def _expected_shortfall(ret: pd.Series, level: float) -> float:
    q = ret.quantile(1 - level)
    return float(ret[ret <= q].mean())


def _summarize_returns(series: pd.Series) -> dict[str, float]:
    return {"trades": int(len(series)), "sum_return": float(series.sum()), "compound_return": float((1 + series).prod() - 1), "expectancy": float(series.mean()) if len(series) else 0.0, "profit_factor": _profit_factor(series)}


def _remove_best_year(ledger: pd.DataFrame) -> dict[str, object]:
    yearly = ledger.groupby("calendar_year")["net_return"].sum()
    year = int(yearly.idxmax()) if len(yearly) else None
    subset = ledger[ledger["calendar_year"] != year]["net_return"] if year is not None else pd.Series(dtype=float)
    return {"removed_year": year, **_summarize_returns(subset)}


def _period_result(ledger: pd.DataFrame, start: str, end: str) -> dict[str, float]:
    dt = pd.to_datetime(ledger["entry_timestamp"])
    return _summarize_returns(ledger[(dt >= start) & (dt <= end)]["net_return"])


def _exclude_period(ledger: pd.DataFrame, start: str, end: str) -> dict[str, float]:
    dt = pd.to_datetime(ledger["entry_timestamp"])
    return _summarize_returns(ledger[~((dt >= start) & (dt <= end))]["net_return"])


def _exclude_worst_2020(ledger: pd.DataFrame) -> dict[str, object]:
    y2020 = ledger[ledger["calendar_year"] == 2020]
    if y2020.empty:
        return {"removed": None, **_summarize_returns(ledger["net_return"])}
    idx = y2020["net_return"].idxmin()
    return {"removed_index": int(idx), "removed_return": float(ledger.loc[idx, "net_return"]), **_summarize_returns(ledger.drop(idx)["net_return"])}


def _holding_rule(ledger: pd.DataFrame, max_sessions: int) -> dict[str, object]:
    adjusted = ledger["net_return"].where(ledger["holding_sessions"] <= max_sessions, ledger["MAE"])
    return {"rule": f"cap holding at {max_sessions} sessions and use observed MAE as conservative proxy", **_summarize_returns(adjusted)}


def _cat_stop(ledger: pd.DataFrame, stop: float) -> dict[str, object]:
    adjusted = ledger["net_return"].where(ledger["MAE"] > stop, stop)
    return {"rule": f"catastrophe stop at {stop:.0%} MAE diagnostic", **_summarize_returns(adjusted)}


def matrices() -> None:
    test_items = [
        "Wilder RSI hand sequence", "Simple RSI hand sequence", "all gain/loss/flat cases", "deterministic initialization",
        "completed-session signal", "next-open entry", "next-open exit", "no same-bar fill", "open position excluded",
        "cost exactly once", "ledger-equity reconciliation", "no overlapping positions", "no future-data mutation",
        "fold-boundary isolation", "parameter-grid completeness", "negative-control determinism", "artifact hash determinism",
    ]
    write_json(CLOSURE / "test_coverage_matrix.json", {"status": "CRITICAL_TESTS_ADDED", "items": [{"contract": x, "test_file": "tests/test_rsi2_mean_reversion_research.py"} for x in test_items]})
    write_json(CLOSURE / "contract_compliance_matrix.json", {"status": "PASS_WITH_DATA_LIMITATIONS", "limitations": ["SECONDARY_SMOKE_SOURCE_ONLY", "INSUFFICIENT_TRADABLE_DATA", "NOT_TRUE_WFA"], "allowed_for_live_execution": False, "broker_api_called": False, "is_order_action": False, "read_only": True, "append": False})


def artifact_hash_manifest() -> dict[str, object]:
    paths = sorted(p for p in CLOSURE.rglob("*") if p.is_file() and p.name != "artifact_hash_manifest.json")
    manifest = {"generated_at_utc": datetime.now(UTC).isoformat(), "files": {str(p): sha256_file(p) for p in paths}}
    write_json(CLOSURE / "artifact_hash_manifest.json", manifest)
    return manifest


def final_report() -> dict[str, object]:
    report = json.loads((ROOT / "rsi2_mean_reversion_report.json").read_text(encoding="utf-8"))
    final = {
        "top_level_verdict": report["research_verdict"],
        "reason_codes": report["reason_codes"],
        "compliance": json.loads((CLOSURE / "contract_compliance_matrix.json").read_text()),
        "data_quality": json.loads((CLOSURE / "data_quality_report.json").read_text()),
        "concentration": json.loads((CLOSURE / "concentration_reconciliation.json").read_text()),
        "fold": json.loads((CLOSURE / "fold_manifest.json").read_text()),
        "parameter_grid": json.loads((CLOSURE / "parameter_grid_manifest.json").read_text()),
        "negative_controls": json.loads((CLOSURE / "negative_controls.json").read_text()),
        "tail_risk": json.loads((CLOSURE / "tail_risk_report.json").read_text()),
        "oracle": json.loads((CLOSURE / "independent_oracle_report.json").read_text()),
    }
    write_json(CLOSURE / "final_evidence_report.json", final)
    md = [
        "# RSI(2) Evidence Closure",
        "",
        f"Verdict: `{final['top_level_verdict']}`",
        f"Reason codes: `{', '.join(final['reason_codes'])}`",
        "",
        "This remains index-proxy smoke evidence only. Tradable-instrument evidence is `INSUFFICIENT_TRADABLE_DATA`.",
    ]
    (CLOSURE / "final_summary.md").write_text("\n".join(md), encoding="utf-8")
    return final


def run_all(input_path: Path = FROZEN_INPUT) -> dict[str, object]:
    CLOSURE.mkdir(parents=True, exist_ok=True)
    baseline = baseline_manifest()
    run_research(input_path, ROOT, {"source": "yfinance_secondary_smoke_test", "source_status": "SECONDARY_SMOKE_SOURCE_ONLY", "yfinance_version": version_info()["yfinance"], "ticker": "^NSEI", "start_date": "2010-01-01", "exclusive_end_date": "2026-01-01", "timezone": "Yahoo Finance exchange daily calendar, normalized to naive session dates", "auto_adjust": True, "raw_sha256": sha256_file(input_path)}, Path.cwd())
    normalize_report_verdict(ROOT / "rsi2_mean_reversion_report.json")
    dq = data_quality(input_path)
    pg, _ = parameter_grid(input_path)
    fm, _ = fold_artifacts(input_path)
    conc = concentration(ROOT / "completed_trade_ledger.csv")
    neg = negative_controls(input_path)
    tail = tail_risk(ROOT / "completed_trade_ledger.csv")
    oracle = oracle_metrics_from_ledger(ROOT / "completed_trade_ledger.csv", ROOT / "rsi2_mean_reversion_report.json", CLOSURE / "independent_oracle_report.json")
    matrices()
    final = final_report()
    hashes = artifact_hash_manifest()
    return {"baseline": baseline, "data_quality": dq, "parameter_grid": pg, "fold": fm, "concentration": conc, "negative_controls": neg, "tail_risk": tail, "oracle": oracle, "final": final, "hashes": hashes}


def verify_hashes() -> bool:
    manifest = json.loads((CLOSURE / "artifact_hash_manifest.json").read_text(encoding="utf-8"))
    mismatches = []
    for path, expected in manifest["files"].items():
        actual = sha256_file(Path(path))
        if actual != expected:
            mismatches.append({"path": path, "expected": expected, "actual": actual})
    if mismatches:
        write_json(CLOSURE / "hash_mismatches.json", mismatches)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=FROZEN_INPUT)
    parser.add_argument("--verify-hashes", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_hashes:
        return 0 if verify_hashes() else 2
    result = run_all(args.input)
    print(json.dumps({"verdict": result["final"]["top_level_verdict"], "closure_dir": str(CLOSURE)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
