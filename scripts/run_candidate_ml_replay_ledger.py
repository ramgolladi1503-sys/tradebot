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
from core.analytics.candidate_ml_v2.replay_ledger import (
    REPLAY_LEDGER_REQUIRED_FEATURES,
    build_replay_ledger_dataset,
    load_jsonl_records,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a read-only strategy proxy selector from a historical replay ledger.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--min-train-rows", type=int, default=70)
    parser.add_argument("--min-validation-rows", type=int, default=20)
    parser.add_argument("--min-positive-rows", type=int, default=10)
    args = parser.parse_args()

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "replay_ledger_training_report.json"
    try:
        records, source_manifest = load_jsonl_records(args.ledger)
        dataset, corpus_evidence = build_replay_ledger_dataset(records)
    except Exception as exc:
        report = {
            "verdict": "REPLAY_LEDGER_TRAINING_BLOCKED",
            "reason": f"{type(exc).__name__}:{exc}",
            "model_trained": False,
            "candidate_edge_certification_allowed": False,
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

    _write_json(output_root / "replay_ledger_source_manifest.json", source_manifest)
    _write_json(output_root / "replay_ledger_corpus_evidence.json", corpus_evidence)
    dataset_path = output_root / "replay_ledger_candidate_dataset.parquet"
    dataset.to_parquet(dataset_path, index=False)

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
        ensemble_disagreement_threshold=0.30,
        required_features=tuple(REPLAY_LEDGER_REQUIRED_FEATURES),
    )

    holdout = None
    research = dataset
    if int(dataset["session_date"].nunique()) >= 20:
        research, seal = seal_locked_holdout(
            dataset,
            holdout_path=output_root / "replay_ledger_holdout_LOCKED.parquet",
            holdout_fraction=0.20,
        )
        verify_locked_holdout(seal)
        holdout = seal.to_dict()

    model_trained = False
    training_reason = ""
    model_manifest = None
    certification = None
    try:
        bundle = fit_candidate_ml(research, config=config)
        model_path = bundle.save(output_root / "replay_ledger_proxy_selector.joblib")
        model_manifest = bundle_manifest(bundle)
        model_manifest.update(
            {
                "model_path": str(model_path),
                "model_authority": "STRATEGY_PROXY_SELECTOR_ONLY",
                "execution_grade": False,
                "option_truth": "MOCKED_CONTRACT_PROXY_PNL",
                "candidate_lineage_available": True,
                "candidate_edge_certification_allowed": False,
                "allowed_for_paper_execution": False,
            }
        )
        _write_json(output_root / "replay_ledger_proxy_selector_manifest.json", model_manifest)
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
                    min_selected_per_fold=3,
                    min_positive_fold_fraction=0.34,
                    max_ece=0.35,
                    max_top_five_positive_contribution=0.80,
                    max_best_session_positive_contribution=0.40,
                    min_permutation_gap_r=0.0,
                    min_delayed_mean_lift_r=-0.05,
                    max_ablation_features=3,
                ),
            )
            certification["candidate_edge_certification_allowed"] = False
            certification["model_authority"] = "STRATEGY_PROXY_SELECTOR_ONLY"
            certification["interpretation"] = "Historical replay candidate selection evidence only; option contracts and PnL remain proxy/mock."
            _write_json(output_root / "replay_ledger_proxy_certification.json", certification)
        except Exception as exc:
            certification = {
                "verdict": "PROXY_CERTIFICATION_BLOCKED",
                "reason": f"{type(exc).__name__}:{exc}",
                "candidate_edge_certification_allowed": False,
            }
            _write_json(output_root / "replay_ledger_proxy_certification.json", certification)

    report = {
        **corpus_evidence,
        "verdict": "REPLAY_LEDGER_PROXY_SELECTOR_BUILT" if model_trained else "REPLAY_LEDGER_FOUND_MODEL_NOT_BUILT",
        "dataset_path": str(dataset_path),
        "source_manifest_path": str(output_root / "replay_ledger_source_manifest.json"),
        "model_trained": model_trained,
        "training_reason": training_reason,
        "model_manifest": model_manifest,
        "certification": certification,
        "locked_holdout": holdout,
        "holdout_metrics_consumed": False,
        "candidate_edge_certification_allowed": False,
        "allowed_for_paper_execution": False,
    }
    _write_json(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
