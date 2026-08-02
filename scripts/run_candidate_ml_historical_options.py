from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.analytics.candidate_ml_v2 import (
    CandidateMLCertificationConfig,
    CandidateMLConfig,
    bundle_manifest,
    certify_candidate_ml,
    fit_candidate_ml,
    seal_locked_holdout,
    verify_locked_holdout,
)
from core.analytics.candidate_ml_v2.historical_option_reconstruction import (
    HISTORICAL_OPTION_REQUIRED_FEATURES,
    build_historical_option_datasets,
    load_canonical_intents,
    load_option_replay_blockers,
    load_option_trade_ledger,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build and certify a read-only candidate selector from frozen TradeBot "
            "canonical intents joined to real expired-option minute-candle outcomes."
        )
    )
    parser.add_argument("--intents-csv", type=Path, required=True)
    parser.add_argument("--trade-ledger-csv", type=Path, required=True)
    parser.add_argument("--blockers-csv", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--stop-loss-pct", type=float, default=0.25)
    parser.add_argument("--nearest-proxy-max-points", type=float, default=100.0)
    parser.add_argument("--min-train-rows", type=int, default=70)
    parser.add_argument("--min-validation-rows", type=int, default=20)
    parser.add_argument("--min-positive-rows", type=int, default=10)
    args = parser.parse_args()

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "historical_option_training_report.json"

    try:
        intents, intents_manifest = load_canonical_intents(args.intents_csv)
        trades, trades_manifest = load_option_trade_ledger(args.trade_ledger_csv)
        blockers, blockers_manifest = load_option_replay_blockers(args.blockers_csv)
        exact, proxy, corpus_evidence = build_historical_option_datasets(
            intents,
            trades,
            blockers,
            stop_loss_pct=float(args.stop_loss_pct),
            nearest_proxy_max_points=float(args.nearest_proxy_max_points),
        )
    except Exception as exc:
        report = {
            "verdict": "HISTORICAL_OPTION_RECONSTRUCTION_BLOCKED",
            "reason": f"{type(exc).__name__}:{exc}",
            "model_trained": False,
            "holdout_metrics_consumed": False,
            "candidate_edge_research_allowed": False,
            "allowed_for_paper_execution": False,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
            "append": False,
        }
        _write_json(report_path, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    source_manifest = {
        "intents": intents_manifest,
        "trades": trades_manifest,
        "blockers": blockers_manifest,
    }
    _write_json(output_root / "historical_option_source_manifest.json", source_manifest)
    _write_json(output_root / "historical_option_corpus_evidence.json", corpus_evidence)
    exact_path = output_root / "historical_option_exact_atm_dataset.parquet"
    proxy_path = output_root / "historical_option_nearest_strike_proxy_dataset.parquet"
    exact.to_parquet(exact_path, index=False)
    proxy.to_parquet(proxy_path, index=False)

    config = CandidateMLConfig(
        min_train_rows=int(args.min_train_rows),
        min_validation_rows=int(args.min_validation_rows),
        min_strategy_rows=10_000,
        min_positive_rows=int(args.min_positive_rows),
        validation_fraction=0.20,
        calibration_fraction=0.50,
        purge_rows=1,
        max_missing_ratio=0.20,
        probability_floor=0.55,
        ensemble_disagreement_threshold=0.25,
        required_features=tuple(HISTORICAL_OPTION_REQUIRED_FEATURES),
    )

    research = exact
    holdout = None
    if not exact.empty and int(exact["session_date"].nunique()) >= 20:
        research, seal = seal_locked_holdout(
            exact,
            holdout_path=output_root / "historical_option_holdout_LOCKED.parquet",
            holdout_fraction=0.20,
        )
        verify_locked_holdout(seal)
        holdout = seal.to_dict()

    model_trained = False
    training_reason = ""
    model_manifest = None
    certification = None
    if exact.empty:
        training_reason = "exact_atm_dataset_empty"
    else:
        try:
            bundle = fit_candidate_ml(research, config=config)
            model_path = bundle.save(output_root / "historical_option_selector.joblib")
            model_manifest = bundle_manifest(bundle)
            model_manifest.update(
                {
                    "model_path": str(model_path),
                    "model_authority": "REAL_OPTION_CANDLE_RESEARCH_ONLY",
                    "option_truth": "UPSTOX_EXPIRED_OPTION_MINUTE_OHLC",
                    "candidate_lineage": "FROZEN_TRADEBOT_CANONICAL_INTENT_IDENTITY",
                    "execution_grade": False,
                    "nearest_strike_proxy_consumed": False,
                    "allowed_for_paper_execution": False,
                }
            )
            _write_json(output_root / "historical_option_selector_manifest.json", model_manifest)
            model_trained = True
        except Exception as exc:
            training_reason = f"{type(exc).__name__}:{exc}"

    if model_trained:
        try:
            certification = certify_candidate_ml(
                research,
                model_config=config,
                certification_config=CandidateMLCertificationConfig(
                    n_splits=3,
                    min_train_sessions=20,
                    min_selected_per_fold=5,
                    min_positive_fold_fraction=0.50,
                    min_mean_lift_r=0.0,
                    max_ece=0.25,
                    max_top_five_positive_contribution=0.70,
                    max_best_session_positive_contribution=0.35,
                    min_permutation_gap_r=0.01,
                    min_delayed_mean_lift_r=-0.05,
                    max_ablation_features=5,
                ),
            )
            certification.update(
                {
                    "model_authority": "REAL_OPTION_CANDLE_RESEARCH_ONLY",
                    "nearest_strike_proxy_consumed": False,
                    "holdout_metrics_consumed": False,
                    "allowed_for_paper_execution": False,
                    "interpretation": (
                        "Real option-candle candidate selection evidence only. "
                        "Bid/ask, depth and actual fill evidence remain unavailable."
                    ),
                }
            )
            _write_json(output_root / "historical_option_certification.json", certification)
        except Exception as exc:
            certification = {
                "verdict": "HISTORICAL_OPTION_CERTIFICATION_BLOCKED",
                "reason": f"{type(exc).__name__}:{exc}",
                "holdout_metrics_consumed": False,
                "allowed_for_paper_execution": False,
            }
            _write_json(output_root / "historical_option_certification.json", certification)

    certification_verdict = (
        str((certification or {}).get("verdict") or "") if model_trained else ""
    )
    if not model_trained:
        verdict = "HISTORICAL_OPTION_CORPUS_FOUND_MODEL_NOT_BUILT"
    elif certification_verdict == "READY_FOR_LOCKED_HOLDOUT":
        verdict = "HISTORICAL_OPTION_ML_READY_FOR_LOCKED_HOLDOUT"
    elif certification_verdict in {"NO_OUT_OF_SAMPLE_ML_LIFT", "ML_EVIDENCE_QUARANTINED"}:
        verdict = certification_verdict
    else:
        verdict = "HISTORICAL_OPTION_ML_RESEARCH_COMPLETE"

    report = {
        **corpus_evidence,
        "verdict": verdict,
        "exact_dataset_path": str(exact_path),
        "nearest_proxy_dataset_path": str(proxy_path),
        "source_manifest_path": str(output_root / "historical_option_source_manifest.json"),
        "model_trained": model_trained,
        "training_reason": training_reason,
        "model_manifest": model_manifest,
        "certification": certification,
        "locked_holdout": holdout,
        "holdout_metrics_consumed": False,
        "nearest_strike_proxy_consumed_by_model": False,
        "candidate_edge_research_allowed": bool(corpus_evidence["candidate_edge_research_allowed"]),
        "execution_grade": False,
        "allowed_for_paper_execution": False,
    }
    _write_json(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
