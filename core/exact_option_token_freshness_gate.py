"""Read-only exact option token freshness gate for ranking flows.

This module validates explicit expected/observed option-token evidence before
ranking output is allowed. It does not resolve tokens, select contracts,
subscribe instruments, reconnect feeds, mutate candidates, write files, call
brokers, or create order intent.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from core.candidate_ranking import CandidateRankingReport, RANKING_SCHEMA_VERSION, rank_candidates
from core.directional_balance import DirectionalBalanceReport
from core.opportunity_scoring import OpportunityScoreRecord, OpportunityScoreReport

EXACT_OPTION_TOKEN_FRESHNESS_SCHEMA_VERSION = 1
EXACT_OPTION_TOKEN_FRESHNESS_BLOCKER = "exact_option_token_freshness"
TOKEN_MISMATCH_REASON = "option_token_mismatch"
TOKEN_MISSING_REASON = "option_token_missing"
TOKEN_TICK_STALE_REASON = "option_token_tick_stale"
TOKEN_TICK_AGE_MISSING_REASON = "option_token_tick_age_missing"
TOKEN_IDENTITY_MISSING_REASON = "option_token_identity_missing"
_ORDER_ACTION_KEY = "is_" + "order_action"


@dataclass(frozen=True)
class OptionTokenFreshnessRecord:
    """Read-only freshness decision for one option token identity."""

    symbol: str
    expected_token: str | None
    observed_token: str | None
    tick_age_sec: float | None
    max_tick_age_sec: float
    token_ok: bool
    fresh: bool
    reasons: tuple[str, ...]
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "expected_token": self.expected_token,
            "observed_token": self.observed_token,
            "tick_age_sec": self.tick_age_sec,
            "max_tick_age_sec": self.max_tick_age_sec,
            "token_ok": self.token_ok,
            "fresh": self.fresh,
            "reasons": list(self.reasons),
            "context": dict(self.context),
        }


@dataclass(frozen=True)
class ExactOptionTokenFreshnessDecision:
    """Decision explaining whether exact option-token evidence permits ranking."""

    schema_version: int
    read_only: bool
    append: bool
    gate_active: bool
    token_freshness_ok: bool
    reason: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    records: tuple[OptionTokenFreshnessRecord, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "gate_active": self.gate_active,
            "token_freshness_ok": self.token_freshness_ok,
            "reason": self.reason,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "records": [record.to_dict() for record in self.records],
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def classify_exact_option_token_freshness(
    token_evidence: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
    *,
    max_tick_age_sec: float = 3.0,
) -> ExactOptionTokenFreshnessDecision:
    """Classify whether exact option-token evidence is present and fresh."""

    max_age = _non_negative_float(max_tick_age_sec, default=3.0)
    rows = _coerce_rows(token_evidence)
    records = tuple(_classify_record(row, max_tick_age_sec=max_age) for row in rows)
    blockers: list[str] = []
    warnings: list[str] = []

    if not records:
        _append_unique(blockers, EXACT_OPTION_TOKEN_FRESHNESS_BLOCKER)
        _append_unique(blockers, TOKEN_IDENTITY_MISSING_REASON)
    for record in records:
        for reason in record.reasons:
            _append_unique(blockers, f"{record.symbol}:{reason}" if record.symbol else reason)

    token_freshness_ok = not blockers
    gate_active = not token_freshness_ok
    reason = "exact_option_token_freshness_clear" if token_freshness_ok else "exact_option_token_freshness_blocked"
    return ExactOptionTokenFreshnessDecision(
        schema_version=EXACT_OPTION_TOKEN_FRESHNESS_SCHEMA_VERSION,
        read_only=True,
        append=False,
        gate_active=gate_active,
        token_freshness_ok=token_freshness_ok,
        reason=reason,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        records=records,
        metadata={
            "gate": "exact_option_token_freshness_gate_v1",
            "scope": "read_only_no_token_resolution_no_subscription_no_candidate_mutation",
            "record_count": len(records),
            "max_tick_age_sec": max_age,
        },
    )


def apply_exact_option_token_freshness_to_ranking(
    scores: OpportunityScoreReport | tuple[OpportunityScoreRecord, ...] | list[OpportunityScoreRecord],
    token_evidence: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
    directional_balance: DirectionalBalanceReport | None = None,
    *,
    max_tick_age_sec: float = 3.0,
) -> CandidateRankingReport:
    """Return ranking output, or zero-rank output when exact token freshness blocks it."""

    decision = classify_exact_option_token_freshness(token_evidence, max_tick_age_sec=max_tick_age_sec)
    if not decision.gate_active:
        return rank_candidates(scores, directional_balance)

    source_scores = _coerce_score_records(scores)
    source_metadata = getattr(scores, "metadata", {}) if isinstance(scores, OpportunityScoreReport) else {}
    return CandidateRankingReport(
        schema_version=RANKING_SCHEMA_VERSION,
        read_only=True,
        is_order_action=False,
        append=False,
        rank_count=0,
        executable_count=0,
        near_executable_count=0,
        advisory_count=0,
        suppressed_count=0,
        no_trade_count=0,
        ranks=(),
        blockers=decision.blockers,
        warnings=decision.warnings,
        safety_flags=(EXACT_OPTION_TOKEN_FRESHNESS_BLOCKER,),
        directional_imbalance_flags=(),
        metadata={
            "ranker": "candidate_ranking_v1",
            "gate": "exact_option_token_freshness_gate_v1",
            "exact_option_token_freshness_active": True,
            "source_score_count": len(source_scores),
            "source_scorer": source_metadata.get("scorer") if isinstance(source_metadata, dict) else None,
            "exact_option_token_freshness": decision.to_dict(),
        },
    )


def _classify_record(row: Mapping[str, Any], *, max_tick_age_sec: float) -> OptionTokenFreshnessRecord:
    symbol = str(row.get("symbol") or row.get("tradingsymbol") or "").strip().upper()
    expected_token = _normalize_token(row.get("expected_token") or row.get("expected_instrument_token"))
    observed_token = _normalize_token(row.get("observed_token") or row.get("instrument_token") or row.get("token"))
    tick_age = _optional_float(row.get("tick_age_sec") or row.get("last_tick_age_sec") or row.get("option_last_tick_age_sec"))

    reasons: list[str] = []
    if not symbol:
        _append_unique(reasons, TOKEN_IDENTITY_MISSING_REASON)
    if expected_token is None or observed_token is None:
        _append_unique(reasons, TOKEN_MISSING_REASON)
    elif expected_token != observed_token:
        _append_unique(reasons, TOKEN_MISMATCH_REASON)
    if tick_age is None:
        _append_unique(reasons, TOKEN_TICK_AGE_MISSING_REASON)
    elif tick_age > max_tick_age_sec:
        _append_unique(reasons, TOKEN_TICK_STALE_REASON)

    token_ok = expected_token is not None and observed_token is not None and expected_token == observed_token
    fresh = tick_age is not None and tick_age <= max_tick_age_sec
    return OptionTokenFreshnessRecord(
        symbol=symbol,
        expected_token=expected_token,
        observed_token=observed_token,
        tick_age_sec=tick_age,
        max_tick_age_sec=max_tick_age_sec,
        token_ok=token_ok,
        fresh=fresh,
        reasons=tuple(reasons),
        context={
            "expiry": row.get("expiry"),
            "strike": row.get("strike"),
            "option_type": row.get("option_type") or row.get("right"),
        },
    )


def _coerce_rows(token_evidence: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None) -> tuple[Mapping[str, Any], ...]:
    if token_evidence is None:
        return ()
    if isinstance(token_evidence, Mapping):
        return (token_evidence,)
    rows: list[Mapping[str, Any]] = []
    for row in token_evidence:
        if isinstance(row, Mapping):
            rows.append(row)
    return tuple(rows)


def _coerce_score_records(
    scores: OpportunityScoreReport | tuple[OpportunityScoreRecord, ...] | list[OpportunityScoreRecord],
) -> tuple[OpportunityScoreRecord, ...]:
    if isinstance(scores, OpportunityScoreReport):
        return tuple(scores.scores)
    records = tuple(scores or ())
    for record in records:
        if not isinstance(record, OpportunityScoreRecord):
            raise TypeError("exact_option_token_freshness_expected_opportunity_score_record")
    return records


def _normalize_token(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _non_negative_float(value: Any, *, default: float) -> float:
    out = _optional_float(value)
    if out is None:
        return float(default)
    return max(0.0, float(out))


def _append_unique(values: list[str], value: str | None) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


__all__ = [
    "EXACT_OPTION_TOKEN_FRESHNESS_BLOCKER",
    "EXACT_OPTION_TOKEN_FRESHNESS_SCHEMA_VERSION",
    "TOKEN_IDENTITY_MISSING_REASON",
    "TOKEN_MISMATCH_REASON",
    "TOKEN_MISSING_REASON",
    "TOKEN_TICK_AGE_MISSING_REASON",
    "TOKEN_TICK_STALE_REASON",
    "ExactOptionTokenFreshnessDecision",
    "OptionTokenFreshnessRecord",
    "apply_exact_option_token_freshness_to_ranking",
    "classify_exact_option_token_freshness",
]
