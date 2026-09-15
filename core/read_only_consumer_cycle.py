"""One-cycle downstream consumer coordinator for the canonical observer.

This coordinator is deliberately evidence-first: missing inputs produce
PENDING/BLOCKED states, not synthetic candidates or PASS results.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from core.live_candidate_contract import candidate_from_mapping
from core.live_ranking_contract import rank_advisory_candidates
from core.advisory_queue_contract import append_advisory
from core.read_only_option_eligibility import build_option_surface, evaluate_candidate_eligibility
from core.cas_morning_reversal_advisory import STRATEGY_ID, evaluate
from core import risk_halt
from core.storage_bounds_v37 import MAX_ATOMIC_ARTIFACT_BYTES, StorageBoundViolation
import time
from core.trade_truth.decision_hash import compute_deterministic_hash
from core.trade_truth.truth_feed_runtime_hook import CheckpointSpan, TruthFeedRuntimeHook
from core.trade_truth.trade_builder_input_contract import (
    build_canonical_tradebuilder_input,
    parse_iso_or_epoch_seconds,
)
from strategies.trade_builder import TradeBuilder


CONSUMERS = (
    "regime", "strategies", "cas_v2", "candidate_pool", "option_surface",
    "trade_builder", "eligibility", "ranking", "advisory_queue", "ui", "monitoring", "evidence",
)


def _state(verdict: str, *, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    payload = {"verdict": verdict, **extra}
    if reason:
        payload["reason"] = reason
    return payload


def _write_bounded_json(path: Path, payload: Mapping[str, Any]) -> None:
    data = (json.dumps(dict(payload), sort_keys=True, indent=2, default=str) + "\n").encode("utf-8")
    if len(data) > MAX_ATOMIC_ARTIFACT_BYTES:
        raise StorageBoundViolation("ATOMIC_ARTIFACT_BYTES_EXCEEDED")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _risk_halt_evidence() -> dict[str, Any]:
    """Read existing halt state without clearing or changing risk policy."""
    try:
        payload = risk_halt.load_halt()
    except Exception:
        payload = {}
    if not isinstance(payload, Mapping):
        payload = {}
    return {
        "risk_halt": bool(payload.get("halted")) if "halted" in payload else None,
        "risk_halt_reason": payload.get("reason") if payload.get("halted") else None,
        "risk_halt_timestamp": payload.get("timestamp_ist") if payload.get("halted") else None,
    }


def run_consumer_cycle(
    *, runtime_outputs: Mapping[str, Any], output_root: str | Path,
    session_id: str, source_sha: str, cycle_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(output_root)
    context = dict(cycle_context or {})
    cycle_id = str(context.get("cycle_id") or "").strip()
    if not cycle_id:
        raise ValueError("CURRENT_CYCLE_INPUT_MISMATCH")
    ranked_pipeline = runtime_outputs.get("ranked_pipeline_latest")
    if not isinstance(ranked_pipeline, Mapping):
        raise ValueError("CURRENT_CYCLE_RANKED_REPORTS_MISSING")
    reports = ranked_pipeline.get("reports")
    if not isinstance(reports, list) or not reports:
        raise ValueError("CURRENT_CYCLE_RANKED_REPORTS_MISSING")
    expected_sha = str(source_sha).strip()
    provenance = ranked_pipeline.get("cycle_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("CURRENT_CYCLE_PROVENANCE_MISSING")
    expected_session = str(session_id).strip()
    for key, expected in (("cycle_id", cycle_id), ("source_sha", expected_sha), ("session_id", expected_session)):
        if str(provenance.get(key) or "").strip() != expected:
            raise ValueError("CURRENT_CYCLE_PROVENANCE_MISMATCH")
    rows: list[Mapping[str, Any]] = []
    regime: Mapping[str, Any] | None = None
    for report in reports:
        if not isinstance(report, Mapping):
            raise ValueError("CURRENT_CYCLE_RANKED_REPORTS_INVALID")
        candidate_pool = report.get("candidate_pool")
        if not isinstance(candidate_pool, Mapping):
            raise ValueError("CURRENT_CYCLE_CANDIDATE_POOL_MISSING")
        report_regime = candidate_pool.get("regime")
        if isinstance(report_regime, Mapping) and report_regime:
            regime = regime or report_regime
        candidates = candidate_pool.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("CURRENT_CYCLE_STRATEGY_REPORTS_MISSING")
        rows.extend(row for row in candidates if isinstance(row, Mapping))
    if not isinstance(regime, Mapping) or not regime:
        raise ValueError("CURRENT_CYCLE_REGIME_NOT_TERMINAL")

    valid_candidates = []
    rejected = 0
    for row in rows:
        try:
            cand_dict = candidate_from_mapping(row).to_dict()
            # Preserve non-causal candidate fields for downstream audit/UI only.
            for key in ("entry", "ltp", "close", "spot_ltp", "symbol"):
                if key in row and key not in cand_dict:
                    cand_dict[key] = row[key]
            valid_candidates.append(cand_dict)
        except (TypeError, ValueError, KeyError):
            rejected += 1

    result: dict[str, Any] = {
        "schema_version": 1,
        "session_id": session_id,
        "source_sha": source_sha,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_execution_authorized": False,
        "broker_order_calls": 0,
        "consumers": {},
        "cycle_context": context,
        "current_cycle_input": {
            "cycle_id": cycle_id,
            "source_sha": expected_sha,
            "session_id": session_id,
            "report_count": len(reports),
            "strategy_report_count": sum(1 for report in reports if isinstance(report.get("candidate_pool"), Mapping)),
            "ranked_report_count": len(reports),
            "stale_advisory_fallback_used": False,
            "session_date": str(provenance.get("session_date") or ""),
        },
    }
    result["consumers"]["regime"] = _state(
        "PASS" if isinstance(regime, Mapping) and regime else "PENDING",
        reason=None if isinstance(regime, Mapping) and regime else "regime_evidence_missing",
        observed=isinstance(regime, Mapping) and bool(regime),
    )
    result["consumers"]["strategies"] = _state(
        "PASS" if valid_candidates or isinstance(ranked_pipeline, Mapping) else "PENDING",
        reason=None if valid_candidates or isinstance(ranked_pipeline, Mapping) else "no_validated_strategy_candidates",
        candidate_count=len(valid_candidates),
    )
    result["consumers"]["cas_v2"] = _evaluate_cas(
        runtime_outputs=runtime_outputs, output_root=root, session_id=session_id,
        source_sha=source_sha, now=datetime.now(timezone.utc),
    )
    # Emit CANDIDATE_POOL checkpoint via TruthFeedRuntimeHook.
    hook = TruthFeedRuntimeHook(
        session_root=root,
        session_date=str(provenance.get("session_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        session_id=session_id,
    )
    cand_pool_input_hash = compute_deterministic_hash({
        "cycle_id": cycle_id,
        "session_id": session_id,
        "source_sha": source_sha,
        "raw_rows_count": len(rows),
    })
    cand_pool_output_hash = compute_deterministic_hash({
        "valid_candidates": [
            {k: v for k, v in c.items() if k not in {"ts", "run_id"}}
            for c in valid_candidates
        ],
        "rejected_count": rejected,
        "cycle_id": cycle_id,
        "session_id": session_id,
        "source_sha": source_sha,
    })
    cand_pool_status = "PASS" if valid_candidates or isinstance(ranked_pipeline, Mapping) else "PENDING"
    cand_pool_reason = None if cand_pool_status == "PASS" else "no_validated_strategy_candidates"
    candidate_pool_span = hook.record_checkpoint(
        stage_name="CANDIDATE_POOL",
        trace_id=cycle_id,
        parent_span_id=None,
        entered_at=time.time(),
        exited_at=time.time(),
        input_hash=cand_pool_input_hash,
        output_hash=cand_pool_output_hash,
        status=cand_pool_status,
        reason_code=cand_pool_reason or "CANONICAL_RUNTIME_OBSERVED",
        exception=None,
    )

    result["consumers"]["candidate_pool"] = _state(
        cand_pool_status, candidate_count=len(valid_candidates), rejected_count=rejected,
    )
    option_rows = runtime_outputs.get("option_surface")
    option_evidence_by_candidate = option_rows if isinstance(option_rows, Mapping) else {}
    surfaces = [
        build_option_surface(
            candidate=candidate,
            option_evidence=option_evidence_by_candidate.get(candidate["candidate_id"]),
        )
        for candidate in valid_candidates
    ]
    option_ready_count = sum(surface["verdict"] == "PASS" for surface in surfaces)
    result["consumers"]["option_surface"] = _state(
        "PASS" if (not valid_candidates and isinstance(ranked_pipeline, Mapping)) or (valid_candidates and option_ready_count == len(valid_candidates)) else "PENDING",
        reason=None if ((not valid_candidates and isinstance(ranked_pipeline, Mapping)) or (valid_candidates and option_ready_count == len(valid_candidates))) else "current_option_surface_evidence_missing",
        candidate_count=len(valid_candidates), ready_count=option_ready_count,
    )

    # Invoke TradeBuilder in the canonical observer runtime. Candidate rows may
    # choose the symbol only; executable market truth must come from the current
    # canonical market snapshot.
    tb_trades: list[dict[str, Any]] = []
    tb_traces: list[dict[str, Any]] = []
    trade_builder = TradeBuilder()

    market_snapshot = runtime_outputs.get("market_snapshot")
    snapshot_symbols = (
        market_snapshot.get("symbols")
        if isinstance(market_snapshot, Mapping) and isinstance(market_snapshot.get("symbols"), Mapping)
        else {}
    )

    tb_symbols: list[str] = []
    for c in valid_candidates:
        sym = str(c.get("underlying") or c.get("symbol") or "").strip().upper()
        if sym and sym not in tb_symbols:
            tb_symbols.append(sym)

    upstream_span_id = candidate_pool_span.span_id

    tb_t0 = time.time()
    tb_input_payloads: list[dict[str, Any]] = []
    tb_invocation_attempted = False
    tb_runtime_reached = False
    reject_reasons: list[str] = []
    tb_blocked_data = False

    causal_cutoff_str = str(context.get("causal_data_cutoff") or "").strip()
    causal_cutoff_sec = parse_iso_or_epoch_seconds(causal_cutoff_str)

    for sym in tb_symbols:
        sym_snapshot = snapshot_symbols.get(sym) if isinstance(snapshot_symbols, Mapping) else None
        if not isinstance(sym_snapshot, Mapping):
            tb_blocked_data = True
            reject_reasons.append(f"MARKET_SNAPSHOT_MISSING_FOR_SYMBOL:{sym}")
            continue

        try:
            spot_px = float(sym_snapshot.get("spot") or sym_snapshot.get("ltp"))
        except (TypeError, ValueError):
            spot_px = 0.0
        if spot_px <= 0.0:
            tb_blocked_data = True
            reject_reasons.append(f"MARKET_SNAPSHOT_PRICE_INVALID:{sym}")
            continue

        snapshot_regime = sym_snapshot.get("regime") if isinstance(sym_snapshot.get("regime"), Mapping) else None
        if not isinstance(snapshot_regime, Mapping) or not snapshot_regime or not any(
            value is not None for value in snapshot_regime.values()
        ):
            tb_blocked_data = True
            reject_reasons.append(f"MARKET_SNAPSHOT_REGIME_MISSING:{sym}")
            continue

        quote_truth = sym_snapshot.get("quote_truth") if isinstance(sym_snapshot.get("quote_truth"), Mapping) else {}
        event_ts = quote_truth.get("last_tick_ts")
        if event_ts in (None, "", "None"):
            # Backward-compatible authoritative fields are accepted only when
            # explicitly carried on the symbol snapshot. Snapshot generation
            # time and the causal cutoff are never substitutes for market time.
            event_ts = sym_snapshot.get("timestamp") or sym_snapshot.get("quote_timestamp")
        if event_ts in (None, "", "None"):
            tb_blocked_data = True
            reject_reasons.append(f"EVENT_TIMESTAMP_MISSING:{sym}")
            continue

        event_sec = parse_iso_or_epoch_seconds(event_ts)
        if event_sec is None:
            tb_blocked_data = True
            reject_reasons.append(f"EVENT_TIMESTAMP_INVALID:{sym}:{event_ts}")
            continue
        if causal_cutoff_sec is None:
            tb_blocked_data = True
            reject_reasons.append(f"CAUSAL_DATA_CUTOFF_INVALID:{causal_cutoff_str}")
            continue
        if event_sec > causal_cutoff_sec:
            tb_blocked_data = True
            reject_reasons.append(f"FUTURE_EVENT_TIMESTAMP_LEAK:{sym}:{event_ts}>{causal_cutoff_str}")
            continue

        snapshot_feed_truth = {
            "feed_health": dict(sym_snapshot.get("feed_health") or {}),
            "quote_truth": dict(quote_truth),
        }
        try:
            market_data = build_canonical_tradebuilder_input(
                symbol=sym,
                ltp=spot_px,
                regime=snapshot_regime,
                cycle_id=cycle_id,
                session_id=session_id,
                source_sha=source_sha,
                market_open=(market_snapshot.get("market_open") if isinstance(market_snapshot, Mapping) else None),
                execution_mode=context.get("execution_mode") if "execution_mode" in context else None,
                feed_truth=snapshot_feed_truth,
                event_timestamp=event_ts,
            )
        except ValueError as exc:
            tb_blocked_data = True
            reject_reasons.append(str(exc))
            continue

        tb_input_payloads.append(market_data)
        tb_invocation_attempted = True

        trade, trace = trade_builder.build_with_trace(
            market_data,
            quick_mode=False,
            allow_fallbacks=False,
            allow_baseline=False,
        )
        tb_runtime_reached = True
        if trade is not None:
            tb_trades.append({
                "native_trade": trade,
                "symbol": sym,
                "cycle_id": cycle_id,
                "read_only_envelope": True,
            })
        else:
            reason = getattr(trade_builder, "_reject_reason", None) or "REJECTED_BY_TRADE_BUILDER"
            reject_reasons.append(str(reason))

        if trace:
            tb_traces.append(trace)

    tb_t1 = time.time()
    tb_input_hash = compute_deterministic_hash({
        "cycle_id": cycle_id,
        "session_id": session_id,
        "source_sha": source_sha,
        "items": tb_input_payloads,
    })

    if tb_runtime_reached:
        if tb_trades:
            tb_result_status = "TRADE_CONSTRUCTED"
            tb_status = "PASS"
            tb_reason_code = "CANONICAL_RUNTIME_OBSERVED"
        else:
            tb_result_status = "NO_TRADE"
            tb_status = "PASS"
            tb_reason_code = "CANONICAL_RUNTIME_OBSERVED"
    elif tb_blocked_data:
        tb_result_status = "BLOCKED_DATA"
        tb_status = "BLOCKED"
        tb_reason_code = reject_reasons[0] if reject_reasons else "BLOCKED_DATA"
    else:
        tb_result_status = "NOT_REACHED"
        tb_status = "SKIPPED_NOT_APPLICABLE"
        tb_reason_code = "NO_ACTIVE_SYMBOLS_OR_CANDIDATES"

    normalized_traces = []
    for tr in tb_traces:
        tr_dict = tr.to_dict() if hasattr(tr, "to_dict") else dict(tr) if isinstance(tr, Mapping) else vars(tr) if hasattr(tr, "__dict__") else {}
        norm_dict = {k: v for k, v in tr_dict.items() if k not in {"ts", "run_id"}}
        normalized_traces.append(norm_dict)

    tb_output_hash = compute_deterministic_hash({
        "trades": [
            t["native_trade"].to_dict() if hasattr(t["native_trade"], "to_dict")
            else dict(t["native_trade"]) if isinstance(t["native_trade"], Mapping)
            else str(t["native_trade"])
            for t in tb_trades
        ],
        "traces": normalized_traces,
        "result_status": tb_result_status,
        "reject_reasons": reject_reasons,
        "cycle_id": cycle_id,
        "session_id": session_id,
        "source_sha": source_sha,
    })

    hook.record_checkpoint(
        stage_name="TRADE_BUILDER",
        trace_id=cycle_id,
        parent_span_id=upstream_span_id,
        entered_at=tb_t0,
        exited_at=tb_t1,
        input_hash=tb_input_hash,
        output_hash=tb_output_hash,
        status=tb_status,
        reason_code=tb_reason_code,
        exception=None,
    )

    if tb_status == "PASS":
        tradebuilder_consumer_verdict = "PASS"
    elif tb_status == "BLOCKED":
        tradebuilder_consumer_verdict = "BLOCKED"
    else:
        tradebuilder_consumer_verdict = "PENDING"

    result["consumers"]["trade_builder"] = _state(
        tradebuilder_consumer_verdict,
        reason=None if tb_status == "PASS" else tb_reason_code,
        built_trade_count=len(tb_trades),
        trace_count=len(tb_traces),
        result_status=tb_result_status,
        runtime_reached=tb_runtime_reached,
        invocation_attempted=tb_invocation_attempted,
        parent_span_id=upstream_span_id,
        input_hash=tb_input_hash,
        output_hash=tb_output_hash,
    )

    eligibility_rows = [
        evaluate_candidate_eligibility(candidate=candidate, option_surface=surface, regime=regime)
        for candidate, surface in zip(valid_candidates, surfaces)
    ]
    eligible_candidates = [
        candidate for candidate, eligibility in zip(valid_candidates, eligibility_rows)
        if eligibility.get("status") == "eligible"
    ]
    result["consumers"]["eligibility"] = _state(
        "PASS" if eligible_candidates or isinstance(ranked_pipeline, Mapping) else "PENDING",
        reason=None if eligible_candidates or isinstance(ranked_pipeline, Mapping) else "no_candidates_passed_common_eligibility",
        candidate_count=len(valid_candidates), eligible_count=len(eligible_candidates),
    )
    ranked: list[dict[str, Any]] = []
    if eligible_candidates:
        try:
            ranked = rank_advisory_candidates(eligible_candidates)
        except (TypeError, ValueError):
            ranked = []
    result["consumers"]["ranking"] = _state(
        "PASS" if ranked or isinstance(ranked_pipeline, Mapping) else "PENDING", reason=None if ranked or isinstance(ranked_pipeline, Mapping) else "no_rankable_candidates",
        ranked_count=len(ranked),
    )
    advisory_path = root / "advisory_queue.jsonl"
    appended = 0
    for row in ranked:
        try:
            append_advisory(
                advisory_path,
                {**row, "source_sha": source_sha},
                session_id=session_id,
            )
            appended += 1
        except (TypeError, ValueError, OSError):
            continue
    result["consumers"]["advisory_queue"] = _state(
        "PASS" if appended or (not ranked and isinstance(ranked_pipeline, Mapping)) else "PENDING", reason=None if appended or (not ranked and isinstance(ranked_pipeline, Mapping)) else "no_advisory_rows_appended",
        appended_count=appended,
    )

    for name in ("ui", "monitoring", "evidence"):
        result["consumers"][name] = _state("PENDING", reason="consumer_artifact_not_yet_sealed")
    destination = root / "consumer_cycle_latest.json"
    _write_bounded_json(destination, result)
    return result


def _evaluate_cas(*, runtime_outputs: Mapping[str, Any], output_root: Path,
                  session_id: str, source_sha: str, now: datetime) -> dict[str, Any]:
    """Evaluate only the canonical short-horizon causal advisory input."""
    boundary = now.replace(hour=15, minute=14, second=0, microsecond=0)
    raw = runtime_outputs.get("cas_short_horizon_inputs")
    if not isinstance(raw, Mapping) or not raw:
        halt = _risk_halt_evidence()
        _write_bounded_json(output_root / "cas_readiness_latest.json", {
            "schema_version": 1, "strategy_id": STRATEGY_ID, "session_id": session_id,
            "source_sha": source_sha, "cycle_id": "", "readiness_state": "PENDING",
            "cas_short_horizon_inputs_present": False, "cas_invoked": False,
            "execution_status": "advisory_only", "broker_write_authority": False,
            "order_authority": False, **halt,
        })
        return _state("PENDING", reason="short_horizon_inputs_missing", freeze_boundary=boundary.isoformat())
    try:
        decision = evaluate(session_id=session_id, symbol=str(raw["symbol"]),
                            morning_return=float(raw["morning_return"]),
                            observation_timestamp=datetime.fromisoformat(str(raw["observation_timestamp"])),
                            cutoff_timestamp=boundary, received_timestamp=(datetime.fromisoformat(str(raw["received_timestamp"])) if raw.get("received_timestamp") else None),
                            source_sha=source_sha, signal_input_09_15=raw.get("signal_input_09_15"), signal_input_10_00=raw.get("signal_input_10_00"))
    except (KeyError, TypeError, ValueError) as exc:
        halt = _risk_halt_evidence()
        _write_bounded_json(output_root / "cas_readiness_latest.json", {
            "schema_version": 1, "strategy_id": STRATEGY_ID, "session_id": session_id,
            "source_sha": source_sha, "cycle_id": str(raw.get("cycle_id") or ""),
            "readiness_state": "BLOCKED" if halt["risk_halt"] is True else "PENDING",
            "cas_short_horizon_inputs_present": True, "cas_invoked": False,
            "cas_rejection_reason": str(exc), "execution_status": "advisory_only",
            "broker_write_authority": False, "order_authority": False, **halt,
        })
        return _state("PENDING", reason=str(exc))
    destination = output_root / "cas_v2_artifact.json"
    payload = {"schema_version": 1, "cas_spec_id": STRATEGY_ID, "session_id": session_id,
               "source_sha": source_sha, "decision": decision,
               "read_only": True, "execution_status": "advisory_only",
               "broker_write_authority": False, "order_authority": False,
               "paper_authorized": False, "live_execution_authorized": False,
               "broker_order_calls": 0}
    decision = payload["decision"]
    halt = _risk_halt_evidence()
    _write_bounded_json(output_root / "cas_readiness_latest.json", {
        "schema_version": 1, "strategy_id": STRATEGY_ID, "session_id": session_id,
        "source_sha": source_sha, "cycle_id": str(raw.get("cycle_id") or ""),
        "readiness_state": "BLOCKED" if halt["risk_halt"] is True else ("NO_SIGNAL" if decision.get("direction") == "NO_SIGNAL" else "READY"),
        "morning_return": raw.get("morning_return"), "signal_direction": decision.get("direction"),
        "primitive_0915_price": raw.get("signal_input_09_15"), "primitive_1000_price": raw.get("signal_input_10_00"),
        "cas_short_horizon_inputs_present": True, "cas_invoked": True,
        "execution_status": "advisory_only", "broker_write_authority": False,
        "order_authority": False, **halt,
    })
    _write_bounded_json(destination, payload)
    return _state("PASS", freeze_boundary=boundary.isoformat(), decision=payload["decision"])
