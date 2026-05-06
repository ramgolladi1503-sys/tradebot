from __future__ import annotations

from datetime import date
from typing import Any


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def classify_contract_resolution(
    *,
    requested_symbol: str,
    requested_expiry: date,
    requested_strike: float,
    requested_option_type: str,
    resolved: dict[str, Any] | None,
    max_expiry_distance_days: int = 7,
    max_strike_distance: float = 50.0,
) -> dict[str, Any]:
    """Classify whether a resolved option contract is safe to execute.

    This pure guard exists so CI can test contract-resolution safety without broker
    instruments, market sessions, or Kite credentials.
    """

    if not isinstance(resolved, dict) or not resolved:
        return {
            "ok": False,
            "classification": "unresolved",
            "blocker": "CONTRACT_UNRESOLVED",
            "reason": "No option contract was resolved for the requested candidate.",
        }

    token = resolved.get("instrument_token")
    if token in (None, "", "None"):
        return {
            "ok": False,
            "classification": "invalid_token",
            "blocker": "CONTRACT_TOKEN_MISSING",
            "reason": "Resolved contract does not include a usable instrument token.",
        }

    resolution_path = str(resolved.get("resolution_path") or "").strip().lower()
    if resolution_path == "exact_contract_match":
        return {
            "ok": True,
            "classification": "exact_contract_match",
            "blocker": None,
            "reason": "Exact contract match resolved.",
        }

    if resolution_path != "safe_nearest_contract_fallback":
        return {
            "ok": False,
            "classification": "unknown_resolution_path",
            "blocker": "CONTRACT_RESOLUTION_PATH_UNKNOWN",
            "reason": "Contract resolution path is not recognized as executable-safe.",
            "resolution_path": resolution_path,
        }

    resolved_expiry = resolved.get("resolved_expiry")
    resolved_strike = resolved.get("resolved_strike")
    if not isinstance(resolved_expiry, date):
        return {
            "ok": False,
            "classification": "fallback_invalid_expiry",
            "blocker": "FALLBACK_EXPIRY_INVALID",
            "reason": "Fallback contract does not include a valid resolved expiry date.",
        }

    try:
        strike_distance = abs(float(resolved_strike) - float(requested_strike))
    except (TypeError, ValueError):
        return {
            "ok": False,
            "classification": "fallback_invalid_strike",
            "blocker": "FALLBACK_STRIKE_INVALID",
            "reason": "Fallback contract does not include a valid resolved strike.",
        }

    expiry_distance_days = abs((resolved_expiry - requested_expiry).days)
    if expiry_distance_days > max(0, int(max_expiry_distance_days)):
        return {
            "ok": False,
            "classification": "fallback_expiry_too_far",
            "blocker": "FALLBACK_EXPIRY_DISTANCE_EXCEEDED",
            "reason": "Fallback expiry distance exceeds safety threshold.",
            "expiry_distance_days": expiry_distance_days,
            "max_expiry_distance_days": max(0, int(max_expiry_distance_days)),
        }

    if strike_distance > max(0.0, float(max_strike_distance)):
        return {
            "ok": False,
            "classification": "fallback_strike_too_far",
            "blocker": "FALLBACK_STRIKE_DISTANCE_EXCEEDED",
            "reason": "Fallback strike distance exceeds safety threshold.",
            "strike_distance": strike_distance,
            "max_strike_distance": max(0.0, float(max_strike_distance)),
        }

    return {
        "ok": True,
        "classification": "safe_nearest_contract_fallback",
        "blocker": None,
        "reason": "Fallback contract is inside configured expiry and strike guardrails.",
        "expiry_distance_days": expiry_distance_days,
        "strike_distance": strike_distance,
        "requested_symbol": normalize_symbol(requested_symbol),
        "requested_option_type": normalize_symbol(requested_option_type),
    }
