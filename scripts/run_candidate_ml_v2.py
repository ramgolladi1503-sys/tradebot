from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.analytics.candidate_ml_v2 import (
    CandidateMLConfig,
    build_candidate_dataset,
    bundle_manifest,
    fit_candidate_ml,
    semantic_dataset_hash,
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
    parser = argparse.ArgumentParser(description="Build and train the read-only Candidate ML V2 evidence bundle.")
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--outcomes", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--friction-r", type=float, default=0.10)
    parser.add_argument("--min-train-rows", type=int, default=250)
    parser.add_argument("--min-validation-rows", type=int, default=80)
    parser.add_argument("--min-strategy-rows", type=int, default=250)
    parser.add_argument("--min-positive-rows", type=int, default=30)
    args = parser.parse_args()

    events = _read_records(args.events)
    outcomes = _read_records(args.outcomes)
    dataset = build_candidate_dataset(events, outcomes, friction_r=float(args.friction_r))
    if dataset.empty:
        raise SystemExit("candidate_dataset_empty_after_event_outcome_join")

    config = CandidateMLConfig(
        min_train_rows=int(args.min_train_rows),
        min_validation_rows=int(args.min_validation_rows),
        min_strategy_rows=int(args.min_strategy_rows),
        min_positive_rows=int(args.min_positive_rows),
        cost_r=float(args.friction_r),
    )
    bundle = fit_candidate_ml(dataset, config=config)

    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    dataset_path = output_root / "candidate_ml_dataset.parquet"
    model_path = output_root / "candidate_ml_bundle.joblib"
    manifest_path = output_root / "candidate_ml_manifest.json"
    dataset.to_parquet(dataset_path, index=False)
    bundle.save(model_path)

    manifest = bundle_manifest(bundle)
    manifest.update(
        {
            "dataset_rows": int(len(dataset)),
            "dataset_sessions": int(dataset["session_date"].nunique()),
            "dataset_semantic_sha256": semantic_dataset_hash(dataset),
            "events_source": str(args.events),
            "outcomes_source": str(args.outcomes),
            "dataset_path": str(dataset_path),
            "model_path": str(model_path),
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
