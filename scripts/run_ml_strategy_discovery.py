from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research.ml_strategy_discovery.audit import (
    assert_rule_oracle_agreement,
    build_evidence_manifest,
    write_manifest,
)
from research.ml_strategy_discovery.contracts import DiscoveryConfig
from research.ml_strategy_discovery.dataset import (
    build_discovery_dataset,
    chronological_split,
)
from research.ml_strategy_discovery.evaluation import (
    cost_stress,
    evaluate_candidate,
    parameter_stability,
    run_negative_controls,
    walk_forward_evaluate,
)
from research.ml_strategy_discovery.models import train_discovery_models


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the research-only ML strategy-discovery core."
    )
    parser.add_argument("--bars", required=True, help="CSV or parquet OHLCV input")
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--option-quotes", help="Optional CSV/parquet bid/ask quotes")
    parser.add_argument("--target-atr", type=float, default=1.2)
    parser.add_argument("--stop-atr", type=float, default=0.6)
    parser.add_argument("--horizon-bars", type=int, default=30)
    return parser.parse_args()


def read_frame(path: str) -> pd.DataFrame:
    source = Path(path)
    if source.suffix.lower() == ".parquet":
        return pd.read_parquet(source)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source)
    raise ValueError(f"unsupported input type: {source.suffix}")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = DiscoveryConfig(
        instrument=args.instrument,
        timestamp_column=args.timestamp_column,
        target_atr=args.target_atr,
        stop_atr=args.stop_atr,
        barrier_horizon_bars=args.horizon_bars,
    )
    bars = read_frame(args.bars)
    option_quotes = read_frame(args.option_quotes) if args.option_quotes else None
    dataset = build_discovery_dataset(
        bars, config=config, option_quotes=option_quotes
    )
    split_dataset = chronological_split(
        dataset,
        validation_fraction=config.validation_fraction,
        holdout_fraction=config.holdout_fraction,
    )
    artifacts = train_discovery_models(split_dataset, config=config)

    dataset_path = output_dir / "discovery_dataset.parquet"
    split_dataset.to_parquet(dataset_path, index=False)

    candidates_payload = [candidate.to_dict() for candidate in artifacts.candidates]
    (output_dir / "feature_importance.json").write_text(
        json.dumps(list(artifacts.feature_importance), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "candidates.json").write_text(
        json.dumps(candidates_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    candidate = artifacts.candidates[0] if artifacts.candidates else None
    validation_evidence = {}
    if candidate is not None:
        validation_evidence = {
            "validation": evaluate_candidate(split_dataset, candidate),
            "walk_forward": walk_forward_evaluate(split_dataset, candidate),
            "negative_controls": run_negative_controls(split_dataset, candidate),
            "parameter_stability": parameter_stability(split_dataset, candidate),
            "cost_stress": cost_stress(split_dataset, candidate),
            "rule_oracle": assert_rule_oracle_agreement(split_dataset, candidate),
        }

    manifest = build_evidence_manifest(
        config=config,
        dataset=split_dataset,
        candidate=candidate,
        validation_metrics=artifacts.validation_metrics,
        validation_evidence=validation_evidence,
    )
    write_manifest(output_dir / "evidence_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
