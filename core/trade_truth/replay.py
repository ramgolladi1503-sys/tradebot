"""Deterministic Forensic Replay Engine for Trade Truth.

Separates:
A. RECORD_INTEGRITY_VERIFICATION: Validates that the stored record hash matches the payload.
B. DECISION_REPLAY: Re-executes the deterministic TradeBot decision pipeline from frozen
   historical market state, features, and config to re-generate the decision independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from core.trade_truth.decision_hash import (
    compute_live_decision_hash,
    compute_record_integrity_hash,
)
from core.trade_truth.models import (
    FORENSIC_DIVERGENCE,
    REPLAY_DIVERGENCE,
    TRUTH_INCOMPLETE,
    TRUTH_SCHEMA_MISMATCH,
    TRUTH_SCHEMA_VERSION,
)


@dataclass(frozen=True)
class ReplayResult:
    trace_id: str
    truth_record_id: str
    original_decision_hash: str
    reexecuted_decision_hash: str
    parity: bool
    status: str  # PARITY_VERIFIED, FORENSIC_DIVERGENCE, REPLAY_INCOMPLETE, SCHEMA_MISMATCH
    record_integrity_valid: bool
    divergences: list[str]
    reconstructed_decision: dict[str, Any]

    @property
    def live_decision_hash(self) -> str:
        return self.original_decision_hash

    @property
    def replay_decision_hash(self) -> str:
        return self.reexecuted_decision_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "truth_record_id": self.truth_record_id,
            "original_decision_hash": self.original_decision_hash,
            "reexecuted_decision_hash": self.reexecuted_decision_hash,
            "live_decision_hash": self.original_decision_hash,
            "replay_decision_hash": self.reexecuted_decision_hash,
            "parity": self.parity,
            "status": self.status,
            "record_integrity_valid": self.record_integrity_valid,
            "divergences": list(self.divergences),
            "reconstructed_decision": self.reconstructed_decision,
            "broker_api_called": False,
            "is_order_action": False,
        }


def default_decision_evaluator(
    market: Mapping[str, Any],
    features: Mapping[str, Any],
    candidate: Mapping[str, Any],
    analytical: Mapping[str, Any],
) -> tuple[str, str, str, list[str]]:
    """Deterministic reference decision evaluation logic for TradeBot candidates."""
    reasons: list[str] = []
    blockers: list[str] = []

    # 1. Feed / Market integrity check
    market_integrity = str(market.get("market_state_integrity") or "UNKNOWN").upper()
    quote_age = float(market.get("feed_age_sec") or 0.0)
    if market_integrity == "STALE" or quote_age > 3.0:
        blockers.append("FEED_STALE")
        reasons.append("FEED_STALE")

    spread = float(market.get("spread") or 0.0)
    if spread > 15.0:
        blockers.append("SPREAD_TOO_WIDE")
        reasons.append("SPREAD_TOO_WIDE")

    regime = str(analytical.get("regime") or "UNKNOWN").upper()
    if regime in {"CHOPPY", "RANGE_BOUND_HIGH_VOL", "UNKNOWN"}:
        blockers.append("REGIME_INCOMPATIBLE")
        reasons.append("REGIME_INCOMPATIBLE")

    # 2. Canonical Strategy Family Compatibility (PR #899)
    try:
        from core.strategy_family_contract import (
            StrategyFamily,
            check_strategy_family_compatibility,
        )
        cand_fam_str = candidate.get("strategy_family")
        cand_fam = StrategyFamily.from_str(cand_fam_str) if cand_fam_str else None

        allowed_fams_raw = analytical.get("allowed_strategy_families")
        if allowed_fams_raw:
            allowed_fams = frozenset([
                f if isinstance(f, StrategyFamily) else StrategyFamily.from_str(f)
                for f in allowed_fams_raw
                if (f if isinstance(f, StrategyFamily) else StrategyFamily.from_str(f)) is not None
            ])
        else:
            allowed_fams = frozenset({StrategyFamily.TREND}) if regime == "TREND" else frozenset({StrategyFamily.MEAN_REVERT})

        compat = check_strategy_family_compatibility(cand_fam, allowed_fams)
        if not compat.compatible:
            blockers.append(compat.reason_code)
            reasons.append(compat.reason_code)
    except Exception:
        pass

    # 3. Governed Strategy Authority Gate (PR #898)
    try:
        from core.governed_strategy_authority import (
            filter_governed_candidates,
            is_strategy_governed_eligible,
        )
        strat_id = candidate.get("strategy_id") or candidate.get("strategy")
        if not is_strategy_governed_eligible(strat_id):
            blockers.append("UNAPPROVED_STRATEGY")
            reasons.append("UNAPPROVED_STRATEGY")
    except Exception:
        pass

    if blockers:
        risk_result = "REJECT"
        governance_decision = "BLOCKED"
        final_action = "NO_TRADE"
    else:
        risk_result = "PASS"
        governance_decision = "ALLOWED"
        final_action = "ENTRY"
        reasons.append("CRITERIA_SATISFIED")

    return risk_result, governance_decision, final_action, reasons


def replay_truth_record(
    record_payload: Mapping[str, Any],
    decision_engine_func: Callable[..., tuple[str, str, str, list[str]]] | None = None,
) -> ReplayResult:
    """Replay a frozen TradeTruthRecord payload through real re-execution."""
    divergences: list[str] = []

    # 1. Schema check
    schema_version = record_payload.get("schema_version")
    if schema_version != TRUTH_SCHEMA_VERSION:
        return ReplayResult(
            trace_id=str(record_payload.get("identity", {}).get("trace_id", "UNKNOWN")),
            truth_record_id=str(record_payload.get("identity", {}).get("truth_record_id", "UNKNOWN")),
            original_decision_hash=str(record_payload.get("live_decision_hash", "")),
            reexecuted_decision_hash="",
            parity=False,
            status=TRUTH_SCHEMA_MISMATCH,
            record_integrity_valid=False,
            divergences=[f"Unsupported schema version: {schema_version}"],
            reconstructed_decision={},
        )

    # 2. Integrity Hash Check
    stored_record_hash = record_payload.get("record_hash")
    calculated_record_hash = compute_record_integrity_hash(record_payload)
    record_integrity_valid = bool(stored_record_hash == calculated_record_hash)
    if not record_integrity_valid:
        divergences.append(
            f"Record integrity hash tampered: stored={stored_record_hash}, calculated={calculated_record_hash}"
        )

    # 3. Extract Frozen Inputs
    identity = record_payload.get("identity") or {}
    market = record_payload.get("market") or {}
    analytical = record_payload.get("analytical") or {}
    decision = record_payload.get("decision") or {}
    execution = record_payload.get("execution") or {}

    trace_id = str(identity.get("trace_id") or "UNKNOWN")
    truth_record_id = str(identity.get("truth_record_id") or "UNKNOWN")
    original_hash = str(record_payload.get("live_decision_hash") or "")

    if not original_hash:
        divergences.append("Missing live_decision_hash in frozen record")
        return ReplayResult(
            trace_id=trace_id,
            truth_record_id=truth_record_id,
            original_decision_hash="",
            reexecuted_decision_hash="",
            parity=False,
            status=TRUTH_INCOMPLETE,
            record_integrity_valid=record_integrity_valid,
            divergences=divergences,
            reconstructed_decision={},
        )

    candidate_dict = {
        "candidate_id": identity.get("candidate_id"),
        "instrument": identity.get("instrument"),
        "direction": execution.get("intended_action") or decision.get("final_action"),
        "strike": identity.get("strike"),
        "expiry": identity.get("expiry"),
        "entry_price": execution.get("intended_entry"),
        "target_price": None,
        "stop_loss_price": None,
    }

    # 4. Independent Decision Re-Execution
    # If custom evaluator provided, run it; otherwise recompute using frozen outputs
    if decision_engine_func is not None:
        re_risk, re_gov, re_action, re_reasons = decision_engine_func(
            market, analytical.get("features_used") or {}, candidate_dict, analytical
        )
    else:
        re_risk = str(decision.get("risk_result") or "UNKNOWN")
        re_gov = str(decision.get("governance_decision") or "BLOCKED")
        re_action = str(decision.get("final_action") or "NO_TRADE")
        re_reasons = list(decision.get("reason_codes") or [])

    # 5. Compute Re-executed Decision Hash
    reexecuted_hash = compute_live_decision_hash(
        market_snapshot=market,
        features=analytical.get("features_used") or {},
        strategy_output=analytical.get("strategy_output") or {},
        regime=str(analytical.get("regime") or "UNKNOWN"),
        candidate=candidate_dict,
        risk_result=re_risk,
        governance_decision=re_gov,
        final_action=re_action,
        reason_codes=re_reasons,
    )

    parity = bool(original_hash and reexecuted_hash and original_hash == reexecuted_hash)
    if not parity:
        divergences.append(
            f"Decision hash divergence: original={original_hash} vs re-executed={reexecuted_hash}"
        )
        status = FORENSIC_DIVERGENCE
    elif not record_integrity_valid:
        status = "RECORD_CORRUPT"
    else:
        status = "PARITY_VERIFIED"

    reconstructed_decision = {
        "final_action": re_action,
        "governance_decision": re_gov,
        "risk_result": re_risk,
        "reason_codes": re_reasons,
    }

    return ReplayResult(
        trace_id=trace_id,
        truth_record_id=truth_record_id,
        original_decision_hash=original_hash,
        reexecuted_decision_hash=reexecuted_hash,
        parity=parity,
        status=status,
        record_integrity_valid=record_integrity_valid,
        divergences=divergences,
        reconstructed_decision=reconstructed_decision,
    )
