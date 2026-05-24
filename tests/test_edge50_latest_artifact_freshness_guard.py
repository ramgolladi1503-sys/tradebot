from __future__ import annotations

import json

from core.latest_artifact_freshness_guard import (
    FRESH_STATUS,
    FUTURE_STATUS,
    INVALID_STATUS,
    MISSING_STATUS,
    STALE_STATUS,
    UNKNOWN_STATUS,
    assess_latest_artifact_freshness,
    assess_latest_artifacts_freshness,
)


def test_latest_artifact_is_fresh_when_timestamp_age_is_within_limit():
    decision = assess_latest_artifact_freshness(
        "ranked_candidates_latest",
        payload={"generated_epoch": 1_000.0},
        now_epoch=1_030.0,
        max_age_seconds=60.0,
    )

    assert decision.status == FRESH_STATUS
    assert decision.fresh is True
    assert decision.age_seconds == 30.0
    assert decision.timestamp_source == "generated_epoch"
    assert decision.context["is_order_action"] is False
    assert decision.context["broker_api_called"] is False


def test_latest_artifact_is_stale_when_timestamp_age_exceeds_limit():
    decision = assess_latest_artifact_freshness(
        "selector_evidence_latest",
        payload={"generated_epoch": 1_000.0},
        now_epoch=1_181.0,
        max_age_seconds=180.0,
    )

    assert decision.status == STALE_STATUS
    assert decision.fresh is False
    assert decision.age_seconds == 181.0
    assert "artifact_age_exceeds_max_age" in decision.reasons


def test_latest_artifact_missing_when_payload_and_path_absent():
    decision = assess_latest_artifact_freshness("runtime_latest", now_epoch=1_000.0)

    assert decision.status == MISSING_STATUS
    assert decision.fresh is False
    assert decision.reasons == ("artifact_payload_and_path_missing",)


def test_latest_artifact_missing_when_path_does_not_exist(tmp_path):
    decision = assess_latest_artifact_freshness(
        "runtime_latest",
        path=tmp_path / "missing.json",
        now_epoch=1_000.0,
    )

    assert decision.status == MISSING_STATUS
    assert decision.fresh is False
    assert decision.reasons == ("artifact_path_missing",)


def test_latest_artifact_invalid_when_json_is_not_object(tmp_path):
    artifact = tmp_path / "latest.json"
    artifact.write_text("[]", encoding="utf-8")

    decision = assess_latest_artifact_freshness("runtime_latest", path=artifact, now_epoch=1_000.0)

    assert decision.status == INVALID_STATUS
    assert decision.fresh is False
    assert decision.reasons == ("artifact_payload_not_object",)


def test_latest_artifact_unknown_when_timestamp_missing():
    decision = assess_latest_artifact_freshness(
        "runtime_latest",
        payload={"status": "ready"},
        now_epoch=1_000.0,
    )

    assert decision.status == UNKNOWN_STATUS
    assert decision.fresh is False
    assert decision.reasons == ("artifact_timestamp_missing",)


def test_latest_artifact_future_timestamp_is_not_fresh():
    decision = assess_latest_artifact_freshness(
        "runtime_latest",
        payload={"generated_epoch": 1_010.0},
        now_epoch=1_000.0,
        future_tolerance_seconds=5.0,
    )

    assert decision.status == FUTURE_STATUS
    assert decision.fresh is False
    assert decision.age_seconds == -10.0
    assert decision.reasons == ("artifact_timestamp_in_future",)


def test_latest_artifact_can_load_timestamp_from_json_path(tmp_path):
    artifact = tmp_path / "latest.json"
    artifact.write_text(json.dumps({"metadata": {"generated_epoch": 1_000.0}}), encoding="utf-8")

    decision = assess_latest_artifact_freshness(
        "runtime_latest",
        path=artifact,
        now_epoch=1_010.0,
        max_age_seconds=60.0,
    )

    assert decision.status == FRESH_STATUS
    assert decision.timestamp_source == "metadata.generated_epoch"
    assert decision.path == str(artifact)


def test_latest_artifacts_report_aggregates_blockers_and_non_action_fields():
    report = assess_latest_artifacts_freshness(
        {
            "fresh": {"generated_epoch": 1_000.0},
            "stale": {"generated_epoch": 800.0},
            "unknown": {"status": "ready"},
        },
        now_epoch=1_010.0,
        max_age_seconds=60.0,
    )
    payload = report.to_payload()

    assert report.artifact_count == 3
    assert report.fresh_count == 1
    assert report.stale_count == 1
    assert report.invalid_count == 0
    assert "artifact_age_exceeds_max_age" in report.blockers
    assert "artifact_timestamp_missing" in report.blockers
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
