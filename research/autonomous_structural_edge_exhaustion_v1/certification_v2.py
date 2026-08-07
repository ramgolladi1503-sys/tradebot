from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from .batch_b import BATCH_B_FEATURES
from .certification import *
from .common import FAMILY_FEATURES, digest

CAMPAIGN_GLOBAL_Q = 0.05
BATCH_COUNT = 2
ALL_FAMILIES = tuple(FAMILY_FEATURES) + tuple(BATCH_B_FEATURES)


def structural_screen_v2(outcomes: Mapping[str, Any]) -> dict[str, Any]:
    base = structural_screen(outcomes)
    survivors: list[str] = []
    for row in base.get("results", []):
        gates = dict(row.get("gates") or {})
        gates.pop("global_bh_q_le_10pct", None)
        gates["campaign_global_bh_q_le_5pct"] = float(row.get("bh_q", 1.0)) <= CAMPAIGN_GLOBAL_Q
        row["gates"] = gates
        row["passed"] = all(gates.values())
        if row["passed"]:
            survivors.append(str(row["hypothesis_id"]))
    base["principal_verdict"] = (
        "AUTONOMOUS_TWO_BATCH_STRUCTURAL_SCREEN_SURVIVORS"
        if survivors
        else "NO_AUTONOMOUS_TWO_BATCH_STRUCTURAL_EDGE_CANDIDATE_SURVIVED_SCREEN"
    )
    base["survivor_hypothesis_ids"] = survivors
    base["campaign_batch_count"] = BATCH_COUNT
    base["campaign_global_q_threshold"] = CAMPAIGN_GLOBAL_Q
    base["policy"] = {
        **dict(base.get("policy") or {}),
        "campaign_global_multiple_testing_correction": "BENJAMINI_HOCHBERG_ACROSS_BATCH_A_AND_BATCH_B",
        "adaptive_batch_penalty": "Q_THRESHOLD_TIGHTENED_FROM_10PCT_TO_5PCT",
        "batch_a_failed_families_reopened": False,
        "unopened_sessions_scored": False,
    }
    base["semantic_sha256"] = digest(base)
    return base


def exhaustion_ledger_v2(
    discovery: Mapping[str, Any],
    screen: Mapping[str, Any],
    wfa: Mapping[str, Any],
    robust: Mapping[str, Any],
    final: Mapping[str, Any],
) -> dict[str, Any]:
    screen_by_family = Counter(
        str(r["family"]) for r in screen.get("results", []) if r.get("passed")
    )
    wfa_by_family = Counter(
        str(r["family"]) for r in wfa.get("results", []) if r.get("passed")
    )
    hyp_family: dict[str, str] = {
        str(r["hypothesis_id"]): str(r["family"])
        for r in screen.get("results", [])
    }
    robust_by_family = Counter(
        hyp_family.get(str(hid), "UNKNOWN")
        for hid in robust.get("survivor_hypothesis_ids", [])
    )
    final_by_family = Counter(
        hyp_family.get(str(hid), "UNKNOWN")
        for hid in final.get("survivor_hypothesis_ids", [])
    )
    rows: list[dict[str, Any]] = []
    for family_record in discovery.get("families", []):
        family = str(family_record["family"])
        rows.append(
            {
                "family": family,
                "batch": str(family_record.get("batch") or ("A" if family in FAMILY_FEATURES else "B")),
                "outcome_blind_motifs": int(family_record.get("motif_count", 0)),
                "structural_screen_survivors": int(screen_by_family.get(family, 0)),
                "validation_wfa_survivors": int(wfa_by_family.get(family, 0)),
                "robustness_survivors": int(robust_by_family.get(family, 0)),
                "final_unopened_survivors": int(final_by_family.get(family, 0)),
                "family_reopen_authorized": False,
            }
        )
    attempted = {str(row["family"]) for row in rows}
    catalog = {
        "principal_verdict": "AVAILABLE_CONSTITUENT_INFORMATION_FAMILIES_EXHAUSTED_ACROSS_TWO_PREDECLARED_BATCHES",
        "families": rows,
        "family_count": len(rows),
        "batch_count": BATCH_COUNT,
        "batch_a_family_count": len(FAMILY_FEATURES),
        "batch_b_family_count": len(BATCH_B_FEATURES),
        "all_predeclared_families_attempted": attempted == set(ALL_FAMILIES),
        "failed_families_reopened": False,
        "campaign_global_q_threshold": CAMPAIGN_GLOBAL_Q,
        "unopened_tail_used_only_after_robustness": bool(final.get("unopened_sessions_scored")),
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def build_report_v2(stages: Mapping[str, Any]) -> str:
    discovery = stages["stage3_discovery"]
    screen = stages["stage6_structural_screen"]
    final = stages["stage9_final_unopened"]
    strategies = stages["stage10_strategy_specs"]
    lines = [
        "# Autonomous Structural Edge Exhaustion V2 — Two-Batch Campaign",
        "",
        "Batch A and orthogonal Batch B were executed under one campaign-level multiplicity ledger.",
        "Batch A failed families were not reopened or threshold-tuned.",
        "The global BH threshold was tightened to 5% when Batch B was added.",
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
        "Any statistical survivor remains blocked from full constituent-certified authority until point-in-time NIFTY membership is proven.",
    ]
    return "\n".join(lines) + "\n"
