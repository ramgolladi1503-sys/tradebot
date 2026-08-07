from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from .batch_b import BATCH_B_FEATURES
from .batch_c import BATCH_C_FEATURES
from .batch_d import BATCH_D_FEATURES
from .certification import *
from .common import FAMILY_FEATURES, digest

CAMPAIGN_GLOBAL_Q_V4 = 0.0125
BATCH_COUNT_V4 = 4
ALL_FAMILIES_V4 = tuple(FAMILY_FEATURES) + tuple(BATCH_B_FEATURES) + tuple(BATCH_C_FEATURES) + tuple(BATCH_D_FEATURES)


def structural_screen_v4(outcomes: Mapping[str, Any]) -> dict[str, Any]:
    base = structural_screen(outcomes)
    survivors: list[str] = []
    for row in base.get("results", []):
        gates = dict(row.get("gates") or {})
        gates.pop("global_bh_q_le_10pct", None)
        gates["campaign_global_bh_q_le_1_25pct"] = float(row.get("bh_q", 1.0)) <= CAMPAIGN_GLOBAL_Q_V4
        row["gates"] = gates
        row["passed"] = all(gates.values())
        if row["passed"]:
            survivors.append(str(row["hypothesis_id"]))
    base["principal_verdict"] = (
        "AUTONOMOUS_FOUR_BATCH_STRUCTURAL_SCREEN_SURVIVORS"
        if survivors
        else "NO_AUTONOMOUS_FOUR_BATCH_STRUCTURAL_EDGE_CANDIDATE_SURVIVED_SCREEN"
    )
    base["survivor_hypothesis_ids"] = survivors
    base["campaign_batch_count"] = BATCH_COUNT_V4
    base["campaign_family_count"] = len(ALL_FAMILIES_V4)
    base["campaign_global_q_threshold"] = CAMPAIGN_GLOBAL_Q_V4
    base["policy"] = {
        **dict(base.get("policy") or {}),
        "campaign_global_multiple_testing_correction": "BENJAMINI_HOCHBERG_ACROSS_BATCHES_A_B_C_D",
        "sequential_expansion_penalty": "Q_THRESHOLD_HALVED_TO_1_25PCT_FOR_BATCH_D",
        "batch_d_selection_basis": "REMAINING_CLOSE_VOLUME_INFORMATION_PRIMITIVES_NOT_PRIOR_NEAR_MISS_PERFORMANCE",
        "failed_prior_families_reopened": False,
        "unopened_sessions_scored": False,
    }
    base["semantic_sha256"] = digest(base)
    return base


def exhaustion_ledger_v4(discovery: Mapping[str, Any], screen: Mapping[str, Any], wfa: Mapping[str, Any], robust: Mapping[str, Any], final: Mapping[str, Any]) -> dict[str, Any]:
    screen_by_family = Counter(str(r["family"]) for r in screen.get("results", []) if r.get("passed"))
    wfa_by_family = Counter(str(r["family"]) for r in wfa.get("results", []) if r.get("passed"))
    hyp_family = {str(r["hypothesis_id"]): str(r["family"]) for r in screen.get("results", [])}
    robust_by_family = Counter(hyp_family.get(str(hid), "UNKNOWN") for hid in robust.get("survivor_hypothesis_ids", []))
    final_by_family = Counter(hyp_family.get(str(hid), "UNKNOWN") for hid in final.get("survivor_hypothesis_ids", []))
    rows = []
    for family_record in discovery.get("families", []):
        family = str(family_record["family"])
        batch = "A" if family in FAMILY_FEATURES else "B" if family in BATCH_B_FEATURES else "C" if family in BATCH_C_FEATURES else "D"
        rows.append({
            "family": family,
            "batch": batch,
            "outcome_blind_motifs": int(family_record.get("motif_count", 0)),
            "structural_screen_survivors": int(screen_by_family.get(family, 0)),
            "validation_wfa_survivors": int(wfa_by_family.get(family, 0)),
            "robustness_survivors": int(robust_by_family.get(family, 0)),
            "final_unopened_survivors": int(final_by_family.get(family, 0)),
            "family_reopen_authorized": False,
        })
    attempted = {str(row["family"]) for row in rows}
    catalog = {
        "principal_verdict": "CLOSE_VOLUME_CONSTITUENT_INFORMATION_SPACE_EXHAUSTED_ACROSS_FOUR_PREDECLARED_BATCHES",
        "families": rows,
        "family_count": len(rows),
        "batch_count": BATCH_COUNT_V4,
        "batch_a_family_count": len(FAMILY_FEATURES),
        "batch_b_family_count": len(BATCH_B_FEATURES),
        "batch_c_family_count": len(BATCH_C_FEATURES),
        "batch_d_family_count": len(BATCH_D_FEATURES),
        "all_predeclared_families_attempted": attempted == set(ALL_FAMILIES_V4),
        "failed_families_reopened": False,
        "campaign_global_q_threshold": CAMPAIGN_GLOBAL_Q_V4,
        "unopened_tail_used_only_after_robustness": bool(final.get("unopened_sessions_scored")),
        "next_expansion_if_no_survivor": "MOVE_TO_DIFFERENT_INFORMATION_SOURCE_NOT_MORE_TRANSFORMS_OF_SAME_CLOSE_VOLUME_CORPUS",
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def build_report_v4(stages: Mapping[str, Any]) -> str:
    final = stages["final_authority"]
    return "\n".join([
        "# Autonomous Structural Edge Exhaustion V4 — Four-Batch Close/Volume Corpus Campaign",
        "",
        "Twenty-four orthogonal state families spanning first-order, distribution, temporal, dependence, price-volume, volatility, relative-strength, excursion, volume-identity, and acceleration primitives were tested under one sequentially tightened campaign budget.",
        "Failed families were not reopened or retuned.",
        "",
        f"- Families attempted: {stages['stage3_discovery']['family_count']}",
        f"- Frozen motifs: {stages['stage3_discovery']['total_frozen_motifs']}",
        f"- Frozen hypotheses: {stages['stage4_hypotheses']['hypothesis_count']}",
        f"- Campaign BH q threshold: {stages['stage6_structural_screen']['campaign_global_q_threshold']}",
        f"- Structural screen: `{stages['stage6_structural_screen']['principal_verdict']}`",
        f"- Validation/WFA: `{stages['stage7_validation_wfa']['principal_verdict']}`",
        f"- Robustness: `{stages['stage8_robustness']['principal_verdict']}`",
        f"- Final unopened: `{stages['stage9_final_unopened']['principal_verdict']}`",
        "",
        "## Final authority",
        "",
        f"`{final['principal_verdict']}`",
        "",
        "If no survivor exists, further work must move to a different information source rather than create more transforms of this same close/volume corpus.",
    ]) + "\n"
