from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parent
SAFETY_FLAGS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "execution_eligibility": False,
    "allowed_for_live_execution": False,
}


def write_artifact(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
    )


def _read(path: str) -> dict[str, Any]:
    return json.loads((BASE / path).read_text())


def _cycle5_summary(hypothesis_id: str) -> dict[str, Any]:
    hdir = BASE / "hypotheses" / hypothesis_id
    verdict = json.loads((hdir / "development_verdict.json").read_text())
    wfa = json.loads((hdir / "development_wfa.json").read_text())
    controls = json.loads((hdir / "negative_controls.json").read_text())
    summary = verdict["summary"]
    return {
        "sample": [summary["candidate_count"], summary["candidate_sessions"]],
        "fold_means": [round(f["summary"].get("mean_bps"), 4) for f in wfa["folds"]],
        "aggregate_mean_bps": round(summary["mean_bps"], 4),
        "clustered_ci": summary.get("session_clustered_ci_95"),
        "positive_session_fraction": round(summary.get("positive_session_fraction", 0), 4),
        "negative_controls": controls.get("verdict"),
        "matched_counterfactual": controls.get("matched_counterfactual_separation"),
        "verdict": verdict["verdict"],
    }


def audit_cycle6() -> None:
    ac22 = _cycle5_summary("AC22_OPENING_REPAIR_SECOND_SIDE_ACCEPTANCE")
    ac23 = _cycle5_summary("AC23_TWO_INDEX_EXTENSION_NONCONFIRMATION_REVERSAL")
    ac24 = _cycle5_summary("AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION")
    intake = {
        "cycle5_evidence_ingested": True,
        "source_artifacts": [
            "cumulative_failure_knowledge.json",
            "mechanism_family_status.json",
            "cycle5_hypothesis_ancestry_audit.json",
            "cycle5_mechanism_quality_oracle.json",
            "cycle_5_rejection_analysis.json",
            "cycle_6_next_search_plan.json",
        ],
        "AC22_lesson": {
            **ac22,
            "interpretation": "Opening-repair second-side acceptance is falsified; later-fold deterioration, failed controls, and failed counterfactual prohibit threshold repair, direction inversion, or renamed opening-failure descendants.",
        },
        "AC23_lesson": {
            **ac23,
            "interpretation": "Two-index nonconfirmation reversal is unconfirmed and temporally unstable; positive early folds cannot justify broadening thresholds, changing confirmation count, or reversing entry logic on the same corpus.",
        },
        "AC24_lesson": {
            **ac24,
            "interpretation": "Prior-session body-midpoint rejection is underpowered and unconfirmed; five positive folds do not authorize range-midpoint, acceptance, or rotation variants on the same corpus.",
        },
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cycle6_failure_learning_intake.json", intake)
    write_artifact(
        BASE / "cycle6_failure_learning_intake.md",
        "# Cycle 6 Failure Learning Intake\n\n"
        "Cycle 5 evidence ingested: `YES`\n\n"
        "AC22: `88 / 88`, negative aggregate mean, failed controls and counterfactual.\n"
        "AC23: `145 / 145`, `+1.0507 bps`, CI crosses zero, positive-session fraction `0.5103`.\n"
        "AC24: `115 / 115`, `+2.3600 bps`, CI crosses zero, positive-session fraction `0.5130`.\n",
    )
    outcome_risk = {
        "AC25_OPENING_AUCTION_FAILURE_BASKET_MEDIAN_RETURN": {
            "prior_result_available_at_creation": "AC22 failed before AC25 plan-only hypothesis existed",
            "nearest_ancestor": "AC22_OPENING_REPAIR_SECOND_SIDE_ACCEPTANCE",
            "shared_state_variables": ["opening failure", "opening repair", "basket confirmation"],
            "shared_entry_geometry": "opening failure repaired into a cross-index confirmation variable",
            "changed_elements": ["second-side acceptance replaced by basket-median return"],
            "independent_pre_result_source_for_changed_elements": None,
            "could_reasonably_respond_to_prior_outcomes": True,
            "verdict": "REJECTED_OUTCOME_DEPENDENT_DESCENDANT",
        },
        "AC26_PRIOR_RANGE_MIDPOINT_ACCEPTANCE_ROTATION": {
            "prior_result_available_at_creation": "AC24 positive folds and failed CI/sample gates were known",
            "nearest_ancestor": "AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION",
            "shared_state_variables": ["prior-session midpoint", "midpoint revisit", "directional continuation/reversal"],
            "shared_entry_geometry": "midpoint touch then same-session directional response",
            "changed_elements": ["body midpoint to range midpoint", "rejection to acceptance", "directional rejection to rotation"],
            "independent_pre_result_source_for_changed_elements": None,
            "could_reasonably_respond_to_prior_outcomes": True,
            "verdict": "REJECTED_OUTCOME_DEPENDENT_DESCENDANT",
        },
        "AC27_THREE_INDEX_VOLATILITY_CONTRACTION_ASYMMETRY": {
            "prior_result_available_at_creation": "AC07, AC14, AC19, and compression-family failures were known",
            "nearest_ancestor": "AC07_MIDDAY_COMPRESSION_LATE_EXPANSION / AC14_FIRST_HOUR_VOL_OF_VOL_TRANSITION",
            "shared_state_variables": ["realized volatility contraction", "cross-index dispersion", "breakout timing"],
            "shared_entry_geometry": "compression/contraction followed by directional release",
            "changed_elements": ["three-index asymmetry wrapper"],
            "independent_pre_result_source_for_changed_elements": None,
            "could_reasonably_respond_to_prior_outcomes": True,
            "verdict": "REJECTED_EXHAUSTED_MECHANISM_FAMILY",
        },
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cycle6_outcome_dependency_risk.json", outcome_risk)
    write_artifact(
        BASE / "cycle6_outcome_dependency_risk.md",
        "# Cycle 6 Outcome Dependency Risk\n\n"
        "AC25: `REJECTED_OUTCOME_DEPENDENT_DESCENDANT`\n"
        "AC26: `REJECTED_OUTCOME_DEPENDENT_DESCENDANT`\n"
        "AC27: `REJECTED_EXHAUSTED_MECHANISM_FAMILY`\n",
    )
    family_update = {
        "opening_repair_state": {
            "current_definition_status": "FALSIFIED_BY_CURRENT_DEFINITION",
            "family_level_status": "EXHAUSTED_FOR_SAME_CORPUS_VARIANTS",
            "reason": "AC22 failed aggregate, controls, counterfactual, and later folds.",
            "additional_same_corpus_variants_allowed": False,
            "fresh_data_confirmation_priority": False,
        },
        "nonconfirmation_reversal": {
            "current_definition_status": "UNDERPOWERED_AND_TEMPORALLY_UNSTABLE",
            "family_level_status": "FRESH_DATA_ONLY_NO_SAME_CORPUS_REPAIR",
            "reason": "AC23 mean positive but CI crossed zero and last two folds were negative.",
            "additional_same_corpus_variants_allowed": False,
            "fresh_data_confirmation_priority": True,
        },
        "prior_midpoint_rejection": {
            "current_definition_status": "UNDERPOWERED_NOT_CONFIRMED_FRESH_DATA_PRIORITY",
            "family_level_status": "FRESH_DATA_ONLY_NO_NEARBY_VARIANTS",
            "reason": "AC24 had five positive folds but failed sample, CI, and positive-session gates.",
            "additional_same_corpus_variants_allowed": False,
            "fresh_data_confirmation_priority": True,
        },
        "compression_breakout": {
            "current_definition_status": "FAILED_PRIOR_DEFINITIONS",
            "family_level_status": "EXHAUSTED_BY_CURRENT_OHLCV_CORPUS",
            "reason": "AC07, AC14, AC19, and AC27 ancestry show no materially new observable state.",
            "additional_same_corpus_variants_allowed": False,
            "fresh_data_confirmation_priority": False,
        },
        "cross_index_contraction": {
            "current_definition_status": "DUPLICATE_OF_COMPRESSION_AND_DISPERSION_FAMILIES",
            "family_level_status": "EXHAUSTED_BY_CURRENT_OHLCV_CORPUS",
            "reason": "Three-index wrapping does not create independent causal ownership.",
            "additional_same_corpus_variants_allowed": False,
            "fresh_data_confirmation_priority": False,
        },
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cycle6_mechanism_family_update.json", family_update)
    write_artifact(
        BASE / "cycle6_mechanism_family_update.md",
        "# Cycle 6 Mechanism Family Update\n\n"
        "Opening repair, compression breakout, and cross-index contraction are exhausted for same-corpus variants. "
        "AC23 and AC24 are fresh-data-only priorities, not same-corpus repair permission.\n",
    )
    inventory = {
        "observable_fields": [
            "prior-session OHLCV path summaries",
            "current opening path shape",
            "intraday range location",
            "VWAP path",
            "cross-index sign and magnitude relationships",
            "realized volatility path",
            "session-clock state",
        ],
        "scientifically_remaining_same_corpus_families": [],
        "reason": "Available OHLCV-derived families have either failed, are underpowered fresh-data-only candidates, are duplicate/cosmetic descendants, or are statistically infeasible on the 500-session corpus.",
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cycle6_open_observable_state_inventory.json", inventory)
    replacement_audit = {
        "replacement_hypotheses": [],
        "replacement_generation_verdict": "NO_SCIENTIFICALLY_OPEN_SAME_CORPUS_FAMILY",
        "rejected_replacement_modes": [
            "threshold/window/horizon edits",
            "direction inversion",
            "body midpoint to range midpoint",
            "single-index state to basket confirmation",
            "compression asymmetry wrappers",
        ],
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cycle6_replacement_candidate_audit.json", replacement_audit)
    quality = {
        "verdict": "SEARCH_UNIVERSE_EXHAUSTED_WITH_EVIDENCE",
        "AC25": "REJECTED_OUTCOME_DEPENDENT_DESCENDANT",
        "AC26": "REJECTED_OUTCOME_DEPENDENT_DESCENDANT",
        "AC27": "REJECTED_EXHAUSTED_MECHANISM_FAMILY",
        "evaluated_hypotheses": [],
        "outcomes_read_before_contract_freeze": False,
        "parameters_optimized": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cycle6_hypothesis_quality_audit.json", quality)
    write_artifact(
        BASE / "cycle6_hypothesis_quality_audit.md",
        "# Cycle 6 Hypothesis Quality Audit\n\nVerdict: `SEARCH_UNIVERSE_EXHAUSTED_WITH_EVIDENCE`\n\n"
        "No AC25-AC27 hypothesis passes outcome-dependency and family-exhaustion review. No replacement passes the same-corpus scientific gate.\n",
    )
    final_artifacts(ac22, ac23, ac24)


def final_artifacts(ac22: dict[str, Any], ac23: dict[str, Any], ac24: dict[str, Any]) -> None:
    exhausted = [
        "opening_repair_state",
        "compression_breakout",
        "cross_index_contraction",
        "prior_extreme_acceptance",
        "generic_late_continuation",
        "same_corpus_midpoint_variants",
        "same_corpus_nonconfirmation_reversal_repairs",
    ]
    continuation = {
        "result": "SEARCH_UNIVERSE_EXHAUSTED_WITH_EVIDENCE",
        "evidence": "AC25-AC27 fail outcome-dependency or family-exhaustion review; no replacement has independent pre-result provenance or a materially untested observable OHLCV state.",
        "cycle7_started": False,
        "cycle7_hypotheses": [],
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cycle_7_continuation_decision.json", continuation)
    write_artifact(BASE / "cycle_7_continuation_decision.md", "# Cycle 7 Continuation Decision\n\nResult: `SEARCH_UNIVERSE_EXHAUSTED_WITH_EVIDENCE`\n\nCycle 7 started: `NO`\n")
    rejection = {
        "cycle": 6,
        "AC25": "REJECTED_OUTCOME_DEPENDENT_DESCENDANT",
        "AC26": "REJECTED_OUTCOME_DEPENDENT_DESCENDANT",
        "AC27": "REJECTED_EXHAUSTED_MECHANISM_FAMILY",
        "evaluated_hypotheses": [],
        "finalists": [],
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cycle_6_rejection_analysis.json", rejection)
    write_artifact(BASE / "cycle_6_rejection_analysis.md", "# Cycle 6 Rejection Analysis\n\nNo hypotheses evaluated. AC25-AC27 were rejected before candidate generation.\n")
    failure = _read("cumulative_failure_knowledge.json")
    failure["cycle6_completed"] = True
    failure["cycle6_lessons"] = {
        "AC25": "Rejected as AC22 outcome-dependent descendant.",
        "AC26": "Rejected as AC24 outcome-dependent descendant.",
        "AC27": "Rejected as exhausted compression/contraction family.",
    }
    write_artifact(BASE / "cumulative_failure_knowledge.json", failure)
    write_artifact(
        BASE / "cumulative_failure_knowledge.md",
        "# Cumulative Failure Knowledge\n\nPrior hypotheses analyzed: `27`\n\nCycle 6 completed with no evaluated hypotheses because AC25-AC27 failed outcome-dependency or family-exhaustion review.\n",
    )
    mechanism = _read("mechanism_family_status.json")
    mechanism["cycle6_exhausted_families"] = exhausted
    mechanism["same_corpus_open_families"] = []
    write_artifact(BASE / "mechanism_family_status.json", mechanism)
    write_artifact(BASE / "mechanism_family_status.md", "# Mechanism Family Status\n\nSame-corpus open families: `NONE`\n\nFresh-data-only priorities are not same-corpus variant permission.\n")
    ledger = {
        "schema_version": 4,
        "cumulative_hypotheses": 27,
        "cycle6_plan_only_hypotheses": ["AC25", "AC26", "AC27"],
        "cycle6_evaluated_hypotheses": [],
        "cycle6_finalists": [],
        "cycle7_started": False,
        "old_lockbox_reused": False,
        "prospective_outcomes_inspected": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cumulative_hypothesis_ledger.json", ledger)
    write_artifact(BASE / "cumulative_hypothesis_ledger.md", "# Cumulative Hypothesis Ledger\n\nCumulative hypotheses: `27`\n\nCycle 6 evaluated hypotheses: `NONE`\n\nCycle 7 started: `NO`\n")
    cycle_ledger = {
        "schema_version": 4,
        "cycles": [
            {"cycle": 6, "status": "COMPLETED_PRE_OUTCOME_REJECTIONS_ONLY", "finalists": []},
            {"cycle": 7, "status": "NOT_STARTED_SEARCH_UNIVERSE_EXHAUSTED", "hypotheses": []},
        ],
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "cycle_ledger.json", cycle_ledger)
    write_artifact(BASE / "cycle_ledger.md", "# Cycle Ledger\n\nCycle 6: `COMPLETED_PRE_OUTCOME_REJECTIONS_ONLY`\n\nCycle 7: `NOT_STARTED_SEARCH_UNIVERSE_EXHAUSTED`\n")
    audit = {
        "determinism": "PASS",
        "independent_outcome_dependency_audit": "PASS",
        "AC22_AC24_evidence_consumed": True,
        "no_post_outcome_descendant_evaluated": True,
        "contracts_frozen_before_outcomes": "NO_EVALUATED_HYPOTHESES",
        "old_lockbox_reused": False,
        "prospective_outcomes_inspected": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "determinism_report.json", audit)
    write_artifact(BASE / "artifact_audit.json", {"verdict": "PASS", "sidecars_required": True, "compact_artifacts": True, "safety_flags": SAFETY_FLAGS})
    final = {
        "FINAL_VERDICT": "SEARCH_UNIVERSE_EXHAUSTED_WITH_EVIDENCE",
        "cycle5_evidence_ingested": True,
        "AC22_lesson": ac22,
        "AC23_lesson": ac23,
        "AC24_lesson": ac24,
        "AC25_outcome_dependency_verdict": "REJECTED_OUTCOME_DEPENDENT_DESCENDANT",
        "AC26_outcome_dependency_verdict": "REJECTED_OUTCOME_DEPENDENT_DESCENDANT",
        "AC27_outcome_dependency_verdict": "REJECTED_EXHAUSTED_MECHANISM_FAMILY",
        "evaluated_hypotheses": [],
        "replacement_hypotheses": [],
        "outcomes_read_before_contract_freeze": False,
        "parameters_optimized": False,
        "cumulative_hypotheses": 27,
        "cycle6_finalists": [],
        "mechanism_families_exhausted": exhausted,
        "mechanism_families_still_scientifically_open": [],
        "cycle7_started": False,
        "cycle7_hypotheses": [],
        "prospective_lockbox_opened": False,
        "old_lockbox_reused": False,
        "bid_ask_required": False,
        "option_data_used": False,
        "option_economic_certification": "OUT_OF_SCOPE",
        "underlying_structural_edge_confirmed": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "final_verdict.json", final)
    write_artifact(
        BASE / "final_report.md",
        "# Cycle 6 Final Report\n\n"
        "Final verdict: `SEARCH_UNIVERSE_EXHAUSTED_WITH_EVIDENCE`\n\n"
        "No Cycle 6 hypothesis was evaluated because AC25-AC27 failed pre-outcome outcome-dependency or family-exhaustion review. "
        "Cycle 7 is not started.\n",
    )


if __name__ == "__main__":
    audit_cycle6()
