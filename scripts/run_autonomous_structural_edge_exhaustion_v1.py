#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.autonomous_structural_edge_exhaustion_v1.common import *
from research.autonomous_structural_edge_exhaustion_v1.discovery import *
from research.autonomous_structural_edge_exhaustion_v1.outcomes import *
from research.autonomous_structural_edge_exhaustion_v1.certification import *


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    output = args.output_root
    source_info = verify_source(args.source_file)
    raw = canonicalize_source(args.source_file)
    index_rows, accepted_sessions = accepted_index_sessions(raw)
    splits = split_sessions(accepted_sessions)
    universe = select_observation_universe(raw, index_rows, splits)
    development_sessions = [
        *splits["observation"], *splits["replication"], *splits["validation"]
    ]
    cross = build_cross_sectional_frame(
        raw, index_rows, universe["selected_symbols"], development_sessions
    )
    cross = add_split_column(cross, splits)

    stage0 = {
        "principal_verdict": "PINNED_CONSTITUENT_INDEX_SOURCE_AUTHORIZED_FOR_OUTCOME_BLIND_DISCOVERY",
        **source_info,
        "canonical_rows": int(len(raw)),
        "accepted_index_sessions": len(accepted_sessions),
        "first_session": accepted_sessions[0],
        "last_session": accepted_sessions[-1],
        "post_cas_sessions": 0,
        "policy": {"pre_cas_only": True, "outcomes_read": False, "allowed_for_live_execution": False},
    }
    stage0["semantic_sha256"] = digest(stage0)
    stage1 = {
        "principal_verdict": "GLOBAL_CHRONOLOGICAL_SPLIT_FROZEN",
        "splits": splits,
        "counts": {k: len(v) for k, v in splits.items()},
        "unopened_sessions_scored": False,
    }
    stage1["semantic_sha256"] = digest(stage1)
    stage2 = {"principal_verdict": "OBSERVATION_SELECTED_CONSTITUENT_UNIVERSE_FROZEN", **universe}
    stage2["semantic_sha256"] = digest(stage2)

    models, assignments, stage3 = freeze_discovery(cross, splits)
    stage4 = hypothesis_catalog(stage3)

    # Persist all outcome-blind authority before any future return is calculated.
    for name, payload in (
        ("stage0_source_authority", stage0),
        ("stage1_chronological_split", stage1),
        ("stage2_universe_authority", stage2),
        ("stage3_discovery", stage3),
        ("stage4_hypotheses", stage4),
    ):
        stable_write(output / f"{name}.json", payload)

    stage5 = attach_development_outcomes(stage4, stage3, assignments, cross, splits)
    stage6 = structural_screen(stage5)
    stage7 = validation_and_wfa(stage5, stage6)
    stage8 = robustness(stage5, stage7)
    pre_final_candidates = rank_final_candidates(stage5, stage6, stage7, stage8)
    if pre_final_candidates:
        unopened_cross = build_cross_sectional_frame(
            raw, index_rows, universe["selected_symbols"], splits["unopened"]
        )
        unopened_cross = add_split_column(unopened_cross, splits)
        needed_families = sorted({
            str(next(h for h in stage4["hypotheses"] if h["hypothesis_id"] == hid)["family"])
            for hid in pre_final_candidates
        })
        unopened_assignments = {
            family: assign_family(unopened_cross, models[family])
            for family in needed_families
        }
        stage9 = unopened_test(
            stage5, stage4, unopened_assignments, unopened_cross, stage6, stage7, stage8
        )
    else:
        stage9 = unopened_test(
            stage5, stage4, {}, pd.DataFrame(), stage6, stage7, stage8
        )
    stage10 = build_strategy_specs(stage9, stage5, stage4, models, stage2)
    stage11 = exhaustion_ledger(stage3, stage6, stage7, stage8, stage9)

    statistical_survivors = list(stage9.get("survivor_hypothesis_ids", []))
    if statistical_survivors:
        principal = "STATISTICAL_STRUCTURAL_EDGE_SURVIVOR_FOUND_MEMBERSHIP_AUTHORITY_REQUIRED"
    else:
        principal = "NO_STRUCTURAL_EDGE_SURVIVED_PREDECLARED_CONSTITUENT_INFORMATION_FAMILIES"
    final = {
        "principal_verdict": principal,
        "statistical_structural_edge_survivor_ids": statistical_survivors,
        "full_structural_edge_certified": False,
        "membership_authority": "REQUIRES_POINT_IN_TIME_NIFTY_MEMBERSHIP" if statistical_survivors else "NOT_APPLICABLE_NO_SURVIVOR",
        "options_edge_certified": False,
        "shadow_authorized": False,
        "paper_authorized": False,
        "live_authorized": False,
        "order_authorized": False,
        "pre_post_cas_pooled": False,
        "failed_family_reopening_authorized": False,
    }
    final["semantic_sha256"] = digest(final)

    stages = {
        "stage0_source_authority": stage0,
        "stage1_chronological_split": stage1,
        "stage2_universe_authority": stage2,
        "stage3_discovery": stage3,
        "stage4_hypotheses": stage4,
        "stage5_development_outcomes": stage5,
        "stage6_structural_screen": stage6,
        "stage7_validation_wfa": stage7,
        "stage8_robustness": stage8,
        "stage9_final_unopened": stage9,
        "stage10_strategy_specs": stage10,
        "stage11_exhaustion_ledger": stage11,
        "final_authority": final,
    }
    for name, payload in stages.items():
        stable_write(output / f"{name}.json", payload)
    (output / "REPORT.md").write_text(build_report(stages), encoding="utf-8")
    print(json.dumps(final, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
