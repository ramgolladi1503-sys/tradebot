from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.ai_reliability_agent.pr763_session import (
    PASS_VERDICT,
    certify_pr763_session,
    verify_authority_snapshots,
    verify_sealed_evidence_root,
)
from core.read_only_live_evidence import (
    MegIntervalScheduler,
    _valid_retained_evidence_row,
    append_jsonl_record,
    persist_meg_cycle,
    semantic_sha256,
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


def _retained_row(*, evidence_kind: str, run_id: str, session_date: str, interval: str, exported: bool = True):
    row = {
        "schema_version": 1,
        "proof_kind": "PR763_LIVE_ACCEPTANCE",
        "evidence_kind": evidence_kind,
        "run_id": run_id,
        "session_date": session_date,
        "source_interval_identity": interval,
        "market_event_graph_traversal": exported,
        "market_event_graph_traversal_count": int(exported),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "broker_write_authority": False,
        "order_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
    }
    if evidence_kind == "MEG_TRAVERSAL_EVENT":
        row["exported"] = exported
    return row


@pytest.mark.parametrize(
    ("evidence_kind", "field", "exported"),
    [
        ("MEG_TRAVERSAL_EVENT", "schema_version", True),
        ("MEG_TRAVERSAL_EVENT", "market_event_graph_traversal_count", True),
        ("MEG_LIVE_SOURCE_EXPORT", "schema_version", True),
        ("MEG_LIVE_SOURCE_EXPORT", "market_event_graph_traversal_count", True),
    ],
)
def test_retained_evidence_rejects_boolean_values_for_integer_fields(evidence_kind, field, exported):
    row = _retained_row(
        evidence_kind=evidence_kind,
        run_id="run-bool-type",
        session_date="2026-08-04",
        interval="2026-08-04:100",
        exported=exported,
    )
    row[field] = True
    hash_field = "event_sha256" if evidence_kind == "MEG_TRAVERSAL_EVENT" else "row_sha256"
    row[hash_field] = semantic_sha256(row, exclude=(hash_field,))

    assert not _valid_retained_evidence_row(
        row,
        hash_field=hash_field,
        evidence_kind=evidence_kind,
        run_id="run-bool-type",
        session_date="2026-08-04",
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
    assert first["exported_cycle_count"] == 1
    assert first["cumulative_session_export_count"] is None
    assert first["cumulative_export_count_complete"] is False
    assert second["latest_cycle_exported"] is False
    assert second["exported_cycle_count"] == 1
    assert second["cumulative_session_export_count"] is None
    assert len(export_path.read_text(encoding="utf-8").splitlines()) == 1
    assert len(traversal_path.read_text(encoding="utf-8").splitlines()) == 2


def test_meg_summary_counts_retained_traversal_rotations_and_labels_scope(tmp_path: Path):
    traversal_path = tmp_path / "meg_traversal_events.jsonl"
    rotated = traversal_path.with_name(traversal_path.name + ".1")
    append_jsonl_record(
        rotated,
        _retained_row(
            evidence_kind="MEG_TRAVERSAL_EVENT",
            run_id="run-retained-counts",
            session_date="2026-08-04",
            interval="2026-08-04:90",
        ),
        hash_field="event_sha256",
    )
    export_path = tmp_path / "meg_live_source_exports.jsonl"
    for index in range(4):
        path = export_path if index == 0 else export_path.with_name(f"{export_path.name}.{index}")
        append_jsonl_record(
            path,
            _retained_row(
                evidence_kind="MEG_LIVE_SOURCE_EXPORT",
                run_id="run-retained-counts",
                session_date="2026-08-04",
                interval=f"2026-08-04:{index}",
            ),
            hash_field="row_sha256",
        )

    summary = persist_meg_cycle(
        bridge=_Bridge(tmp_path / "missing-captured.jsonl"),
        result=_result(exported=False, reason="NO_SOURCE_DATA"),
        summary_path=tmp_path / "meg_wiring_evidence.json",
        traversal_path=traversal_path,
        export_ledger_path=export_path,
        cycle_count=1,
        session_date="2026-08-04",
        run_id="run-retained-counts",
        interval_end_epoch=100.0,
    )

    assert summary["attempted_cycle_count"] == 2
    assert summary["rejected_cycle_count"] == 1
    assert summary["traversal_count_scope"] == "retained_rotation_generations_only"
    assert summary["retained_traversal_generation_count"] == 2
    assert summary["older_traversal_generations_may_have_been_rotated_out"] is True
    assert summary["exported_cycle_count"] == 4
    assert summary["export_count_scope"] == "retained_rotation_generations_only"
    assert summary["cumulative_export_count_complete"] is False
    assert summary["cumulative_session_export_count"] is None
    assert summary["retained_export_rows_valid"] is True


def test_meg_summary_marks_holey_or_corrupt_export_ring_unknown(tmp_path: Path):
    traversal_path = tmp_path / "meg_traversal_events.jsonl"
    export_path = tmp_path / "meg_live_source_exports.jsonl"
    append_jsonl_record(
        export_path,
        _retained_row(
            evidence_kind="MEG_LIVE_SOURCE_EXPORT",
            run_id="run-holey-counts",
            session_date="2026-08-04",
            interval="2026-08-04:90",
        ),
        hash_field="row_sha256",
    )
    # A suffix gap cannot prove that no generation was rotated away.
    append_jsonl_record(
        export_path.with_name(export_path.name + ".2"),
        _retained_row(
            evidence_kind="MEG_LIVE_SOURCE_EXPORT",
            run_id="run-holey-counts",
            session_date="2026-08-04",
            interval="2026-08-04:80",
        ),
        hash_field="row_sha256",
    )

    summary = persist_meg_cycle(
        bridge=_Bridge(tmp_path / "missing-captured.jsonl"),
        result=_result(exported=False, reason="NO_SOURCE_DATA"),
        summary_path=tmp_path / "meg_wiring_evidence.json",
        traversal_path=traversal_path,
        export_ledger_path=export_path,
        cycle_count=1,
        session_date="2026-08-04",
        run_id="run-holey-counts",
        interval_end_epoch=100.0,
    )
    assert summary["cumulative_export_count_complete"] is False
    assert summary["cumulative_session_export_count"] is None
    append_jsonl_record(
        export_path.with_name(export_path.name + ".1"),
        _retained_row(
            evidence_kind="MEG_LIVE_SOURCE_EXPORT",
            run_id="different-run",
            session_date="2026-08-04",
            interval="2026-08-04:85",
        ),
        hash_field="row_sha256",
    )
    summary = persist_meg_cycle(
        bridge=_Bridge(tmp_path / "missing-captured.jsonl"),
        result=_result(exported=False, reason="NO_SOURCE_DATA"),
        summary_path=tmp_path / "meg_wiring_evidence.json",
        traversal_path=traversal_path,
        export_ledger_path=export_path,
        cycle_count=2,
        session_date="2026-08-04",
        run_id="run-holey-counts",
        interval_end_epoch=160.0,
    )
    assert summary["retained_export_rows_valid"] is False
    assert summary["cumulative_export_count_complete"] is False
    assert summary["cumulative_session_export_count"] is None
    export_path.write_text('{"row":"tampered","row_sha256":"bad"}\nnot-json\n', encoding="utf-8")
    summary = persist_meg_cycle(
        bridge=_Bridge(tmp_path / "missing-captured.jsonl"),
        result=_result(exported=False, reason="NO_SOURCE_DATA"),
        summary_path=tmp_path / "meg_wiring_evidence.json",
        traversal_path=traversal_path,
        export_ledger_path=export_path,
        cycle_count=2,
        session_date="2026-08-04",
        run_id="run-corrupt-counts",
        interval_end_epoch=160.0,
    )
    assert summary["retained_export_rows_valid"] is False
    assert summary["cumulative_export_count_complete"] is False
    assert summary["cumulative_session_export_count"] is None


def test_observation_runtime_preserves_unknown_meg_count(monkeypatch, tmp_path: Path):
    from core import kite_read_only_observation_runtime as runtime

    monkeypatch.setattr(runtime, "latest_completed_index_interval", lambda *_args, **_kwargs: 100.0)
    monkeypatch.setattr(
        runtime,
        "persist_meg_cycle",
        lambda **_kwargs: {
            "cumulative_session_export_count": None,
            "cumulative_export_count_complete": False,
            "read_only": True,
            "is_order_action": False,
        },
    )
    monkeypatch.setattr(runtime, "_measured_meg_facts", lambda **_kwargs: {})
    monkeypatch.setattr(runtime, "write_json_atomic", lambda *_args, **_kwargs: None)

    # The function imports the primitive writer locally, so intercept that import
    # through the canonical module before the call.
    import core.meg_request_scoped_causality as causality
    monkeypatch.setattr(causality, "append_meg_cycle_primitives", lambda *_args, **_kwargs: None)

    result = runtime.write_meg_wiring_evidence(
        bridge=SimpleNamespace(),
        result=SimpleNamespace(exported=False),
        output_path=tmp_path / "summary.json",
        cycle_count=1,
        session_date="2026-08-04",
        run_id="run-unknown-count",
        producer_commit="",
    )
    assert result["market_event_graph_traversal_count"] is None
    assert result["market_event_graph_traversal"] is None

def test_live_evidence_accepts_bounded_subscription_snapshot(tmp_path: Path):
    path = tmp_path / "meg_traversal_events.jsonl"
    row = append_jsonl_record(
        path,
        {
            "evidence_kind": "MEG_TRAVERSAL_EVENT",
            "subscription_evidence": {"tokens": ["TOKEN"] * 12_000},
            "read_only": True,
            "is_order_action": False,
            "broker_write_authority": False,
            "order_authority": False,
        },
        hash_field="event_sha256",
    )
    assert row["event_sha256"]
    assert path.stat().st_size > 64 * 1024
    assert path.stat().st_size <= 256 * 1024


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
