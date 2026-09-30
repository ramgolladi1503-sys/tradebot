import hashlib
import json

from core.read_only_coverage_ledger import (
    ReadOnlyCoverageLedger,
    build_process_gap_report,
)
from core.market_heritage_graph import publish_same_session_cas_manifest
from core.market_heritage_verifier import verify_market_heritage_manifest


SESSION = {"trading_date": "2026-09-29", "venue": "NSE",
    "calendar_id": "fixture-calendar", "calendar_version": "v1"}


def tick(token, source_epoch, receive_epoch=None):
    payload = {"instrument_token": token, "underlying_symbol": "NIFTY",
        "last_price": 25000.0, "source_timestamp_field": "exchange_timestamp",
        "source_timestamp_epoch": source_epoch}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()
    return {**payload, "receive_timestamp_epoch": receive_epoch or source_epoch,
        "timestamp_source_field": "exchange_timestamp",
        "source_event_payload": payload, "source_event_sha256": digest,
        "source_event_id": f"run-a:1:{token}:{digest[:16]}"}


def test_coverage_ledger_reports_intended_vs_observed_and_event_identity():
    ledger = ReadOnlyCoverageLedger(run_id="run-a", session_identity=SESSION,
        intended_tokens=[256265, 999], started_epoch=100.0)
    ledger.record_tick(tick(256265, 101.0))
    ledger.record_tick(tick(256265, 103.5))
    report = ledger.snapshot(ended_epoch=110.0)

    assert report["total_callback_count"] == 2
    assert report["per_token"]["256265"]["coverage_status"] == "OBSERVED_INTERVAL_ONLY"
    assert report["per_token"]["256265"]["verified_event_identity_count"] == 2
    assert report["per_token"]["256265"]["max_observed_source_interarrival_seconds"] == 2.5
    assert report["per_token"]["999"]["coverage_status"] == "NO_TICKS_OBSERVED"
    assert report["per_token"]["999"]["expected_cadence_seconds"] is None
    assert report["per_token"]["999"]["gap_classification"] == "UNKNOWN_EXPECTED_CADENCE_NOT_PROVIDED"
    assert report["downstream_per_token_correlation"].startswith("UNKNOWN")
    assert report["read_only"] is True and report["append"] is False
    assert report["broker_api_called"] is False and report["allowed_for_live_execution"] is False


def test_coverage_ledger_counts_invalid_and_unexpected_callbacks_without_growth():
    ledger = ReadOnlyCoverageLedger(run_id="run-a", session_identity=SESSION,
        intended_tokens=[256265], started_epoch=100.0)
    ledger.record_tick(None)
    invalid = tick(256265, 101.0)
    invalid["source_event_payload"] = {"tampered": True}
    ledger.record_tick(invalid)
    ledger.record_tick({"instrument_token": 888, "source_timestamp_epoch": 102.0})
    report = ledger.snapshot(ended_epoch=103.0)

    assert report["invalid_callback_rows"] == 1
    assert report["unexpected_token_callback_count"] == 1
    assert report["unexpected_tokens"] == [888]
    assert report["per_token"]["256265"]["missing_or_invalid_event_identity_count"] == 1


def test_process_gap_uses_only_verified_prior_same_session_intervals():
    report = {"run_id": "run-a", "session_identity": SESSION,
        "run_started_epoch": 80.0, "run_ended_epoch": 100.0,
        "read_only": True, "broker_api_called": False,
        "allowed_for_live_execution": False}
    report_hash = hashlib.sha256(json.dumps(report, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    prior = [{**report, "source_run_id": "run-a",
        "source_manifest_sha256": "a" * 64,
        "coverage_report_sha256": report_hash,
        "status": "VERIFIED_SAME_SESSION_RUN_COVERAGE"}]
    result = build_process_gap_report(current_run_id="run-b",
        current_started_epoch=145.0, session_identity=SESSION,
        prior_coverage=prior)
    assert result["status"] == "MEASURED_UNOBSERVED_PROCESS_INTERVAL"
    assert result["unobserved_interval_seconds"] == 45.0

    unknown = build_process_gap_report(current_run_id="run-b",
        current_started_epoch=145.0,
        session_identity=SESSION,
        prior_coverage=[{**prior[0], "status": "LEGACY_UNVERIFIED"}])
    assert unknown["status"] == "UNKNOWN"


def test_process_gap_rejects_prior_run_ending_after_current_start():
    report = {"run_id": "run-a", "session_identity": SESSION,
        "run_started_epoch": 80.0, "run_ended_epoch": 101.0,
        "read_only": True, "broker_api_called": False,
        "allowed_for_live_execution": False}
    report_hash = hashlib.sha256(json.dumps(report, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    result = build_process_gap_report(current_run_id="run-b",
        current_started_epoch=100.0, session_identity=SESSION,
        prior_coverage=[{**report, "source_run_id": "run-a",
            "source_manifest_sha256": "a" * 64,
            "coverage_report_sha256": report_hash,
            "status": "VERIFIED_SAME_SESSION_RUN_COVERAGE"}])
    assert result["status"] == "UNKNOWN"


def test_process_gap_rejects_wrong_session_and_tampered_coverage_hash():
    report = {"run_id": "run-a", "session_identity": SESSION,
        "run_started_epoch": 80.0, "run_ended_epoch": 100.0,
        "read_only": True, "broker_api_called": False,
        "allowed_for_live_execution": False}
    report_hash = hashlib.sha256(json.dumps(report, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    prior = {**report, "source_run_id": "run-a",
        "source_manifest_sha256": "a" * 64,
        "coverage_report_sha256": report_hash,
        "status": "VERIFIED_SAME_SESSION_RUN_COVERAGE"}
    wrong_session = {**prior, "session_identity": {**SESSION, "trading_date": "2026-09-28"}}
    tampered = {**prior, "run_ended_epoch": 110.0}
    for row in (wrong_session, tampered):
        result = build_process_gap_report(current_run_id="run-b",
            current_started_epoch=145.0, session_identity=SESSION,
            prior_coverage=[row])
        assert result["status"] == "UNKNOWN"
        assert result["reason"] == "NO_VERIFIED_PRIOR_RUN_INTERVAL"


def test_independent_verifier_rejects_self_consistent_wrong_run_coverage(tmp_path):
    report = {"schema_version": 1, "run_id": "run-a",
        "session_identity": SESSION, "run_started_epoch": 80.0,
        "run_ended_epoch": 100.0, "intended_token_count": 1,
        "intended_tokens": [256265],
        "per_token": {"256265": {"coverage_status": "OBSERVED_INTERVAL_ONLY"}},
        "read_only": True, "append": False, "is_order_action": False,
        "broker_api_called": False, "broker_write_authority": False,
        "order_authority": False, "paper_authorized": False,
        "live_authorized": False, "allowed_for_live_execution": False}
    root = tmp_path / "coverage-heritage"
    published = publish_same_session_cas_manifest(heritage_root=root,
        session_identity=SESSION, run_id="run-a", source_sha="a" * 40,
        underlying_token=256265, primitives={}, coverage_report=report)
    path = __import__("pathlib").Path(published["manifest_path"])
    artifact = json.loads(path.read_text())
    node = next(row for row in artifact["nodes"]
        if row.get("payload", {}).get("record_type") == "run_coverage")
    node["payload"]["run_id"] = "forged-run"
    node["payload"]["coverage_report"]["run_id"] = "forged-run"
    node["source_sha256"] = hashlib.sha256(json.dumps(
        node["payload"]["coverage_report"], sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    body = {key: value for key, value in node.items() if key != "node_id"}
    node["node_id"] = hashlib.sha256(json.dumps(body, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    node_ids = {row.get("node_id") for row in artifact["nodes"]}
    artifact["graph_sha256"] = hashlib.sha256(json.dumps({
        "session_identity": artifact["session_identity"],
        "nodes": sorted(node_ids),
        "edges": sorted(artifact["edges"], key=lambda row: (
            row.get("parent_id", ""), row.get("child_id", ""), row.get("requirement", ""))),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
       allow_nan=False).encode()).hexdigest()
    tampered_path = tmp_path / "self-consistent-forgery.json"
    tampered_path.write_text(json.dumps(artifact, sort_keys=True))

    result = verify_market_heritage_manifest(tampered_path)
    assert result["verdict"] == "BLOCKED"
    assert "RUN_COVERAGE_IDENTITY_OR_HASH_INVALID" in {
        item["code"] for item in result["errors"]}
