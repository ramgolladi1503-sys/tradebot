from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .contracts import (
    CandidateAutopsy,
    ClaimKind,
    Contributor,
    DecisionOutcomeClass,
    FailureFactor,
    OutcomeKind,
    OutcomeScope,
    RejectionVerdict,
    SessionVerdict,
)

_EXECUTABLE_STAGES = {"approved", "selected", "execute", "executed", "filled"}
_BLOCKED_STAGES = {"blocked", "rejected", "advisory_only", "queue_only"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "on"}


def normalize_outcome(row: Mapping[str, Any]) -> OutcomeKind:
    raw = _upper(row.get("outcome") or row.get("outcome_label") or row.get("exit_reason"))
    if raw in {"TARGET", "TARGET_HIT", "HIT_TARGET", "WIN"}:
        return OutcomeKind.TARGET
    if raw in {"STOP", "STOP_HIT", "SL", "HIT_SL", "LOSS", "TRAIL_STOP"}:
        return OutcomeKind.STOP
    if raw in {"TIME", "TIME_EXIT", "EOD", "SESSION_END"}:
        return OutcomeKind.TIME_EXIT
    if raw in {"MANUAL", "MANUAL_EXIT", "USER_EXIT"}:
        return OutcomeKind.MANUAL_EXIT
    if raw in {"NO_HIT", "NONE", "OPEN"}:
        return OutcomeKind.NO_HIT
    if raw in {"NOT_EXECUTED", "REJECTED", "BLOCKED", "ADVISORY_ONLY"}:
        return OutcomeKind.NOT_EXECUTED
    return OutcomeKind.UNKNOWN


def candidate_key(row: Mapping[str, Any]) -> str:
    return _text(row.get("candidate_id") or row.get("trade_id") or row.get("instrument_id") or row.get("id"))


def group_candidate_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        key = candidate_key(row) or f"UNKNOWN-{index}"
        grouped[key].append(dict(row))
    for values in grouped.values():
        timestamps = [_float(item.get("ts_epoch")) for item in values]
        if values and all(value is not None for value in timestamps):
            values.sort(key=lambda item: float(item.get("ts_epoch")))
    return dict(grouped)


def pipeline_funnel(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        stage = _text(row.get("stage") or row.get("pipeline_stage") or "unknown").lower()
        status = _text(row.get("stage_status") or row.get("status") or "unknown").lower()
        counts[f"stage:{stage}"] += 1
        counts[f"status:{status}"] += 1
        if _bool(row.get("displayable")):
            counts["displayable"] += 1
        if _bool(row.get("rankable")):
            counts["rankable"] += 1
        if _bool(row.get("executable")):
            counts["executable"] += 1
        if _bool(row.get("top_opportunity")):
            counts["top_opportunity"] += 1
    return dict(sorted(counts.items()))


def rejection_breakdown(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        status = _text(row.get("stage_status") or row.get("status")).lower()
        if status not in _BLOCKED_STAGES and not _text(row.get("block_reason") or row.get("block_reason_code")):
            continue
        reason = _text(
            row.get("block_reason_code")
            or row.get("block_reason")
            or row.get("reject_reason_code")
            or row.get("reject_reason")
            or "UNKNOWN_REJECTION"
        )
        counts[reason] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _entry_quality_valid(row: Mapping[str, Any]) -> bool | None:
    if _bool(row.get("fallback_used")) or _bool(row.get("recovered_fallback")) or _bool(row.get("stale_quote")):
        return False
    if row.get("execution_ok") is False or row.get("liquidity_ok") is False:
        return False
    required = [row.get("quote_age_sec"), row.get("option_ltp_age_sec"), row.get("spread_pct")]
    if all(item is None for item in required) and row.get("execution_ok") is None:
        return None
    return True


def classify_decision_outcome(*, decision_valid: bool | None, outcome: OutcomeKind) -> DecisionOutcomeClass:
    if decision_valid is None or outcome in {OutcomeKind.UNKNOWN, OutcomeKind.NO_HIT, OutcomeKind.NOT_EXECUTED}:
        return DecisionOutcomeClass.UNVERIFIABLE
    good_outcome = outcome == OutcomeKind.TARGET
    if decision_valid and good_outcome:
        return DecisionOutcomeClass.GOOD_DECISION_GOOD_OUTCOME
    if decision_valid and not good_outcome:
        return DecisionOutcomeClass.GOOD_DECISION_BAD_OUTCOME
    if not decision_valid and good_outcome:
        return DecisionOutcomeClass.BAD_DECISION_GOOD_OUTCOME
    return DecisionOutcomeClass.BAD_DECISION_BAD_OUTCOME


def classify_rejection(row: Mapping[str, Any], outcome: OutcomeKind) -> RejectionVerdict:
    reason_present = bool(_text(row.get("block_reason") or row.get("block_reason_code") or row.get("reject_reason")))
    invalid_rejection = not reason_present or _bool(row.get("rejection_contract_invalid"))
    if invalid_rejection:
        return RejectionVerdict.INVALID_REJECTION
    if outcome == OutcomeKind.TARGET:
        if row.get("counterfactual_net_positive") is True or row.get("became_executable_later") is True:
            return RejectionVerdict.MISSED_OPPORTUNITY
        if row.get("counterfactual_executable") is False or row.get("spread_cost_exceeded_move") is True:
            return RejectionVerdict.CORRECT_REJECTION
        return RejectionVerdict.UNVERIFIABLE
    if outcome == OutcomeKind.STOP:
        return RejectionVerdict.CORRECT_REJECTION
    if outcome in {OutcomeKind.NO_HIT, OutcomeKind.TIME_EXIT, OutcomeKind.MANUAL_EXIT}:
        return RejectionVerdict.NEUTRAL_REJECTION
    return RejectionVerdict.UNVERIFIABLE


def observed_contributors(entry: Mapping[str, Any], final: Mapping[str, Any], outcome: OutcomeKind) -> tuple[Contributor, ...]:
    contributors: list[Contributor] = []
    if any(_bool(entry.get(key)) for key in ("fallback_used", "recovered_fallback", "stale_quote")):
        contributors.append(Contributor(
            FailureFactor.DATA_QUALITY_FAILURE,
            ClaimKind.DETERMINISTIC_FACT,
            1.0,
            {key: entry.get(key) for key in ("fallback_used", "recovered_fallback", "stale_quote")},
            "The entry record used degraded or stale market-data truth.",
        ))
    breadth_entry = _float(entry.get("breadth") or entry.get("breadth_pct") or entry.get("participation"))
    breadth_final = _float(final.get("breadth") or final.get("breadth_pct") or final.get("participation"))
    if breadth_entry is not None and breadth_final is not None and breadth_final - breadth_entry <= -0.15:
        contributors.append(Contributor(
            FailureFactor.PARTICIPATION_COLLAPSE,
            ClaimKind.LIKELY_CONTRIBUTOR,
            min(0.95, 0.65 + abs(breadth_final - breadth_entry)),
            {"breadth_entry": breadth_entry, "breadth_final": breadth_final},
            "Observed participation contracted materially after entry.",
        ))
    spread_entry = _float(entry.get("spread_pct") or entry.get("spread"))
    spread_final = _float(final.get("spread_pct") or final.get("spread"))
    if spread_entry not in (None, 0.0) and spread_final is not None and spread_final >= spread_entry * 1.5:
        contributors.append(Contributor(
            FailureFactor.LIQUIDITY_DETERIORATION,
            ClaimKind.LIKELY_CONTRIBUTOR,
            0.8,
            {"spread_entry": spread_entry, "spread_final": spread_final},
            "Observed spread widened by at least 50% after entry.",
        ))
    entry_extension = _float(entry.get("entry_extension_atr"))
    if entry_extension is not None and entry_extension >= 1.5:
        contributors.append(Contributor(
            FailureFactor.LATE_ENTRY,
            ClaimKind.STATISTICAL_ASSOCIATION,
            0.7,
            {"entry_extension_atr": entry_extension},
            "Entry was materially extended from the reference setup in ATR units.",
        ))
    regime_entry = _upper(entry.get("regime"))
    regime_final = _upper(final.get("regime"))
    if regime_entry and regime_final and regime_entry != regime_final:
        contributors.append(Contributor(
            FailureFactor.REGIME_TRANSITION,
            ClaimKind.LIKELY_CONTRIBUTOR,
            0.75,
            {"regime_entry": regime_entry, "regime_final": regime_final},
            "Observed market regime changed during the candidate lifecycle.",
        ))
    breakout_held = final.get("breakout_held")
    if outcome == OutcomeKind.STOP and breakout_held is False:
        contributors.append(Contributor(
            FailureFactor.THESIS_INVALIDATED,
            ClaimKind.DETERMINISTIC_FACT,
            0.95,
            {"breakout_held": False, "outcome": outcome.value},
            "The recorded breakout condition failed before the terminal stop outcome.",
        ))
    iv_change = _float(final.get("iv_change"))
    underlying_move = _float(final.get("underlying_move"))
    option_move = _float(final.get("option_move"))
    direction = _upper(entry.get("direction") or entry.get("option_type") or final.get("direction") or final.get("option_type"))
    underlying_favorable = final.get("underlying_favorable")
    if underlying_favorable is None and underlying_move is not None:
        if direction in {"BUY_CALL", "CALL", "CE"}:
            underlying_favorable = underlying_move > 0
        elif direction in {"BUY_PUT", "PUT", "PE"}:
            underlying_favorable = underlying_move < 0
    if iv_change is not None and iv_change < 0 and underlying_favorable is True and option_move is not None and option_move <= 0:
        contributors.append(Contributor(
            FailureFactor.IV_CONTRACTION,
            ClaimKind.LIKELY_CONTRIBUTOR,
            0.7,
            {
                "iv_change": iv_change,
                "underlying_move": underlying_move,
                "underlying_favorable": True,
                "option_move": option_move,
                "direction": direction,
            },
            "Underlying moved favorably for the recorded option direction while option response was non-positive and IV contracted.",
        ))
    slippage = _float(final.get("slippage") or entry.get("slippage"))
    initial_risk = _float(entry.get("initial_risk"))
    if slippage is not None and initial_risk not in (None, 0.0) and slippage / initial_risk >= 0.5:
        contributors.append(Contributor(
            FailureFactor.EXCESSIVE_SLIPPAGE,
            ClaimKind.DETERMINISTIC_FACT,
            0.95,
            {"slippage": slippage, "initial_risk": initial_risk},
            "Recorded slippage consumed at least half of the initial risk budget.",
        ))
    if outcome == OutcomeKind.STOP and not contributors:
        contributors.append(Contributor(
            FailureFactor.NORMAL_VARIANCE,
            ClaimKind.UNVERIFIED_HYPOTHESIS,
            0.35,
            {},
            "No deterministic invalidation factor was available; normal variance remains a hypothesis.",
        ))
    if not contributors:
        contributors.append(Contributor(
            FailureFactor.INSUFFICIENT_EVIDENCE,
            ClaimKind.UNVERIFIED_HYPOTHESIS,
            0.0,
            {},
            "Available lifecycle fields are insufficient for outcome attribution.",
        ))
    return tuple(contributors)


def classify_outcome_scope(
    *, approved: bool, executed: bool, final: Mapping[str, Any], outcome: OutcomeKind
) -> OutcomeScope:
    explicit = _upper(final.get("outcome_scope"))
    if explicit in {item.value for item in OutcomeScope}:
        return OutcomeScope(explicit)
    if outcome == OutcomeKind.UNKNOWN:
        return OutcomeScope.UNRESOLVED
    if _text(final.get("evidence_source")).lower() == "trade_log" or executed:
        return OutcomeScope.ACTUAL
    if approved:
        return OutcomeScope.HYPOTHETICAL
    return OutcomeScope.COUNTERFACTUAL


def build_candidate_autopsy(candidate_id: str, rows: list[Mapping[str, Any]]) -> CandidateAutopsy:
    if not rows:
        raise ValueError("candidate_rows_required")
    materialized = [dict(row) for row in rows]
    approved_rows = [
        row for row in materialized
        if _text(row.get("stage_status") or row.get("status")).lower() in _EXECUTABLE_STAGES
        or _bool(row.get("top_opportunity"))
        or _upper(row.get("permission")) == "EXECUTE"
    ]
    blocked_rows = [
        row for row in materialized
        if _text(row.get("stage_status") or row.get("status")).lower() in _BLOCKED_STAGES
        or bool(_text(row.get("block_reason") or row.get("block_reason_code")))
    ]
    entry = dict(approved_rows[0] if approved_rows else blocked_rows[0] if blocked_rows else materialized[0])
    terminal_rows = [row for row in materialized if normalize_outcome(row) != OutcomeKind.UNKNOWN]
    final = dict(terminal_rows[-1] if terminal_rows else materialized[-1])
    strategy_name = _text(entry.get("strategy_name") or final.get("strategy_name"))
    approved = bool(approved_rows)
    executed = any(
        _text(row.get("stage") or row.get("execution_status")).lower() in {"executed", "filled", "closed"}
        or _text(row.get("stage_status") or row.get("status")).lower() in {"executed", "filled", "closed", "complete", "completed"}
        or (_text(row.get("evidence_source")).lower() == "trade_log" and normalize_outcome(row) != OutcomeKind.UNKNOWN)
        or _bool(row.get("filled"))
        for row in materialized
    )
    outcome = normalize_outcome(final)
    outcome_scope = classify_outcome_scope(approved=approved, executed=executed, final=final, outcome=outcome)
    decision_valid = _entry_quality_valid(entry) if approved else None
    decision_class = classify_decision_outcome(decision_valid=decision_valid, outcome=outcome)
    rejection_verdict = None if approved else classify_rejection({**entry, **final}, outcome)
    evidence_ids = tuple(
        _text(row.get("evidence_id")) for row in materialized if _text(row.get("evidence_id"))
    )
    facts = {
        "row_count": len(rows),
        "entry_stage": _text(entry.get("stage")),
        "final_stage": _text(final.get("stage")),
        "block_reason": _text(entry.get("block_reason") or entry.get("block_reason_code")),
        "mfe": _float(final.get("mfe")),
        "mae": _float(final.get("mae")),
        "pnl": _float(final.get("realized_pnl") or final.get("pnl")),
        "fallback_used": _bool(entry.get("fallback_used")),
        "recovered_fallback": _bool(entry.get("recovered_fallback")),
        "stale_quote": _bool(entry.get("stale_quote")),
        "outcome_scope": outcome_scope.value,
        "evidence_source": _text(final.get("evidence_source")) or "candidate_lineage",
    }
    return CandidateAutopsy(
        candidate_id=candidate_id,
        strategy_name=strategy_name,
        approved=approved,
        executed=executed,
        outcome=outcome,
        outcome_scope=outcome_scope,
        decision_outcome_class=decision_class,
        rejection_verdict=rejection_verdict,
        observed_contributors=observed_contributors(entry, final, outcome),
        facts=facts,
        evidence_ids=evidence_ids,
    )


def _score_band(value: float | None) -> str:
    if value is None:
        return "MISSING"
    if value < 0.25:
        return "0.00-0.24"
    if value < 0.50:
        return "0.25-0.49"
    if value < 0.75:
        return "0.50-0.74"
    return "0.75-1.00"


def score_calibration(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped = group_candidate_rows(rows)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate_rows in grouped.values():
        scored = next((row for row in reversed(candidate_rows) if _float(row.get("final_score") or row.get("score")) is not None), candidate_rows[0])
        terminal = next((row for row in reversed(candidate_rows) if normalize_outcome(row) != OutcomeKind.UNKNOWN), candidate_rows[-1])
        score = _float(scored.get("final_score") or scored.get("score"))
        buckets[_score_band(score)].append({
            "outcome": normalize_outcome(terminal),
            "pnl": _float(terminal.get("realized_pnl") or terminal.get("pnl")),
            "mfe": _float(terminal.get("mfe")),
            "mae": _float(terminal.get("mae")),
        })
    out: dict[str, dict[str, Any]] = {}
    for band, values in sorted(buckets.items()):
        known = [item for item in values if item["outcome"] not in {OutcomeKind.UNKNOWN, OutcomeKind.NO_HIT}]
        targets = sum(item["outcome"] == OutcomeKind.TARGET for item in known)

        def mean(key: str) -> float | None:
            numbers = [item[key] for item in values if item[key] is not None]
            return round(sum(numbers) / len(numbers), 6) if numbers else None

        out[band] = {
            "count": len(values),
            "known_outcome_count": len(known),
            "target_rate": round(targets / len(known), 6) if known else None,
            "mean_pnl": mean("pnl"),
            "mean_mfe": mean("mfe"),
            "mean_mae": mean("mae"),
        }
    return out


def segment_summary(rows: Iterable[Mapping[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    grouped = group_candidate_rows(rows)
    segments: dict[str, list[tuple[OutcomeKind, float | None, bool]]] = defaultdict(list)
    for candidate_rows in grouped.values():
        reference = next((row for row in candidate_rows if _text(row.get(field))), candidate_rows[0])
        terminal = next((row for row in reversed(candidate_rows) if normalize_outcome(row) != OutcomeKind.UNKNOWN), candidate_rows[-1])
        key = _text(reference.get(field)) or "UNKNOWN"
        executed = any(_text(row.get("stage") or row.get("execution_status")).lower() in {"executed", "filled", "closed"} for row in candidate_rows)
        segments[key].append((normalize_outcome(terminal), _float(terminal.get("realized_pnl") or terminal.get("pnl")), executed))
    out: dict[str, dict[str, Any]] = {}
    for key, values in sorted(segments.items()):
        known = [value for value in values if value[0] not in {OutcomeKind.UNKNOWN, OutcomeKind.NO_HIT}]
        pnl_values = [value[1] for value in values if value[1] is not None]
        out[key] = {
            "count": len(values),
            "executed_count": sum(value[2] for value in values),
            "target_rate": round(sum(value[0] == OutcomeKind.TARGET for value in known) / len(known), 6) if known else None,
            "mean_pnl": round(sum(pnl_values) / len(pnl_values), 6) if pnl_values else None,
        }
    return out


def analyze_candidates(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = [dict(row) for row in rows if isinstance(row, Mapping)]
    grouped = group_candidate_rows(materialized)
    autopsies = [build_candidate_autopsy(candidate_id, values) for candidate_id, values in sorted(grouped.items())]
    return {
        "candidate_count": len(autopsies),
        "pipeline_funnel": pipeline_funnel(materialized),
        "rejection_breakdown": rejection_breakdown(materialized),
        "decision_outcome_classes": dict(Counter(item.decision_outcome_class.value for item in autopsies)),
        "rejection_verdicts": dict(Counter(item.rejection_verdict.value for item in autopsies if item.rejection_verdict)),
        "outcomes": dict(Counter(item.outcome.value for item in autopsies)),
        "actual_outcomes": dict(Counter(item.outcome.value for item in autopsies if item.executed)),
        "counterfactual_outcomes": dict(Counter(item.outcome.value for item in autopsies if not item.executed)),
        "score_calibration": score_calibration(materialized),
        "segments": {
            field: segment_summary(materialized, field)
            for field in ("strategy_name", "regime", "option_type", "expiry_context", "time_bucket")
        },
        "autopsies": [item.to_dict() for item in autopsies],
    }


def derive_session_verdict(
    *,
    session_data_valid: bool,
    emitted_untrustworthy: int,
    unexplained_disappearances: int,
    observability_gaps: int,
    materially_missed_candidates: int,
) -> SessionVerdict:
    if not session_data_valid:
        return SessionVerdict.LIVE_SESSION_INVALID
    if emitted_untrustworthy > 0:
        return SessionVerdict.PIPELINE_EMITTED_UNTRUSTWORTHY_CANDIDATES
    if materially_missed_candidates > 0:
        return SessionVerdict.PIPELINE_SUPPRESSED_VALID_CANDIDATES
    if unexplained_disappearances > 0 or observability_gaps > 0:
        return SessionVerdict.PIPELINE_OPERATIONAL_BUT_OBSERVABILITY_INCOMPLETE
    return SessionVerdict.PIPELINE_TRUTHFUL_AND_OPERATIONAL
