"""Builder for canonical TradeTruthRecord instances.

Enforces:
- Exact typing and schema integrity
- Unknown semantics (never fabricate LTP when Ask is missing for BUY; default state is UNKNOWN)
- Timing truth: decision timestamp is None if not provided; never manufactured via time.time()
- Execution truth observation: records authoritative execution events when provided without granting execution authority
- Sequence and chain hashing
"""

from __future__ import annotations

from typing import Any, Mapping

from core.trade_truth.decision_hash import (
    compute_live_decision_hash,
    compute_record_integrity_hash,
)
from core.trade_truth.models import (
    AnalyticalTruth,
    DecisionTruth,
    ExecutionTruth,
    IdentityTruth,
    MarketTruth,
    OutcomeTruth,
    ProvenanceTruth,
    TimingTruth,
    TradeTruthRecord,
    TRUTH_SCHEMA_VERSION,
    TRUTH_SOURCE,
)
from core.trade_truth.provenance import build_provenance_truth, redact_sensitive_dict


def _norm_str(val: Any, default: str = "") -> str:
    return str(val or "").strip() or default


def _norm_float(val: Any) -> float | None:
    if val in (None, "", "None"):
        return None
    try:
        f = float(val)
        return f if f == f else None
    except Exception:
        return None


def _norm_int(val: Any) -> int | None:
    if val in (None, "", "None"):
        return None
    try:
        return int(val)
    except Exception:
        return None


def build_trade_truth_record(
    *,
    trace_id: str,
    session_id: str,
    candidate: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    analytical_context: Mapping[str, Any] | None = None,
    decision_context: Mapping[str, Any] | None = None,
    execution_context: Mapping[str, Any] | None = None,
    outcome_context: Mapping[str, Any] | None = None,
    timing_context: Mapping[str, Any] | None = None,
    provenance_context: Mapping[str, Any] | None = None,
    sequence_number: int = 1,
    previous_record_hash: str = "GENESIS",
    record_type: str = "DECISION_TRUTH",
    parent_truth_record_id: str | None = None,
) -> TradeTruthRecord:
    cand = dict(candidate or {})
    mkt = dict(market_snapshot or {})
    ana = dict(analytical_context or {})
    dec = dict(decision_context or {})
    exc = dict(execution_context or {})
    out = dict(outcome_context or {})
    tim = dict(timing_context or {})
    prov = dict(provenance_context or {})

    # 1. Identity
    truth_record_id = f"truth_{trace_id}_{cand.get('candidate_id', 'cand')}"
    identity = IdentityTruth(
        truth_record_id=truth_record_id,
        trace_id=trace_id,
        session_id=session_id,
        candidate_id=_norm_str(cand.get("candidate_id") or cand.get("trade_id") or "cand_unknown"),
        strategy_id=_norm_str(cand.get("strategy_id") or cand.get("strategy_family") or "UNKNOWN"),
        instrument=_norm_str(cand.get("instrument") or cand.get("symbol") or mkt.get("symbol") or "UNKNOWN"),
        parent_trace_id=_norm_str(cand.get("parent_trace_id")) or None,
        underlying=_norm_str(cand.get("underlying") or mkt.get("underlying") or mkt.get("symbol") or "UNKNOWN"),
        option_type=_norm_str(cand.get("option_type") or cand.get("type")) or None,
        strike=_norm_float(cand.get("strike")),
        expiry=_norm_str(cand.get("expiry") or cand.get("expiry_date")) or None,
        lot_size=_norm_int(cand.get("lot_size") or mkt.get("lot_size")),
    )

    # 2. Timing — Never manufacture decision timestamp via time.time()
    timing = TimingTruth(
        exchange_timestamp_iso=_norm_str(tim.get("exchange_timestamp_iso")) or None,
        receive_timestamp_iso=_norm_str(tim.get("receive_timestamp_iso")) or None,
        normalization_timestamp_iso=_norm_str(tim.get("normalization_timestamp_iso")) or None,
        decision_timestamp_iso=_norm_str(tim.get("decision_timestamp_iso")) or None,
        execution_boundary_timestamp_iso=_norm_str(tim.get("execution_boundary_timestamp_iso")) or None,
        exchange_timestamp_epoch=_norm_float(tim.get("exchange_timestamp_epoch")),
        receive_timestamp_epoch=_norm_float(tim.get("receive_timestamp_epoch")),
        normalization_timestamp_epoch=_norm_float(tim.get("normalization_timestamp_epoch")),
        decision_timestamp_epoch=_norm_float(tim.get("decision_timestamp_epoch")),
        execution_boundary_timestamp_epoch=_norm_float(tim.get("execution_boundary_timestamp_epoch")),
        feed_age_ms=_norm_float(tim.get("feed_age_ms")),
        ingestion_latency_ms=_norm_float(tim.get("ingestion_latency_ms")),
        decision_latency_ms=_norm_float(tim.get("decision_latency_ms")),
    )

    # 3. Market Truth — Default to UNKNOWN unless validated
    depth_raw = mkt.get("depth")
    depth_clipped: tuple[dict[str, Any], ...] = ()
    if isinstance(depth_raw, (list, tuple)):
        depth_clipped = tuple([dict(d) for d in depth_raw[:5] if isinstance(d, dict)])

    market = MarketTruth(
        underlying=_norm_str(mkt.get("underlying") or mkt.get("symbol") or "UNKNOWN"),
        ltp=_norm_float(mkt.get("ltp") or mkt.get("current_ltp")),
        bid=_norm_float(mkt.get("bid") or mkt.get("best_bid")),
        ask=_norm_float(mkt.get("ask") or mkt.get("best_ask")),
        bid_qty=_norm_int(mkt.get("bid_qty") or mkt.get("best_bid_qty")),
        ask_qty=_norm_int(mkt.get("ask_qty") or mkt.get("best_ask_qty")),
        depth=depth_clipped,
        spread=_norm_float(mkt.get("spread")),
        spread_pct=_norm_float(mkt.get("spread_pct")),
        volume=_norm_int(mkt.get("volume")),
        oi=_norm_int(mkt.get("oi")),
        iv=_norm_float(mkt.get("iv")),
        feed_age_sec=_norm_float(mkt.get("quote_age_sec") or mkt.get("feed_age_sec")),
        data_source=_norm_str(mkt.get("data_source") or mkt.get("quote_source") or "UNKNOWN"),
        feed_state=_norm_str(mkt.get("feed_truth_state") or mkt.get("feed_state") or "UNKNOWN"),
        tick_sequence=_norm_int(mkt.get("tick_sequence") or mkt.get("sequence")),
        sequence_gap_status=_norm_str(mkt.get("sequence_gap_status") or "UNKNOWN"),
        market_state_integrity=_norm_str(mkt.get("market_state_integrity") or "UNKNOWN"),
    )

    # 4. Analytical Truth
    clean_features = redact_sensitive_dict(ana.get("features_used") or {})
    analytical = AnalyticalTruth(
        regime=_norm_str(ana.get("regime") or "UNKNOWN"),
        regime_confidence=_norm_float(ana.get("regime_confidence")),
        regime_probabilities=dict(ana.get("regime_probabilities") or {}),
        features_used=clean_features,
        strategy_output=dict(ana.get("strategy_output") or {}),
        model_outputs=dict(ana.get("model_outputs") or {}),
        signal_confidence=_norm_float(ana.get("signal_confidence")),
        volatility_state=_norm_str(ana.get("volatility_state") or "UNKNOWN"),
        liquidity_state=_norm_str(ana.get("liquidity_state") or "UNKNOWN"),
        intraday_memory_refs=tuple([str(x) for x in ana.get("intraday_memory_refs") or []]),
    )

    # 5. Decision Truth
    reason_codes_list = [
        str(r).strip().upper()
        for r in (dec.get("reason_codes") or dec.get("blockers") or [])
        if str(r).strip()
    ]
    ranking_reasons = tuple([str(r).strip() for r in (dec.get("ranking_reasons") or []) if str(r).strip()])
    blockers = tuple([str(b).strip() for b in (dec.get("blockers") or []) if str(b).strip()])
    
    decision = DecisionTruth(
        candidate_generated=bool(dec.get("candidate_generated", True)),
        candidate_score=_norm_float(dec.get("candidate_score") or cand.get("rank_score")),
        rank=_norm_int(dec.get("rank")),
        ranking_reasons=ranking_reasons,
        option_selection_reason=_norm_str(dec.get("option_selection_reason")) or None,
        risk_result=_norm_str(dec.get("risk_result") or "UNKNOWN").upper(),
        blockers=blockers,
        governance_decision=_norm_str(dec.get("governance_decision") or dec.get("permission") or "BLOCKED").upper(),
        final_action=_norm_str(dec.get("final_action") or "NO_TRADE").upper(),
        reason_codes=tuple(reason_codes_list),
    )

    # 6. Provenance Truth
    if "git_sha" in prov:
        provenance = ProvenanceTruth(
            git_sha=str(prov["git_sha"]),
            dirty_tree=bool(prov.get("dirty_tree", False)),
            config_hash=str(prov.get("config_hash", "")),
            model_hash=prov.get("model_hash"),
            model_version=prov.get("model_version"),
            feature_schema_version=int(prov.get("feature_schema_version", 1)),
            strategy_version=str(prov.get("strategy_version", "1.0.0")),
            truth_schema_version=TRUTH_SCHEMA_VERSION,
            runtime_version=str(prov.get("runtime_version", "1.0.0")),
            build_id=prov.get("build_id"),
        )
    else:
        provenance = build_provenance_truth(
            model_hash=prov.get("model_hash"),
            model_version=prov.get("model_version"),
            strategy_version=str(prov.get("strategy_version", "1.0.0")),
            build_id=prov.get("build_id"),
        )

    # 7. Execution Truth — Rigorous Realism
    is_counterfactual = bool(
        decision.final_action == "NO_TRADE"
        or decision.governance_decision == "BLOCKED"
        or exc.get("is_counterfactual", False)
    )
    
    intended_action = _norm_str(exc.get("intended_action") or cand.get("direction") or "NO_TRADE").upper()
    executable_state = _norm_str(exc.get("executable_market_state"))
    theoretical_price = None
    exec_rejection_reason = _norm_str(exc.get("rejection_reason")) or None

    if market.market_state_integrity in {"STALE", "DEGRADED", "CORRUPT"} or "FEED_STALE" in blockers:
        executable_state = "NOT_EXECUTABLE"
        theoretical_price = None
        exec_rejection_reason = "FEED_STALE"
    elif intended_action in {"BUY", "BUY_CALL", "BUY_PUT"}:
        # BUY requires Ask price. If Ask is missing, DO NOT fall back to LTP.
        if market.ask is not None and market.ask > 0:
            theoretical_price = market.ask
            if not executable_state:
                executable_state = "EXECUTABLE" if market.market_state_integrity == "VALID" and not blockers else "NOT_EXECUTABLE"
        else:
            theoretical_price = None
            executable_state = "UNKNOWN"
            exec_rejection_reason = "ASK_UNAVAILABLE"
    else:
        theoretical_price = _norm_float(exc.get("theoretical_executable_price") or cand.get("entry_price") or cand.get("entry"))
        if not executable_state:
            executable_state = "EXECUTABLE" if market.market_state_integrity == "VALID" and not blockers else "NOT_EXECUTABLE"

    execution = ExecutionTruth(
        intended_action=intended_action,
        intended_entry=_norm_float(exc.get("intended_entry") or cand.get("entry_price") or cand.get("entry")),
        executable_market_state=executable_state or "UNKNOWN",
        theoretical_executable_price=theoretical_price,
        execution_type=_norm_str(exc.get("execution_type") or ("SIMULATED" if not is_counterfactual else "OBSERVED_MARKET_EXECUTABILITY")),
        broker_submission_authorized=False,  # Hard locked by safety rules: Truth Layer NEVER submits orders
        actual_broker_submission=bool(exc.get("actual_broker_submission", False)),
        actual_broker_acknowledgment=bool(exc.get("actual_broker_acknowledgment", False)),
        actual_fill=bool(exc.get("actual_fill", False)),
        fill_quantity=_norm_int(exc.get("fill_quantity")) or 0,
        fill_price=_norm_float(exc.get("fill_price")),
        partial_fill_state=_norm_str(exc.get("partial_fill_state") or "NONE"),
        execution_latency_ms=_norm_float(exc.get("execution_latency_ms")),
        observed_slippage=_norm_float(exc.get("observed_slippage")),
        spread_cost=_norm_float(exc.get("spread_cost")),
        estimated_fees=_norm_float(exc.get("estimated_fees")),
        rejection_reason=exec_rejection_reason or (blockers[0] if blockers else None),
        is_counterfactual=is_counterfactual,
    )

    # 8. Outcome Truth
    outcome = OutcomeTruth(
        is_counterfactual=is_counterfactual,
        status=_norm_str(out.get("status") or ("PENDING" if not out.get("horizons") else "OBSERVED")),
        price_basis=_norm_str(out.get("price_basis") or "LTP"),
        horizons=dict(out.get("horizons") or {}),
        mfe_abs=_norm_float(out.get("mfe_abs")),
        mae_abs=_norm_float(out.get("mae_abs")),
        mfe_r=_norm_float(out.get("mfe_r")),
        mae_r=_norm_float(out.get("mae_r")),
        realized_outcome=_norm_str(out.get("realized_outcome")) or None,
        attribution_primary=_norm_str(out.get("attribution_primary") or "UNKNOWN"),
        attribution_secondary=tuple([str(s) for s in out.get("attribution_secondary") or []]),
        attribution_confidence=_norm_float(out.get("attribution_confidence")),
        attribution_evidence=dict(out.get("attribution_evidence") or {}),
    )

    # 9. Deterministic Live Decision Hash
    canonical_cand_for_hash = {
        "candidate_id": identity.candidate_id,
        "instrument": identity.instrument,
        "direction": execution.intended_action or decision.final_action,
        "strike": identity.strike,
        "expiry": identity.expiry,
        "entry_price": execution.intended_entry,
        "target_price": None,
        "stop_loss_price": None,
    }

    from dataclasses import asdict
    live_hash = compute_live_decision_hash(
        market_snapshot=asdict(market),
        features=clean_features,
        strategy_output=analytical.strategy_output,
        regime=analytical.regime,
        candidate=canonical_cand_for_hash,
        risk_result=decision.risk_result,
        governance_decision=decision.governance_decision,
        final_action=decision.final_action,
        reason_codes=decision.reason_codes,
    )

    # 10. Record Integrity Hash
    prelim_record = TradeTruthRecord(
        schema_version=TRUTH_SCHEMA_VERSION,
        source=TRUTH_SOURCE,
        identity=identity,
        timing=timing,
        market=market,
        analytical=analytical,
        decision=decision,
        provenance=provenance,
        execution=execution,
        outcome=outcome,
        live_decision_hash=live_hash,
        record_hash="",
        sequence_number=sequence_number,
        previous_record_hash=previous_record_hash,
        record_type=record_type,
        parent_truth_record_id=parent_truth_record_id,
        read_only=True,
        append_only=True,
        is_order_action=False,
        broker_api_called=False,
        orders_placed=0,
        orders_modified=0,
        orders_cancelled=0,
        integrity_status="VALID",
    )

    record_hash = compute_record_integrity_hash(prelim_record.to_dict())

    return TradeTruthRecord(
        schema_version=TRUTH_SCHEMA_VERSION,
        source=TRUTH_SOURCE,
        identity=identity,
        timing=timing,
        market=market,
        analytical=analytical,
        decision=decision,
        provenance=provenance,
        execution=execution,
        outcome=outcome,
        live_decision_hash=live_hash,
        record_hash=record_hash,
        sequence_number=sequence_number,
        previous_record_hash=previous_record_hash,
        record_type=record_type,
        parent_truth_record_id=parent_truth_record_id,
        read_only=True,
        append_only=True,
        is_order_action=False,
        broker_api_called=False,
        orders_placed=0,
        orders_modified=0,
        orders_cancelled=0,
        integrity_status="VALID",
    )
