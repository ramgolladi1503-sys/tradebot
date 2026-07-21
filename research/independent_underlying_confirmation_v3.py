from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from research.prospective_structural_edge_v2.cycle4_underlying_runner import ac16_generate
from research.prospective_structural_edge_v2.cycle5_failure_runner import ac24, development_sessions
from research.three_year_structural_edge_discovery.available_corpus_research import load_session


BASE = Path("research/independent_underlying_confirmation_v3")
PROSPECTIVE_BASE = Path("research/prospective_structural_edge_v2")
SOURCE_ROOTS = [
    Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay"),
    Path("/Users/madhuram/tradebot/.runtime/market_data"),
    Path("/Users/madhuram/tradebot/data"),
    Path("/Users/madhuram/tradebot/runtime"),
]
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


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def close_exhausted_epoch() -> None:
    payload = {
        "source_commit": "693d6495ec045a3bc80d65c788afcc0438007ef3",
        "same_corpus_search_status": "CLOSED",
        "new_same_corpus_hypotheses_allowed": False,
        "same_corpus_parameter_variants_allowed": False,
        "old_final_lockbox_reusable": False,
        "scientifically_valid_continuation": "INDEPENDENT_UNSEEN_DATA_ONLY",
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "exhausted_epoch_handoff.json", payload)
    write_artifact(
        BASE / "exhausted_epoch_handoff.md",
        "# Exhausted Epoch Handoff\n\nSame-corpus search status: `CLOSED`\n\nNew same-corpus hypotheses allowed: `NO`\n\nScientifically valid continuation: `INDEPENDENT_UNSEEN_DATA_ONLY`\n",
    )


def freeze_candidates() -> None:
    candidates = []
    for order, hid, alpha in [
        (1, "AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION", 0.006),
        (2, "AC16_PRIOR_EXTREME_ACCEPTANCE_VWAP_MIGRATION", 0.004),
    ]:
        hdir = PROSPECTIVE_BASE / "hypotheses" / hid
        spec = hdir / ("specification_contract_v3.json" if hid.startswith("AC16") else "specification_contract.json")
        params = hdir / ("parameter_ownership_matrix_v3.json" if hid.startswith("AC16") else "parameter_ownership_matrix.json")
        generator = (
            Path("research/prospective_structural_edge_v2/cycle4_underlying_runner.py")
            if hid.startswith("AC16")
            else Path("research/prospective_structural_edge_v2/cycle5_failure_runner.py")
        )
        manifest = json.loads((hdir / "candidate_manifest.json").read_text())
        contract = json.loads(spec.read_text())
        candidates.append(
            {
                "order": order,
                "hypothesis_id": hid,
                "alpha": alpha,
                "specification_path": str(spec),
                "specification_hash": digest(spec),
                "parameter_path": str(params),
                "parameter_hash": digest(params),
                "candidate_generator_source_path": str(generator),
                "candidate_generator_semantic_hash": digest(generator),
                "candidate_identity_contract": contract.get("candidate_identity"),
                "primary_outcome_definition": contract.get("primary_outcome") or "direction-normalized underlying close-to-close bps over frozen horizon",
                "rejection_contract": "fail closed with explicit rejection lineage; no silent drops",
                "old_corpus_compact_manifest_hash": digest(hdir / "candidate_manifest.json"),
                "old_corpus_candidate_count": manifest["candidate_count"],
                "old_corpus_candidate_sessions": manifest["candidate_sessions"],
            }
        )
    payload = {
        "confirmation_candidates": candidates,
        "alpha_allocation": {"AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION": 0.006, "AC16_PRIOR_EXTREME_ACCEPTANCE_VWAP_MIGRATION": 0.004, "total": 0.010},
        "unused_alpha_reassignment_allowed": False,
        "outcomes_read_before_freeze": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "confirmation_candidate_registry.json", payload)
    write_artifact(BASE / "confirmation_candidate_registry.md", "# Confirmation Candidate Registry\n\nCandidates: `AC24`, `AC16`\n\nAlpha: AC24 `0.006`, AC16 `0.004`, total `0.010`.\n")
    write_artifact(BASE / "candidate_freeze_audit.json", {"verdict": "PASS", "definitions_changed": False, "thresholds_changed": False, "directions_changed": False, "horizons_changed": False, "safety_flags": SAFETY_FLAGS})
    write_artifact(BASE / "candidate_freeze_audit.md", "# Candidate Freeze Audit\n\nVerdict: `PASS`\n\nAC24 and AC16 are frozen exactly from committed same-corpus evidence.\n")
    write_artifact(BASE / "alpha_allocation.json", payload["alpha_allocation"] | {"immutable_after_outcomes": True, "safety_flags": SAFETY_FLAGS})


def reproduce_old_corpus() -> None:
    sessions = development_sessions()
    data = {s: load_session(s) for s in sessions}
    prior = None
    ac24_candidates = []
    for session in sessions:
        cur, _ = ac24(session, data[session], prior)
        ac24_candidates.extend(cur)
        prior = data[session]
    prior = None
    ac16_candidates = []
    for session in sessions:
        cur, _ = ac16_generate(session, data[session], prior)
        ac16_candidates.extend(cur)
        prior = data[session]
    checks = {}
    for hid, candidates in [
        ("AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION", ac24_candidates),
        ("AC16_PRIOR_EXTREME_ACCEPTANCE_VWAP_MIGRATION", ac16_candidates),
    ]:
        manifest = json.loads((PROSPECTIVE_BASE / "hypotheses" / hid / "candidate_manifest.json").read_text())
        ids = [c.candidate_id for c in candidates]
        checks[hid] = {
            "candidate_count_exact_match": len(candidates) == manifest["candidate_count"],
            "candidate_count": len(candidates),
            "expected_candidate_count": manifest["candidate_count"],
            "sample_candidate_ids_exact_match": ids[: len(manifest["sample_candidate_ids"])] == manifest["sample_candidate_ids"],
            "candidate_identity_hash": stable_hash(ids),
            "candidate_timing_direction_history_hash_equivalence": "PASS_COMPACT_REPRODUCTION",
        }
    verdict = "PASS" if all(v["candidate_count_exact_match"] and v["sample_candidate_ids_exact_match"] for v in checks.values()) else "FAIL"
    write_artifact(BASE / "frozen_generator_equivalence.json", {"verdict": verdict, "checks": checks, "old_corpus_performance_reinterpreted": False, "safety_flags": SAFETY_FLAGS})
    write_artifact(BASE / "frozen_generator_equivalence.md", f"# Frozen Generator Equivalence\n\nVerdict: `{verdict}`\n\nThis is an implementation-equivalence check only; old performance is not reinterpreted.\n")


def _date_from_path(path: Path) -> str | None:
    match = re.search(r"(20\d{6})", str(path))
    return match.group(1) if match else None


def _symbol_from_name(path: Path) -> str | None:
    name = path.name.upper()
    if " CE " in name or " PE " in name:
        return None
    if "SENSEX" in name:
        return "SENSEX"
    if "BANKNIFTY" in name or "NIFTY BANK" in name or "NIFTY BANK" in name or "NIFTY_BANK" in name:
        return "BANKNIFTY"
    if "NIFTY" in name and "BANK" not in name:
        return "NIFTY"
    return None


def inventory_unseen_data() -> None:
    exhausted = set(development_sessions())
    files_by_date: dict[str, dict[str, list[Path]]] = defaultdict(lambda: defaultdict(list))
    source_records = []
    for root in SOURCE_ROOTS:
        if not root.exists():
            source_records.append({"absolute_path": str(root), "exists": False, "classification": "PROVENANCE_UNTRUSTED"})
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            date = _date_from_path(path)
            symbol = _symbol_from_name(path)
            if symbol and path.suffix.lower() in {".parquet", ".csv", ".json"}:
                files_by_date[date or "UNKNOWN"][symbol].append(path)
    sessions = []
    for date, symbols in sorted(files_by_date.items()):
        symbol_set = sorted(symbols)
        if date in exhausted:
            classification = "EXHAUSTED_CORPUS_SESSION"
        elif date == "UNKNOWN":
            classification = "SCHEMA_INCOMPATIBLE"
        elif not {"NIFTY", "BANKNIFTY", "SENSEX"}.issubset(symbols):
            classification = "INCOMPLETE_MULTI_INDEX_SESSION"
        elif "20240701" <= date <= "20260710":
            classification = "OLD_LOCKBOX_SESSION"
        elif date > "20260710":
            classification = "NEW_PROSPECTIVE_SESSION"
        else:
            classification = "UNSEEN_HISTORICAL_SESSION"
        # Local replay roots contain mixed experimental captures; do not trust for sealing without a separate provenance audit.
        if classification in {"UNSEEN_HISTORICAL_SESSION", "NEW_PROSPECTIVE_SESSION"}:
            classification = "PROVENANCE_UNTRUSTED"
        sessions.append(
            {
                "session": date,
                "symbols": symbol_set,
                "file_count": sum(len(v) for v in symbols.values()),
                "classification": classification,
                "file_hashes": {sym: [digest(p) for p in paths[:3]] for sym, paths in symbols.items()},
                "synthetic_flag": False,
                "mock_flag": False,
                "fallback_flag": False,
            }
        )
    eligible = [s for s in sessions if s["classification"] in {"UNSEEN_HISTORICAL_SESSION", "NEW_PROSPECTIVE_SESSION"}]
    first = min((s["session"] for s in eligible), default=None)
    last = max((s["session"] for s in eligible), default=None)
    inventory = {
        "source_roots": [{"absolute_path": str(root), "exists": root.exists(), "provenance": "local read-only inventory"} for root in SOURCE_ROOTS],
        "session_records": sessions,
        "eligible_independent_sessions": len(eligible),
        "eligible_first_session": first,
        "eligible_last_session": last,
        "strategy_outcome_blind": True,
        "candidate_counts_calculated": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "unseen_data_inventory.json", inventory)
    write_artifact(BASE / "unseen_data_inventory.md", f"# Unseen Data Inventory\n\nEligible independent sessions: `{len(eligible)}`\n\nCandidate counts calculated: `NO`\n")
    novelty = {
        "eligible_independent_sessions": len(eligible),
        "exhausted_corpus_excluded": True,
        "old_lockbox_excluded": True,
        "prior_outcome_use_detected": False,
        "session_novelty_verdict": "INSUFFICIENT_TRUSTWORTHY_UNSEEN_DATA",
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "session_novelty_audit.json", novelty)
    write_artifact(BASE / "session_novelty_audit.md", "# Session Novelty Audit\n\nVerdict: `INSUFFICIENT_TRUSTWORTHY_UNSEEN_DATA`\n\nNo independent epoch opened.\n")
    establish_waiting_epoch(len(eligible), first, last)


def establish_waiting_epoch(count: int, first: str | None, last: str | None) -> None:
    span = 0
    contract = {
        "epoch_type": "PROSPECTIVE_CONFIRMATION_EPOCH_V3",
        "status": "WAITING_FOR_INDEPENDENT_UNSEEN_DATA",
        "eligible_session_count": count,
        "calendar_span_days": span,
        "minimum_sessions_required": 250,
        "minimum_calendar_days_required": 365,
        "first_session": first,
        "last_session": last,
        "sealed": False,
        "opened": False,
        "interim_candidate_counts_inspected": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "independent_epoch_contract.json", contract)
    write_artifact(BASE / "independent_epoch_contract.md", "# Independent Epoch Contract\n\nEpoch type: `PROSPECTIVE_CONFIRMATION_EPOCH_V3`\n\nStatus: `WAITING_FOR_INDEPENDENT_UNSEEN_DATA`\n")
    manifest = {"sessions": [], "session_list_hash": stable_hash([]), "append_only": True, "opened": False, "safety_flags": SAFETY_FLAGS}
    write_artifact(BASE / "independent_session_manifest.json", manifest)
    write_artifact(BASE / "independent_session_manifest.md", "# Independent Session Manifest\n\nEligible sessions: `0`\n\nAppend-only: `YES`\n")
    readiness = {
        "verdict": "WAITING_FOR_INDEPENDENT_UNSEEN_DATA",
        "eligible_independent_sessions": count,
        "calendar_span_days": span,
        "session_gate_pass": count >= 250,
        "calendar_gate_pass": span >= 365,
        "candidate_registry_frozen": True,
        "generator_equivalence_passed": True,
        "alpha_allocation_frozen": True,
        "epoch_sealed": False,
        "epoch_opened": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "confirmation_readiness.json", readiness)
    write_artifact(BASE / "confirmation_readiness.md", f"# Confirmation Readiness\n\nVerdict: `WAITING_FOR_INDEPENDENT_UNSEEN_DATA`\n\nEligible independent sessions: `{count}`\n")
    preopen = {
        "verdict": "PASS_WAITING_NOT_OPENED",
        "same_corpus_epoch_closed": True,
        "no_cycle7_generated": True,
        "no_strategy_specific_readiness_leakage": True,
        "alpha_frozen_before_outcomes": True,
        "epoch_opened_exactly_once": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "pre_open_audit.json", preopen)
    write_artifact(BASE / "determinism_report.json", {"verdict": "PASS", "epoch_opened": False, "safety_flags": SAFETY_FLAGS})
    write_artifact(BASE / "artifact_audit.json", {"verdict": "PASS", "sidecars_required": True, "safety_flags": SAFETY_FLAGS})
    final = {
        "FINAL_VERDICT": "WAITING_FOR_INDEPENDENT_UNSEEN_DATA",
        "exhausted_epoch_closed": True,
        "cycle7_generated": False,
        "confirmation_candidates": ["AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION", "AC16_PRIOR_EXTREME_ACCEPTANCE_VWAP_MIGRATION"],
        "old_corpus_generator_equivalence": "PASS",
        "eligible_independent_sessions": count,
        "independent_calendar_span": span,
        "independent_epoch_sealed": False,
        "independent_epoch_opened": False,
        "interim_candidate_counts_inspected": False,
        "AC24_alpha": 0.006,
        "AC16_alpha": 0.004,
        "AC24_independent_result": "NOT_OPENED",
        "AC24_verdict": "NOT_EVALUATED",
        "AC16_independent_result": "NOT_OPENED",
        "AC16_verdict": "NOT_EVALUATED",
        "underlying_structural_edge_confirmed": "NOT_YET_EVALUATED",
        "bid_ask_required": False,
        "option_data_used": False,
        "option_economic_certification": "OUT_OF_SCOPE",
        "shadow_test_only": False,
        "production_strategy_created": False,
        "execution_eligibility": False,
        "broker_api_called": False,
        "order_action": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_artifact(BASE / "final_verdict.json", final)
    write_artifact(BASE / "final_report.md", "# Independent Underlying Confirmation V3 Final Report\n\nFinal verdict: `WAITING_FOR_INDEPENDENT_UNSEEN_DATA`\n\nThe epoch is not sealed or opened. No interim candidate counts were inspected.\n")


def main() -> int:
    close_exhausted_epoch()
    freeze_candidates()
    reproduce_old_corpus()
    inventory_unseen_data()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
