from __future__ import annotations

import argparse
from glob import glob
import json
from pathlib import Path
from typing import Any

from core.analytics.candidate_ml_v2 import (
    CandidateMLCertificationConfig,
    CandidateMLConfig,
    PRETRAINING_REQUIRED_FEATURES,
    MarketCorpusConfig,
    audit_market_tick_corpus,
    build_market_response_pretraining_dataset,
    bundle_manifest,
    certify_candidate_ml,
    fit_candidate_ml,
    market_corpus_summary,
    seal_locked_holdout,
    verify_locked_holdout,
)
from core.analytics.candidate_ml_v2.corpus_loader import load_market_tick_corpus_resilient


def _discover_files(patterns: list[str]) -> list[Path]:
    found: set[Path] = set()
    for pattern in patterns:
        matches = glob(pattern, recursive=True)
        if matches:
            found.update(Path(item) for item in matches)
        else:
            candidate = Path(pattern)
            if candidate.exists():
                found.add(candidate)
    return sorted(path for path in found if path.is_file() and path.suffix.lower() == ".parquet")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit real Upstox parquet data and train a read-only market-response pretraining model.")
    parser.add_argument("--inputs", nargs="+", required=True, help="Parquet paths or glob patterns")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--horizon-bars", type=int, default=5)
    parser.add_argument("--min-move-bps", type=float, default=5.0)
    parser.add_argument("--min-option-instruments", type=int, default=10)
    parser.add_argument("--friction-r", type=float, default=0.10)
    parser.add_argument("--min-train-rows", type=int, default=200)
    parser.add_argument("--min-validation-rows", type=int, default=50)
    parser.add_argument("--min-strategy-rows", type=int, default=100)
    parser.add_argument("--min-positive-rows", type=int, default=20)
    args = parser.parse_args()

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "market_corpus_training_report.json"
    files = _discover_files(list(args.inputs))
    if not files:
        payload = {
            "verdict": "NO_MATERIALIZED_PARQUET_INPUT",
            "input_patterns": list(args.inputs),
            "model_trained": False,
            "candidate_edge_certification_allowed": False,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
            "append": False,
        }
        _write_json(report_path, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    config = MarketCorpusConfig(
        horizon_bars=int(args.horizon_bars),
        min_move_bps=float(args.min_move_bps),
        friction_r=float(args.friction_r),
        min_option_instruments_per_bar=int(args.min_option_instruments),
    )
    try:
        ticks, source_manifest = load_market_tick_corpus_resilient(files)
        audit = audit_market_tick_corpus(ticks, config)
        dataset = build_market_response_pretraining_dataset(ticks, config)
    except Exception as exc:
        payload = {
            "verdict": "REAL_CORPUS_PRETRAINING_BLOCKED",
            "reason": f"{type(exc).__name__}:{exc}",
            "input_files": [str(path) for path in files],
            "model_trained": False,
            "candidate_edge_certification_allowed": False,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
            "append": False,
        }
        _write_json(report_path, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    dataset_path = output_root / "market_response_pretraining_dataset.parquet"
    dataset.to_parquet(dataset_path, index=False)
    source_manifest_path = output_root / "market_corpus_source_manifest.json"
    _write_json(source_manifest_path, source_manifest)
    summary = market_corpus_summary(dataset, audit)
    sessions = int(dataset["session_date"].nunique())
    model_config = CandidateMLConfig(
        min_train_rows=int(args.min_train_rows),
        min_validation_rows=int(args.min_validation_rows),
        min_strategy_rows=int(args.min_strategy_rows),
        min_positive_rows=int(args.min_positive_rows),
        max_missing_ratio=0.35,
        cost_r=float(args.friction_r),
        purge_rows=max(1, int(args.horizon_bars)),
        required_features=tuple(PRETRAINING_REQUIRED_FEATURES),
    )

    model_trained = False
    model_manifest: dict[str, Any] | None = None
    certification: dict[str, Any] | None = None
    holdout: dict[str, Any] | None = None
    training_reason = ""
    research = dataset

    if sessions >= 10:
        research, seal = seal_locked_holdout(
            dataset,
            holdout_path=output_root / "market_response_holdout_LOCKED.parquet",
            holdout_fraction=0.20,
        )
        verify_locked_holdout(seal)
        holdout = seal.to_dict()
    else:
        training_reason = "LOCKED_HOLDOUT_REQUIRES_AT_LEAST_10_SESSIONS"

    if int(research["session_date"].nunique()) >= 5:
        try:
            bundle = fit_candidate_ml(research, config=model_config)
            model_path = bundle.save(output_root / "market_response_pretraining_bundle.joblib")
            model_manifest = bundle_manifest(bundle)
            model_manifest.update(
                {
                    "model_path": str(model_path),
                    "model_authority": "PRETRAINING_ONLY",
                    "candidate_lineage_available": False,
                    "candidate_edge_certification_allowed": False,
                }
            )
            _write_json(output_root / "market_response_pretraining_manifest.json", model_manifest)
            model_trained = True
        except Exception as exc:
            training_reason = f"{type(exc).__name__}:{exc}"
    else:
        training_reason = "INSUFFICIENT_INDEPENDENT_SESSIONS_FOR_MODEL_FIT"

    research_sessions = int(research["session_date"].nunique())
    if model_trained and research_sessions >= 8:
        try:
            certification = certify_candidate_ml(
                research,
                model_config=model_config,
                certification_config=CandidateMLCertificationConfig(
                    n_splits=3,
                    min_train_sessions=3,
                    min_selected_per_fold=5,
                ),
            )
            certification["candidate_edge_certification_allowed"] = False
            certification["interpretation"] = "Market-response pretraining control only; not historical TradeBot candidate certification."
            _write_json(output_root / "market_response_pretraining_certification.json", certification)
        except Exception as exc:
            certification = {"verdict": "PRETRAINING_CERTIFICATION_BLOCKED", "reason": f"{type(exc).__name__}:{exc}"}
            _write_json(output_root / "market_response_pretraining_certification.json", certification)

    verdict = "MARKET_RESPONSE_PRETRAINING_MODEL_BUILT" if model_trained else "REAL_CORPUS_FOUND_MODEL_NOT_BUILT"
    payload = {
        **summary,
        "verdict": verdict,
        "input_files": [str(path) for path in files],
        "source_manifest_path": str(source_manifest_path),
        "dataset_path": str(dataset_path),
        "model_trained": model_trained,
        "training_reason": training_reason,
        "model_manifest": model_manifest,
        "certification": certification,
        "locked_holdout": holdout,
        "holdout_metrics_consumed": False,
        "candidate_edge_certification_allowed": False,
        "allowed_for_paper_execution": False,
    }
    _write_json(report_path, payload)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
