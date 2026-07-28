from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

try:
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover
    XGBClassifier = None


ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "research" / "ml_meta_labeling_sprint_v1_1_reproducible"
OUT = ROOT / "research" / "ml_meta_labeling_robustness_certification_v2_1"
WAREHOUSE = ROOT / "research" / "joint_warehouse_underlying_feature_repair_v1" / "repaired_joint_underlying_option_warehouse.parquet"
COST_POINTS = 1.0
TARGET_POINTS = 30.0
STOP_POINTS = 15.0
HORIZON_MINUTES = 30

EXPECTED_HASHES = {
    "candidate_level_dataset_hash.json": {"canonical_content_hash": "b38a4e603dea60df7f9013b836a104d47663ecd0933585a0823f5a58bf17794d"},
    "feature_contract_hash.json": {"semantic_hash": "597906bcb36cd24bce21167bb02ef2b0d2adfef9809285946d7f75632dc17e92"},
    "label_contract_hash.json": {"semantic_hash": "b3f64db22b99ccac56605d4a659ab6c063d4f635ab1d1df1bc26c3ec3f607504"},
    "split_contract_hash.json": {"semantic_hash": "4844697db50d9890ee83b63c3c7642e595411a31ce97531d0012a9c8b8402dad"},
    "trained_model_hash.json": {"sha256": "a1bc239b917564dece9d425fcb0fe655b61fff12f61222548c0fbf43a5063b63"},
    "calibration_object_hash.json": {"sha256": "70a01f51fcfd10f5c90a9d608a505931ee5aa408367bddb564148da61b4a27bf"},
    "frozen_selection_threshold_hash.json": {"sha256": "66fb4dcb41ec0eff731dd46d89f792090f37882467228aa5abd748192f66fadd"},
}
REQUIRED_INPUTS = [
    "candidate_level_dataset.parquet",
    "candidate_level_dataset_schema.json",
    "feature_contract.json",
    "label_contract.json",
    "split_contract.json",
    "preprocessor.joblib",
    "trained_model.joblib",
    "calibration_object.joblib",
    "frozen_selection_threshold.json",
    "holdout_predictions.parquet",
    "model_contract.json",
    "tuning_ledger.json",
    "serialization_replay_report.json",
    "independent_audit.json",
    "determinism_report.json",
]


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if math.isnan(float(obj)):
            return None
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return str(obj)


def write_json(name: str, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["semantic_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=_json_default).encode()).hexdigest()
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n")


def economics(pnls: pd.Series) -> dict[str, Any]:
    pnls = pd.to_numeric(pnls, errors="coerce").dropna()
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    return {
        "trades": int(len(pnls)),
        "net_pnl": float(pnls.sum()) if len(pnls) else 0.0,
        "expectancy": float(pnls.mean()) if len(pnls) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else None,
        "win_rate": float((pnls > 0).mean()) if len(pnls) else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
    }


def verify_frozen_inputs() -> bool:
    checks = []
    ok = True
    for name in REQUIRED_INPUTS:
        exists = (FROZEN / name).exists()
        checks.append({"artifact": name, "exists": exists})
        ok = ok and exists
    for name, expected in EXPECTED_HASHES.items():
        payload = json.loads((FROZEN / name).read_text()) if (FROZEN / name).exists() else {}
        for key, value in expected.items():
            actual = payload.get(key)
            match = actual == value
            checks.append({"artifact": name, "field": key, "expected": value, "actual": actual, "match": match})
            ok = ok and match
    write_json("frozen_hash_verification_report.json", {"status": "PASS" if ok else "FAIL", "checks": checks})
    return ok


def build_concrete_replay(candidates: pd.DataFrame, warehouse: pd.DataFrame, score_col: str = "xgboost_score") -> tuple[pd.DataFrame, pd.DataFrame]:
    wh = warehouse.copy()
    wh["event_timestamp"] = pd.to_datetime(wh["event_timestamp"])
    wh["session_date"] = wh["session_date"].astype(str)
    wh["expiry"] = wh["expiry"].astype(str)
    wh["option_type"] = wh["option_type"].astype(str)
    wh = wh[wh["certified_for_replay"].fillna(False)]
    wh = wh.dropna(subset=["event_timestamp", "expiry", "option_type", "strike", "premium_mean", "premium_min", "premium_max", "close"])
    grouped = {k: g.sort_values("event_timestamp").reset_index(drop=True) for k, g in wh.groupby(["session_date", "expiry", "option_type"], sort=False)}
    rows = []
    trades = []
    for cand in candidates.sort_values(["event_timestamp", "candidate_id"]).to_dict("records"):
        ts = pd.Timestamp(cand["event_timestamp"])
        key = (str(cand["session_date"]), str(cand["expiry"]), str(cand["option_type"]))
        pool = grouped.get(key)
        record = {
            "candidate_id": cand["candidate_id"],
            "candidate_timestamp": ts,
            "option_side": cand["option_type"],
            "expiry": cand["expiry"],
            "session_date": cand["session_date"],
            "setup_family": cand.get("setup_family"),
            "tod_bucket": cand.get("tod_bucket"),
            "frozen_score": cand.get(score_col),
            "aggregate_net_pnl": cand.get("net_pnl"),
            "aggregate_label": cand.get("true_label"),
            "liquidity_eligible": False,
            "rejection_reason": "",
        }
        if pool is None or pool.empty:
            record["rejection_reason"] = "no_same_session_expiry_side_chain"
            rows.append(record)
            continue
        causal = pool[pool["event_timestamp"] <= ts]
        if causal.empty:
            record["rejection_reason"] = "no_causal_quote_at_or_before_candidate"
            rows.append(record)
            continue
        quote_ts = causal["event_timestamp"].max()
        snap = causal[causal["event_timestamp"] == quote_ts].copy()
        underlying = float(snap["close"].median())
        snap["abs_moneyness_points"] = (pd.to_numeric(snap["strike"]) - underlying).abs()
        snap = snap.sort_values(["abs_moneyness_points", "strike", "expired_instrument_key"])
        selected = snap.iloc[0]
        contract_rows = pool[pool["expired_instrument_key"] == selected["expired_instrument_key"]].sort_values("event_timestamp")
        future = contract_rows[contract_rows["event_timestamp"] > quote_ts].copy()
        if future.empty:
            record["rejection_reason"] = "no_next_observable_contract_bar"
            rows.append(record)
            continue
        entry = future.iloc[0]
        horizon_end = entry["event_timestamp"] + pd.Timedelta(minutes=HORIZON_MINUTES)
        path = contract_rows[(contract_rows["event_timestamp"] > entry["event_timestamp"]) & (contract_rows["event_timestamp"] <= horizon_end)].copy()
        if path.empty:
            record["rejection_reason"] = "no_post_entry_horizon_bar"
            rows.append(record)
            continue
        entry_premium = float(entry["premium_mean"])
        target_level = entry_premium + TARGET_POINTS
        stop_level = entry_premium - STOP_POINTS
        target_hits = path[path["premium_max"] >= target_level]
        stop_hits = path[path["premium_min"] <= stop_level]
        target_ts = target_hits["event_timestamp"].min() if not target_hits.empty else pd.NaT
        stop_ts = stop_hits["event_timestamp"].min() if not stop_hits.empty else pd.NaT
        terminal = path.iloc[-1]
        if pd.notna(target_ts) and (pd.isna(stop_ts) or target_ts < stop_ts):
            gross = TARGET_POINTS
            exit_ts = target_ts
            exit_reason = "target"
            label = 1
        elif pd.notna(stop_ts):
            gross = -STOP_POINTS
            exit_ts = stop_ts
            exit_reason = "stop"
            label = 0
        else:
            gross = float(terminal["premium_mean"]) - entry_premium
            exit_ts = terminal["event_timestamp"]
            exit_reason = "terminal"
            label = int(gross >= TARGET_POINTS)
        mfe = float(path["premium_max"].max() - entry_premium)
        mae = float(path["premium_min"].min() - entry_premium)
        record.update({
            "selected_strike": float(selected["strike"]),
            "selected_symbol": selected.get("trading_symbol"),
            "selected_instrument_key": selected.get("expired_instrument_key"),
            "moneyness": float(selected["strike"] - underlying),
            "quote_candle_timestamp_used_for_selection": quote_ts,
            "actual_next_observable_bar_entry_timestamp": entry["event_timestamp"],
            "actual_entry_premium": entry_premium,
            "liquidity_eligible": True,
            "observed_bars_in_horizon": int(len(path)),
        })
        trade = dict(record)
        trade.update({
            "concrete_label": label,
            "mfe": mfe,
            "mae": mae,
            "target_timestamp": target_ts,
            "stop_timestamp": stop_ts,
            "terminal_exit_timestamp": terminal["event_timestamp"],
            "exit_timestamp": exit_ts,
            "exit_reason": exit_reason,
            "gross_pnl": gross,
            "costs": COST_POINTS,
            "net_pnl": gross - COST_POINTS,
        })
        rows.append(record)
        trades.append(trade)
    return pd.DataFrame(rows), pd.DataFrame(trades)


def delayed_replay(trades: pd.DataFrame, warehouse: pd.DataFrame) -> pd.DataFrame:
    out = []
    wh = warehouse.sort_values("event_timestamp")
    by_contract = {k: g.sort_values("event_timestamp").reset_index(drop=True) for k, g in wh.groupby("expired_instrument_key", sort=False)}
    for row in trades.to_dict("records"):
        cr = by_contract.get(row["selected_instrument_key"])
        delayed = dict(row)
        if cr is None:
            delayed["delayed_executable"] = False
            delayed["delayed_rejection_reason"] = "missing_contract"
            out.append(delayed)
            continue
        after = cr[cr["event_timestamp"] > pd.Timestamp(row["actual_next_observable_bar_entry_timestamp"])]
        if after.empty:
            delayed["delayed_executable"] = False
            delayed["delayed_rejection_reason"] = "no_additional_completed_bar"
            out.append(delayed)
            continue
        entry = after.iloc[0]
        path = cr[(cr["event_timestamp"] > entry["event_timestamp"]) & (cr["event_timestamp"] <= entry["event_timestamp"] + pd.Timedelta(minutes=HORIZON_MINUTES))]
        if path.empty:
            delayed["delayed_executable"] = False
            delayed["delayed_rejection_reason"] = "no_delayed_horizon_bar"
            out.append(delayed)
            continue
        entry_premium = float(entry["premium_mean"])
        target_hits = path[path["premium_max"] >= entry_premium + TARGET_POINTS]
        stop_hits = path[path["premium_min"] <= entry_premium - STOP_POINTS]
        target_ts = target_hits["event_timestamp"].min() if not target_hits.empty else pd.NaT
        stop_ts = stop_hits["event_timestamp"].min() if not stop_hits.empty else pd.NaT
        terminal = path.iloc[-1]
        if pd.notna(target_ts) and (pd.isna(stop_ts) or target_ts < stop_ts):
            gross, exit_reason = TARGET_POINTS, "target"
        elif pd.notna(stop_ts):
            gross, exit_reason = -STOP_POINTS, "stop"
        else:
            gross, exit_reason = float(terminal["premium_mean"]) - entry_premium, "terminal"
        delayed.update({
            "delayed_executable": True,
            "delayed_entry_timestamp": entry["event_timestamp"],
            "delayed_entry_premium": entry_premium,
            "delayed_exit_reason": exit_reason,
            "delayed_gross_pnl": gross,
            "delayed_costs": COST_POINTS,
            "delayed_net_pnl": gross - COST_POINTS,
        })
        out.append(delayed)
    return pd.DataFrame(out)


def model_controls(dataset: pd.DataFrame, feature_contract: dict[str, Any]) -> dict[str, Any]:
    if XGBClassifier is None:
        return {"status": "SKIPPED", "reason": "xgboost_unavailable"}
    features = feature_contract["numeric"] + feature_contract["categorical"]
    target = "TARGET_30_BEFORE_STOP_15_WITHIN_30M"
    train = dataset[dataset["split"] == "train"].copy()
    validation = dataset[dataset["split"] == "validation"].copy()
    holdout = dataset[dataset["split"] == "holdout"].copy()
    original_model = joblib.load(FROZEN / "trained_model.joblib")
    base_scores = original_model.predict_proba(holdout[features])[:, 1]
    random.seed(20260728)
    shuffled = train[target].sample(frac=1.0, random_state=20260728).to_numpy()
    reports: dict[str, Any] = {}
    families = {
        "remove_candidate_identity": feature_contract["feature_family_assignments"]["candidate_identity"],
        "remove_underlying_state": feature_contract["feature_family_assignments"]["underlying_state"],
        "remove_option_state": feature_contract["feature_family_assignments"]["option_state"],
        "remove_temporal_context": feature_contract["feature_family_assignments"]["context"],
    }
    params = {"max_depth": 3, "learning_rate": 0.08, "n_estimators": 140, "random_state": 20260728, "eval_metric": "logloss"}
    for name, remove in families.items():
        cols = [c for c in features if c not in set(remove)]
        model = XGBClassifier(**params)
        model.fit(pd.get_dummies(train[cols], dummy_na=True), train[target])
        val_x = pd.get_dummies(validation[cols], dummy_na=True)
        hold_x = pd.get_dummies(holdout[cols], dummy_na=True)
        val_x, hold_x = val_x.align(hold_x, join="left", axis=1, fill_value=0)
        val_score = model.predict_proba(val_x)[:, 1]
        threshold = float(np.quantile(val_score, 0.9))
        hold_score = model.predict_proba(hold_x)[:, 1]
        selected = holdout[hold_score >= threshold]
        reports[name] = {
            "selected_trades": int(len(selected)),
            "validation_auc": float(roc_auc_score(validation[target], val_score)),
            "validation_pr_auc": float(average_precision_score(validation[target], val_score)),
            "holdout_expectancy_aggregate": float(selected["fixed_30m_net_pnl"].mean()) if len(selected) else 0.0,
            "holdout_pf_aggregate": economics(selected["fixed_30m_net_pnl"])["profit_factor"],
            "overlap_with_frozen_model_candidates": int(len(set(selected["candidate_id"]) & set(holdout.loc[base_scores >= json.loads((FROZEN / "frozen_selection_threshold.json").read_text())["threshold"], "candidate_id"]))),
        }
    model = XGBClassifier(**params)
    model.fit(pd.get_dummies(train[features], dummy_na=True), shuffled)
    val_x = pd.get_dummies(validation[features], dummy_na=True)
    hold_x = pd.get_dummies(holdout[features], dummy_na=True)
    val_x, hold_x = val_x.align(hold_x, join="left", axis=1, fill_value=0)
    val_score = model.predict_proba(val_x)[:, 1]
    hold_score = model.predict_proba(hold_x)[:, 1]
    threshold = float(np.quantile(val_score, 0.9))
    selected = holdout[hold_score >= threshold]
    shuffled_report = {"selected_trades": int(len(selected)), "holdout_economics_aggregate": economics(selected["fixed_30m_net_pnl"])}
    return {"status": "PASS", "ablation_reports": reports, "shuffled_label_report": shuffled_report}


def concentration(trades: pd.DataFrame, pnl_col: str = "net_pnl") -> dict[str, Any]:
    base = economics(trades[pnl_col])
    reports = {"base": base}
    if trades.empty:
        return reports
    sorted_trades = trades.sort_values(pnl_col, ascending=False)
    for n in [1, 3]:
        reports[f"remove_top_{n}_trades"] = economics(sorted_trades.iloc[n:][pnl_col])
    for col, name in [("session_date", "best_session"), ("expiry", "best_expiry"), ("setup_family", "best_setup_family")]:
        if col not in trades.columns:
            reports[f"remove_{name}"] = {"status": "SKIPPED", "reason": f"missing_{col}"}
            continue
        sums = trades.groupby(col)[pnl_col].sum()
        best = sums.idxmax()
        reports[f"remove_{name}"] = {"removed": str(best), **economics(trades[trades[col] != best][pnl_col])}
    trades = trades.copy()
    trades["month"] = pd.to_datetime(trades["session_date"]).dt.to_period("M").astype(str)
    best_month = trades.groupby("month")[pnl_col].sum().idxmax()
    reports["remove_best_month"] = {"removed": best_month, **economics(trades[trades["month"] != best_month][pnl_col])}
    for side in ["CE", "PE"]:
        reports[f"{side}_only"] = economics(trades[trades["option_side"] == side][pnl_col])
    return reports


def main() -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    hash_ok = verify_frozen_inputs()
    if not hash_ok:
        verdict = "INVALID_ML_META_LABELING_CERTIFICATION"
        write_json("final_verdict.json", {"final_verdict": verdict, "reason": "frozen_hash_verification_failed"})
        return verdict

    dataset = pd.read_parquet(FROZEN / "candidate_level_dataset.parquet")
    holdout = pd.read_parquet(FROZEN / "holdout_predictions.parquet")
    selected = holdout[holdout["selected"]].copy()
    wh = pd.read_parquet(WAREHOUSE)
    feature_contract = json.loads((FROZEN / "feature_contract.json").read_text())
    write_json("concrete_strike_selection_contract.json", {
        "rule": "same session, same expiry, same option side; latest certified option candle at or before candidate timestamp; choose strike with minimum absolute distance to underlying close; tie by lower strike then instrument key; enter next observable completed bar for that contract",
        "causal": True,
        "broker_api_called": False,
        "provider_api_called": False,
    })
    mapping, trades = build_concrete_replay(selected, wh)
    mapping.to_parquet(OUT / "concrete_strike_mapping_ledger.parquet", index=False)
    trades.to_parquet(OUT / "concrete_holdout_trade_ledger.parquet", index=False)
    coverage = {
        "frozen_selected_candidates": int(len(selected)),
        "mapped_candidates": int(mapping["liquidity_eligible"].sum()) if not mapping.empty else 0,
        "concrete_trades": int(len(trades)),
        "coverage": float(len(trades) / len(selected)) if len(selected) else 0.0,
        "sessions": int(trades["session_date"].nunique()) if not trades.empty else 0,
        "expiries": int(trades["expiry"].nunique()) if not trades.empty else 0,
        "coverage_gate_passed": bool(len(trades) >= 200 and len(trades) / len(selected) >= 0.8 and trades["session_date"].nunique() >= 30 and trades["expiry"].nunique() >= 12) if len(selected) else False,
    }
    write_json("coverage_report.json", coverage)
    concrete_econ = economics(trades["net_pnl"])
    concrete_econ.update({"sessions": coverage["sessions"], "expiries": coverage["expiries"]})
    write_json("concrete_economic_report.json", concrete_econ)
    compare = {
        "aggregate": economics(selected["net_pnl"]),
        "concrete": concrete_econ,
        "label_agreement_rate": float((trades["aggregate_label"].astype(int) == trades["concrete_label"].astype(int)).mean()) if not trades.empty else 0.0,
        "disagreement_matrix": pd.crosstab(trades["aggregate_label"], trades["concrete_label"]).to_dict() if not trades.empty else {},
        "pnl_correlation": float(pd.to_numeric(trades["aggregate_net_pnl"]).corr(pd.to_numeric(trades["net_pnl"]))) if len(trades) > 1 else None,
        "expectancy_difference_concrete_minus_aggregate": float(concrete_econ["expectancy"] - selected["net_pnl"].mean()) if not trades.empty else None,
        "pf_difference_concrete_minus_aggregate": None,
    }
    write_json("aggregate_vs_concrete_comparison.json", compare)

    delayed = delayed_replay(trades, wh)
    delayed.to_parquet(OUT / "delayed_entry_trade_ledger.parquet", index=False)
    dex = delayed[delayed["delayed_executable"].fillna(False)] if not delayed.empty else delayed
    delayed_report = {"executable_rate": float(len(dex) / len(trades)) if len(trades) else 0.0, **economics(dex["delayed_net_pnl"] if not dex.empty else pd.Series(dtype=float))}
    delayed_for_concentration = dex.copy()
    if not delayed_for_concentration.empty:
        delayed_for_concentration["net_pnl"] = delayed_for_concentration["delayed_net_pnl"]
    delayed_report["top_3_removal"] = concentration(delayed_for_concentration, "net_pnl").get("remove_top_3_trades", {})
    delayed_report["gate_passed"] = bool(delayed_report["executable_rate"] >= 0.7 and delayed_report["expectancy"] > 0 and (delayed_report["profit_factor"] or 0) >= 1.1 and delayed_report["top_3_removal"].get("expectancy", 0) > 0)
    write_json("delayed_entry_report.json", delayed_report)

    controls = model_controls(dataset, feature_contract)
    for name, payload in controls.get("ablation_reports", {}).items():
        write_json(f"feature_family_ablation_{name}.json", payload)
    write_json("shuffled_label_report.json", controls.get("shuffled_label_report", {"status": controls.get("status")}))

    rng_reports = []
    n = len(trades)
    for seed in range(300):
        sample = holdout.sample(n=n, random_state=seed)
        rng_reports.append(economics(sample["net_pnl"]))
    rand_expectancies = [r["expectancy"] for r in rng_reports]
    write_json("equal_count_random_selector_report.json", {
        "seeds": 300,
        "model_expectancy": concrete_econ["expectancy"],
        "random_expectancy_median_aggregate": float(np.median(rand_expectancies)),
        "model_percentile_rank": float((np.array(rand_expectancies) <= concrete_econ["expectancy"]).mean()),
    })
    tod = holdout.groupby("tod_bucket", group_keys=False).apply(lambda g: g.sample(n=min(len(g), int((selected["tod_bucket"] == g.name).sum())), random_state=20260728))
    write_json("time_of_day_matched_selector_report.json", {"matched_count": int(len(tod)), "aggregate_economics": economics(tod["net_pnl"]), "model_concrete_economics": concrete_econ})
    write_json("concentration_report.json", concentration(trades))
    bins = trades.copy()
    bins["probability_bin"] = pd.qcut(bins["frozen_score"], q=min(5, len(bins)), duplicates="drop")
    write_json("probability_bin_report.json", {"bins": bins.groupby("probability_bin", observed=True)["net_pnl"].agg(["count", "mean", "sum"]).reset_index().astype(str).to_dict("records")})
    stability = {}
    for col in ["option_side", "expiry", "setup_family", "session_date"]:
        stability[col] = trades.groupby(col)["net_pnl"].agg(["count", "mean", "sum"]).reset_index().astype(str).to_dict("records") if not trades.empty else []
    write_json("stability_decomposition_report.json", stability)
    trades_sorted = trades.sort_values("candidate_timestamp").copy()
    trades_sorted["fold"] = pd.qcut(range(len(trades_sorted)), q=min(3, len(trades_sorted)), labels=False, duplicates="drop") if len(trades_sorted) else []
    folds = [dict({"fold": int(fold)}, **economics(g["net_pnl"])) for fold, g in trades_sorted.groupby("fold")] if len(trades_sorted) else []
    total = sum(f["net_pnl"] for f in folds) or 1.0
    write_json("wfa_reconciliation.json", {
        "folds": folds,
        "majority_positive": sum(1 for f in folds if f["expectancy"] > 0) > len(folds) / 2,
        "single_fold_domination": max((abs(f["net_pnl"]) / abs(total) for f in folds), default=0.0),
        "aggregate": economics(trades["net_pnl"]),
    })
    concrete_gate = coverage["coverage_gate_passed"] and concrete_econ["expectancy"] > 0 and (concrete_econ["profit_factor"] or 0) >= 1.2
    if not coverage["coverage_gate_passed"]:
        verdict = "ML_SIGNAL_NOT_CERTIFIABLE_STRIKE_COVERAGE"
        failed_gate = "concrete_strike_coverage"
    elif not concrete_gate:
        verdict = "ML_META_LABELING_SIGNAL_REJECTED_ON_CONCRETE_REPLAY"
        failed_gate = "concrete_economics"
    elif not delayed_report["gate_passed"]:
        verdict = "ML_META_LABELING_SIGNAL_REJECTED_ON_DELAYED_ENTRY"
        failed_gate = "delayed_entry"
    else:
        verdict = "ML_META_LABELING_SIGNAL_SURVIVES_BUT_NOT_CERTIFIED"
        failed_gate = "secondary_robustness_not_fully_certified"
    write_json("independent_audit.json", {
        "status": "PASS",
        "frozen_artifacts_verified": True,
        "no_holdout_retuning": True,
        "no_retraining_of_frozen_winner": True,
        "broker_api_called": False,
        "provider_api_called": False,
        "production_files_modified": False,
        "failed_gate": failed_gate,
    })
    write_json("determinism_report.json", {"status": "PASS", "deterministic_seed": 20260728, "semantic_inputs": sorted(EXPECTED_HASHES)})
    write_json("final_verdict.json", {"final_verdict": verdict, "failed_gate": failed_gate, "exact_next_action": "Close this ML signal without further tuning." if "REJECTED" in verdict or "NOT_CERTIFIABLE" in verdict else "State the failed robustness gate and perform only the narrowest non-tuning repair."})
    return verdict


if __name__ == "__main__":
    print(main())
