from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from core.ai_reliability_agent.pr763_session import (
    PASS_VERDICT,
    certify_pr763_session,
    verify_authority_snapshots,
    verify_sealed_evidence_root,
)
from core.read_only_live_evidence import (
    MegIntervalScheduler,
    persist_meg_cycle,
    write_authority_snapshot_bundle,
)
from core.unified_live_validation_pr748_756.seal import seal_evidence_root


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class _Bridge:
    def __init__(self, captured: Path) -> None:
        self.exporter = SimpleNamespace(path=captured)
        self.contract = SimpleNamespace(canonical_sha256="universe-sha")

    def _load_universe_contract(self):
        return self.contract, "OK"


def _result(*, exported: bool, reason: str):
    return SimpleNamespace(
        attempted=True,
        exported=exported,
        reason=reason,
        accepted_constituent_count=50 if exported else 0,
        audit={
            "subscription_evidence": {
                "feed_session_id": "feed-session-1",
                "reconnect_generation": 1,
            }
        },
    )


def test_canonical_sealer_emits_exact_pr782_markers(tmp_path: Path):
    root = tmp_path / "evidence"
    _write_json(root / "proof.json", {"read_only": True, "is_order_action": False})
    manifest = seal_evidence_root(root)
    assert (root / "artifact_manifest.json").is_file()
    assert (root / "SHA256SUMS").is_file()
    assert (root / "SEALED").is_file()
    assert manifest["artifact_count"] == 1
    gate = verify_sealed_evidence_root(root)
    assert gate.passed is True, gate.evidence


def test_authority_bundle_is_append_only_and_latest_snapshot_is_verifiable(tmp_path: Path):
    ledger = tmp_path / "authority_snapshots.jsonl"
    latest = tmp_path / "authority_snapshot.json"
    first = write_authority_snapshot_bundle(
        [],
        ledger_path=ledger,
        latest_path=latest,
        run_id="run-1",
        session_date="2026-08-04",
        interval_identity="2026-08-04:100",
        interval_end_epoch=100.0,
        cycle_count=1,
        producer_commit="abc",
    )
    second = write_authority_snapshot_bundle(
        [],
        ledger_path=ledger,
        latest_path=latest,
        run_id="run-1",
        session_date="2026-08-04",
        interval_identity="2026-08-04:160",
        interval_end_epoch=160.0,
        cycle_count=2,
        producer_commit="abc",
    )
    assert first["snapshot_sha256"] != second["snapshot_sha256"]
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 2
    gate = verify_authority_snapshots([latest])
    assert gate.passed is True, gate.evidence
    assert gate.evidence["explicit_empty_snapshot_count"] == 1


def test_meg_success_survives_later_duplicate_cycle(tmp_path: Path):
    captured = tmp_path / "captured_metadata.jsonl"
    captured.write_text(
        json.dumps(
            {
                "session_date": "2026-08-04",
                "source_bar_end_epoch": 100.0,
                "constituent_bar_details": [{} for _ in range(50)],
                "read_only": True,
                "is_order_action": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bridge = _Bridge(captured)
    summary_path = tmp_path / "meg_wiring_evidence.json"
    traversal_path = tmp_path / "meg_traversal_events.jsonl"
    export_path = tmp_path / "meg_live_source_exports.jsonl"

    first = persist_meg_cycle(
        bridge=bridge,
        result=_result(exported=True, reason="WRITTEN"),
        summary_path=summary_path,
        traversal_path=traversal_path,
        export_ledger_path=export_path,
        cycle_count=1,
        session_date="2026-08-04",
        run_id="run-1",
        interval_end_epoch=100.0,
        producer_commit="abc",
    )
    second = persist_meg_cycle(
        bridge=bridge,
        result=_result(exported=False, reason="DUPLICATE_INTERVAL"),
        summary_path=summary_path,
        traversal_path=traversal_path,
        export_ledger_path=export_path,
        cycle_count=2,
        session_date="2026-08-04",
        run_id="run-1",
        interval_end_epoch=100.0,
        producer_commit="abc",
    )
    assert first["cumulative_session_export_count"] == 1
    assert second["latest_cycle_exported"] is False
    assert second["cumulative_session_export_count"] == 1
    assert len(export_path.read_text(encoding="utf-8").splitlines()) == 1
    assert len(traversal_path.read_text(encoding="utf-8").splitlines()) == 2


def test_meg_scheduler_bounds_retries_and_marks_terminal():
    scheduler = MegIntervalScheduler(max_attempts=3, retry_interval_seconds=0.0)
    interval = 100.0
    for _ in range(3):
        assert scheduler.should_attempt(interval, now_monotonic=1.0) is True
        scheduler.record(
            interval,
            reason="INDEX_INTERVAL_MISALIGNED",
            exported=False,
            now_monotonic=1.0,
        )
    assert scheduler.should_attempt(interval, now_monotonic=2.0) is False

    next_interval = 160.0
    assert scheduler.should_attempt(next_interval, now_monotonic=3.0) is True
    scheduler.record(next_interval, reason="WRITTEN", exported=True, now_monotonic=3.0)
    assert scheduler.should_attempt(next_interval, now_monotonic=4.0) is False


def test_full_fixture_passes_pr782_with_new_ledgers(tmp_path: Path):
    root = tmp_path / "evidence"
    _write_json(
        root / "live_acceptance.json",
        {
            "proof_kind": "PR763_LIVE_ACCEPTANCE",
            "post_mode_full_nifty_packets": True,
            "completed_constituent_bar_count": 50,
            "shutdown_and_persistence_drain": True,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "broker_write_authority": False,
            "order_authority": False,
            "allowed_for_live_execution": False,
            "allowed_for_paper_execution": False,
        },
    )
    captured = root / "captured_metadata.jsonl"
    captured.write_text(
        json.dumps(
            {
                "source_bar_end_epoch": 100.0,
                "constituent_bar_details": [{} for _ in range(50)],
                "read_only": True,
                "is_order_action": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    persist_meg_cycle(
        bridge=_Bridge(captured),
        result=_result(exported=True, reason="WRITTEN"),
        summary_path=root / "meg_wiring_evidence.json",
        traversal_path=root / "meg_traversal_events.jsonl",
        export_ledger_path=root / "meg_live_source_exports.jsonl",
        cycle_count=1,
        session_date="2026-08-04",
        run_id="run-1",
        interval_end_epoch=100.0,
        producer_commit="abc",
    )
    authority_latest = root / "authority_snapshot.json"
    write_authority_snapshot_bundle(
        [],
        ledger_path=root / "authority_snapshots.jsonl",
        latest_path=authority_latest,
        run_id="run-1",
        session_date="2026-08-04",
        interval_identity="2026-08-04:100",
        interval_end_epoch=100.0,
        cycle_count=1,
        producer_commit="abc",
    )
    seal_evidence_root(root)
    report = certify_pr763_session(
        evidence_root=root,
        authority_snapshot_paths=[authority_latest],
        generated_at="2026-08-04T12:00:00+00:00",
    )
    assert report["verdict"] == PASS_VERDICT, report
    assert all(gate["passed"] for gate in report["gates"])
