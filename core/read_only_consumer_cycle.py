"""One-cycle downstream consumer coordinator for the canonical observer.

This coordinator is deliberately evidence-first: missing inputs produce
PENDING/BLOCKED states, not synthetic candidates or PASS results.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from core.live_candidate_contract import candidate_from_mapping
from core.live_ranking_contract import rank_advisory_candidates
from core.advisory_queue_contract import append_advisory
from core.read_only_option_eligibility import build_option_surface, evaluate_candidate_eligibility
from core.cas_morning_reversal_advisory import STRATEGY_ID, evaluate
from core import risk_halt


CONSUMERS = (
    "regime", "strategies", "cas_v2", "candidate_pool", "option_surface",
    "eligibility", "ranking", "advisory_queue", "ui", "monitoring", "evidence",
)


def _state(verdict: str, *, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    payload = {"verdict": verdict, **extra}
    if reason:
        payload["reason"] = reason
    return payload


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
            valid_candidates.append(candidate_from_mapping(row).to_dict())
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
    result["consumers"]["candidate_pool"] = _state(
        "PASS" if valid_candidates or isinstance(ranked_pipeline, Mapping) else "PENDING", candidate_count=len(valid_candidates), rejected_count=rejected,
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
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(result, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return result


def _evaluate_cas(*, runtime_outputs: Mapping[str, Any], output_root: Path,
                  session_id: str, source_sha: str, now: datetime) -> dict[str, Any]:
    """Evaluate only the canonical short-horizon causal advisory input."""
    boundary = now.replace(hour=15, minute=14, second=0, microsecond=0)
    raw = runtime_outputs.get("cas_short_horizon_inputs")
    if not isinstance(raw, Mapping) or not raw:
        halt = _risk_halt_evidence()
        (output_root / "cas_readiness_latest.json").write_text(json.dumps({
            "schema_version": 1, "strategy_id": STRATEGY_ID, "session_id": session_id,
            "source_sha": source_sha, "cycle_id": "", "readiness_state": "PENDING",
            "cas_short_horizon_inputs_present": False, "cas_invoked": False,
            "execution_status": "advisory_only", "broker_write_authority": False,
            "order_authority": False, **halt,
        }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return _state("PENDING", reason="short_horizon_inputs_missing", freeze_boundary=boundary.isoformat())
    try:
        decision = evaluate(session_id=session_id, symbol=str(raw["symbol"]),
                            morning_return=float(raw["morning_return"]),
                            observation_timestamp=datetime.fromisoformat(str(raw["observation_timestamp"])),
                            cutoff_timestamp=boundary, received_timestamp=(datetime.fromisoformat(str(raw["received_timestamp"])) if raw.get("received_timestamp") else None),
                            source_sha=source_sha, signal_input_09_15=raw.get("signal_input_09_15"), signal_input_10_00=raw.get("signal_input_10_00"))
    except (KeyError, TypeError, ValueError) as exc:
        # Preserve the fail-closed decision and emit the same readiness
        # contract as a missing input.  A malformed input must not erase the
        # cycle's evidence boundary by aborting before readiness is written.
        halt = _risk_halt_evidence()
        (output_root / "cas_readiness_latest.json").write_text(json.dumps({
            "schema_version": 1, "strategy_id": STRATEGY_ID, "session_id": session_id,
            "source_sha": source_sha, "cycle_id": str(raw.get("cycle_id") or ""),
            "readiness_state": "BLOCKED" if halt["risk_halt"] is True else "PENDING",
            "cas_short_horizon_inputs_present": True, "cas_invoked": False,
            "cas_rejection_reason": str(exc), "execution_status": "advisory_only",
            "broker_write_authority": False, "order_authority": False, **halt,
        }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
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
    (output_root / "cas_readiness_latest.json").write_text(json.dumps({
        "schema_version": 1, "strategy_id": STRATEGY_ID, "session_id": session_id,
        "source_sha": source_sha, "cycle_id": str(raw.get("cycle_id") or ""),
        "readiness_state": "BLOCKED" if halt["risk_halt"] is True else ("NO_SIGNAL" if decision.get("direction") == "NO_SIGNAL" else "READY"),
        "morning_return": raw.get("morning_return"), "signal_direction": decision.get("direction"),
        "primitive_0915_price": raw.get("signal_input_09_15"), "primitive_1000_price": raw.get("signal_input_10_00"),
        "cas_short_horizon_inputs_present": True, "cas_invoked": True,
        "execution_status": "advisory_only", "broker_write_authority": False,
        "order_authority": False, **halt,
    }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return _state("PASS", freeze_boundary=boundary.isoformat(), decision=payload["decision"])
