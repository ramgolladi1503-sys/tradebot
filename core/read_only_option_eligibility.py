"""Shared option-surface and eligibility boundary for read-only candidates."""

from __future__ import annotations

from typing import Any, Mapping


def build_option_surface(*, candidate: Mapping[str, Any], option_evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return measured option evidence or a truthful pending state."""
    evidence = dict(option_evidence or {})
    required = ("underlying", "expiry", "strike", "option_type", "bid", "ask", "quote_timestamp")
    missing = [name for name in required if evidence.get(name) in (None, "")]
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "verdict": "PASS" if not missing else "PENDING",
        "missing_fields": missing,
        "evidence": evidence,
        "read_only": True,
        "execution_status": "advisory_only",
    }


def evaluate_candidate_eligibility(*, candidate: Mapping[str, Any], option_surface: Mapping[str, Any],
                                    regime: Mapping[str, Any] | None) -> dict[str, Any]:
    """Apply the common boundary; never relax gates or create execution authority."""
    blockers: list[str] = []
    if option_surface.get("verdict") != "PASS":
        blockers.append("option_surface_not_ready")
    if not isinstance(regime, Mapping) or not regime:
        blockers.append("regime_not_ready")
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "status": "eligible" if not blockers else "advisory_only",
        "blockers": blockers,
        "execution_status": "advisory_only",
        "read_only": True,
        "order_authority": False,
        "broker_write_authority": False,
    }
