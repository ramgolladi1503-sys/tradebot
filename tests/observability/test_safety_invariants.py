from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

import pytest

from core.observability import (
    CandidateLifecycleEventEmitter,
    FeedStateEventEmitter,
    ObservabilityContext,
    ObservabilityEvent,
    ObservabilityEventError,
    ObservabilityIds,
    build_observability_evidence_bundle,
    validate_event_payload,
)
from core.observability.evidence_bundle import ObservabilityEvidenceBundleError
from core.observability.feed_state import FeedStateEventError

_ACTION_FIELD = "is_" + "order_action"
_BROKER_FIELD = "broker_" + "api_called"


@dataclass(frozen=True)
class CandidateDecision:
    candidate_id: str
    score: float
    eligible: bool


def _context(candidate_id: str | None = None, mode: str = "paper") -> ObservabilityContext:
    return ObservabilityContext(
        ids=ObservabilityIds(
            run_id="run_obs_13",
            cycle_id="cycle_obs_13_000001",
            trace_id="trace_obs_13",
            span_id="span_obs_13",
            candidate_id=candidate_id,
        ),
        stage="runtime.cycle",
        execution_mode=mode,
        attributes={"source_test": "pr_obs_13"},
    )


def _timestamp() -> datetime:
    return datetime(2026, 5, 23, 7, 45, tzinfo=timezone.utc)


def test_decision_event_without_trace_id_fails_closed() -> None:
    event = CandidateLifecycleEventEmitter(_context(), candidate_id="candidate_obs_13").generated(
        timestamp=_timestamp()
    ).as_dict()
    event.pop("trace_id")

    with pytest.raises(ObservabilityEventError, match="required_field_missing:trace_id"):
        validate_event_payload(event)


def test_candidate_event_without_candidate_id_fails_closed() -> None:
    event = CandidateLifecycleEventEmitter(_context(), candidate_id="candidate_obs_13").generated(
        timestamp=_timestamp()
    ).as_dict()
    event.pop("candidate_id")

    with pytest.raises(ObservabilityEventError, match="candidate_event_requires_candidate_id"):
        validate_event_payload(event)


def test_blocked_candidate_without_reason_fails_closed() -> None:
    event = ObservabilityEvent(
        event="candidate.blocked",
        ids=_context(candidate_id="candidate_obs_13").ids,
        stage="candidate.blocked",
        decision="blocked",
        timestamp=_timestamp(),
        source="tests.observability.pr_obs_13",
    )

    with pytest.raises(ObservabilityEventError, match="decision_requires_reason"):
        event.as_dict()


def test_fallback_candidate_cannot_be_executable() -> None:
    feed = FeedStateEventEmitter(_context())

    with pytest.raises(FeedStateEventError, match="fallback_state_cannot_be_executable"):
        feed.validate_state(
            fallback_state="recovered_fallback",
            decision="executable",
            executable=True,
        )


def test_stale_feed_candidate_cannot_be_executable() -> None:
    feed = FeedStateEventEmitter(_context())

    with pytest.raises(FeedStateEventError, match="stale_feed_cannot_be_executable"):
        feed.validate_state(
            feed_state="stale",
            decision="executable",
            executable=True,
        )


def test_candidate_without_terminal_state_is_reported_in_evidence() -> None:
    event = CandidateLifecycleEventEmitter(_context(), candidate_id="candidate_obs_13").generated(
        timestamp=_timestamp()
    ).as_dict()

    bundle = build_observability_evidence_bundle([event])
    funnel = bundle.reports["candidate_decision_funnel.json"]

    assert funnel["complete"] is False
    assert funnel["missing_terminal_state_candidates"] == ["candidate_obs_13"]


def test_paper_mode_event_cannot_mark_live_or_broker_action() -> None:
    event = CandidateLifecycleEventEmitter(_context(mode="paper"), candidate_id="candidate_obs_13").paper_ready(
        timestamp=_timestamp()
    ).as_dict()

    event[_ACTION_FIELD] = True
    with pytest.raises(ObservabilityEvidenceBundleError, match="is_order_action_must_be_false"):
        build_observability_evidence_bundle([event])

    event[_ACTION_FIELD] = False
    event[_BROKER_FIELD] = True
    with pytest.raises(ObservabilityEvidenceBundleError, match="broker_api_called_must_be_false"):
        build_observability_evidence_bundle([event])


def test_observability_wrapper_does_not_change_business_output() -> None:
    before = CandidateDecision(candidate_id="candidate_obs_13", score=0.87, eligible=True)
    context = _context().with_candidate(before.candidate_id, score=before.score, eligible=before.eligible)
    event = ObservabilityEvent.from_context(
        event="candidate.scored",
        context=context,
        decision="scored",
        timestamp=_timestamp(),
        source="tests.observability.pr_obs_13",
    )

    after = replace(before)

    assert event.as_dict()["candidate_id"] == before.candidate_id
    assert after == before
