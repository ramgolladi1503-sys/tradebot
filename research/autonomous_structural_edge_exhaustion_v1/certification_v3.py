from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from .batch_b import BATCH_B_FEATURES
from .batch_c import BATCH_C_FEATURES
from .certification import *
from .common import FAMILY_FEATURES, digest

CAMPAIGN_GLOBAL_Q_V3 = 0.025
BATCH_COUNT_V3 = 3
ALL_FAMILIES_V3 = tuple(FAMILY_FEATURES) + tuple(BATCH_B_FEATURES) + tuple(BATCH_C_FEATURES)


def structural_screen_v3(outcomes: Mapping[str, Any]) -> dict[str, Any]:
    base = structural_screen(outcomes)
    survivors: list[str] = []
    for row in base.get("results", []):
        gates = dict(row.get("gates") or {})
        gates.pop("global_bh_q_le_10pct", None)
        gates["campaign_global_bh_q_le_2_5pct"] = float(row.get("bh_q", 1.0)) <= CAMPAIGN_GLOBAL_Q_V3
        row["gates"] = gates
        row["passed"] = all(gates.values())
        if row["passed"]:
            survivors.append(str(row["hypothesis_id"]))
    base["principal_verdict"] = (
        "AUTONOMOUS_THREE_BATCH_STRUCTURAL_SCREEN_SURVIVORS"
        if survivors
        else "NO_AUTONOMOUS_THREE_BATCH_STRUCTURAL_EDGE_CANDIDATE_SURVIVED_SCREEN"
    )
    base["survivor_hypothesis_ids"] = survivors
    base["campaign_batch_count"] = BATCH_COUNT_V3
    base["campaign_family_count"] = len(ALL_FAMILIES_V3)
    base["campaign_global_q_threshold"] = CAMPAIGN_GLOBAL_Q_V3
    base["policy"] = {
        **dict(base.get("policy") or {}),
        "campaign_global_multiple_testing_correction": "BENJAMINI_HOCHBERG_ACROSS_BATCHES_A_B_C",
        "sequential_expansion_penalty": "Q_THRESHOLD_TIGHTENED_FROM_5PCT_TO_2_5PCT",
        "batch_c_selection_basis": "ABSENT_INFORMATION_PRIMITIVES_NOT_A_B_NEAR_MISS_PERFORMANCE",
        "failed_batch_a_b_families_reopened": False,
        "unopened_sessions_scored": False,
    }
    base["semantic_sha256"] = digest(base)
    return base


def exhaustion_ledger_v3(
    discovery: Mapping[str, Any],
    screen: Mapping[str, Any],
    wfa: Mapping[str, Any],
    robust: Mapping[str, Any],
    final: Mapping[str, Any],
) -> dict[str, Any]:
    screen_by_family = Counter(str(r["family"]) for r in screen.get("results", []) if r.get("passed"))
    wfa_by_family = Counter(str(r["family"]) for r in wfa.get("results", []) if r.get("passed"))
    hyp_family = {str(r["hypothesis_id"]): str(r["family"]) for r in screen.get("results", [])}
    robust_by_family = Counter(hyp_family.get(str(hid), "UNKNOWN") for hid in robust.get("survivor_hypothesis_ids", []))
    final_by_family = Counter(hyp_family.get(str(hid), "UNKNOWN") for hid in final.get("survivor_hypothesis_ids", []))
    rows: list[dict[str, Any]] = []
    for family_record in discovery.get("families", []):
        family = str(family_record["family"])
        if family in FAMILY_FEATURES:
            batch = "A"
        elif family in BATCH_B_FEATURES:
            batch = "B"
        else:
            batch = "C"
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
        "principal_verdict": "AVAILABLE_CONSTITUENT_INFORMATION_FAMILIES_EXHAUSTED_ACROSS_THREE_PREDECLARED_BATCHES",
        "families": rows,
        "family_count": len(rows),
        "batch_count": BATCH_COUNT_V3,
        "batch_a_family_count": len(FAMILY_FEATURES),
        "batch_b_family_count": len(BATCH_B_FEATURES),
        "batch_c_family_count": len(BATCH_C_FEATURES),
        "all_predeclared_families_attempted": attempted == set(ALL_FAMILIES_V3),
        "failed_families_reopened": False,
        "campaign_global_q_threshold": CAMPAIGN_GLOBAL_Q_V3,
        "unopened_tail_used_only_after_robustness": bool(final.get("unopened_sessions_scored")),
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def build_report_v3(stages: Mapping[str, Any]) -> str:
    discovery = stages["stage3_discovery"]
    screen = stages["stage6_structural_screen"]
    final = stages["stage9_final_unopened"]
    strategies = stages["stage10_strategy_specs"]
    lines = [
        "# Autonomous Structural Edge Exhaustion V3 — Three-Batch Campaign",
        "",
        "Three orthogonal information batches were evaluated under one global campaign ledger.",
        "Batch C was selected from absent information primitives, not Batch A/B near-miss performance.",
        "Failed A/B families were not reopened or retuned.",
        "The campaign-global BH threshold is 2.5% after the sequential Batch C expansion.",
        "",
        f"- Families attempted: {discovery['family_count']}",
        f"- Frozen motifs: {discovery['total_frozen_motifs']}",
        f"- Frozen hypotheses: {stages['stage4_hypotheses']['hypothesis_count']}",
        f"- Structural screen: `{screen['principal_verdict']}`",
        f"- Validation/WFA: `{stages['stage7_validation_wfa']['principal_verdict']}`",
        f"- Robustness: `{stages['stage8_robustness']['principal_verdict']}`",
        f"- Final unopened: `{final['principal_verdict']}`",
        f"- Strategy authority: `{strategies['principal_verdict']}`",
        "",
        "## Final authority",
        "",
        f"`{stages['final_authority']['principal_verdict']}`",
        "",
        "Any statistical survivor remains membership-authority-limited until point-in-time NIFTY membership is proven.",
    ]
    return "\n".join(lines) + "\n"
