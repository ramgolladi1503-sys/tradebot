from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.replay_trace import TraceReplayError, main, replay_trace

_ACTION_FIELD = "is_" + "order_action"
_BROKER_FIELD = "broker_" + "api_called"


def _event(
    *,
    event: str,
    stage: str,
    decision: str,
    timestamp: str,
    trace_id: str = "trace_obs_14",
    candidate_id: str = "candidate_obs_14",
    cycle_id: str = "cycle_obs_14",
    reason: str | None = None,
    feed_state: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "event": event,
        "run_id": "run_obs_14",
        "cycle_id": cycle_id,
        "trace_id": trace_id,
        "candidate_id": candidate_id,
        "stage": stage,
        "decision": decision,
        "timestamp": timestamp,
        _ACTION_FIELD: False,
        _BROKER_FIELD: False,
        "source": "tests.test_replay_trace",
    }
    if reason is not None:
        payload["reason"] = reason
    if feed_state is not None:
        payload["feed_state"] = feed_state
    return payload


def _candidate_path() -> list[dict[str, object]]:
    return [
        _event(event="candidate.scored", stage="candidate.scored", decision="scored", timestamp="2026-05-23T09:15:03Z"),
        _event(event="candidate.generated", stage="candidate.generated", decision="generated", timestamp="2026-05-23T09:15:01Z"),
        _event(event="candidate.ranked", stage="candidate.ranked", decision="ranked", timestamp="2026-05-23T09:15:04Z"),
    ]


def test_replay_candidate_decision_path_is_deterministic() -> None:
    result = replay_trace(_candidate_path(), candidate_id="candidate_obs_14")

    assert result.filter_type == "candidate_id"
    assert result.filter_value == "candidate_obs_14"
    assert result.event_count == 3
    assert [event["decision"] for event in result.events] == ["generated", "scored", "ranked"]
    assert result.as_dict()["summary"]["candidate_ids"] == ["candidate_obs_14"]
    assert result.as_dict()[_ACTION_FIELD] is False
    assert result.as_dict()[_BROKER_FIELD] is False


def test_replay_blocked_candidate_by_trace_id() -> None:
    events = [
        _event(event="candidate.generated", stage="candidate.generated", decision="generated", timestamp="2026-05-23T09:16:01Z"),
        _event(
            event="candidate.blocked",
            stage="candidate.blocked",
            decision="blocked",
            timestamp="2026-05-23T09:16:02Z",
            reason="NO_TRADE_CHOP",
        ),
    ]

    result = replay_trace(events, trace_id="trace_obs_14")
    payload = result.as_dict()

    assert result.event_count == 2
    assert payload["summary"]["contains_blocked_decision"] is True
    assert payload["summary"]["reasons"] == {"NO_TRADE_CHOP": 1}
    assert result.events[-1]["decision"] == "blocked"


def test_replay_stale_feed_cycle() -> None:
    events = [
        _event(
            event="feed.stale",
            stage="feed.state",
            decision="blocked",
            timestamp="2026-05-23T09:17:01Z",
            candidate_id="candidate_obs_14_stale",
            reason="STALE_FEED",
            feed_state="stale",
        ),
        _event(
            event="candidate.blocked",
            stage="candidate.blocked",
            decision="blocked",
            timestamp="2026-05-23T09:17:02Z",
            candidate_id="candidate_obs_14_stale",
            reason="STALE_FEED_NOT_EXECUTABLE",
            feed_state="stale",
        ),
    ]

    result = replay_trace(events, cycle_id="cycle_obs_14")
    payload = result.as_dict()

    assert result.event_count == 2
    assert payload["summary"]["contains_stale_feed"] is True
    assert payload["summary"]["contains_blocked_decision"] is True


def test_replay_requires_exactly_one_filter() -> None:
    with pytest.raises(TraceReplayError, match="exactly_one_replay_filter_required"):
        replay_trace(_candidate_path())

    with pytest.raises(TraceReplayError, match="exactly_one_replay_filter_required"):
        replay_trace(_candidate_path(), trace_id="trace_obs_14", candidate_id="candidate_obs_14")


def test_replay_fails_closed_on_invalid_event() -> None:
    event = _event(event="candidate.generated", stage="candidate.generated", decision="generated", timestamp="2026-05-23T09:18:01Z")
    event.pop("trace_id")

    with pytest.raises(TraceReplayError, match="invalid_event:0:required_field_missing:trace_id"):
        replay_trace([event], candidate_id="candidate_obs_14")


def test_replay_fails_when_target_has_no_events() -> None:
    with pytest.raises(TraceReplayError, match="no_events_found:candidate_id:unknown_candidate"):
        replay_trace(_candidate_path(), candidate_id="unknown_candidate")


def test_cli_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text("\n".join(json.dumps(event) for event in _candidate_path()) + "\n", encoding="utf-8")

    exit_code = main(["--input", str(source), "--candidate-id", "candidate_obs_14", "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["filter_type"] == "candidate_id"
    assert output["event_count"] == 3
    assert [event["decision"] for event in output["events"]] == ["generated", "scored", "ranked"]


def test_cli_text_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text("\n".join(json.dumps(event) for event in _candidate_path()) + "\n", encoding="utf-8")

    exit_code = main(["--input", str(source), "--trace-id", "trace_obs_14"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Trace replay: trace_id=trace_obs_14" in output
    assert "decision=generated" in output
    assert "decision=ranked" in output


def test_cli_returns_error_for_missing_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text("\n".join(json.dumps(event) for event in _candidate_path()) + "\n", encoding="utf-8")

    exit_code = main(["--input", str(source), "--candidate-id", "unknown_candidate"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "trace replay failed" in captured.err
