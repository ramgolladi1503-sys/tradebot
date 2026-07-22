#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path


from research.ml_strategy_discovery.contracts import DiscoveryConfig, TimestampSemantics
from research.ml_strategy_discovery.dataset import (
    build_discovery_dataset,
    model_feature_names,
)
from research.ml_strategy_discovery.upstox_source import (
    load_certified_upstox_underlying,
)
from research.ml_strategy_discovery_v2.artifacts import (
    build_semantic_hash_manifest,
    envelope,
    resolve_code_sha,
    sha256_file,
    write_json,
)
from research.ml_strategy_discovery_v2.contracts import (
    StabilityConfig,
    canonical_hash,
    require_causal_features,
)
from research.ml_strategy_discovery_v2.data import (
    load_development_for_selection,
    load_registry,
)
from research.ml_strategy_discovery_v2.freeze import (
    candidate_bundle,
    write_frozen_registry,
)
from research.ml_strategy_discovery_v2.pipeline import run_stability_first_discovery
from research.ml_strategy_discovery_v2.source import (
    development_manifest_payload,
    load_and_verify_manifest,
    verify_selected_record_files,
)

LOGGER = logging.getLogger("ml_strategy_discovery_v2")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run certified development-only ML strategy discovery V2"
    )
    parser.add_argument("--source-project-root", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument(
        "--registry",
        default="research/ml_strategy_discovery/v2_validation_registry.json",
    )
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--side", required=True, choices=("LONG", "SHORT"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--v1-long-dir", required=True)
    parser.add_argument("--v1-short-dir", required=True)
    parser.add_argument("--v1-audit-dir", required=True)
    parser.add_argument("--target-atr", type=float, default=1.2)
    parser.add_argument("--stop-atr", type=float, default=0.6)
    parser.add_argument("--horizon-bars", type=int, default=30)
    parser.add_argument("--outer-folds", type=int, default=5)
    parser.add_argument("--inner-folds", type=int, default=4)
    parser.add_argument("--bootstrap-iterations", type=int, default=1000)
    parser.add_argument("--permutation-iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--development-only", action="store_true", required=True)
    return parser.parse_args()


def _resolve(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _required_evidence_hashes(args: argparse.Namespace) -> dict[str, str]:
    requirements = {
        "v1_long_evidence_manifest": Path(args.v1_long_dir) / "evidence_manifest.json",
        "v1_short_evidence_manifest": Path(args.v1_short_dir)
        / "evidence_manifest.json",
        "v1_audit_final_report": Path(args.v1_audit_dir) / "final_report.md",
    }
    hashes: dict[str, str] = {}
    for name, path in requirements.items():
        if not path.is_file():
            raise ValueError(f"required V1 evidence file is missing: {path}")
        hashes[name] = sha256_file(path)
    return hashes


def _write_report(path: Path, result: dict, confirmation_status: str) -> None:
    candidate = result.get("candidate")
    lines = [
        "# ML Strategy Discovery V2 — Certified Development Screen",
        "",
        f"- Side: `{result['side']}`",
        f"- Development verdict: `{result['verdict']}`",
        f"- Confirmation status: `{confirmation_status}`",
        f"- Outer folds: `{result['candidate_funnel']['outer_folds']}`",
        f"- Inner hypotheses: `{result['candidate_funnel'].get('total_inner_hypotheses', 0)}`",
        f"- Unique hypotheses: `{result['candidate_funnel'].get('unique_hypotheses', 0)}`",
    ]
    if candidate is not None:
        lines.extend(
            [
                f"- Candidate rule hash: `{candidate['rule_hash']}`",
                f"- Candidate conditions: `{json.dumps(candidate['conditions'], sort_keys=True)}`",
            ]
        )
    if result.get("rejection_reasons"):
        lines.append(f"- Rejection reasons: `{', '.join(result['rejection_reasons'])}`")
    lines.extend(
        [
            "",
            "The screen uses underlying research-label outcomes only. It is not option P&L, execution, profitability, paper, or live certification.",
            "",
            "`NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = parse_args()
    project_root = Path(args.source_project_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    code_sha = resolve_code_sha(project_root)
    manifest_path = _resolve(project_root, args.source_manifest)
    registry_path = _resolve(project_root, args.registry)
    registry = load_registry(registry_path)
    source_payload, source_identity = load_and_verify_manifest(manifest_path)
    v1_hashes = _required_evidence_hashes(args)

    # The parent manifest is read as metadata only. Only DEVELOPMENT records are
    # materialized into a child selection manifest before any parquet is opened.
    selected_manifest = development_manifest_payload(
        source_payload,
        instrument=args.instrument,
        registry=registry,
    )
    selected_manifest_path = output_dir / "development_source_selection_manifest.json"
    selected_manifest_path.write_text(
        json.dumps(selected_manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    selected_manifest_hash = sha256_file(selected_manifest_path)
    selected_file_verification = verify_selected_record_files(
        project_root, selected_manifest["records"]
    )

    source_bundle = load_certified_upstox_underlying(
        source_project_root=project_root,
        source_manifest_path=selected_manifest_path,
        instrument=args.instrument,
    )
    config = DiscoveryConfig(
        instrument=args.instrument,
        timestamp_column="timestamp",
        timestamp_semantics=TimestampSemantics.START,
        source_timezone="Asia/Kolkata",
        bar_interval_minutes=1,
        strict_bar_cadence=True,
        source_kind="CERTIFIED_UPSTOX_V2_DEVELOPMENT_ONLY",
        target_atr=args.target_atr,
        stop_atr=args.stop_atr,
        barrier_horizon_bars=args.horizon_bars,
        label_side=args.side,
        random_seed=args.seed,
    )
    dataset = build_discovery_dataset(
        source_bundle.bars, config=config, option_quotes=None
    )
    development = load_development_for_selection(dataset, registry=registry)
    features = require_causal_features(model_feature_names(development))
    stability_config = StabilityConfig(
        outer_folds=args.outer_folds,
        inner_folds=args.inner_folds,
        bootstrap_iterations=args.bootstrap_iterations,
        permutation_iterations=args.permutation_iterations,
        seed=args.seed,
    )
    LOGGER.info(
        "running side=%s rows=%s sessions=%s features=%s",
        args.side,
        len(development),
        development["session_date"].nunique(),
        len(features),
    )
    result = run_stability_first_discovery(
        development,
        side=args.side,
        features=features,
        config=stability_config,
    )

    input_hashes = {
        "parent_source_manifest": source_identity["manifest_sha256"],
        "development_source_selection_manifest": selected_manifest_hash,
        "registry": registry.source_hash,
        **v1_hashes,
    }
    seeds = [args.seed]
    common = dict(
        code_sha=code_sha, input_hashes=input_hashes, deterministic_seeds=seeds
    )
    write_json(
        output_dir / "input_inventory.json",
        envelope(
            {
                "instrument": args.instrument,
                "side": args.side,
                "parent_source_identity": source_identity,
                "development_source_record_count": len(selected_manifest["records"]),
                "development_source_record_set_hash": canonical_hash(
                    selected_manifest["records"]
                ),
                "development_source_file_verification": selected_file_verification,
                "development_rows": len(development),
                "development_sessions": int(development["session_date"].nunique()),
            },
            **common,
        ),
    )
    write_json(
        output_dir / "partition_registry.json",
        envelope(
            {
                "registry_hash": registry.source_hash,
                "loaded_partition": "DEVELOPMENT_V1",
                "validation_v1_consumed_loaded": False,
                "holdout_v1_locked_loaded": False,
                "fresh_confirmation_loaded": False,
            },
            **common,
        ),
    )
    write_json(
        output_dir / "feature_schema.json",
        envelope(
            {
                "features": list(features),
                "feature_schema_hash": result.get(
                    "feature_schema_hash", canonical_hash(features)
                ),
            },
            **common,
        ),
    )
    write_json(
        output_dir / "fold_manifest.json",
        envelope(
            {
                "folds": result["folds"],
                "fold_manifest_hash": result["fold_manifest_hash"],
            },
            **common,
        ),
    )
    write_json(
        output_dir / "candidate_funnel.json",
        envelope(result["candidate_funnel"], **common),
    )
    write_json(
        output_dir / "outer_fold_results.json",
        envelope(
            {
                "results": result["outer_fold_results"],
                "summary": result.get("fold_summary", {}),
            },
            **common,
        ),
    )
    write_json(
        output_dir / "multiple_testing.json",
        envelope(result["multiple_testing"], **common),
    )
    write_json(
        output_dir / "stability_selection.json",
        envelope(
            {
                "recurrence": result.get("recurrence"),
                "gate_results": result.get("gate_results", {}),
            },
            **common,
        ),
    )
    write_json(
        output_dir / "negative_controls.json",
        envelope(
            result.get(
                "negative_controls",
                {"passes": False, "rejection_reasons": ["NO_CANDIDATE_TO_CONTROL"]},
            ),
            **common,
        ),
    )

    bundles: list[dict] = []
    if result.get("candidate") is not None:
        bundles.append(
            candidate_bundle(
                candidate=result["candidate"],
                side=args.side,
                source_manifest_hash=source_identity["manifest_sha256"],
                development_dataset_hash=result["development_dataset_hash"],
                feature_schema_hash=result["feature_schema_hash"],
                fold_manifest_hash=result["fold_manifest_hash"],
                search_space_hash=result["search_space_hash"],
                multiple_testing=result["candidate_significance"],
                recurrence=result["recurrence"],
                concentration=result["concentration"],
                bootstrap=result["bootstrap"],
                imputation_dependence=result["imputation_dependence"],
                controls=result["negative_controls"],
                code_sha=code_sha,
            )
        )
    frozen = write_frozen_registry(
        output_dir / "frozen_candidates.json",
        bundles=bundles,
        code_sha=code_sha,
        input_hashes=input_hashes,
        seeds=seeds,
    )
    confirmation_status = "NEED_NEW_FRESH_CONFIRMATION_DATA"
    write_json(
        output_dir / "confirmation_lock.json",
        envelope(
            {
                "status": confirmation_status,
                "candidate_bundle_hashes": [
                    item["candidate_bundle_hash"] for item in bundles
                ],
                "token_issued": False,
                "consumed_fresh_dates": {"start": "2026-07-11", "end": "2026-07-21"},
            },
            **common,
        ),
    )
    _write_report(output_dir / "final_report.md", result, confirmation_status)
    semantic_manifest = build_semantic_hash_manifest(output_dir)
    write_json(
        output_dir / "semantic_hash_manifest.json",
        envelope(semantic_manifest, **common),
    )
    LOGGER.info(
        "development verdict=%s frozen_registry_verdict=%s",
        result["verdict"],
        frozen["verdict"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
