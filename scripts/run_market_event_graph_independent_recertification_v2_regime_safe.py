#!/usr/bin/env python3
"""Regime-safe entrypoint for Market Event Graph independent recertification V2.

This wrapper exists only to enforce the PRE_CAS / POST_CAS separation before the
V2 fixed-graph certifier is allowed to evaluate an independent dataset.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CAS_START = "2026-08-03"


def load_v2():
    path = Path(__file__).with_name(
        "run_market_event_graph_independent_recertification_v2.py"
    )
    spec = importlib.util.spec_from_file_location("meg_independent_v2_impl", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load V2 implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V2 = load_v2()


def classify_independent_regime(frame: pd.DataFrame) -> dict[str, object]:
    sessions, policy = V2.validate_independent_frame(frame)
    pre = [value for value in sessions if value < CAS_START]
    post = [value for value in sessions if value >= CAS_START]
    if pre and post:
        raise ValueError(
            "independent_dataset_crosses_cas_boundary "
            f"pre_cas_sessions={len(pre)} post_cas_sessions={len(post)}"
        )
    regime = "POST_CAS" if post else "PRE_CAS"
    return {
        **policy,
        "regime": regime,
        "cas_start": CAS_START,
        "pre_cas_session_count": len(pre),
        "post_cas_session_count": len(post),
        "regimes_pooled": False,
    }


def certify_regime_safe(frame: pd.DataFrame, thresholds: dict[str, float]) -> dict:
    regime_policy = classify_independent_regime(frame)
    result = V2.independent_certification(frame, thresholds)
    result["policy"] = {**dict(result.get("policy") or {}), **regime_policy}
    result["semantic_sha256"] = V2.semantic_hash(
        {key: value for key, value in result.items() if key != "semantic_sha256"}
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--independent-dataset", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    frame = pd.read_parquet(args.independent_dataset).sort_values(
        ["session_date", "timestamp"], kind="mergesort"
    )
    result = certify_regime_safe(frame, V2.frozen_thresholds())
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    V2.write_json(args.output_json, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
