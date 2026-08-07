#!/usr/bin/env python3
"""Recertify PRE-CAS Pattern Atlas motifs on trajectory-accepted sessions only.

The original Stage-3 motif lane read the full causal trajectory directly. That
allowed sessions rejected by the Stage-1 trajectory-quality gates to enter motif
clustering. This V2 lane reconstructs the authoritative source in memory, keeps
only trajectory-accepted sessions, and then runs the frozen outcome-blind motif
algorithm unchanged.

The previous catalog is retained as superseded evidence. No outcomes, future
returns, direction, P&L, broker, live/paper authority, or unopened-session
outcomes are opened.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
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


ANALOGUE_V1 = load_sibling(
    "pattern_atlas_analogues_v1_for_recert",
    "run_observation_first_pattern_atlas_analogues_v1.py",
)
MOTIF = ANALOGUE_V1.MOTIF
BASE = ANALOGUE_V1.BASE
V3 = ANALOGUE_V1.V3

CAMPAIGN = "observation_first_pattern_atlas_v1"
STAGE = "trajectory_accepted_native_cadence_motif_recertification_v2"
TARGET_REGIME = "PRE_CAS"


def safe_previous_catalog(catalog: dict[str, Any]) -> None:
    policy = dict(catalog.get("policy") or {})
    forbidden_true = {
        "outcomes_read": policy.get("outcomes_read"),
        "future_returns_calculated": policy.get("future_returns_calculated"),
        "pnl_calculated": policy.get("pnl_calculated"),
        "direction_selected": policy.get("direction_selected"),
        "unopened_sessions_scored": policy.get("unopened_sessions_scored"),
    }
    if any(value is True for value in forbidden_true.values()):
        raise ValueError(f"Previous motif catalog is outside outcome-blind authority: {forbidden_true}")


def motif_counts_by_window(catalog: dict[str, Any], instrument: str, regime: str) -> dict[str, int]:
    lanes = [
        lane
        for lane in catalog.get("lanes", [])
        if str(lane.get("instrument")) == instrument
        and str(lane.get("regime")) == regime
    ]
    if len(lanes) != 1:
        return {}
    counts: dict[str, int] = {}
    for item in lanes[0].get("windows", []):
        counts[f"{int(item['window_minutes'])}m"] = len(item.get("motifs", []))
    return counts


def build_report(catalog: dict[str, Any]) -> str:
    comparison = catalog["superseded_catalog_comparison"]
    lane = catalog["lanes"][0] if catalog.get("lanes") else {}
    lines = [
        "# Pattern Atlas — PRE-CAS Motif Recertification V2",
        "",
        f"Principal verdict: `{catalog['principal_verdict']}`",
        "",
        "The original Stage-3 catalog is retained as superseded evidence because it was built from the full causal trajectory rather than the trajectory-accepted session universe.",
        "",
        f"Accepted sessions used: `{catalog['source_authority']['accepted_sessions']}`",
        f"Rejected sessions excluded: `{catalog['source_authority']['rejected_sessions']}`",
        f"Previous frozen motif count: `{comparison['previous_frozen_motif_count']}`",
        f"Recertified frozen motif count: `{catalog['frozen_motif_count']}`",
        "",
        "## Motif counts by horizon",
        "",
    ]
    previous = comparison.get("previous_counts_by_window", {})
    current = comparison.get("recertified_counts_by_window", {})
    for key in ("5m", "10m", "15m", "30m", "60m"):
        lines.append(f"- `{key}`: previous `{previous.get(key, 0)}` → recertified `{current.get(key, 0)}`")
    lines.extend(
        [
            "",
            f"Observation sessions: `{len(lane.get('observation_sessions', []))}`",
            f"Replication sessions: `{len(lane.get('replication_sessions', []))}`",
            f"Unopened sessions: `{len(lane.get('unopened_sessions', []))}`",
            "",
            "No outcomes, P&L, strategy rules, broker calls, live/paper authority, or unopened-session outcomes were opened.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--previous-motif-catalog", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-sha256", default=V3.DEFAULT_NIFTY_SOURCE_SHA256)
    parser.add_argument("--source-size", type=int, default=V3.DEFAULT_NIFTY_SOURCE_SIZE)
    parser.add_argument("--source-basename", default="constituent_index_5m.parquet")
    parser.add_argument("--instrument", default="NIFTY")
    parser.add_argument("--minimum-source-sessions", type=int, default=120)
    parser.add_argument("--minimum-median-price", type=float, default=10000.0)
    parser.add_argument("--minimum-native-coverage", type=float, default=0.90)
    parser.add_argument("--maximum-staleness-multiple", type=float, default=1.25)
    parser.add_argument("--minimum-motif-sessions", type=int, default=120)
    args = parser.parse_args()

    previous = json.loads(args.previous_motif_catalog.read_text(encoding="utf-8"))
    safe_previous_catalog(previous)

    native, source_authority = ANALOGUE_V1.authoritative_native_rows(
        source_file=args.source_file,
        source_sha256=args.source_sha256,
        source_size=args.source_size,
        source_basename=args.source_basename,
        instrument=args.instrument,
        minimum_source_sessions=args.minimum_source_sessions,
        minimum_median_price=args.minimum_median_price,
        minimum_native_coverage=args.minimum_native_coverage,
        maximum_staleness_multiple=args.maximum_staleness_multiple,
    )

    instrument_native = native.loc[native["instrument"].eq(args.instrument)].copy()
    regimes = sorted(str(value) for value in instrument_native["regime"].unique())
    lanes = [
        MOTIF.run_lane(
            instrument_native,
            args.instrument,
            regime,
            args.minimum_motif_sessions,
        )
        for regime in regimes
    ]
    frozen_count = sum(int(lane.get("frozen_motif_count", 0)) for lane in lanes)
    principal = (
        "OUTCOME_BLIND_TRAJECTORY_ACCEPTED_MOTIFS_RECERTIFIED"
        if frozen_count
        else "NO_TRAJECTORY_ACCEPTED_MOTIF_PASSED"
    )

    accepted_sessions = sorted(str(value) for value in instrument_native["session_date"].unique())
    accepted_session_set_sha256 = BASE.digest(accepted_sessions)

    provisional = {
        "schema_version": 2,
        "campaign": CAMPAIGN,
        "stage": STAGE,
        "instrument": args.instrument,
        "principal_verdict": principal,
        "frozen_motif_count": frozen_count,
        "lanes": lanes,
        "source_authority": {
            **source_authority,
            "accepted_session_set_sha256": accepted_session_set_sha256,
        },
        "superseded_catalog_comparison": {
            "previous_catalog_semantic_sha256": previous.get("semantic_sha256"),
            "previous_frozen_motif_count": int(previous.get("frozen_motif_count", 0)),
            "previous_counts_by_window": motif_counts_by_window(
                previous, args.instrument, TARGET_REGIME
            ),
            "recertified_counts_by_window": {},
            "reason_superseded": (
                "original motif discovery used the full causal trajectory and did not "
                "restrict clustering to Stage-1 trajectory-accepted sessions"
            ),
        },
        "policy": {
            "native_observed_rows_only": True,
            "trajectory_quality_accepted_sessions_only": True,
            "rejected_sessions_excluded": True,
            "regimes_mixed": False,
            "observation_replication_chronological": True,
            "unopened_sessions_scored": False,
            "outcomes_read": False,
            "future_returns_calculated": False,
            "pnl_calculated": False,
            "direction_selected": False,
            "allowed_for_live_execution": False,
        },
    }
    provisional["superseded_catalog_comparison"]["recertified_counts_by_window"] = (
        motif_counts_by_window(provisional, args.instrument, TARGET_REGIME)
    )
    provisional["semantic_sha256"] = BASE.digest(provisional)

    output = args.output_root.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    BASE.stable_write(output / "native_motif_catalog_v2.json", provisional)
    (output / "MOTIF_RECERTIFICATION_RESULT.md").write_text(
        build_report(provisional), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "principal_verdict": principal,
                "accepted_sessions": source_authority["accepted_sessions"],
                "rejected_sessions_excluded": source_authority["rejected_sessions"],
                "previous_frozen_motif_count": int(previous.get("frozen_motif_count", 0)),
                "recertified_frozen_motif_count": frozen_count,
                "semantic_sha256": provisional["semantic_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
