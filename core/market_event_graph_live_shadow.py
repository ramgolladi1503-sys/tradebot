"""Read-only Stage A/B observation harness for the frozen market-event graph.

This module classifies captured completed-interval metadata, delegates graph
matching to the merged producer/adapter/strategy, and writes immutable ledgers.
It does not fetch live data, call brokers, place orders, tune thresholds, or
grant execution authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.market_event_graph_breadth_producer import (
    attach_completed_constituent_breadth_snapshots,
    frozen_threshold_metadata,
    initial_market_event_graph_runtime_state,
)
from core.market_event_graph_contract import (
    DATASET_SHA256,
    FROZEN_DISCOVERY_SPEC_SHA256,
    FROZEN_GRAPH,
    FROZEN_THRESHOLDS,
    STRATEGY_ID,
    metadata_has_frozen_contract,
    thresholds_match_frozen,
)
from core.market_event_graph_live_adapter import attach_market_event_graph_history
from core.market_event_graph_live_source import validate_live_captured_metadata_row
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.market_event_graph_reversal import (
    generate_market_event_graph_reversal_candidates,
)

ACCEPTED = "ACCEPTED"
REJECTION_CODES = (
    "MISSING_INDEX_BAR",
    "MISSING_CONSTITUENT_BARS",
    "INSUFFICIENT_COVERAGE",
    "PARTIAL_INTERVAL",
    "TIMESTAMP_MISALIGNMENT",
    "NON_MONOTONIC_TS",
    "NON_MONOTONIC_SOURCE_BAR_END",
    "DUPLICATE_INTERVAL",
    "STALE_CONSTITUENT",
    "MALFORMED_ROW",
    "FROZEN_PROVENANCE_MISMATCH",
    "RUNTIME_STATE_INVALID",
    "SESSION_MISMATCH",
    "NO_GRAPH_EVENT",
    ACCEPTED,
)
GRAPH_STATES = (
    "NO_EVENT",
    "A_MATCHED",
    "A_B_MATCHED",
    "GRAPH_COMPLETED_PENDING_ENTRY",
    "GRAPH_EMITTED",
    "GRAPH_REJECTED",
    "GRAPH_DUPLICATE_SUPPRESSED",
    "SESSION_RESET",
)
ARTIFACT_FILES = (
    "README.md",
    "runtime_path_map.md",
    "constituent_universe_manifest.json",
    "frozen_runtime_contract.json",
    "interval_availability.jsonl",
    "breadth_event_ledger.jsonl",
    "graph_state_ledger.jsonl",
    "candidate_stage_trace.jsonl",
    "quote_observation_ledger.jsonl",
    "hypothetical_outcomes.jsonl",
    "operational_matrix.jsonl",
    "rejection_summary.json",
    "stage_a_report.json",
    "stage_b_report.json",
    "daily_summary.md",
    "replay_determinism_report.json",
    "independent_audit_report.json",
    "reproduction_command.txt",
    "live_observation_command.txt",
    "SHA256SUMS",
)


@dataclass
class CampaignConfig:
    min_intervals: int = 60
    min_valid_ratio: float = 0.90
    min_constituents: int = int(FROZEN_THRESHOLDS["min_constituents"])
    session_date: str | None = None
    symbol: str = "NIFTY"
    observation_mode: str = "REPLAY"


@dataclass
class RuntimeState:
    session_date: str
    producer_state: dict[str, Any]
    last_ts_epoch: float | None = None
    last_source_bar_end_epoch: float | None = None
    accepted_interval_keys: set[tuple[str, float]] = field(default_factory=set)
    graph_labels: list[dict[str, Any]] = field(default_factory=list)
    emitted_triplets: set[str] = field(default_factory=set)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            text = line.strip()
            if not text:
                continue
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{lineno}: expected JSON object")
            rows.append(value)
    return rows


def run_campaign(
    snapshots: Sequence[Mapping[str, Any]],
    output_dir: Path,
    *,
    config: CampaignConfig | None = None,
    universe: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or CampaignConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    _truncate_ledgers(output_dir)
    session_date = cfg.session_date or _first_session_date(snapshots) or "UNKNOWN_SESSION"
    runtime = RuntimeState(
        session_date=session_date,
        producer_state=initial_market_event_graph_runtime_state(session_date),
    )

    interval_rows: list[dict[str, Any]] = []
    graph_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    quote_rows: list[dict[str, Any]] = []
    outcome_rows: list[dict[str, Any]] = []
    breadth_rows: list[dict[str, Any]] = []

    for raw in snapshots:
        metadata = _metadata_from_snapshot(raw, runtime, live_schema_required=cfg.observation_mode == "LIVE")
        interval = classify_interval(metadata, runtime, cfg)
        interval_rows.append(interval)
        _append_jsonl(output_dir / "interval_availability.jsonl", interval)
        if interval["producer_status"] != ACCEPTED:
            graph_row = _graph_row(metadata, interval, "GRAPH_REJECTED", runtime, None, None)
            graph_rows.append(graph_row)
            _append_jsonl(output_dir / "graph_state_ledger.jsonl", graph_row)
            continue

        enriched = attach_completed_constituent_breadth_snapshots(metadata)
        enriched = attach_market_event_graph_history(enriched)
        for event in enriched.get("completed_constituent_breadth_snapshots", []) or []:
            breadth = _breadth_event_row(event, interval)
            breadth_rows.append(breadth)
            _append_jsonl(output_dir / "breadth_event_ledger.jsonl", breadth)
        history = list(enriched.get("market_event_graph_history") or [])
        runtime.graph_labels = history
        state_name = _principal_graph_state(history, metadata, runtime)
        ctx = _strategy_context(enriched, cfg.symbol, metadata["ts_epoch"])
        before = copy.deepcopy(runtime.producer_state)
        candidates = generate_market_event_graph_reversal_candidates(ctx, _regime())
        after = copy.deepcopy(runtime.producer_state)
        candidate = candidates[0] if candidates else None
        if candidate is not None:
            triplet = str(candidate.evidence.get("triplet_id") or "")
            if triplet in runtime.emitted_triplets:
                state_name = "GRAPH_DUPLICATE_SUPPRESSED"
                candidate = None
            else:
                runtime.emitted_triplets.add(triplet)
                state_name = "GRAPH_EMITTED"
                candidate_trace = _candidate_trace(candidate, interval, before, after)
                candidate_rows.extend(candidate_trace)
                for row in candidate_trace:
                    _append_jsonl(output_dir / "candidate_stage_trace.jsonl", row)
                quote = _quote_row(candidate, metadata, interval)
                quote_rows.append(quote)
                _append_jsonl(output_dir / "quote_observation_ledger.jsonl", quote)
                outcome = _hypothetical_outcome_row(candidate, metadata, interval)
                outcome_rows.append(outcome)
                _append_jsonl(output_dir / "hypothetical_outcomes.jsonl", outcome)
        graph_row = _graph_row(metadata, interval, state_name, runtime, before, candidate)
        graph_rows.append(graph_row)
        _append_jsonl(output_dir / "graph_state_ledger.jsonl", graph_row)
        _advance_runtime_watermarks(runtime, interval)

    reports = _write_reports(
        output_dir,
        cfg,
        universe or {},
        interval_rows,
        graph_rows,
        candidate_rows,
        quote_rows,
        outcome_rows,
    )
    _write_static_docs(output_dir, cfg, universe or {}, reports)
    _write_operational_matrix(output_dir, interval_rows, graph_rows, candidate_rows, quote_rows)
    reports["independent_audit"] = independent_audit(output_dir)
    _write_json(output_dir / "independent_audit_report.json", reports["independent_audit"])
    _write_sha256s(output_dir)
    return reports


def classify_interval(
    metadata: Mapping[str, Any],
    runtime: RuntimeState,
    config: CampaignConfig,
) -> dict[str, Any]:
    metadata = _normalize_interval_metadata(metadata)
    detail: list[str] = []
    code = _interval_rejection_code(metadata, runtime, config, detail)
    bars = metadata.get("completed_constituent_bars") if isinstance(metadata, Mapping) else None
    bar = bars[-1] if isinstance(bars, Sequence) and bars and isinstance(bars[-1], Mapping) else {}
    expected = int(metadata.get("expected_constituents") or metadata.get("constituent_count") or 0)
    returns = bar.get("constituent_ret1") if isinstance(bar, Mapping) else None
    received = _count_returns(returns, finite_only=False)
    valid = _count_returns(returns, finite_only=True)
    missing = list(metadata.get("missing_constituents") or [])
    stale = list(metadata.get("stale_constituents") or [])
    duplicate = list(metadata.get("duplicate_constituents") or [])
    misaligned = list(metadata.get("misaligned_constituents") or [])
    late = list(metadata.get("late_constituents") or [])
    events = attach_completed_constituent_breadth_snapshots(metadata).get(
        "completed_constituent_breadth_snapshots", []
    )
    return {
        "session_date": str(metadata.get("session_date") or runtime.session_date),
        "interval_end": metadata.get("interval_end") or metadata.get("ts_epoch"),
        "ts_epoch": metadata.get("ts_epoch"),
        "source_bar_end_epoch": metadata.get("source_bar_end_epoch"),
        "index_bar_available": bool(metadata.get("index_bar_available", metadata.get("index_ret1") is not None)),
        "expected_constituents": expected,
        "received_constituents": received,
        "valid_constituents": valid,
        "coverage_ratio": (valid / expected) if expected else 0.0,
        "missing_constituents": missing,
        "stale_constituents": stale,
        "duplicate_constituents": duplicate,
        "misaligned_constituents": misaligned,
        "late_constituents": late,
        "producer_status": code,
        "producer_rejection_reason": code if code != ACCEPTED else "",
        "producer_rejection_detail": ";".join(detail),
        "adapter_status": "READY" if events else ("NO_GRAPH_EVENT" if code == ACCEPTED else code),
        "adapter_rejection_reason": "" if events else ("NO_GRAPH_EVENT" if code == ACCEPTED else code),
        "event_count": len(events),
        "event_labels": [event.get("event_label") for event in events],
        "metadata_injected": _metadata_injected(metadata),
        "runtime_state_valid": _runtime_state_valid(metadata.get("market_event_graph_runtime_state"), runtime.session_date),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def independent_audit(output_dir: Path) -> dict[str, Any]:
    intervals = _read_jsonl(output_dir / "interval_availability.jsonl")
    graph = _read_jsonl(output_dir / "graph_state_ledger.jsonl")
    candidates = _read_jsonl(output_dir / "candidate_stage_trace.jsonl")
    quotes = _read_jsonl(output_dir / "quote_observation_ledger.jsonl")
    failures: list[str] = []
    accepted = [row for row in intervals if row.get("producer_status") == ACCEPTED]
    _audit_monotonic(accepted, "ts_epoch", failures)
    _audit_monotonic(accepted, "source_bar_end_epoch", failures)
    if any(row.get("is_order_action") for row in intervals + graph + candidates):
        failures.append("order_action_seen")
    if any(row.get("broker_api_called") for row in intervals + graph + candidates):
        failures.append("broker_call_seen")
    if any(row.get("allowed_for_live_execution") for row in intervals + graph + candidates):
        failures.append("live_execution_authority_seen")
    if any(row.get("fallback_used") and row.get("executable") for row in quotes):
        failures.append("fallback_quote_marked_executable")
    triplets = [row.get("triplet_id") for row in graph if row.get("graph_state") == "GRAPH_EMITTED"]
    if len([t for t in triplets if t]) != len(set(t for t in triplets if t)):
        failures.append("duplicate_emitted_triplet")
    ledger_hashes = {
        path.name: _sha256(path)
        for path in sorted(output_dir.glob("*.jsonl"))
        if path.name != "SHA256SUMS"
    }
    verdict = (
        "FAIL_STAGE_A_B_INDEPENDENT_AUDIT"
        if failures
        else ("PASS_STAGE_A_B_INDEPENDENT_AUDIT" if accepted else "INSUFFICIENT_STAGE_A_B_EVIDENCE")
    )
    return {
        "verdict": verdict,
        "failures": failures,
        "interval_count": len(intervals),
        "accepted_interval_count": len(accepted),
        "graph_rows": len(graph),
        "candidate_stage_rows": len(candidates),
        "ledger_hashes": ledger_hashes,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _interval_rejection_code(
    metadata: Mapping[str, Any],
    runtime: RuntimeState,
    config: CampaignConfig,
    detail: list[str],
) -> str:
    if not metadata_has_frozen_contract(metadata) or not thresholds_match_frozen(metadata.get("market_event_graph_thresholds") or {}):
        detail.append("frozen provenance or thresholds missing/mismatched")
        return "FROZEN_PROVENANCE_MISMATCH"
    if not _runtime_state_valid(metadata.get("market_event_graph_runtime_state"), runtime.session_date):
        detail.append("runtime state missing or session/spec mismatch")
        return "RUNTIME_STATE_INVALID"
    bars = metadata.get("completed_constituent_bars")
    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)) or not bars:
        detail.append("completed_constituent_bars missing")
        return "MISSING_CONSTITUENT_BARS"
    bar = bars[-1]
    if not isinstance(bar, Mapping):
        detail.append("latest completed bar malformed")
        return "MALFORMED_ROW"
    if bar.get("completed") is False or bar.get("is_completed") is False:
        detail.append("latest interval marked partial")
        return "PARTIAL_INTERVAL"
    if metadata.get("index_bar_available") is False or bar.get("index_ret1") is None:
        detail.append("index completed bar unavailable")
        return "MISSING_INDEX_BAR"
    try:
        ts = float(bar["ts_epoch"])
        source_end = float(bar.get("source_bar_end_epoch", ts))
        index_end = float(metadata.get("index_source_bar_end_epoch", source_end))
    except (KeyError, TypeError, ValueError):
        detail.append("timestamp fields malformed")
        return "MALFORMED_ROW"
    if not all(math.isfinite(value) for value in (ts, source_end, index_end)):
        detail.append("timestamp fields non-finite")
        return "MALFORMED_ROW"
    if source_end > ts:
        detail.append("source_bar_end_epoch is in the future")
        return "TIMESTAMP_MISALIGNMENT"
    if source_end != index_end:
        detail.append("index and constituent interval ends differ")
        return "TIMESTAMP_MISALIGNMENT"
    if runtime.last_ts_epoch is not None and ts <= runtime.last_ts_epoch:
        detail.append("ts_epoch did not increase")
        return "NON_MONOTONIC_TS"
    if runtime.last_source_bar_end_epoch is not None and source_end <= runtime.last_source_bar_end_epoch:
        detail.append("source_bar_end_epoch did not increase")
        return "NON_MONOTONIC_SOURCE_BAR_END"
    key = (str(bar.get("session_date") or metadata.get("session_date") or ""), source_end)
    if key in runtime.accepted_interval_keys:
        detail.append("duplicate accepted interval key")
        return "DUPLICATE_INTERVAL"
    if str(bar.get("session_date") or "") != runtime.session_date:
        detail.append("bar session differs from runtime session")
        return "SESSION_MISMATCH"
    returns = bar.get("constituent_ret1")
    valid = _count_returns(returns, finite_only=True)
    if valid < config.min_constituents:
        detail.append(f"valid constituents {valid} below minimum {config.min_constituents}")
        return "INSUFFICIENT_COVERAGE"
    if metadata.get("stale_constituents"):
        detail.append("stale constituents present")
        return "STALE_CONSTITUENT"
    return ACCEPTED


def _metadata_from_snapshot(
    raw: Mapping[str, Any],
    runtime: RuntimeState,
    *,
    live_schema_required: bool = False,
) -> dict[str, Any]:
    metadata = dict(raw.get("metadata") or raw)
    if live_schema_required:
        validation = validate_live_captured_metadata_row(metadata)
        if not validation.accepted:
            raise ValueError(
                "live captured metadata schema validation failed: "
                f"{validation.reason}:{','.join(validation.details)}"
            )
    metadata = _normalize_interval_metadata(metadata)
    metadata.setdefault("market_event_graph_runtime_state", runtime.producer_state)
    metadata.setdefault("index_bar_available", metadata.get("index_ret1") is not None)
    metadata.setdefault("expected_constituents", metadata.get("constituent_count") or 50)
    for key, value in frozen_threshold_metadata().items():
        metadata.setdefault(key, value)
    return metadata


def _normalize_interval_metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(source)
    latest = _latest_bar(metadata)
    if latest:
        metadata["ts_epoch"] = latest.get("ts_epoch")
        metadata["source_bar_end_epoch"] = latest.get("source_bar_end_epoch", latest.get("ts_epoch"))
        metadata["session_date"] = latest.get("session_date", metadata.get("session_date"))
        metadata.setdefault("index_ret1", latest.get("index_ret1"))
        metadata.setdefault("index_source_bar_end_epoch", latest.get("source_bar_end_epoch", latest.get("ts_epoch")))
    return metadata


def _latest_bar(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    bars = metadata.get("completed_constituent_bars")
    if isinstance(bars, Sequence) and not isinstance(bars, (str, bytes)) and bars:
        latest = bars[-1]
        if isinstance(latest, Mapping):
            return latest
    return {}


def _strategy_context(metadata: dict[str, Any], symbol: str, ts_epoch: Any) -> StrategyContext:
    return StrategyContext(
        symbol=symbol,
        ts_epoch=float(ts_epoch),
        spot_ltp=_optional_float(metadata.get("nifty_level")),
        option_ce_ltp=_optional_float(metadata.get("ltp") or metadata.get("option_ce_ltp")),
        ce_spread_pct=_optional_float(metadata.get("spread_pct") or metadata.get("ce_spread_pct")),
        ce_depth=_optional_float(metadata.get("depth") or metadata.get("ce_depth")),
        quote_source=str(metadata.get("quote_source") or "captured_runtime"),
        fallback_used=bool(metadata.get("fallback_used", False)),
        option_ltp_age_sec=_optional_float(metadata.get("quote_age")),
        metadata=metadata,
    )


def _regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.6,
            "TREND_DOWN": 0.2,
            "VOLATILITY_EXPANSION": 0.4,
            "COMPRESSION": 0.2,
            "TRAP_RISK": 0.1,
            "CHOP": 0.1,
        },
    )


def _principal_graph_state(
    history: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    runtime: RuntimeState,
) -> str:
    labels = [str(row.get("event_label") or "") for row in history[-3:]]
    if not labels:
        return "NO_EVENT"
    if labels[-1:] == [FROZEN_GRAPH[0]]:
        return "A_MATCHED"
    if labels[-2:] == list(FROZEN_GRAPH[:2]):
        return "A_B_MATCHED"
    if labels[-3:] == list(FROZEN_GRAPH):
        entry_ts = _optional_float(history[-1].get("market_event_graph_entry_bar_ts_epoch"))
        now_ts = _optional_float(metadata.get("ts_epoch"))
        triplet = str(history[-1].get("market_event_graph_triplet_id") or "")
        if triplet and triplet in runtime.emitted_triplets:
            return "GRAPH_DUPLICATE_SUPPRESSED"
        if entry_ts is not None and now_ts is not None and entry_ts > now_ts:
            return "GRAPH_COMPLETED_PENDING_ENTRY"
        return "GRAPH_COMPLETED_PENDING_ENTRY"
    return "GRAPH_REJECTED"


def _graph_row(
    metadata: Mapping[str, Any],
    interval: Mapping[str, Any],
    graph_state: str,
    runtime: RuntimeState,
    before: Mapping[str, Any] | None,
    candidate: StrategyCandidate | None,
) -> dict[str, Any]:
    history = list(metadata.get("market_event_graph_history") or runtime.graph_labels or [])
    labels = [row.get("event_label") for row in history[-3:]]
    triplet = ""
    if candidate is not None:
        triplet = str(candidate.evidence.get("triplet_id") or "")
    elif history:
        triplet = str(history[-1].get("market_event_graph_triplet_id") or "")
    return {
        "strategy_id": STRATEGY_ID,
        "session_date": interval.get("session_date"),
        "evaluation_ts": interval.get("ts_epoch"),
        "source_bar_end": interval.get("source_bar_end_epoch"),
        "graph_state": graph_state,
        "A_ts": history[-3].get("ts_epoch") if len(history) >= 3 else None,
        "B_ts": history[-2].get("ts_epoch") if len(history) >= 2 else None,
        "C_ts": history[-1].get("ts_epoch") if len(history) >= 1 else None,
        "entry_bar_ts": history[-1].get("market_event_graph_entry_bar_ts_epoch") if history else None,
        "event_labels": labels,
        "triplet_id": triplet,
        "idempotency_key": _audit_id(triplet),
        "runtime_state_before": dict(before or runtime.producer_state),
        "runtime_state_after": dict(runtime.producer_state),
        "candidate_created": candidate is not None,
        "candidate_id": _candidate_id(candidate) if candidate is not None else None,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _candidate_trace(
    candidate: StrategyCandidate,
    interval: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidate_id = _candidate_id(candidate)
    triplet = str(candidate.evidence.get("triplet_id") or "")
    stages = (
        "breadth_producer",
        "live_adapter",
        "strategy",
        "TradeBuilder",
        "Phase 1",
        "Phase 2",
        "candidate_pool",
        "executable_truth",
        "ranking",
        "UI/dashboard",
        "shadow_approval",
        "mock_order_intent",
        "paper_reconciliation",
    )
    rows: list[dict[str, Any]] = []
    for stage in stages:
        executable = False
        accepted = stage in {"breadth_producer", "live_adapter", "strategy", "candidate_pool", "ranking", "UI/dashboard"}
        reason = "ADVISORY_ONLY" if accepted else "OBSERVATION_ONLY_NOT_EXECUTABLE"
        rows.append(
            {
                "entered_stage": stage,
                "exited_stage": stage,
                "accepted": accepted,
                "rejected": not accepted,
                "downgraded": stage in {"executable_truth", "shadow_approval", "mock_order_intent", "paper_reconciliation"},
                "reason_code": reason,
                "reason_detail": "frozen graph campaign preserves shadow-only authority",
                "candidate_id": candidate_id,
                "triplet_id": triplet,
                "timestamp": interval.get("ts_epoch"),
                "input_hash": _stable_hash({"stage": stage, "candidate": candidate.to_dict(), "before": before}),
                "output_hash": _stable_hash({"stage": stage, "candidate_id": candidate_id, "after": after, "accepted": accepted}),
                "raw_strategy_confidence": candidate.confidence_score,
                "phase1_score": candidate.price_structure_score if stage in {"Phase 1", "Phase 2", "ranking"} else None,
                "phase2_score": candidate.confidence_score if stage in {"Phase 2", "ranking"} else None,
                "final_ranking_score": candidate.raw_score if stage == "ranking" else None,
                "rank": 1 if stage == "ranking" else None,
                "displayable": stage == "UI/dashboard",
                "dashboard_visible": stage == "UI/dashboard",
                "dashboard_section": "shadow_advisory_candidates" if stage == "UI/dashboard" else None,
                "executable": executable,
                "advisory": True,
                "promotion_state": "ADVISORY_ONLY",
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            }
        )
    return rows


def _quote_row(candidate: StrategyCandidate, metadata: Mapping[str, Any], interval: Mapping[str, Any]) -> dict[str, Any]:
    fallback = bool(metadata.get("fallback_used", False))
    return {
        "candidate_id": _candidate_id(candidate),
        "triplet_id": candidate.evidence.get("triplet_id"),
        "timestamp": interval.get("ts_epoch"),
        "nifty_level": metadata.get("nifty_level"),
        "selected_expiry": metadata.get("selected_expiry"),
        "selected_ce_strike": metadata.get("selected_ce_strike"),
        "instrument_identifier": metadata.get("instrument_identifier"),
        "bid": metadata.get("bid"),
        "ask": metadata.get("ask"),
        "ltp": metadata.get("ltp") or candidate.evidence.get("option_ltp"),
        "spread": metadata.get("spread"),
        "spread_pct": metadata.get("spread_pct") or candidate.evidence.get("spread_pct"),
        "quote_timestamp": metadata.get("quote_timestamp"),
        "quote_age": metadata.get("quote_age"),
        "depth": metadata.get("depth") or candidate.evidence.get("depth"),
        "volume": metadata.get("volume"),
        "open_interest": metadata.get("open_interest"),
        "fallback_used": fallback,
        "quote_source": metadata.get("quote_source"),
        "executable": False,
        "advisory": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _hypothetical_outcome_row(
    candidate: StrategyCandidate,
    metadata: Mapping[str, Any],
    interval: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_id": _candidate_id(candidate),
        "triplet_id": candidate.evidence.get("triplet_id"),
        "hypothetical_next_bar_entry": interval.get("ts_epoch"),
        "entry_bid": metadata.get("bid"),
        "entry_ask": metadata.get("ask"),
        "entry_ltp": metadata.get("ltp") or candidate.evidence.get("option_ltp"),
        "MFE": metadata.get("mfe"),
        "MAE": metadata.get("mae"),
        "outcome_5m": metadata.get("outcome_5m"),
        "outcome_10m": metadata.get("outcome_10m"),
        "outcome_15m": metadata.get("outcome_15m"),
        "outcome_20m": metadata.get("outcome_20m"),
        "outcome_30m": metadata.get("outcome_30m"),
        "target_path": metadata.get("target_path"),
        "stop_path": metadata.get("stop_path"),
        "same_candle_ambiguity": bool(metadata.get("same_candle_ambiguity", False)),
        "fees": metadata.get("fees"),
        "spread": metadata.get("spread"),
        "slippage_assumption": metadata.get("slippage_assumption", "conservative_observation_only"),
        "observation_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _write_reports(
    output_dir: Path,
    cfg: CampaignConfig,
    universe: Mapping[str, Any],
    intervals: list[dict[str, Any]],
    graph: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted = [row for row in intervals if row["producer_status"] == ACCEPTED]
    reject_counts = Counter(row["producer_status"] for row in intervals)
    valid_ratio = (len(accepted) / len(intervals)) if intervals else 0.0
    future_violations = sum(
        1 for row in accepted if float(row["source_bar_end_epoch"]) > float(row["ts_epoch"])
    )
    stage_a_verdict = "PASS_BREADTH_RUNTIME_AVAILABILITY"
    if not intervals:
        stage_a_verdict = "INSUFFICIENT_LIVE_BREADTH_EVIDENCE"
    elif cfg.observation_mode.upper() != "LIVE":
        stage_a_verdict = "INSUFFICIENT_LIVE_BREADTH_EVIDENCE"
    elif len(intervals) < cfg.min_intervals or valid_ratio < cfg.min_valid_ratio:
        stage_a_verdict = "INSUFFICIENT_LIVE_BREADTH_EVIDENCE"
    elif future_violations:
        stage_a_verdict = "INVALID_LIVE_BREADTH_PIPELINE"
    emitted = [row for row in graph if row.get("graph_state") == "GRAPH_EMITTED"]
    safety_violation = any(row.get("is_order_action") or row.get("broker_api_called") or row.get("allowed_for_live_execution") for row in graph + candidates)
    if safety_violation:
        stage_b_verdict = "INVALID_SHADOW_SAFETY_BOUNDARY"
    elif not emitted:
        stage_b_verdict = "INSUFFICIENT_GRAPH_TRIGGER_EVIDENCE"
    else:
        stage_b_verdict = "PASS_GRAPH_FORWARD_SHADOW_CORRECTNESS"
    stage_a = {
        "verdict": stage_a_verdict,
        "observation_mode": cfg.observation_mode,
        "intervals_observed": len(intervals),
        "accepted_intervals": len(accepted),
        "rejected_intervals": len(intervals) - len(accepted),
        "valid_ratio": valid_ratio,
        "future_data_violations": future_violations,
        "rejection_counts": dict(reject_counts),
        "constituent_count": universe.get("constituent_count"),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    stage_b = {
        "verdict": stage_b_verdict,
        "graph_state_counts": dict(Counter(row.get("graph_state") for row in graph)),
        "completed_graphs": len(emitted),
        "candidate_stage_rows": len(candidates),
        "quote_rows": len(quotes),
        "hypothetical_outcome_rows": len(outcomes),
        "safety_violation": safety_violation,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    replay = {
        "verdict": "DETERMINISTIC_REPLAY_REQUIRES_SAME_INPUT_REPLAY",
        "input_row_count": len(intervals),
        "ledger_sha256": {
            name: _sha256(output_dir / name)
            for name in (
                "interval_availability.jsonl",
                "breadth_event_ledger.jsonl",
                "graph_state_ledger.jsonl",
                "candidate_stage_trace.jsonl",
            )
            if (output_dir / name).exists()
        },
    }
    rejection_summary = {"rejection_counts": dict(reject_counts), "allowed_codes": list(REJECTION_CODES)}
    _write_json(output_dir / "stage_a_report.json", stage_a)
    _write_json(output_dir / "stage_b_report.json", stage_b)
    _write_json(output_dir / "rejection_summary.json", rejection_summary)
    _write_json(output_dir / "replay_determinism_report.json", replay)
    return {"stage_a": stage_a, "stage_b": stage_b, "replay": replay}


def _write_operational_matrix(
    output_dir: Path,
    intervals: Sequence[Mapping[str, Any]],
    graph: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    quotes: Sequence[Mapping[str, Any]],
) -> None:
    if not intervals:
        return
    first_ts = _optional_float(intervals[0].get("ts_epoch"))
    last_ts = _optional_float(intervals[-1].get("ts_epoch"))
    accepted = [row for row in intervals if row.get("producer_status") == ACCEPTED]
    rejected = [row for row in intervals if row.get("producer_status") != ACCEPTED]
    row = {
        "window_start": first_ts,
        "window_end": last_ts,
        "intervals_expected": len(intervals),
        "intervals_received": len(intervals),
        "breadth_accepted": len(accepted),
        "breadth_rejected": len(rejected),
        "partial_sequences": sum(1 for item in intervals if item.get("producer_status") == "PARTIAL_INTERVAL"),
        "completed_graphs": sum(1 for item in graph if item.get("graph_state") == "GRAPH_EMITTED"),
        "candidates_created": len({item.get("candidate_id") for item in candidates if item.get("candidate_id")}),
        "phase1_accepted": sum(1 for item in candidates if item.get("entered_stage") == "Phase 1" and item.get("accepted")),
        "phase2_accepted": sum(1 for item in candidates if item.get("entered_stage") == "Phase 2" and item.get("accepted")),
        "ranked": sum(1 for item in candidates if item.get("entered_stage") == "ranking" and item.get("accepted")),
        "dashboard_visible": sum(1 for item in candidates if item.get("dashboard_visible")),
        "fallback_quotes": sum(1 for item in quotes if item.get("fallback_used")),
        "errors": [item.get("producer_status") for item in rejected],
        "top_blocker": rejected[0].get("producer_status") if rejected else "",
    }
    _append_jsonl(output_dir / "operational_matrix.jsonl", row)


def _write_static_docs(
    output_dir: Path,
    cfg: CampaignConfig,
    universe: Mapping[str, Any],
    reports: Mapping[str, Any],
) -> None:
    _write_json(
        output_dir / "frozen_runtime_contract.json",
        {
            "strategy_id": STRATEGY_ID,
            "frozen_graph": list(FROZEN_GRAPH),
            "thresholds": FROZEN_THRESHOLDS,
            "dataset_sha256": DATASET_SHA256,
            "frozen_spec_sha256": FROZEN_DISCOVERY_SPEC_SHA256,
            "timing": "A(t-2) -> B(t-1) -> C(t), entry eligibility next completed bar",
            "cooldown_minutes": 15,
            "holding_research_horizon_bars": 15,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        },
    )
    _write_json(output_dir / "constituent_universe_manifest.json", dict(universe or _empty_universe()))
    (output_dir / "README.md").write_text(
        "# Market Event Graph Live Shadow V1\n\n"
        "Read-only Stage A/B observation artifacts for the frozen graph. "
        "Replay output is not live runtime availability proof.\n",
        encoding="utf-8",
    )
    (output_dir / "runtime_path_map.md").write_text(
        "# Runtime Path Map\n\n"
        "market feed -> NIFTY constituent universe -> completed constituent bars -> "
        "completed_constituent_breadth_snapshots -> market_event_graph_history -> "
        "market_event_graph_reversal_v1 -> advisory candidate path.\n\n"
        "Current campaign harness consumes captured metadata JSONL and does not fetch data or call brokers.\n",
        encoding="utf-8",
    )
    (output_dir / "daily_summary.md").write_text(
        "# Daily Summary\n\n"
        f"Stage A verdict: {reports['stage_a']['verdict']}\n\n"
        f"Stage B verdict: {reports['stage_b']['verdict']}\n",
        encoding="utf-8",
    )
    (output_dir / "reproduction_command.txt").write_text(
        "python scripts/run_market_event_graph_live_shadow_v1.py --input PATH_TO_CAPTURED_METADATA_JSONL "
        "--output research/market_event_graph_live_shadow_v1 --mode REPLAY\n",
        encoding="utf-8",
    )
    (output_dir / "live_observation_command.txt").write_text(
        "python scripts/run_market_event_graph_live_shadow_v1.py --input PATH_TO_LIVE_CAPTURED_METADATA_JSONL "
        "--output research/market_event_graph_live_shadow_v1 --mode LIVE\n",
        encoding="utf-8",
    )


def _empty_universe() -> dict[str, Any]:
    return {
        "source": "NOT_CAPTURED",
        "source_timestamp": None,
        "constituent_count": 0,
        "instrument_identifiers": [],
        "index_instrument_identifier": None,
        "inactive_or_missing_instruments": [],
        "universe_sha256": _stable_hash([]),
    }


def _advance_runtime_watermarks(runtime: RuntimeState, interval: Mapping[str, Any]) -> None:
    runtime.last_ts_epoch = _optional_float(interval.get("ts_epoch"))
    runtime.last_source_bar_end_epoch = _optional_float(interval.get("source_bar_end_epoch"))
    runtime.accepted_interval_keys.add((str(interval.get("session_date")), float(interval.get("source_bar_end_epoch"))))


def _metadata_injected(metadata: Mapping[str, Any]) -> bool:
    return all(
        key in metadata
        for key in (
            "completed_constituent_bars",
            "market_event_graph_strategy_id",
            "market_event_graph_dataset_sha256",
            "market_event_graph_frozen_spec_sha256",
            "market_event_graph_thresholds",
            "market_event_graph_runtime_state",
        )
    )


def _runtime_state_valid(state: Any, session_date: str) -> bool:
    return (
        isinstance(state, Mapping)
        and int(state.get("schema_version", -1)) == 1
        and str(state.get("strategy_id") or "") == STRATEGY_ID
        and str(state.get("frozen_spec_sha256") or "") == FROZEN_DISCOVERY_SPEC_SHA256
        and str(state.get("session_date") or "") == str(session_date)
    )


def _count_returns(values: Any, *, finite_only: bool) -> int:
    if isinstance(values, Mapping):
        values = values.values()
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return 0
    if not finite_only:
        return len(values)
    count = 0
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            count += 1
    return count


def _breadth_event_row(event: Mapping[str, Any], interval: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": STRATEGY_ID,
        "session_date": event.get("session_date"),
        "interval_end": interval.get("interval_end"),
        "ts_epoch": event.get("ts_epoch"),
        "source_bar_end_epoch": event.get("source_bar_end_epoch"),
        "event_label": event.get("event_label"),
        "triplet_id": event.get("market_event_graph_triplet_id"),
        "idempotency_key": _audit_id(event.get("market_event_graph_triplet_id")),
        "event_count": 1,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _candidate_id(candidate: StrategyCandidate | None) -> str | None:
    if candidate is None:
        return None
    return _stable_hash(
        {
            "strategy_id": candidate.strategy_id,
            "symbol": candidate.symbol,
            "direction": candidate.direction,
            "triplet_id": candidate.evidence.get("triplet_id"),
        }
    )


def _audit_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"audit-{text[:16]}"


def _first_session_date(snapshots: Sequence[Mapping[str, Any]]) -> str | None:
    for raw in snapshots:
        latest = _latest_bar(raw.get("metadata") or raw)
        value = latest.get("session_date") or raw.get("session_date")
        if value:
            return str(value)
    return None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _truncate_ledgers(output_dir: Path) -> None:
    for name in ARTIFACT_FILES:
        path = output_dir / name
        if path.suffix == ".jsonl":
            path.write_text("", encoding="utf-8")


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _stable_hash(payload: Any) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        return ""
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_sha256s(output_dir: Path) -> None:
    lines = []
    for path in sorted(output_dir.iterdir()):
        if path.name == "SHA256SUMS" or not path.is_file():
            continue
        lines.append(f"{_sha256(path)}  {path.name}")
    (output_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _audit_monotonic(rows: Iterable[Mapping[str, Any]], key: str, failures: list[str]) -> None:
    prev: float | None = None
    for row in rows:
        value = _optional_float(row.get(key))
        if value is None:
            failures.append(f"{key}_missing")
            return
        if prev is not None and value <= prev:
            failures.append(f"{key}_non_monotonic")
            return
        prev = value


__all__ = [
    "ACCEPTED",
    "ARTIFACT_FILES",
    "CampaignConfig",
    "GRAPH_STATES",
    "REJECTION_CODES",
    "RuntimeState",
    "classify_interval",
    "independent_audit",
    "load_jsonl",
    "run_campaign",
]
