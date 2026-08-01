from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.analytics.candidate_ml_v2 import (
    CandidateMLCertificationConfig,
    CandidateMLConfig,
    build_candidate_dataset,
    bundle_manifest,
    certify_candidate_ml,
    fit_candidate_ml,
    seal_locked_holdout,
    semantic_dataset_hash,
    verify_locked_holdout,
)


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError(f"non_object_jsonl_row:{path}:{line_number}")
                rows.append(payload)
        return rows
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        for key in ("events", "outcomes", "rows", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(row) for row in value if isinstance(row, dict)]
        raise ValueError(f"json_object_has_no_supported_record_list:{path}")
    if not isinstance(payload, list):
        raise ValueError(f"unsupported_json_root:{path}")
    return [dict(row) for row in payload if isinstance(row, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build, seal, and certify the read-only Candidate ML V2 evidence bundle.")
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--outcomes", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--friction-r", type=float, default=0.10)
    parser.add_argument("--holdout-fraction", type=float, default=0.20)
    parser.add_argument("--certification-splits", type=int, default=5)
    parser.add_argument("--min-train-rows", type=int, default=250)
    parser.add_argument("--min-validation-rows", type=int, default=80)
    parser.add_argument("--min-strategy-rows", type=int, default=250)
    parser.add_argument("--min-positive-rows", type=int, default=30)
    parser.add_argument("--require-ready-for-holdout", action="store_true")
    args = parser.parse_args()

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    events = _read_records(args.events)
    outcomes = _read_records(args.outcomes)
    full_dataset = build_candidate_dataset(events, outcomes, friction_r=float(args.friction_r))
    if full_dataset.empty:
        raise SystemExit("candidate_dataset_empty_after_event_outcome_join")

    full_join_path = output_root / "candidate_ml_full_join.parquet"
    holdout_path = output_root / "candidate_ml_holdout_LOCKED.parquet"
    research_path = output_root / "candidate_ml_research_dataset.parquet"
    model_path = output_root / "candidate_ml_bundle.joblib"
    manifest_path = output_root / "candidate_ml_manifest.json"
    certification_path = output_root / "candidate_ml_certification.json"
    full_dataset.to_parquet(full_join_path, index=False)
    research_dataset, holdout_seal = seal_locked_holdout(
        full_dataset,
        holdout_path=holdout_path,
        holdout_fraction=float(args.holdout_fraction),
    )
    verify_locked_holdout(holdout_seal)
    research_dataset.to_parquet(research_path, index=False)

    model_config = CandidateMLConfig(
        min_train_rows=int(args.min_train_rows),
        min_validation_rows=int(args.min_validation_rows),
        min_strategy_rows=int(args.min_strategy_rows),
        min_positive_rows=int(args.min_positive_rows),
        cost_r=float(args.friction_r),
    )
    certification_config = CandidateMLCertificationConfig(n_splits=int(args.certification_splits))
    certification = certify_candidate_ml(
        research_dataset,
        model_config=model_config,
        certification_config=certification_config,
    )
    certification_path.write_text(json.dumps(certification, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    bundle = fit_candidate_ml(research_dataset, config=model_config)
    bundle.save(model_path)
    manifest = bundle_manifest(bundle)
    manifest.update(
        {
            "full_dataset_rows": int(len(full_dataset)),
            "research_dataset_rows": int(len(research_dataset)),
            "research_dataset_sessions": int(research_dataset["session_date"].nunique()),
            "research_dataset_semantic_sha256": semantic_dataset_hash(research_dataset),
            "events_source": str(args.events),
            "outcomes_source": str(args.outcomes),
            "full_join_path": str(full_join_path),
            "research_dataset_path": str(research_path),
            "model_path": str(model_path),
            "certification_path": str(certification_path),
            "certification_verdict": certification["verdict"],
            "locked_holdout": holdout_seal.to_dict(),
            "holdout_metrics_consumed": False,
            "allowed_for_paper_execution": False,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if args.require_ready_for_holdout and certification["verdict"] != "READY_FOR_LOCKED_HOLDOUT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
