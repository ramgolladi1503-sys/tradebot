"""Canonical read-only analytical cycle coordinator.

This module owns cycle admission and evidence.  It delegates analytical work to
the existing snapshot producer and consumer stages; it never imports broker or
execution modules and never creates candidates or orders.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.read_only_consumer_cycle import run_consumer_cycle
from core.runtime_snapshot_producer import produce_and_store_runtime_snapshots


IDLE, REQUESTED, SCHEDULED, RUNNING, COMPLETE, FAILED = (
    "IDLE", "REQUESTED", "SCHEDULED", "RUNNING", "COMPLETE", "FAILED"
)
TRIGGERS = frozenset({"MARKET_OPEN_INITIAL", "NORMAL_CADENCE", "FEED_RECOVERY"})


def normalize_feed_truth(
    value: Mapping[str, Any],
    *,
    runtime_truth: Mapping[str, Any],
    expected_session_id: str,
    expected_source_sha: str,
    now_epoch: float | None = None,
    max_age_seconds: float = 10.0,
) -> dict[str, Any]:
    """Normalize the canonical feed-truth envelope for cycle admission.

    The persisted artifact is wrapped as ``payload.feed_health_truth`` while
    the snapshot producer returns that payload directly.  Both forms are
    accepted, but all required nested fields, current runtime lineage, and
    freshness are mandatory.  Ambiguous or stale truth fails closed.
    """
    if not isinstance(value, Mapping) or not isinstance(runtime_truth, Mapping):
        raise ValueError("FEED_TRUTH_WRAPPER_INVALID")
    payload = value.get("payload") if isinstance(value.get("payload"), Mapping) else value
    nested = payload.get("feed_health_truth")
    context = nested.get("context") if isinstance(nested, Mapping) else None
    if not isinstance(nested, Mapping) or not isinstance(context, Mapping):
        raise ValueError("FEED_TRUTH_REQUIRED_WRAPPER_MISSING")
    feed_state = context.get("feed_state")
    runtime_state = context.get("runtime_state")
    websocket_ok = nested.get("websocket_ok")
    feed_ok = nested.get("feed_ok")
    if not isinstance(feed_state, str) or not isinstance(runtime_state, str):
        raise ValueError("FEED_TRUTH_REQUIRED_CONTEXT_FIELD_INVALID")
    if not isinstance(feed_ok, bool):
        raise ValueError("FEED_TRUTH_REQUIRED_FIELD_INVALID")
    startup_not_ready = (
        feed_state.upper() == "STARTING"
        and runtime_state.upper() == "STARTING"
        and websocket_ok is None
    )
    if not isinstance(websocket_ok, bool) and not startup_not_ready:
        raise ValueError("FEED_TRUTH_REQUIRED_FIELD_INVALID")
    session_id = payload.get("session_id")
    source_sha = payload.get("source_sha")
    if session_id != expected_session_id:
        raise ValueError("FEED_TRUTH_SESSION_MISMATCH")
    if source_sha != expected_source_sha:
        raise ValueError("FEED_TRUTH_SOURCE_SHA_MISMATCH")
    ts_epoch = runtime_truth.get("ts_epoch")
    try:
        age = float(now_epoch if now_epoch is not None else time.time()) - float(ts_epoch)
    except (TypeError, ValueError):
        raise ValueError("FEED_TRUTH_RUNTIME_TIMESTAMP_INVALID") from None
    if age < -1.0 or age > float(max_age_seconds):
        raise ValueError("FEED_TRUTH_RUNTIME_STALE")
    runtime_ws = runtime_truth.get("ws_connected")
    if not isinstance(runtime_ws, bool) and not (startup_not_ready and runtime_ws is None):
        raise ValueError("FEED_TRUTH_RUNTIME_WS_INVALID")
    if str(runtime_truth.get("runtime_state") or "") != runtime_state:
        raise ValueError("FEED_TRUTH_RUNTIME_STATE_MISMATCH")
    if str(runtime_truth.get("feed_truth_state") or "").upper() != feed_state.upper():
        raise ValueError("FEED_TRUTH_RUNTIME_STATE_MISMATCH")
    if not startup_not_ready and bool(runtime_ws) != websocket_ok:
        raise ValueError("FEED_TRUTH_RUNTIME_WS_MISMATCH")
    return {
        "feed_state": feed_state.upper(),
        "runtime_state": runtime_state.upper(),
        "ws_connected": websocket_ok,
        "feed_ok": feed_ok,
        "overlay_state": "feed_recovered" if feed_state.upper() == "LIVE" else "feed_unhealthy",
        "normalization_status": "VALID_NOT_READY" if startup_not_ready else "VALID_READY",
        "normalization_valid": True,
        "coordinator_admission_allowed": not startup_not_ready and feed_ok and bool(websocket_ok),
        "waiting_for_feed_truth": startup_not_ready,
        "session_id": expected_session_id,
        "source_sha": expected_source_sha,
        "runtime_truth_ts_epoch": float(ts_epoch),
    }


@dataclass(frozen=True)
class CycleRequest:
    cycle_id: str
    trigger: str
    requested_at: str
    causal_data_cutoff: str
    session_id: str
    source_sha: str


class CanonicalCycleCoordinator:
    """Serialize canonical cycles and emit reconstructable cycle evidence."""

    def __init__(self, *, output_root: str | Path, session_id: str, source_sha: str,
                 cadence_seconds: float = 60.0) -> None:
        self.output_root = Path(output_root)
        self.session_id = str(session_id)
        self.source_sha = str(source_sha)
        self.cadence_seconds = float(cadence_seconds)
        self._lock = threading.Lock()
        self._last_started = 0.0
        self._sequence = 0
        self._recovery_seen = False
        self._initial_requested = False

    @property
    def current_path(self) -> Path:
        return self.output_root / "canonical_cycle_latest.json"

    @property
    def history_path(self) -> Path:
        return self.output_root / "canonical_cycle_history.jsonl"

    def should_request(self, *, market_open: bool, feed_live: bool,
                       feed_recovered: bool = False, now: float | None = None) -> str | None:
        if not market_open or not feed_live:
            return None
        current = time.time() if now is None else float(now)
        if feed_recovered and not self._recovery_seen:
            self._recovery_seen = True
            return "FEED_RECOVERY"
        if self._last_started <= 0 and not self._initial_requested:
            self._initial_requested = True
            return "MARKET_OPEN_INITIAL"
        if current - self._last_started >= self.cadence_seconds:
            return "NORMAL_CADENCE"
        return None

    def request(self, trigger: str, *, cutoff: datetime | None = None) -> CycleRequest:
        if trigger not in TRIGGERS:
            raise ValueError("canonical_cycle_trigger_invalid")
        if trigger == "MARKET_OPEN_INITIAL":
            self._initial_requested = True
        requested = datetime.now(timezone.utc)
        cutoff = cutoff or requested
        self._sequence += 1
        return CycleRequest(
            cycle_id=f"{self.session_id}:{self._sequence}:{uuid.uuid4().hex[:12]}",
            trigger=trigger,
            requested_at=requested.isoformat(),
            causal_data_cutoff=cutoff.astimezone(timezone.utc).isoformat(),
            session_id=self.session_id,
            source_sha=self.source_sha,
        )

    def run(self, request: CycleRequest) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return self._write_failure(request, "OVERLAPPING_CYCLE", "canonical_cycle_coordinator.py:run")
        started = datetime.now(timezone.utc)
        self._last_started = started.timestamp()
        base = {
            "session_id": request.session_id, "source_sha": request.source_sha,
            "cycle_id": request.cycle_id, "trigger": request.trigger,
            "requested_at": request.requested_at, "scheduled_at": started.isoformat(),
            "started_at": started.isoformat(), "causal_data_cutoff": request.causal_data_cutoff,
            "state": RUNNING, "cycle_ok": False, "read_only": True,
            "broker_write_authority": False, "order_authority": False,
            "paper_authorized": False, "live_authorized": False,
            "execution_status": "advisory_only", "broker_order_calls": 0,
        }
        self._write_current(base)
        try:
            runtime_outputs = produce_and_store_runtime_snapshots(
                market_snapshot=None, producer="canonical_cycle_coordinator",
                loop_id=request.cycle_id,
                cycle_feed_truth_payload=None,
            )
            consumer = run_consumer_cycle(
                runtime_outputs=runtime_outputs, output_root=self.output_root,
                session_id=request.session_id, source_sha=request.source_sha,
                cycle_context={"cycle_id": request.cycle_id, "causal_data_cutoff": request.causal_data_cutoff,
                               "trigger": request.trigger},
            )
            counts = _counts(runtime_outputs, consumer)
            completed = datetime.now(timezone.utc)
            base.update(counts)
            consumer_states = consumer.get("consumers") if isinstance(consumer, Mapping) else {}
            mandatory_stages = ("regime", "strategies", "candidate_pool", "option_surface", "eligibility", "ranking", "advisory_queue")
            analytical_complete = (
                counts["strategies_evaluated_count"] > 0
                and isinstance(consumer_states, Mapping)
                and all((consumer_states.get(stage) or {}).get("verdict") == "PASS" for stage in mandatory_stages)
            )
            base.update({
                "state": COMPLETE, "cycle_ok": analytical_complete,
                "completed_at": completed.isoformat(),
                "cycle_outcome": (
                    "NO_ELIGIBLE_CANDIDATE" if counts["eligible_count"] == 0 else "ADVISORY_AVAILABLE"
                ) if analytical_complete else "ANALYTICAL_PIPELINE_INCOMPLETE",
            })
        except Exception as exc:
            base.update({"state": FAILED, "failure_class": type(exc).__name__,
                         "failure_callsite": "canonical_cycle_coordinator.py:run",
                         "failed_stage": "analytical_cycle", "failed_consumer": "canonical_cycle"})
        finally:
            self._write_current(base)
            self._append_history(base)
            self._lock.release()
        return dict(base)

    def _write_failure(self, request: CycleRequest, failure_class: str, callsite: str) -> dict[str, Any]:
        payload = {"session_id": request.session_id, "source_sha": request.source_sha,
                   "cycle_id": request.cycle_id, "trigger": request.trigger,
                   "requested_at": request.requested_at, "state": FAILED, "cycle_ok": False,
                   "failure_class": failure_class, "failure_callsite": callsite,
                   "read_only": True, "broker_order_calls": 0}
        self._write_current(payload); self._append_history(payload)
        return payload

    def _write_current(self, payload: Mapping[str, Any]) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        tmp = self.current_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(payload), sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(self.current_path)

    def _append_history(self, payload: Mapping[str, Any]) -> None:
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), sort_keys=True, default=str) + "\n")


def _counts(runtime_outputs: Mapping[str, Any], consumer: Mapping[str, Any]) -> dict[str, Any]:
    ranked = runtime_outputs.get("ranked_pipeline_latest") or {}
    if not isinstance(ranked, Mapping):
        try:
            from core.runtime_snapshot_store import RANKED_PIPELINE_LATEST_PATH
            ranked = json.loads(Path(RANKED_PIPELINE_LATEST_PATH).read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            ranked = {}
    reports = ranked.get("reports") if isinstance(ranked, Mapping) else []
    reports = reports if isinstance(reports, list) else []
    strategies = sum(int((r or {}).get("candidate_pool", {}).get("generator_count", 0) or 0) for r in reports if isinstance(r, Mapping))
    candidates = sum(int((r or {}).get("raw_candidate_count", 0) or 0) for r in reports if isinstance(r, Mapping))
    eligible = sum(int((r or {}).get("rankable_candidates", 0) or 0) for r in reports if isinstance(r, Mapping))
    ranked_count = sum(int((r or {}).get("ranked_candidate_count", 0) or 0) for r in reports if isinstance(r, Mapping))
    advisory = len((ranked.get("top_advisory") or []) if isinstance(ranked, Mapping) else [])
    return {"strategies_evaluated_count": strategies, "candidates_generated_count": candidates,
            "candidates_rejected_count": int(consumer.get("rejected_count", 0) or 0),
            "eligible_count": eligible, "ranked_count": ranked_count, "advisory_count": advisory,
            "consumer_cycle": dict(consumer)}


__all__ = ["CanonicalCycleCoordinator", "CycleRequest", "COMPLETE", "FAILED", "IDLE", "REQUESTED", "SCHEDULED", "RUNNING"]
