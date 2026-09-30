"""Bounded read-only tick callback coverage evidence for one observer run."""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Iterable, Mapping

MAX_COVERAGE_TOKENS = 10_000
AUTHORITY = {
    "read_only": True,
    "append": False,
    "is_order_action": False,
    "broker_api_called": False,
    "broker_write_authority": False,
    "order_authority": False,
    "paper_authorized": False,
    "live_authorized": False,
    "allowed_for_live_execution": False,
}


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _valid_event_identity(tick: Mapping[str, Any], token: int) -> bool:
    payload = tick.get("source_event_payload")
    event_id = tick.get("source_event_id")
    event_sha = tick.get("source_event_sha256")
    if not isinstance(payload, Mapping) or not isinstance(event_id, str) or not event_id:
        return False
    if not isinstance(event_sha, str) or len(event_sha) != 64:
        return False
    if any(char not in "0123456789abcdef" for char in event_sha):
        return False
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, default=str).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != event_sha:
            return False
        return (int(payload.get("instrument_token")) == token
            and int(tick.get("instrument_token")) == token
            and float(payload.get("last_price")) == float(tick.get("last_price"))
            and float(payload.get("source_timestamp_epoch")) == float(tick.get("source_timestamp_epoch"))
            and payload.get("source_timestamp_field") == tick.get("timestamp_source_field")
            and event_id.endswith(f":{token}:{event_sha[:16]}"))
    except (TypeError, ValueError, OverflowError):
        return False


class ReadOnlyCoverageLedger:
    """Aggregate source and receipt ranges without retaining a tick history.

    An observed maximum interarrival interval is reported as a measurement,
    not classified as a gap because no expected per-token cadence is supplied.
    """

    def __init__(self, *, run_id: str, session_identity: Mapping[str, Any],
                 intended_tokens: Iterable[int], started_epoch: float | None = None):
        tokens = set()
        for value in intended_tokens:
            try:
                token = int(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if token > 0:
                tokens.add(token)
        if len(tokens) > MAX_COVERAGE_TOKENS:
            raise ValueError("COVERAGE_TOKEN_BOUND_EXCEEDED")
        if not run_id or not isinstance(session_identity, Mapping) or not session_identity:
            raise ValueError("COVERAGE_RUN_AND_SESSION_IDENTITY_REQUIRED")
        self.run_id = str(run_id)
        self.session_identity = dict(session_identity)
        self.intended_tokens = tuple(sorted(tokens))
        self.started_epoch = _finite(started_epoch) or time.time()
        self.total_callbacks = 0
        self.invalid_callback_rows = 0
        self.unexpected_token_callbacks = 0
        self.unexpected_tokens: set[int] = set()
        self.stats: dict[int, dict[str, Any]] = {
            token: {"observed_callback_count": 0, "verified_event_identity_count": 0,
                "missing_or_invalid_event_identity_count": 0,
                "invalid_source_time_count": 0, "out_of_order_source_time_count": 0,
                "first_source_epoch": None, "last_source_epoch": None,
                "first_receive_epoch": None, "last_receive_epoch": None,
                "max_observed_source_interarrival_seconds": None}
            for token in self.intended_tokens
        }

    def record_tick(self, tick: Mapping[str, Any]) -> None:
        """Record one callback in O(1) memory and bounded time."""
        self.total_callbacks += 1
        if not isinstance(tick, Mapping):
            self.invalid_callback_rows += 1
            return
        try:
            token = int(tick.get("instrument_token"))
        except (TypeError, ValueError, OverflowError):
            self.invalid_callback_rows += 1
            return
        if token not in self.stats:
            self.unexpected_token_callbacks += 1
            if len(self.unexpected_tokens) < MAX_COVERAGE_TOKENS:
                self.unexpected_tokens.add(token)
            return
        row = self.stats[token]
        row["observed_callback_count"] += 1
        if _valid_event_identity(tick, token):
            row["verified_event_identity_count"] += 1
        else:
            row["missing_or_invalid_event_identity_count"] += 1

        source = _finite(tick.get("source_timestamp_epoch"))
        receive = _finite(tick.get("receive_timestamp_epoch"))
        if source is None:
            row["invalid_source_time_count"] += 1
        else:
            prior = row["last_source_epoch"]
            if prior is None:
                row["first_source_epoch"] = source
            elif source < prior:
                row["out_of_order_source_time_count"] += 1
            else:
                gap = source - prior
                current = row["max_observed_source_interarrival_seconds"]
                row["max_observed_source_interarrival_seconds"] = gap if current is None else max(current, gap)
            row["last_source_epoch"] = source
        if receive is not None:
            if row["first_receive_epoch"] is None:
                row["first_receive_epoch"] = receive
            row["last_receive_epoch"] = receive

    def snapshot(self, *, ended_epoch: float | None = None) -> dict[str, Any]:
        ended = _finite(ended_epoch) or time.time()
        if ended < self.started_epoch:
            raise ValueError("COVERAGE_END_PRECEDES_START")
        rows = {}
        for token, stats in sorted(self.stats.items()):
            count = stats["observed_callback_count"]
            rows[str(token)] = {
                "intended_subscription": True,
                "coverage_status": "OBSERVED_INTERVAL_ONLY" if count else "NO_TICKS_OBSERVED",
                **stats,
                "expected_cadence_seconds": None,
                "gap_classification": "UNKNOWN_EXPECTED_CADENCE_NOT_PROVIDED",
            }
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "session_identity": self.session_identity,
            "run_started_epoch": self.started_epoch,
            "run_ended_epoch": ended,
            "run_observed_duration_seconds": ended - self.started_epoch,
            "intended_token_count": len(self.intended_tokens),
            "intended_tokens": list(self.intended_tokens),
            "total_callback_count": self.total_callbacks,
            "invalid_callback_rows": self.invalid_callback_rows,
            "unexpected_token_callback_count": self.unexpected_token_callbacks,
            "unexpected_tokens": sorted(self.unexpected_tokens),
            "per_token": rows,
            "downstream_per_token_correlation": "UNKNOWN_NOT_EXPOSED_BY_CURRENT_FEED_TRUTH_CONTRACT",
            "scheduler_expected_cadence": "UNKNOWN_NOT_CONFIGURED_PER_TOKEN",
            **AUTHORITY,
        }


def build_process_gap_report(*, current_run_id: str, current_started_epoch: float,
                             session_identity: Mapping[str, Any],
                             prior_coverage: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Measure downtime only from prior same-session sealed run intervals."""
    start = _finite(current_started_epoch)
    if start is None or not current_run_id or not isinstance(session_identity, Mapping) or not session_identity:
        return {"status": "BLOCKED", "reason": "CURRENT_RUN_INTERVAL_INVALID", **AUTHORITY}
    candidates: list[tuple[float, str]] = []
    for item in prior_coverage:
        if not isinstance(item, Mapping) or item.get("run_id") == current_run_id:
            continue
        report = {key: value for key, value in item.items() if key not in {
            "source_run_id", "source_manifest_sha256", "coverage_report_sha256", "status"}}
        try:
            report_hash = hashlib.sha256(json.dumps(report, sort_keys=True,
                separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
        except (TypeError, ValueError):
            continue
        if (item.get("session_identity") != dict(session_identity)
                or item.get("source_run_id") != item.get("run_id")
                or item.get("coverage_report_sha256") != report_hash
                or not isinstance(item.get("source_manifest_sha256"), str)
                or len(item.get("source_manifest_sha256", "")) != 64):
            continue
        end = _finite(item.get("run_ended_epoch"))
        if end is None or end > start or item.get("status") != "VERIFIED_SAME_SESSION_RUN_COVERAGE":
            continue
        candidates.append((end, str(item.get("source_run_id") or item.get("run_id") or "")))
    if not candidates:
        return {"status": "UNKNOWN", "reason": "NO_VERIFIED_PRIOR_RUN_INTERVAL",
                "current_run_id": current_run_id, "current_started_epoch": start, **AUTHORITY}
    prior_end, prior_run_id = max(candidates)
    return {"status": "MEASURED_UNOBSERVED_PROCESS_INTERVAL",
        "prior_run_id": prior_run_id, "prior_run_ended_epoch": prior_end,
        "current_run_id": current_run_id, "current_run_started_epoch": start,
        "unobserved_interval_seconds": start - prior_end,
        "does_not_classify_intraprocess_market_gaps": True, **AUTHORITY}
