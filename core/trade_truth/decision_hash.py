"""Deterministic Live Decision Hashing and Parity Verification.

Invariants:
- Canonical serialization (sorted keys, compact separators, UTF-8, no NaN).
- Hashing strictly input and deterministic output domains.
- Excluding non-deterministic wall-clock timestamps or volatile runtime IDs from decision hash.
- Parity: live_decision_hash == replay_decision_hash for identical frozen inputs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def canonical_json_bytes(data: Any) -> bytes:
    """Produce deterministic byte sequence for hashing."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def compute_deterministic_hash(data: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def extract_decision_domain(
    *,
    market_snapshot: Mapping[str, Any],
    features: Mapping[str, Any],
    strategy_output: Mapping[str, Any],
    regime: str,
    candidate: Mapping[str, Any],
    risk_result: str,
    governance_decision: str,
    final_action: str,
    reason_codes: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Extract strictly reproducible inputs and outputs that form the decision truth."""
    # Filter market state to deterministic price / quote components
    canonical_market = {
        "underlying": str(market_snapshot.get("underlying") or market_snapshot.get("symbol") or ""),
        "ltp": _norm_num(market_snapshot.get("ltp")),
        "bid": _norm_num(market_snapshot.get("bid")),
        "ask": _norm_num(market_snapshot.get("ask")),
        "spread": _norm_num(market_snapshot.get("spread")),
        "data_source": str(market_snapshot.get("data_source") or market_snapshot.get("quote_source") or "UNKNOWN"),
        "feed_state": str(market_snapshot.get("feed_truth_state") or market_snapshot.get("feed_state") or "UNKNOWN"),
    }

    # Deterministic features (round floats to prevent floating-point platform noise)
    canonical_features = {
        k: _norm_num(v) if isinstance(v, (int, float)) else str(v)
        for k, v in sorted(dict(features).items())
        if not k.startswith("_") and k not in {"timestamp", "created_at", "run_id"}
    }

    # Deterministic candidate
    canonical_candidate = {
        "candidate_id": str(candidate.get("candidate_id") or candidate.get("trade_id") or ""),
        "instrument": str(candidate.get("instrument") or candidate.get("symbol") or ""),
        "direction": str(candidate.get("direction") or candidate.get("side") or "").upper(),
        "strike": _norm_num(candidate.get("strike")),
        "expiry": str(candidate.get("expiry") or candidate.get("expiry_date") or ""),
        "entry_price": _norm_num(candidate.get("entry_price") or candidate.get("entry")),
        "target_price": _norm_num(candidate.get("target_price") or candidate.get("target")),
        "stop_loss_price": _norm_num(candidate.get("stop_loss_price") or candidate.get("stop_loss")),
    }

    return {
        "market": canonical_market,
        "features": canonical_features,
        "regime": str(regime).upper(),
        "strategy_output": {
            k: _norm_num(v) if isinstance(v, (int, float)) else str(v)
            for k, v in sorted(dict(strategy_output).items())
            if not k.startswith("_")
        },
        "candidate": canonical_candidate,
        "risk_result": str(risk_result).upper(),
        "governance_decision": str(governance_decision).upper(),
        "final_action": str(final_action).upper(),
        "reason_codes": sorted(list({str(r).strip().upper() for r in reason_codes if str(r).strip()})),
    }


def compute_live_decision_hash(
    *,
    market_snapshot: Mapping[str, Any],
    features: Mapping[str, Any],
    strategy_output: Mapping[str, Any],
    regime: str,
    candidate: Mapping[str, Any],
    risk_result: str,
    governance_decision: str,
    final_action: str,
    reason_codes: list[str] | tuple[str, ...],
) -> str:
    domain = extract_decision_domain(
        market_snapshot=market_snapshot,
        features=features,
        strategy_output=strategy_output,
        regime=regime,
        candidate=candidate,
        risk_result=risk_result,
        governance_decision=governance_decision,
        final_action=final_action,
        reason_codes=reason_codes,
    )
    return compute_deterministic_hash(domain)


def compute_record_integrity_hash(record_dict: Mapping[str, Any]) -> str:
    """Hash the entire record excluding the record_hash itself."""
    shallow = dict(record_dict)
    shallow.pop("record_hash", None)
    return compute_deterministic_hash(shallow)


def _norm_num(val: Any) -> float | int | None:
    if val is None or val == "" or val == "None":
        return None
    try:
        f = float(val)
        if f != f:  # NaN
            return None
        return round(f, 4)
    except Exception:
        return None
