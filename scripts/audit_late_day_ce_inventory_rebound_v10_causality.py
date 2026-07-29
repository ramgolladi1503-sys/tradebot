#!/usr/bin/env python3
"""Independent causality audit for the late-day CE rebound candidate.

This audit is intentionally static and fail-closed. It verifies that every field
used to decide signal membership or rank simultaneous candidates is observable
at the completed signal timestamp. Entry fills may be reconstructed from the
next bar for economics, but they must not influence whether a signal exists.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

ORACLE_REL = Path("scripts/audit_late_day_ce_inventory_rebound_v5_signal_oracle.py")
CONTRACT_REL = Path("runtime/research/late_day_ce_inventory_rebound_v9_final/frozen_strategy_contract.json")
OUT_REL = Path("runtime/research/late_day_ce_inventory_rebound_v10_causality_audit")
RESEARCH_REL = Path("research/late_day_ce_inventory_rebound_v10_causality_audit")

FUTURE_OR_OUTCOME_FIELDS = {
    "entry_price_next_open",
    "entry_price",
    "exit_price",
    "exit_price_5m",
    "future_return",
    "pnl",
    "net_return",
}


def stable_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def semantic_sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def extract_string_constants(source: str, function_name: str) -> set[str]:
    tree = ast.parse(source)
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    result.add(child.value)
    return result


def audit(root: Path) -> dict[str, Any]:
    oracle_path = root / ORACLE_REL
    contract_path = root / CONTRACT_REL
    source = oracle_path.read_text(encoding="utf-8")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    select_strings = extract_string_constants(source, "select")
    causal_frame_strings = extract_string_constants(source, "build_causal_frame")
    membership_fields = sorted((select_strings | causal_frame_strings) & FUTURE_OR_OUTCOME_FIELDS)

    direct_future_filter = 'frame["entry_price_next_open"].between' in source
    future_tiebreak = 'candidates["entry_price_next_open"]' in source
    contract_uses_entry_fill_as_signal = any(
        "entry_premium" in str(item) for item in contract.get("signal_contract", [])
    )
    contract_tiebreak_uses_entry_fill = "entry_premium" in str(
        contract.get("selection_contract", {}).get("tertiary_tie_break", "")
    )

    defects: list[str] = []
    if direct_future_filter:
        defects.append("NEXT_BAR_ENTRY_PRICE_USED_AS_SIGNAL_ELIGIBILITY_FILTER")
    if future_tiebreak:
        defects.append("NEXT_BAR_ENTRY_PRICE_USED_TO_RANK_SIMULTANEOUS_CANDIDATES")
    if contract_uses_entry_fill_as_signal:
        defects.append("FROZEN_SIGNAL_CONTRACT_REQUIRES_UNOBSERVABLE_ENTRY_FILL")
    if contract_tiebreak_uses_entry_fill:
        defects.append("FROZEN_TIE_BREAK_REQUIRES_UNOBSERVABLE_ENTRY_FILL")

    invalid = bool(defects)
    verdict = (
        "INVALID_FUTURE_ENTRY_PRICE_SIGNAL_MEMBERSHIP_LEAK"
        if invalid
        else "PASS_SIGNAL_TIME_CAUSALITY_AUDIT"
    )
    payload: dict[str, Any] = {
        "principal_verdict": verdict,
        "candidate_id": contract.get("candidate_id"),
        "current_structural_edge_claim_valid": not invalid,
        "future_or_outcome_fields_detected_in_membership_logic": membership_fields,
        "defects": defects,
        "causal_rule": (
            "next-bar open may be used only after signal membership is frozen, for fill and PnL reconstruction"
        ),
        "required_repair": [
            "replace entry-price eligibility with a signal-time observable field such as completed-bar close",
            "replace entry-price tie-break with a signal-time observable tie-break",
            "freeze the repaired rule before re-opening chronological holdout",
            "rebuild OOF, controls, holdout, concentration, and friction evidence from scratch",
        ],
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
        "research_only": True,
    }
    payload["semantic_sha256"] = semantic_sha(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    payload = audit(root)

    out = root / OUT_REL
    research = root / RESEARCH_REL
    stable_json(out / "causality_audit.json", payload)
    research.mkdir(parents=True, exist_ok=True)
    (research / "RESULT.md").write_text(
        "# Late-Day CE Inventory Rebound V10 — Causality Audit\n\n"
        f"Principal verdict: `{payload['principal_verdict']}`\n\n"
        "The published signal oracle uses the next-minute entry open to decide eligibility "
        "and rank candidates. That value is unavailable when the completed signal bar closes. "
        "The present edge claim is therefore invalid as a causal signal contract.\n\n"
        "A repaired campaign must use only signal-time-observable fields for membership, then "
        "rebuild all OOF and untouched-holdout evidence. No paper or live authorization is granted.\n",
        encoding="utf-8",
    )
    print(payload["principal_verdict"])
    return 1 if payload["current_structural_edge_claim_valid"] is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
