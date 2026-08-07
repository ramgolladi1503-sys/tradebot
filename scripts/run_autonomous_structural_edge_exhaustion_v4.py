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

from research.autonomous_structural_edge_exhaustion_v1.batch_b import *
from research.autonomous_structural_edge_exhaustion_v1.batch_c import *
from research.autonomous_structural_edge_exhaustion_v1.batch_d import *
from research.autonomous_structural_edge_exhaustion_v1.certification import build_strategy_specs, rank_final_candidates, robustness, unopened_test, validation_and_wfa
from research.autonomous_structural_edge_exhaustion_v1.certification_v4 import *
from research.autonomous_structural_edge_exhaustion_v1.common import *
from research.autonomous_structural_edge_exhaustion_v1.discovery import *
from research.autonomous_structural_edge_exhaustion_v1.outcomes import attach_development_outcomes


def combined_discovery(a: dict, b: dict, c: dict, d: dict, clock_norms: dict) -> dict:
    families = []
    for record in a.get("families", []): families.append({**record, "batch": "A"})
    for record in b.get("families", []): families.append({**record, "batch": "B"})
    for record in c.get("families", []): families.append({**record, "batch": "C"})
    for record in d.get("families", []): families.append({**record, "batch": "D"})
    catalog = {
        "schema_version": 4,
        "campaign": CAMPAIGN,
        "principal_verdict": "AUTONOMOUS_FOUR_BATCH_OUTCOME_BLIND_FAMILY_DISCOVERY_FROZEN",
        "batch_count": 4,
        "family_count": len(families),
        "families_attempted": [str(f["family"]) for f in families],
        "families": families,
        "total_frozen_motifs": int(sum(int(f.get("motif_count", 0)) for f in families)),
        "batch_a_semantic_sha256": a.get("semantic_sha256"),
        "batch_b_semantic_sha256": b.get("semantic_sha256"),
        "batch_c_semantic_sha256": c.get("semantic_sha256"),
        "batch_d_semantic_sha256": d.get("semantic_sha256"),
        "batch_b_clock_norm_authority": clock_norms,
        "batch_c_selection_basis": c.get("selection_basis"),
        "batch_d_selection_basis": d.get("selection_basis"),
        "policy": {
            "outcomes_seen_when_frozen": False,
            "future_returns_calculated": False,
            "direction_selected": False,
            "unopened_sessions_scored": False,
            "failed_prior_families_reopened": False,
            "campaign_global_multiple_testing_budget": True,
            "campaign_global_q_threshold": CAMPAIGN_GLOBAL_Q_V4,
        },
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


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
    development_sessions = [*splits["observation"], *splits["replication"], *splits["validation"]]

    base_cross = add_split_column(build_cross_sectional_frame(raw, index_rows, universe["selected_symbols"], development_sessions), splits)
    batch_b_cross, clock_norms = build_batch_b_frame(raw, universe["selected_symbols"], development_sessions, base_cross, clock_norms=None)
    batch_c_cross = build_batch_c_frame(raw, universe["selected_symbols"], development_sessions, base_cross)
    batch_d_cross = build_batch_d_frame(raw, universe["selected_symbols"], development_sessions, base_cross)

    stage0 = {
        "principal_verdict": "PINNED_CONSTITUENT_INDEX_SOURCE_AUTHORIZED_FOR_FOUR_BATCH_OUTCOME_BLIND_DISCOVERY",
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
        "principal_verdict": "GLOBAL_CHRONOLOGICAL_SPLIT_FROZEN_FOR_FOUR_BATCH_CAMPAIGN",
        "splits": splits,
        "counts": {k: len(v) for k, v in splits.items()},
        "unopened_sessions_scored": False,
    }
    stage1["semantic_sha256"] = digest(stage1)
    stage2 = {"principal_verdict": "OBSERVATION_SELECTED_CONSTITUENT_UNIVERSE_FROZEN", **universe}
    stage2["semantic_sha256"] = digest(stage2)

    a_models, a_assignments, a_discovery = freeze_discovery(base_cross, splits)
    b_models, b_assignments, b_discovery = freeze_batch_b_discovery(batch_b_cross, splits)
    c_models, c_assignments, c_discovery = freeze_batch_c_discovery(batch_c_cross, splits)
    d_models, d_assignments, d_discovery = freeze_batch_d_discovery(batch_d_cross, splits)
    stage3 = combined_discovery(a_discovery, b_discovery, c_discovery, d_discovery, clock_norms)
    stage4 = hypothesis_catalog(stage3)
    models = {**a_models, **b_models, **c_models, **d_models}
    assignments = {**a_assignments, **b_assignments, **c_assignments, **d_assignments}

    stage5 = attach_development_outcomes(stage4, stage3, assignments, base_cross, splits)
    stage6 = structural_screen_v4(stage5)
    stage7 = validation_and_wfa(stage5, stage6)
    stage8 = robustness(stage5, stage7)
    pre_final_candidates = rank_final_candidates(stage5, stage6, stage7, stage8)

    if pre_final_candidates:
        unopened_base = add_split_column(build_cross_sectional_frame(raw, index_rows, universe["selected_symbols"], splits["unopened"]), splits)
        unopened_b, _ = build_batch_b_frame(raw, universe["selected_symbols"], splits["unopened"], unopened_base, clock_norms=clock_norms)
        unopened_c = build_batch_c_frame(raw, universe["selected_symbols"], splits["unopened"], unopened_base)
        unopened_d = build_batch_d_frame(raw, universe["selected_symbols"], splits["unopened"], unopened_base)
        h_lookup = {str(h["hypothesis_id"]): h for h in stage4.get("hypotheses", [])}
        needed = sorted({str(h_lookup[hid]["family"]) for hid in pre_final_candidates})
        unopened_assignments = {}
        for family in needed:
            if family in a_models: unopened_assignments[family] = assign_family(unopened_base, a_models[family])
            elif family in b_models: unopened_assignments[family] = assign_family(unopened_b, b_models[family])
            elif family in c_models: unopened_assignments[family] = assign_family(unopened_c, c_models[family])
            elif family in d_models: unopened_assignments[family] = assign_family(unopened_d, d_models[family])
            else: raise ValueError(f"final candidate references unknown family: {family}")
        stage9 = unopened_test(stage5, stage4, unopened_assignments, unopened_base, stage6, stage7, stage8)
    else:
        stage9 = unopened_test(stage5, stage4, {}, pd.DataFrame(), stage6, stage7, stage8)

    stage10 = build_strategy_specs(stage9, stage5, stage4, models, stage2)
    stage11 = exhaustion_ledger_v4(stage3, stage6, stage7, stage8, stage9)
    survivors = list(stage9.get("survivor_hypothesis_ids", []))
    final = {
        "principal_verdict": (
            "STATISTICAL_STRUCTURAL_EDGE_SURVIVOR_FOUND_AFTER_FOUR_BATCH_CAMPAIGN_MEMBERSHIP_AUTHORITY_REQUIRED"
            if survivors else "NO_STRUCTURAL_EDGE_SURVIVED_FOUR_BATCH_CLOSE_VOLUME_INFORMATION_EXHAUSTION"
        ),
        "statistical_structural_edge_survivor_ids": survivors,
        "full_structural_edge_certified": False,
        "membership_authority": "REQUIRES_POINT_IN_TIME_NIFTY_MEMBERSHIP" if survivors else "NOT_APPLICABLE_NO_SURVIVOR",
        "campaign_batch_count": 4,
        "campaign_family_count": len(ALL_FAMILIES_V4),
        "campaign_global_q_threshold": CAMPAIGN_GLOBAL_Q_V4,
        "source_information_space": "CONSTITUENT_INDEX_5M_CLOSE_VOLUME",
        "same_source_further_transform_search_authorized_if_no_survivor": False,
        "next_research_lane_if_no_survivor": "DIFFERENT_INFORMATION_SOURCE",
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
    (output / "REPORT.md").write_text(build_report_v4(stages), encoding="utf-8")
    print(json.dumps(final, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
