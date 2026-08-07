from __future__ import annotations

import math
from collections import Counter
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .common import *
from .discovery import FamilyModel, assign_family, precompute_motif_signals
from .outcomes import build_outcome_lookup, summarize


def structural_screen(outcomes: Mapping[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    pvalues: list[float] = []
    for record in outcomes.get("records", []):
        obs = record["stats"]["observation"]["directional_excess"]
        rep = record["stats"]["replication"]["directional_excess"]
        pvalues.append(float(rep["sign_p"]))
        rows.append({
            "hypothesis_id": record["hypothesis"]["hypothesis_id"],
            "family": record["hypothesis"]["family"],
            "observation": obs,
            "replication": rep,
        })
    qvalues = PA.bh_qvalues(pvalues)
    survivors: list[str] = []
    for row, q in zip(rows, qvalues):
        obs, rep = row["observation"], row["replication"]
        gates = {
            "observation_n_ge_20": obs["n"] >= 20,
            "observation_abs_mean_ge_2bps": abs(float(obs["mean_bps"] or 0.0)) >= 2.0,
            "replication_n_ge_10": rep["n"] >= 10,
            "replication_mean_ge_2bps": float(rep["mean_bps"] or -1e9) >= 2.0,
            "replication_hit_rate_ge_55pct": float(rep["hit_rate"] or 0.0) >= 0.55,
            "replication_ci90_lower_positive": rep["ci90"][0] is not None and float(rep["ci90"][0]) > 0.0,
            "global_bh_q_le_10pct": float(q) <= 0.10,
        }
        row["bh_q"] = float(q)
        row["gates"] = gates
        row["passed"] = all(gates.values())
        if row["passed"]:
            survivors.append(row["hypothesis_id"])
    catalog = {
        "principal_verdict": "AUTONOMOUS_STRUCTURAL_SCREEN_SURVIVORS" if survivors else "NO_AUTONOMOUS_STRUCTURAL_EDGE_CANDIDATE_SURVIVED_SCREEN",
        "global_hypothesis_count": len(rows),
        "survivor_hypothesis_ids": survivors,
        "results": rows,
        "policy": {"global_multiple_testing_correction": "BENJAMINI_HOCHBERG", "unopened_sessions_scored": False},
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def _events_by_hypothesis(outcomes: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {str(r["hypothesis"]["hypothesis_id"]): list(r["events"]) for r in outcomes.get("records", [])}


def _hypothesis_lookup(outcomes: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r["hypothesis"]["hypothesis_id"]): dict(r["hypothesis"]) for r in outcomes.get("records", [])}


def validation_and_wfa(outcomes: Mapping[str, Any], screen: Mapping[str, Any]) -> dict[str, Any]:
    events_lookup = _events_by_hypothesis(outcomes)
    hyp_lookup = _hypothesis_lookup(outcomes)
    results: list[dict[str, Any]] = []
    survivors: list[str] = []
    for hid in screen.get("survivor_hypothesis_ids", []):
        events = events_lookup.get(hid, [])
        val = [e for e in events if e["split"] == "validation"]
        val_stats = summarize([e["net_proxy_bps"] for e in val])
        dev = [e for e in events if e["split"] in {"observation", "replication", "validation"}]
        dates = sorted({str(e["session_date"]) for e in dev})
        folds = np.array_split(np.asarray(dates, dtype=object), 4) if dates else []
        fold_stats = []
        positive_folds = 0
        usable_folds = 0
        for i, fold_dates in enumerate(folds):
            allowed = set(map(str, fold_dates.tolist()))
            vals = [float(e["net_proxy_bps"]) for e in dev if str(e["session_date"]) in allowed]
            stats = summarize(vals)
            fold_stats.append({"fold": i, **stats})
            if stats["n"] >= 3:
                usable_folds += 1
                positive_folds += int(float(stats["mean_bps"] or -1e9) > 0.0)
        worst = min((float(f["mean_bps"]) for f in fold_stats if f["n"] >= 3 and f["mean_bps"] is not None), default=-1e9)
        gates = {
            "validation_n_ge_8": val_stats["n"] >= 8,
            "validation_mean_net_positive": float(val_stats["mean_bps"] or -1e9) > 0.0,
            "validation_hit_rate_ge_50pct": float(val_stats["hit_rate"] or 0.0) >= 0.50,
            "wfa_usable_folds_ge_3": usable_folds >= 3,
            "wfa_positive_fold_share_ge_75pct": usable_folds >= 3 and positive_folds / usable_folds >= 0.75,
            "wfa_worst_fold_gt_minus5bps": worst > -5.0,
        }
        passed = all(gates.values())
        results.append({
            "hypothesis_id": hid,
            "family": hyp_lookup[hid]["family"],
            "validation": val_stats,
            "folds": fold_stats,
            "gates": gates,
            "passed": passed,
        })
        if passed:
            survivors.append(hid)
    catalog = {
        "principal_verdict": "AUTONOMOUS_FIXED_RULE_WFA_SURVIVORS" if survivors else "NO_AUTONOMOUS_CANDIDATE_SURVIVED_VALIDATION_WFA",
        "survivor_hypothesis_ids": survivors,
        "results": results,
        "policy": {"parameters_retrained_per_fold": False, "unopened_sessions_scored": False},
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def robustness(outcomes: Mapping[str, Any], wfa: Mapping[str, Any]) -> dict[str, Any]:
    lookup = _events_by_hypothesis(outcomes)
    results: list[dict[str, Any]] = []
    survivors: list[str] = []
    for hid in wfa.get("survivor_hypothesis_ids", []):
        events = [e for e in lookup.get(hid, []) if e["split"] in {"observation", "replication", "validation"}]
        gross = np.asarray([float(e["directional_gross_bps"]) for e in events], dtype=float)
        if len(gross) < 20:
            results.append({"hypothesis_id": hid, "passed": False, "reason": "insufficient_trades"})
            continue
        base = gross - COST_BPS
        high_cost = gross - ROBUST_COST_BPS
        cutoff = max(1, int(math.ceil(len(base) * 0.10)))
        remove_idx = np.argsort(base)[-cutoff:]
        keep = np.ones(len(base), dtype=bool)
        keep[remove_idx] = False
        stripped = base[keep]
        delayed = np.asarray([float(e["delayed_net_proxy_bps"]) for e in events if e.get("delayed_net_proxy_bps") is not None], dtype=float)
        shorter = np.asarray([float(e["shorter_net_proxy_bps"]) for e in events if e.get("shorter_net_proxy_bps") is not None], dtype=float)
        longer = np.asarray([float(e["longer_net_proxy_bps"]) for e in events if e.get("longer_net_proxy_bps") is not None], dtype=float)
        concentration = PA.concentration_ratio(base, 5)
        gates = {
            "base_mean_positive": float(np.mean(base)) > 0.0,
            "ten_bps_cost_mean_positive": float(np.mean(high_cost)) > 0.0,
            "remove_best_10pct_mean_positive": len(stripped) > 0 and float(np.mean(stripped)) > 0.0,
            "top5_positive_concentration_le_60pct": concentration <= 0.60,
            "delayed_entry_mean_positive": len(delayed) >= 10 and float(np.mean(delayed)) > 0.0,
            "shorter_horizon_not_catastrophic": len(shorter) >= 10 and float(np.mean(shorter)) > -5.0,
            "longer_horizon_not_catastrophic": len(longer) >= 10 and float(np.mean(longer)) > -5.0,
        }
        passed = all(gates.values())
        record = {
            "hypothesis_id": hid,
            "passed": passed,
            "gates": gates,
            "base_mean_bps": float(np.mean(base)),
            "ten_bps_cost_mean_bps": float(np.mean(high_cost)),
            "remove_best_10pct_mean_bps": float(np.mean(stripped)) if len(stripped) else None,
            "top5_positive_concentration": float(concentration),
            "delayed_entry_mean_bps": float(np.mean(delayed)) if len(delayed) else None,
            "shorter_horizon_mean_bps": float(np.mean(shorter)) if len(shorter) else None,
            "longer_horizon_mean_bps": float(np.mean(longer)) if len(longer) else None,
        }
        results.append(record)
        if passed:
            survivors.append(hid)
    catalog = {
        "principal_verdict": "AUTONOMOUS_ROBUSTNESS_SURVIVORS" if survivors else "NO_AUTONOMOUS_CANDIDATE_SURVIVED_ROBUSTNESS",
        "survivor_hypothesis_ids": survivors,
        "results": results,
        "policy": {"thresholds_tuned_after_attack": False, "unopened_sessions_scored": False},
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def rank_final_candidates(outcomes: Mapping[str, Any], screen: Mapping[str, Any], wfa: Mapping[str, Any], robust: Mapping[str, Any]) -> list[str]:
    survivors = set(map(str, robust.get("survivor_hypothesis_ids", [])))
    if not survivors:
        return []
    screen_lookup = {r["hypothesis_id"]: r for r in screen.get("results", [])}
    wfa_lookup = {r["hypothesis_id"]: r for r in wfa.get("results", [])}
    robust_lookup = {r["hypothesis_id"]: r for r in robust.get("results", [])}
    scored = []
    for hid in survivors:
        rep = screen_lookup[hid]["replication"]
        val = wfa_lookup[hid]["validation"]
        rob = robust_lookup[hid]
        score = min(
            float(rep["mean_bps"] or -1e9),
            float(val["mean_bps"] or -1e9),
            float(rob.get("remove_best_10pct_mean_bps") or -1e9),
        )
        scored.append((score, -float(screen_lookup[hid]["bh_q"]), hid))
    scored.sort(reverse=True)
    return [hid for _, _, hid in scored[:MAX_FINAL_CANDIDATES]]


def unopened_test(
    outcomes: Mapping[str, Any],
    hypotheses: Mapping[str, Any],
    assignments: Mapping[str, pd.DataFrame],
    frame: pd.DataFrame,
    screen: Mapping[str, Any],
    wfa: Mapping[str, Any],
    robust: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = rank_final_candidates(outcomes, screen, wfa, robust)
    if not candidates:
        catalog = {
            "principal_verdict": "UNOPENED_NOT_ACCESSED_NO_ROBUST_AUTONOMOUS_SURVIVOR",
            "unopened_sessions_scored": False,
            "tested_hypothesis_ids": [],
            "survivor_hypothesis_ids": [],
            "results": [],
        }
        catalog["semantic_sha256"] = digest(catalog)
        return catalog

    outcome_lookup = build_outcome_lookup(frame, {"unopened"})
    pseudo_discovery = {
        "families": [
            {
                "family": family,
                "motifs": [
                    {"motif_id": h["motif_id"], "motif": h["motif"], "family": family}
                    for h in hypotheses.get("hypotheses", []) if h["family"] == family
                ],
            }
            for family in assignments
        ]
    }
    signal_table = precompute_motif_signals(pseudo_discovery, assignments)
    hyp_lookup = {h["hypothesis_id"]: h for h in hypotheses.get("hypotheses", [])}
    development_lookup = _hypothesis_lookup(outcomes)
    results = []
    survivors = []
    for hid in candidates:
        h = hyp_lookup[hid]
        family = str(h["family"])
        horizon = int(h["horizon_bars"])
        direction = int(development_lookup[hid]["direction_selected_from_observation_only"])
        trades = []
        for session_date, signal in signal_table.get(str(h["motif_id"]), {}).items():
            if split_name_for_date(str(session_date), {
                "observation": [], "replication": [], "validation": [],
                "unopened": assignments[family].loc[assignments[family]["split"].eq("unopened"), "session_date"].astype(str).unique().tolist(),
            }) != "unopened":
                continue
            outcome = outcome_lookup.get((str(session_date), int(pd.Timestamp(signal).value), horizon))
            if outcome is None:
                continue
            trades.append({
                "session_date": str(session_date),
                "net_proxy_bps": direction * float(outcome["raw_return_bps"]) - COST_BPS,
            })
        values = np.asarray([t["net_proxy_bps"] for t in trades], dtype=float)
        stats = summarize(values)
        concentration = PA.concentration_ratio(values, 5) if len(values) else 1.0
        gates = {
            "n_ge_8": stats["n"] >= 8,
            "mean_net_ge_2bps": float(stats["mean_bps"] or -1e9) >= 2.0,
            "hit_rate_ge_55pct": float(stats["hit_rate"] or 0.0) >= 0.55,
            "ci90_lower_positive": stats["ci90"][0] is not None and float(stats["ci90"][0]) > 0.0,
            "top5_positive_concentration_le_70pct": float(concentration) <= 0.70,
        }
        passed = all(gates.values())
        results.append({
            "hypothesis_id": hid,
            "passed": passed,
            "stats": stats,
            "top5_positive_concentration": float(concentration),
            "gates": gates,
        })
        if passed:
            survivors.append(hid)
    catalog = {
        "principal_verdict": "AUTONOMOUS_FINAL_UNOPENED_STRUCTURAL_EDGE_SURVIVORS" if survivors else "NO_AUTONOMOUS_CANDIDATE_SURVIVED_FINAL_UNOPENED_TEST",
        "unopened_sessions_scored": True,
        "tested_hypothesis_ids": candidates,
        "survivor_hypothesis_ids": survivors,
        "results": results,
        "policy": {"one_shot_final_test": True, "maximum_candidates": MAX_FINAL_CANDIDATES, "post_test_tuning_authorized": False},
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def build_strategy_specs(
    final: Mapping[str, Any],
    outcomes: Mapping[str, Any],
    hypotheses: Mapping[str, Any],
    models: Mapping[str, FamilyModel],
    universe: Mapping[str, Any],
) -> dict[str, Any]:
    final_ids = set(map(str, final.get("survivor_hypothesis_ids", [])))
    if not final_ids:
        catalog = {
            "principal_verdict": "NO_AUTONOMOUS_STRUCTURAL_EDGE_STRATEGY_SPEC_CREATED",
            "strategies": [],
            "membership_authority": "BLOCKED_BY_POINT_IN_TIME_MEMBERSHIP",
        }
        catalog["semantic_sha256"] = digest(catalog)
        return catalog
    hyp_lookup = {h["hypothesis_id"]: h for h in hypotheses.get("hypotheses", [])}
    dev_lookup = _hypothesis_lookup(outcomes)
    strategies = []
    for hid in sorted(final_ids):
        h = hyp_lookup[hid]
        model = models[h["family"]]
        direction = int(dev_lookup[hid]["direction_selected_from_observation_only"])
        spec = {
            "strategy_id": f"ASEV1::{hid}",
            "hypothesis_id": hid,
            "family": h["family"],
            "motif": h["motif"],
            "state_model_sha256": model.model_semantic_sha256,
            "direction": "LONG" if direction > 0 else "SHORT",
            "trigger": "first chronological confident completion of frozen state sequence",
            "entry": "next completed 5-minute NIFTY bar",
            "hold_bars": int(h["horizon_bars"]),
            "hold_minutes": int(h["horizon_minutes"]),
            "exit": "fixed hold horizon",
            "cost_proxy_bps": COST_BPS,
            "risk_stop_or_target": "NOT_OPTIMIZED_OR_AUTHORIZED",
            "point_in_time_membership_available": False,
            "membership_authority": "REQUIRES_POINT_IN_TIME_CONSTITUENT_CONFIRMATION",
            "options_translation_authorized": False,
            "shadow_authorized": False,
            "paper_authorized": False,
            "live_authorized": False,
            "order_authorized": False,
        }
        spec["semantic_sha256"] = digest(spec)
        strategies.append(spec)
    catalog = {
        "principal_verdict": "PROXY_UNDERLYING_STRUCTURAL_EDGE_STRATEGY_SPECS_FROZEN_MEMBERSHIP_CONFIRMATION_REQUIRED",
        "strategies": strategies,
        "membership_authority": "REQUIRES_POINT_IN_TIME_CONSTITUENT_CONFIRMATION",
        "universe_semantic_sha256": universe["semantic_sha256"],
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def exhaustion_ledger(discovery: Mapping[str, Any], screen: Mapping[str, Any], wfa: Mapping[str, Any], robust: Mapping[str, Any], final: Mapping[str, Any]) -> dict[str, Any]:
    screen_by_family = Counter(r["family"] for r in screen.get("results", []) if r.get("passed"))
    wfa_by_family = Counter(r["family"] for r in wfa.get("results", []) if r.get("passed"))
    hyp_family: dict[str, str] = {r["hypothesis_id"]: r["family"] for r in screen.get("results", [])}
    robust_by_family = Counter(hyp_family.get(hid, "UNKNOWN") for hid in robust.get("survivor_hypothesis_ids", []))
    final_by_family = Counter(hyp_family.get(hid, "UNKNOWN") for hid in final.get("survivor_hypothesis_ids", []))
    rows = []
    for family_record in discovery.get("families", []):
        family = family_record["family"]
        rows.append({
            "family": family,
            "outcome_blind_motifs": int(family_record.get("motif_count", 0)),
            "structural_screen_survivors": int(screen_by_family.get(family, 0)),
            "validation_wfa_survivors": int(wfa_by_family.get(family, 0)),
            "robustness_survivors": int(robust_by_family.get(family, 0)),
            "final_unopened_survivors": int(final_by_family.get(family, 0)),
            "family_reopen_authorized": False,
        })
    catalog = {
        "principal_verdict": "AVAILABLE_CONSTITUENT_INFORMATION_FAMILIES_EXHAUSTED_UNDER_FROZEN_SEARCH_BUDGET",
        "families": rows,
        "family_count": len(rows),
        "all_predeclared_families_attempted": set(r["family"] for r in rows) == set(FAMILY_FEATURES),
        "failed_families_reopened": False,
        "unopened_tail_used_only_after_robustness": bool(final.get("unopened_sessions_scored")),
    }
    catalog["semantic_sha256"] = digest(catalog)
    return catalog


def build_report(stages: Mapping[str, Any]) -> str:
    final = stages["stage9_final_unopened"]
    strategies = stages["stage10_strategy_specs"]
    lines = [
        "# Autonomous Structural Edge Exhaustion V1",
        "",
        "Six predeclared cross-sectional information families were searched under one global testing budget.",
        "Failed families are not reopened or threshold-tuned.",
        "",
        f"- Source authority: `{stages['stage0_source_authority']['principal_verdict']}`",
        f"- Outcome-blind discovery: `{stages['stage3_discovery']['principal_verdict']}`",
        f"- Hypotheses frozen: {stages['stage4_hypotheses']['hypothesis_count']}",
        f"- Structural screen: `{stages['stage6_structural_screen']['principal_verdict']}`",
        f"- Validation/WFA: `{stages['stage7_validation_wfa']['principal_verdict']}`",
        f"- Robustness: `{stages['stage8_robustness']['principal_verdict']}`",
        f"- Final unopened: `{final['principal_verdict']}`",
        f"- Strategy authority: `{strategies['principal_verdict']}`",
        "",
        "## Final authority",
        "",
        f"`{stages['final_authority']['principal_verdict']}`",
        "",
        "A statistical survivor remains blocked from full constituent-certified authority because point-in-time NIFTY membership is not present in this corpus.",
    ]
    return "\n".join(lines) + "\n"
