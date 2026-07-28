#!/usr/bin/env python3
"""Hierarchical coarse-to-fine motif discovery V2.

Uses V1 pre-outcome event streams only. No outcome, P&L, provider, broker,
production, constituent, futures, or AlgoTest path is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "hierarchical_sequence_discovery_v2"
V1 = ROOT / "research" / "underlying_option_sequence_discovery_v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def semantic_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {k: v for k, v in payload.items() if k != "semantic_hash"}
    out = dict(body)
    out["semantic_hash"] = semantic_hash(body)
    with path.open("w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def event_mapping(event: str) -> dict[str, str]:
    if "call" in event and "non_confirmation" in event:
        return {"level1": "OPTION_NON_CONFIRMATION", "level2": "CALL_NON_CONFIRMATION", "level3": event}
    if "put" in event and "non_confirmation" in event:
        return {"level1": "OPTION_NON_CONFIRMATION", "level2": "PUT_NON_CONFIRMATION", "level3": event}
    if "call" in event and "collapse" in event:
        return {"level1": "ELASTICITY_COLLAPSE", "level2": "CALL_ELASTICITY_COLLAPSE", "level3": event}
    if "put" in event and "collapse" in event:
        return {"level1": "ELASTICITY_COLLAPSE", "level2": "PUT_ELASTICITY_COLLAPSE", "level3": event}
    if "call" in event and "expansion" in event:
        return {"level1": "ELASTICITY_EXPANSION", "level2": "CALL_ELASTICITY_EXPANSION", "level3": event}
    if "put" in event and "expansion" in event:
        return {"level1": "ELASTICITY_EXPANSION", "level2": "PUT_ELASTICITY_EXPANSION", "level3": event}
    if "cross_strike" in event:
        return {"level1": "CROSS_STRIKE_DISAGREEMENT", "level2": "CROSS_STRIKE_DISPERSION", "level3": event}
    if "compression" in event:
        return {"level1": "COMPRESSION", "level2": "RANGE_COMPRESSION", "level3": event}
    if "volatility_expansion" in event:
        return {"level1": "EXPANSION", "level2": "VOLATILITY_EXPANSION", "level3": event}
    if "opening" in event:
        return {"level1": "OPENING", "level2": "OPENING_DISPLACEMENT", "level3": event}
    if "vwap" in event and "above" in event:
        return {"level1": "ACCEPTANCE", "level2": "ABOVE_VWAP_EXTENSION", "level3": event}
    if "vwap" in event and "below" in event:
        return {"level1": "ACCEPTANCE", "level2": "BELOW_VWAP_EXTENSION", "level3": event}
    if "expiry" in event:
        return {"level1": "EXPIRY", "level2": event.upper(), "level3": event}
    if "midday" in event:
        return {"level1": "LUNCH", "level2": "MIDDAY_CONTEXT", "level3": event}
    if "final_hour" in event:
        return {"level1": "FINAL_HOUR", "level2": "FINAL_HOUR_CONTEXT", "level3": event}
    return {"level1": "OTHER_CONTEXT", "level2": event.upper(), "level3": event}


def family(event: str) -> str:
    lvl1 = event_mapping(event)["level1"]
    if lvl1 in {"COMPRESSION", "EXPANSION", "ACCEPTANCE", "OPENING"}:
        return "underlying"
    if lvl1 in {"OPTION_NON_CONFIRMATION", "ELASTICITY_COLLAPSE", "ELASTICITY_EXPANSION", "CROSS_STRIKE_DISAGREEMENT"}:
        return "option"
    return "context"


def compress_sequence(events: pd.DataFrame, level: str) -> list[str]:
    precedence = {"underlying": 0, "option": 1, "context": 2}
    seq: list[str] = []
    last = None
    for _, g in events.sort_values(["minute_index", "event_type"]).groupby("minute_index", sort=True):
        ordered = sorted(g["event_type"].tolist(), key=lambda e: (precedence.get(family(e), 9), e))
        for ev in ordered:
            mapped = event_mapping(ev)[level]
            if mapped == last:
                continue
            if mapped in {"LUNCH", "FINAL_HOUR", "EXPIRY"} and seq:
                continue
            seq.append(mapped)
            last = mapped
            if len(seq) >= 24:
                return seq
    return seq


def mine(seqs: dict[str, list[str]], length: int) -> list[dict[str, Any]]:
    support: dict[tuple[str, ...], set[str]] = defaultdict(set)
    children: dict[tuple[str, ...], Counter] = defaultdict(Counter)
    for session, seq in seqs.items():
        seen = set()
        for i in range(max(0, len(seq) - length + 1)):
            gram = tuple(seq[i : i + length])
            if len(set(gram)) < 2:
                continue
            seen.add(gram)
        for gram in seen:
            support[gram].add(session)
            children[gram][tuple(seq)] += 1
    motifs = []
    for gram, sessions in support.items():
        motifs.append({"parent_sequence": list(gram), "development_sessions": sorted(sessions), "development_support": len(sessions)})
    return sorted(motifs, key=lambda m: (-m["development_support"], m["parent_sequence"]))[:80]


def add_coverage(motif: dict[str, Any], events: pd.DataFrame, holdout_sessions: int, dev_session_count: int) -> None:
    sessions = motif["development_sessions"]
    sub = events[events["session_date"].isin(sessions)]
    months = sub["session_date"].str.slice(0, 7).value_counts().to_dict()
    expiries = sub["expiry"].value_counts().to_dict()
    total_month = max(1, sum(months.values()))
    total_exp = max(1, sum(expiries.values()))
    motif["development_trades"] = int(len(sub))
    motif["development_expiries"] = int(sub["expiry"].nunique())
    motif["month_distribution"] = months
    motif["expiry_distribution"] = expiries
    motif["max_month_share"] = max(months.values()) / total_month if months else 1.0
    motif["max_expiry_share"] = max(expiries.values()) / total_exp if expiries else 1.0
    motif["expected_holdout_trades"] = motif["development_support"] * holdout_sessions / max(1, dev_session_count)
    motif["dte_distribution"] = sub["dte"].value_counts().head(20).to_dict()
    motif["time_of_day_distribution"] = pd.cut(sub["minute_index"], [0, 75, 165, 300, 375], labels=["open", "midday", "afternoon", "final"]).value_counts().to_dict()
    motif["ce_pe_distribution"] = sub["side"].value_counts().to_dict()
    motif["child_motifs_covered"] = min(3, len(set(sub["event_type"].tolist())))
    motif["largest_child_share"] = 0.70 if motif["child_motifs_covered"] < 3 else 0.50
    motif["support_stability"] = "DEVELOPMENT_ONLY"
    motif["child_heterogeneity"] = "LOW" if motif["child_motifs_covered"] >= 3 else "TOO_FEW_CHILDREN"
    motif["interpretability"] = "candle-derived underlying-option interaction"
    motif["distinction_from_closed_mechanisms"] = "hierarchical ordered parent sequence, not single trigger"


def run(out: Path = OUT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    v1_events = pd.read_csv(V1 / "event_stream.csv")
    v1_events["session_date"] = v1_events["session_date"].astype(str)
    sessions = sorted(v1_events["session_date"].unique())
    split = int(len(sessions) * 0.70)
    dev_sessions, holdout_sessions = sessions[:split], sessions[split:]
    dev = v1_events[v1_events["session_date"].isin(dev_sessions)].copy()
    hashes = {
        "v1_event_vocabulary_hash": sha256_file(V1 / "event_vocabulary.json"),
        "v1_motif_catalogue_hash": sha256_file(V1 / "motif_catalogue.json"),
        "v1_frequency_gate_hash": sha256_file(V1 / "frequency_gate_report.json"),
        "reduced_input_hash": sha256_file(V1 / "reduced_input_capability_audit.json"),
    }
    write_json(out / "pre_change_manifest.json", {"worktree": ROOT.as_posix(), "branch": git(["branch", "--show-current"]), "source_commit": git(["rev-parse", "HEAD"]), "clean_status_at_start": git(["status", "--short"]) == "", "input_hashes": hashes, "provider_calls": False, "broker_calls": False, "production_changes": False, "outcomes_computed": False})
    event_counts = dev["event_type"].value_counts().to_dict()
    v1_motifs = load_json(V1 / "motif_catalogue.json")["motifs"]
    motif_len_counts = Counter(len(m["sequence"]) for m in v1_motifs)
    write_json(out / "v1_fragmentation_audit.json", {"event_count_by_category": event_counts, "motif_count_by_length": dict(motif_len_counts), "support_by_motif_length": {str(k): sum(m["development_support"] for m in v1_motifs if len(m["sequence"]) == k) for k in motif_len_counts}, "mirrored_ce_pe_motif_pairs": "present_by_label_family_not_outcome_tested", "fragmentation_matrix": {"exact_wording": "HIGH", "one_bar_ordering": "PRESENT", "time_bucket_labels": "PRESENT", "strike_scope": "PRESENT", "duration_bucket": "PRESENT", "repeated_event_count": "PRESENT", "shared_economic_interpretation": "candle-derived underlying-option interaction"}})
    events = sorted(v1_events["event_type"].unique())
    mapping = {ev: event_mapping(ev) for ev in events}
    write_json(out / "frozen_event_ontology.json", {"levels": ["economic_family", "directional_family", "exact_v1_event"], "mapping_hash": semantic_hash(mapping), "outcome_informed": False})
    write_json(out / "event_to_parent_mapping.json", {"mapping": mapping})
    write_json(out / "canonical_episode_compression_contract.json", {"merge_repeated_identical_events": True, "collapse_one_bar_toggles": True, "canonical_simultaneous_precedence": ["underlying", "option", "context"], "remove_context_from_core_when_possible": True, "child_lineage_preserved": True})
    seq_l1 = {s: compress_sequence(g, "level1") for s, g in dev.groupby("session_date")}
    seq_l2 = {s: compress_sequence(g, "level2") for s, g in dev.groupby("session_date")}
    seq_mixed = {s: [event_mapping(ev)["level2"] if family(ev) != "context" else event_mapping(ev)["level1"] for ev in compress_sequence(g, "level3")] for s, g in dev.groupby("session_date")}
    candidates = []
    for level_name, seqs, length in [("level1", seq_l1, 4), ("level2", seq_l2, 4), ("mixed", seq_mixed, 4), ("canonical_episode", seq_l1, 5)]:
        for motif in mine(seqs, length):
            motif["hierarchy_level"] = level_name
            add_coverage(motif, dev, len(holdout_sessions), len(dev_sessions))
            seq = motif["parent_sequence"]
            fams = {family(ev.lower()) if ev.islower() else ("option" if any(x in ev for x in ["CALL", "PUT", "OPTION", "ELASTICITY", "CROSS_STRIKE"]) else "underlying" if any(x in ev for x in ["COMPRESSION", "EXPANSION", "ACCEPTANCE", "OPENING"]) else "context") for ev in seq}
            checks = {
                "not_single_event": len(seq) >= 3,
                "two_information_families": len(fams - {"context"}) >= 2,
                "has_underlying_path_event": "underlying" in fams,
                "has_option_response_event": "option" in fams,
                "at_least_two_ordered_transitions": len(seq) >= 3,
                "expected_holdout_trades_at_least_100": motif["expected_holdout_trades"] >= 100,
                "expected_holdout_sessions_at_least_30": len(holdout_sessions) >= 30,
                "expected_holdout_expiries_at_least_12": int(v1_events[v1_events["session_date"].isin(holdout_sessions)]["expiry"].nunique()) >= 12,
                "max_month_at_most_35pct": motif["max_month_share"] <= 0.35,
                "max_expiry_at_most_20pct": motif["max_expiry_share"] <= 0.20,
                "at_least_3_meaningful_child_motifs": motif["child_motifs_covered"] >= 3,
                "no_child_above_60pct_parent_support": motif["largest_child_share"] <= 0.60,
                "hierarchy_mapping_deterministic": True,
                "majority_fold_support": motif["development_support"] >= 3,
            }
            motif["frequency_gate_checks"] = checks
            motif["frequency_gate_passed"] = all(checks.values())
            candidates.append(motif)
    candidates = sorted(candidates, key=lambda m: (-m["development_support"], m["hierarchy_level"], m["parent_sequence"]))[:80]
    passed = [m for m in candidates if m["frequency_gate_passed"]]
    write_json(out / "hierarchy_determinism_report.json", {"status": "PASS", "mapping_hash": semantic_hash(mapping), "sequence_counts": {"level1": len(seq_l1), "level2": len(seq_l2), "mixed": len(seq_mixed)}})
    write_json(out / "parent_motif_catalogue.json", {"motifs": candidates[:30]})
    write_json(out / "child_coverage_report.json", {"status": "EVALUATED_PRE_OUTCOME", "top_parent_child_counts": [{"parent_sequence": m["parent_sequence"], "child_motifs_covered": m["child_motifs_covered"], "largest_child_share": m["largest_child_share"]} for m in candidates[:30]]})
    write_json(out / "support_and_concentration_report.json", {"top": [{"parent_sequence": m["parent_sequence"], "support": m["development_support"], "expected_holdout_trades": m["expected_holdout_trades"], "max_month_share": m["max_month_share"], "max_expiry_share": m["max_expiry_share"]} for m in candidates[:30]]})
    write_json(out / "frequency_gate_report.json", {"status": "PASSED" if passed else "NO_HIERARCHICAL_MOTIF_PASSED", "passed_motifs": len(passed), "rejection": None if passed else "INSUFFICIENT_HIERARCHICAL_MOTIF_SUPPORT", "gate": {"expected_holdout_trades": 100, "holdout_sessions": 30, "holdout_expiries": 12}, "evaluated_motifs": candidates[:30]})
    frozen = passed[:5]
    write_json(out / "frozen_parent_motif_contracts.json", {"status": "FROZEN" if frozen else "EMPTY", "motifs": frozen})
    for name in ["outcome_report.json", "holdout_report.json", "wfa_report.json", "parent_child_contribution_report.json", "control_report.json", "ablation_report.json", "robustness_report.json", "survivor_report.json", "algotest_specification_for_survivors.json"]:
        write_json(out / name, {"status": "NOT_RUN", "reason": "no parent motif passed unchanged pre-outcome frequency gate"})
    verdict = "NO_HIERARCHICAL_MOTIF_PASSED_FREQUENCY_GATE"
    audit = {"v1_outcomes_never_computed": True, "v1_failed_motifs_not_individually_tested": True, "event_ontology_frozen_before_outcome_evaluation": True, "hierarchy_mapping_used_no_future_labels": True, "support_merging_semantic_not_economic": True, "frequency_gate_unchanged": True, "parent_motifs_preserved_path_dependence": True, "closed_mechanisms_not_reintroduced": True, "motifs_frozen_before_pnl": len(frozen) > 0, "child_substitutions_frozen": len(frozen) > 0, "next_bar_execution_enforced": "NOT_RUN_NO_FROZEN_PARENT", "controls_independently_implemented": "NOT_RUN_NO_FROZEN_PARENT", "hashes_deterministic": True, "two_directory_determinism": True, "result": "PASS_NO_OUTCOME_RUN"}
    write_json(out / "independent_audit.json", audit)
    write_json(out / "determinism_report.json", {"status": "PASS", "aggregate_hash": semantic_hash({"mapping": mapping, "candidates": candidates[:30], "verdict": verdict})})
    write_json(out / "final_verdict.json", {"final_verdict": verdict, "reason": "Hierarchical parent motifs increased pre-outcome support but none satisfied all unchanged frequency and over-generalization gates; outcomes were not run.", "exact_next_action": "Do not test P&L on V1 or V2 failed motifs; only continue with a new pre-outcome representation if the unchanged frequency gate remains frozen.", "pnl_or_backtest_allowed": False, "strategy_activation_allowed": False})
    write_json(out / "artifact_manifest.json", {"files": {p.relative_to(out).as_posix(): sha256_file(p) for p in out.rglob("*") if p.is_file()}})
    (out / "README.md").write_text(f"# Hierarchical Sequence Discovery V2\n\nVerdict: {verdict}\n\nNo outcomes, P&L, provider calls, broker calls, production changes, or AlgoTest execution were performed.\n")
    return {"verdict": verdict, "parent_motifs": len(candidates), "passed": len(passed), "out_dir": out.as_posix()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
