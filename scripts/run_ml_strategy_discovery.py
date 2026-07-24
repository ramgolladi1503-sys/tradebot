from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from research.ml_strategy_discovery.audit import (
    assert_rule_oracle_agreement,
    build_evidence_manifest,
    write_manifest,
)
from research.ml_strategy_discovery.contracts import (
    DiscoveryConfig,
    TimestampSemantics,
)
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
from research.ml_strategy_discovery.upstox_source import (
    load_certified_upstox_underlying,
)

_DEFAULT_SOURCE_MANIFEST = (
    "docs/agent_reviews/"
    "opening_range_retest_causal_replay_source_manifest_v2.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the research-only ML strategy-discovery core."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bars", help="Explicit CSV or parquet OHLCV input")
    source.add_argument(
        "--source-project-root",
        help=(
            "Repository root containing the certified "
            "runtime/upstox_candidate_replay corpus"
        ),
    )
    parser.add_argument(
        "--source-manifest",
        default=_DEFAULT_SOURCE_MANIFEST,
        help="Certified source-manifest path relative to source project root",
    )
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument(
        "--timestamp-semantics",
        choices=("START", "END"),
        help="Required for explicit --bars input; certified Upstox is pinned START",
    )
    parser.add_argument("--source-timezone", default="Asia/Kolkata")
    parser.add_argument("--bar-interval-minutes", type=int, default=1)
    parser.add_argument(
        "--strict-bar-cadence",
        action="store_true",
        help="Fail on any within-session cadence deviation",
    )
    parser.add_argument("--option-quotes", help="Optional CSV/parquet bid/ask quotes")
    parser.add_argument("--target-atr", type=float, default=1.2)
    parser.add_argument("--stop-atr", type=float, default=0.6)
    parser.add_argument("--horizon-bars", type=int, default=30)
    parser.add_argument("--side", choices=("LONG", "SHORT"), default="LONG")
    return parser.parse_args()


def read_frame(path: str) -> pd.DataFrame:
    source = Path(path).expanduser()
    if source.suffix.lower() == ".parquet":
        return pd.read_parquet(source)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source)
    raise ValueError(f"unsupported input type: {source.suffix}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_source(args: argparse.Namespace) -> tuple[pd.DataFrame, DiscoveryConfig, dict]:
    if args.source_project_root:
        bundle = load_certified_upstox_underlying(
            source_project_root=args.source_project_root,
            source_manifest_path=args.source_manifest,
            instrument=args.instrument,
        )
        config = DiscoveryConfig(
            instrument=args.instrument,
            timestamp_column="timestamp",
            timestamp_semantics=TimestampSemantics.START,
            source_timezone="Asia/Kolkata",
            bar_interval_minutes=1,
            strict_bar_cadence=True,
            source_kind="CERTIFIED_UPSTOX_CANDIDATE_REPLAY_V2",
            target_atr=args.target_atr,
            stop_atr=args.stop_atr,
            barrier_horizon_bars=args.horizon_bars,
            label_side=args.side,
        )
        return bundle.bars, config, bundle.manifest

    if not args.timestamp_semantics:
        raise ValueError(
            "--timestamp-semantics START or END is mandatory with explicit --bars"
        )
    source = Path(args.bars).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise ValueError(f"bars input is missing: {source}")
    bars = read_frame(str(source))
    config = DiscoveryConfig(
        instrument=args.instrument,
        timestamp_column=args.timestamp_column,
        timestamp_semantics=args.timestamp_semantics,
        source_timezone=args.source_timezone,
        bar_interval_minutes=args.bar_interval_minutes,
        strict_bar_cadence=args.strict_bar_cadence,
        source_kind="EXPLICIT_USER_OHLCV_FILE",
        target_atr=args.target_atr,
        stop_atr=args.stop_atr,
        barrier_horizon_bars=args.horizon_bars,
        label_side=args.side,
    )
    source_manifest = {
        "mode": "ML_STRATEGY_DISCOVERY_EXPLICIT_FILE_SOURCE_V1",
        "candidate_id": f"ALL_{args.instrument.upper()}_EXPLICIT_FILE_ROWS",
        "decision": "EXPLICIT_OHLCV_FILE_BOUND",
        "reason": "user supplied a concrete file and explicit timestamp semantics",
        "timestamp": "SOURCE_FILE_STATIC_EVIDENCE",
        "source": source.name,
        "file_sha256": _sha256_file(source),
        "byte_size": source.stat().st_size,
        "input_rows": len(bars),
        "timestamp_semantics": args.timestamp_semantics,
        "source_timezone": args.source_timezone,
        "bar_interval_minutes": args.bar_interval_minutes,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_action": False,
        "broker_order_action": False,
        "allowed_for_live_execution": False,
        "append": False,
    }
    return bars, config, source_manifest


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bars, config, source_adapter_manifest = _load_source(args)
    option_quotes = read_frame(args.option_quotes) if args.option_quotes else None
    dataset = build_discovery_dataset(
        bars,
        config=config,
        option_quotes=option_quotes,
    )
    split_dataset = chronological_split(
        dataset,
        validation_fraction=config.validation_fraction,
        holdout_fraction=config.holdout_fraction,
    )
    artifacts = train_discovery_models(split_dataset, config=config)

    split_dataset.to_parquet(
        output_dir / "discovery_dataset.parquet",
        index=False,
    )
    (output_dir / "source_adapter_manifest.json").write_text(
        json.dumps(source_adapter_manifest, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "feature_importance.json").write_text(
        json.dumps(
            list(artifacts.feature_importance),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "candidates.json").write_text(
        json.dumps(
            [candidate.to_dict() for candidate in artifacts.candidates],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    candidate = artifacts.candidates[0] if artifacts.candidates else None
    validation_evidence = {}
    if candidate is not None:
        validation_evidence = {
            "validation": evaluate_candidate(split_dataset, candidate),
            "frozen_validation_slices": walk_forward_evaluate(
                split_dataset,
                candidate,
            ),
            "negative_controls": run_negative_controls(
                split_dataset,
                candidate,
            ),
            "parameter_stability": parameter_stability(
                split_dataset,
                candidate,
            ),
            "label_cost_stress": cost_stress(
                split_dataset,
                candidate,
            ),
            "rule_oracle": assert_rule_oracle_agreement(
                split_dataset,
                candidate,
            ),
        }

    manifest = build_evidence_manifest(
        config=config,
        dataset=split_dataset,
        candidate=candidate,
        validation_metrics=artifacts.validation_metrics,
        validation_evidence=validation_evidence,
        source_adapter_manifest=source_adapter_manifest,
    )
    write_manifest(output_dir / "evidence_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
