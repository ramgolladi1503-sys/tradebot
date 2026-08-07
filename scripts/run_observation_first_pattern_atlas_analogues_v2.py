#!/usr/bin/env python3
"""Run matched PRE-CAS geometric analogues from the recertified motif catalog.

This wrapper preserves the Stage-4 V1 analogue algorithm but strengthens its
input authority. Only a motif catalog explicitly recertified on Stage-1
trajectory-accepted sessions may be used. Legacy Stage-3 catalogs fail closed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def load_sibling(name: str, filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load sibling module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


V1 = load_sibling(
    "pattern_atlas_analogues_v1_for_v2",
    "run_observation_first_pattern_atlas_analogues_v1.py",
)
ORIGINAL_VALIDATE = V1.validate_catalog


def validate_recertified_catalog(
    catalog: dict[str, Any], instrument: str, regime: str
) -> dict[str, Any]:
    lane = ORIGINAL_VALIDATE(catalog, instrument, regime)
    policy = dict(catalog.get("policy") or {})
    if policy.get("trajectory_quality_accepted_sessions_only") is not True:
        raise ValueError(
            "Matched analogue execution requires a motif catalog recertified on "
            "trajectory-accepted sessions only"
        )
    if policy.get("rejected_sessions_excluded") is not True:
        raise ValueError(
            "Matched analogue execution requires proof that trajectory-rejected "
            "sessions were excluded"
        )
    if catalog.get("schema_version") != 2:
        raise ValueError("Matched analogue execution requires motif catalog schema_version=2")
    if catalog.get("stage") != "trajectory_accepted_native_cadence_motif_recertification_v2":
        raise ValueError("Unexpected motif recertification stage authority")
    return lane


def main() -> int:
    V1.validate_catalog = validate_recertified_catalog
    return V1.main()


if __name__ == "__main__":
    raise SystemExit(main())
