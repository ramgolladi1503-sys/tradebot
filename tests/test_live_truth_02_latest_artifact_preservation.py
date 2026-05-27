from __future__ import annotations

import json

from core.live_truth_latest_artifact_preservation import (
    INCOMING_EMPTY_NO_PREVIOUS_REASON,
    INCOMING_EMPTY_PREVIOUS_NON_EMPTY_REASON,
    INCOMING_NON_EMPTY_REASON,
    INVALID_INCOMING_PAYLOAD_REASON,
    LATEST_ARTIFACT_PRESERVATION_SOURCE,
    LATEST_ARTIFACT_STATUS_BLOCKED,
    LATEST_ARTIFACT_STATUS_PRESERVED,
    LATEST_ARTIFACT_STATUS_WRITTEN,
    build_latest_artifact_preservation_decision,
    write_latest_artifact_preserving_non_empty,
)


def test_preserves_previous_non_empty_when_incoming_cycle_is_empty():
    previous = {
        "source": "top_opportunities_latest",
        "source_candidate_count": 3,
        "top_opportunities": [{"trade_id": "T1"}],
        "generated_epoch": 100.0,
    }
    incoming = {
        "source": "top_opportunities_latest",
        "source_candidate_count": 0,
        "top_opportunities": [],
        "generated_epoch": 120.0,
    }

    payload = build_latest_artifact_preservation_decision(
        incoming,
        previous,
        artifact_name="top_opportunities_latest.json",
        now_epoch=130.0,
    ).to_payload()

    assert payload["status"] == LATEST_ARTIFACT_STATUS_PRESERVED
    assert payload["reason_code"] == INCOMING_EMPTY_PREVIOUS_NON_EMPTY_REASON
    assert payload["write_incoming"] is False
    assert payload["preserved_previous"] is True
    assert payload["incoming_non_empty"] is False
    assert payload["previous_non_empty"] is True
    assert payload["selected_payload"] == previous
    assert payload["incoming_summary"]["non_empty"] is False
    assert payload["previous_summary"]["non_empty"] is True


def test_writes_incoming_when_incoming_is_non_empty_even_if_previous_exists():
    previous = {"source_candidate_count": 1, "top_opportunities": [{"trade_id": "OLD"}]}
    incoming = {"source_candidate_count": 2, "top_opportunities": [{"trade_id": "NEW"}]}

    payload = build_latest_artifact_preservation_decision(incoming, previous).to_payload()

    assert payload["status"] == LATEST_ARTIFACT_STATUS_WRITTEN
    assert payload["reason_code"] == INCOMING_NON_EMPTY_REASON
    assert payload["write_incoming"] is True
    assert payload["preserved_previous"] is False
    assert payload["selected_payload"] == incoming


def test_writes_empty_incoming_when_no_previous_non_empty_exists():
    incoming = {"source_candidate_count": 0, "top_opportunities": [], "executable_count": 0}

    payload = build_latest_artifact_preservation_decision(incoming, None).to_payload()

    assert payload["status"] == LATEST_ARTIFACT_STATUS_WRITTEN
    assert payload["reason_code"] == INCOMING_EMPTY_NO_PREVIOUS_REASON
    assert payload["write_incoming"] is True
    assert payload["preserved_previous"] is False
    assert payload["selected_payload"] == incoming


def test_blocks_invalid_incoming_payload_before_write():
    payload = build_latest_artifact_preservation_decision(
        ["not", "a", "mapping"],
        {"source_candidate_count": 2},
    ).to_payload()

    assert payload["status"] == LATEST_ARTIFACT_STATUS_BLOCKED
    assert payload["reason_code"] == INVALID_INCOMING_PAYLOAD_REASON
    assert payload["write_incoming"] is False
    assert payload["preserved_previous"] is False
    assert payload["selected_payload"] == {}


def test_non_empty_detection_uses_count_sequence_and_signal_keys():
    by_count = build_latest_artifact_preservation_decision({"ranked_executable_count": 1}, {}).to_payload()
    by_sequence = build_latest_artifact_preservation_decision({"rows": [{"id": "row-1"}]}, {}).to_payload()
    by_signal = build_latest_artifact_preservation_decision({"top_reportable_executable": True}, {}).to_payload()

    assert by_count["incoming_summary"]["positive_count_keys"] == ["ranked_executable_count"]
    assert by_sequence["incoming_summary"]["non_empty_sequence_keys"] == ["rows"]
    assert by_signal["incoming_summary"]["non_empty_signal_keys"] == ["top_reportable_executable"]


def test_writer_does_not_overwrite_existing_file_when_empty_cycle_arrives(tmp_path):
    target = tmp_path / "top_opportunities_latest.json"
    evidence = tmp_path / "latest_artifact_preservation_latest.json"
    previous = {"source_candidate_count": 1, "top_opportunities": [{"trade_id": "KEEP"}]}
    target.write_text(json.dumps(previous), encoding="utf-8")

    decision = write_latest_artifact_preserving_non_empty(
        target,
        {"source_candidate_count": 0, "top_opportunities": []},
        evidence_path=evidence,
        now_epoch=1.0,
    )

    assert decision.status == LATEST_ARTIFACT_STATUS_PRESERVED
    assert json.loads(target.read_text(encoding="utf-8")) == previous
    evidence_payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert evidence_payload["preserved_previous"] is True
    assert evidence_payload["write_incoming"] is False


def test_writer_replaces_file_when_incoming_is_non_empty(tmp_path):
    target = tmp_path / "top_opportunities_latest.json"
    previous = {"source_candidate_count": 1, "top_opportunities": [{"trade_id": "OLD"}]}
    incoming = {"source_candidate_count": 2, "top_opportunities": [{"trade_id": "NEW"}]}
    target.write_text(json.dumps(previous), encoding="utf-8")

    decision = write_latest_artifact_preserving_non_empty(target, incoming)

    assert decision.status == LATEST_ARTIFACT_STATUS_WRITTEN
    assert json.loads(target.read_text(encoding="utf-8")) == incoming


def test_payload_is_json_serializable_and_non_action():
    payload = build_latest_artifact_preservation_decision(
        {"source_candidate_count": 1},
        {},
    ).to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["source"] == LATEST_ARTIFACT_PRESERVATION_SOURCE
    assert decoded["read_only"] is True
    assert decoded["append"] is False
    assert decoded["metadata"]["evidence_only_no_runtime_change"] is True
