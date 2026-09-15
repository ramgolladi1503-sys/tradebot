"""Strict Raw-Capture Level-C Input Contract and Validator.

Enforces:
- Input must contain ONLY:
  session date, trace/decision timestamp, raw market file references + SHA256,
  historical instrument metadata, historical config/model/runtime provenance,
  historical risk/account state if required and available.
- Forbids ANY downstream analytical / decision / outcome ledger fields:
  rolling_15m_return_bps, r15m_bps, bar_index from historical output ledger,
  spot_close from downstream ledger, session_open from downstream ledger,
  features, regime, allowed families, strategy qualification, candidate result,
  ranking result, risk result, governance result, final action, reason codes, decision hash.
- Fails closed immediately if any prohibited downstream key is present.
"""

from __future__ import annotations

from typing import Any, Mapping

PROHIBITED_DOWNSTREAM_KEYS = frozenset({
    "rolling_15m_return_bps",
    "r15m_bps",
    "c1_qualified",
    "c1_reason",
    "c2_qualified",
    "c2_reason",
    "qualified",
    "decision",
    "reason_code",
    "regime",
    "gate_allowed",
    "gate_reasons",
    "candidate_created",
    "lifecycle_stage",
    "pool_status",
    "ranking_status",
    "advisory_status",
    "top_strategy_id",
    "top_score",
    "executable_count",
    "suppressed_count",
    "no_trade_count",
    "raw_candidates",
    "ranked_candidates",
    "live_decision_hash",
    "truth_record_hash",
})


class LevelCContractViolation(ValueError):
    pass


def validate_level_c_input_bundle(bundle: Mapping[str, Any]) -> bool:
    """Validate that input bundle contains zero downstream analytical or decision fields."""
    found_violations = []
    for k in bundle.keys():
        if k in PROHIBITED_DOWNSTREAM_KEYS:
            found_violations.append(k)

    if found_violations:
        raise LevelCContractViolation(
            f"LEVEL_C_INPUT_CONTRACT_VIOLATION: prohibited downstream fields found in replay input: {sorted(found_violations)}"
        )
    return True
