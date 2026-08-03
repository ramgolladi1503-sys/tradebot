from __future__ import annotations

import json
from pathlib import Path

from core.ai_reliability_agent.pr763_session import (
    FAILED_VERDICT,
    PASS_VERDICT,
    PENDING_VERDICT,
    certify_pr763_session,
    verify_sealed_evidence_root,
)
from core.unified_live_validation_pr748_756.seal import seal_evidence_root


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _proof(*, graph: bool = True, order_authority: bool = False) -> dict:
    return {
        "proof_kind": "PR763_LIVE_ACCEPTANCE",
        "post_mode_full_nifty_packets": True,
        "completed_constituent_bars": 50,
        "market_event_graph_traversal": graph,
        "meg_traversal_count": 1 if graph else 0,
        "shutdown_and_persistence_drain": True,
        "read_only": True,
        "is_order_action": False,
        "order_authority": order_authority,
        "broker_write_authority": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _authority_snapshot(path: Path, *, unsafe_executable: bool = False) -> Path:
    executable = {
        "trade_id": "EXEC-1",
        "authority_state": "EXECUTABLE",
        "authority_allowed": True,
        "operator_bucket": "TOP_EXECUTABLE",
        "selection_score": 0.82,
        "opportunity_score": 0.88,
        "diagnostic_score": 0.91,
        "quote_source": "KITE_WS_FULL",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "truth_allows_execution": True,
        "tradable": True,
        "execution_ok": True,
        "selected_for_execution": True,
        "capital_assigned": 5000.0,
    }
    if unsafe_executable:
        executable["recovered_fallback"] = True
        executable["quote_source"] = "REST_FALLBACK"
    advisory = {
        "trade_id": "ADV-1",
        "authority_state": "ADVISORY_ONLY",
        "authority_allowed": False,
        "operator_bucket": "ADVISORY_ONLY",
        "selection_score": 0.0,
        "opportunity_score": 0.97,
        "diagnostic_score": 0.99,
        "quote_source": "REST_FALLBACK",
        "recovered_fallback": True,
        "execution_allowed": False,
        "eligible_for_execution": False,
        "selected_for_execution": False,
        "capital_assigned": 0.0,
    }
    blocked = {
        "trade_id": "BLOCK-1",
        "authority_state": "BLOCKED",
        "authority_allowed": False,
        "operator_bucket": "BLOCKED_DEBUG",
        "selection_score": 0.0,
        "opportunity_score": 0.44,
        "diagnostic_score": 0.61,
        "quote_source": "UNKNOWN",
        "execution_allowed": False,
        "eligible_for_execution": False,
        "selected_for_execution": False,
        "allocated_capital": 0.0,
    }
    _write_json(
        path,
        {
            "authority_snapshot": True,
            "top_executable": [executable],
            "top_advisory": [advisory],
            "blocked_debug": [blocked],
        },
    )
    return path


def _sealed_root(
    tmp_path: Path,
    *,
    graph: bool = True,
    order_authority: bool = False,
) -> Path:
    root = tmp_path / "evidence"
    _write_json(
        root / "live" / "pr763_live_acceptance.json",
        _proof(graph=graph, order_authority=order_authority),
    )
    _write_json(
        root / "presession" / "campaign_identity.json",
        {
            "run_id": "PR763-TEST",
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        },
    )
    seal_evidence_root(root)
    return root


def test_complete_sealed_read_only_session_passes(tmp_path: Path):
    root = _sealed_root(tmp_path)
    snapshot = _authority_snapshot(tmp_path / "authority.json")
    report = certify_pr763_session(
        evidence_root=root,
        authority_snapshot_paths=[snapshot],
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert report["verdict"] == PASS_VERDICT
    assert report["implementation_complete"] is True
    assert report["live_evidence_complete"] is True
    assert all(gate["passed"] for gate in report["gates"])


def test_missing_live_semantic_proof_remains_pending_not_fabricated_pass(
    tmp_path: Path,
):
    root = _sealed_root(tmp_path, graph=False)
    snapshot = _authority_snapshot(tmp_path / "authority.json")
    report = certify_pr763_session(
        evidence_root=root,
        authority_snapshot_paths=[snapshot],
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert report["verdict"] == PENDING_VERDICT
    assert report["implementation_complete"] is True
    assert report["live_evidence_complete"] is False
    live_gate = next(
        gate
        for gate in report["gates"]
        if gate["gate_id"] == "PR763_LIVE_SEMANTICS"
    )
    assert "market_event_graph_traversal" in live_gate["evidence"]["missing"]


def test_post_seal_mutation_fails_hash_authority(tmp_path: Path):
    root = _sealed_root(tmp_path)
    target = root / "live" / "pr763_live_acceptance.json"
    target.write_text(
        target.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    gate = verify_sealed_evidence_root(root)
    assert gate.passed is False
    assert any(
        "artifact_sha_mismatch" in error
        or "artifact_size_mismatch" in error
        for error in gate.evidence["errors"]
    )


def test_unsafe_fallback_cannot_appear_in_executable_bucket(tmp_path: Path):
    root = _sealed_root(tmp_path)
    snapshot = _authority_snapshot(
        tmp_path / "authority.json",
        unsafe_executable=True,
    )
    report = certify_pr763_session(
        evidence_root=root,
        authority_snapshot_paths=[snapshot],
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert report["verdict"] == FAILED_VERDICT
    gate = next(
        gate
        for gate in report["gates"]
        if gate["gate_id"] == "RUNTIME_AUTHORITY_SNAPSHOTS"
    )
    assert any(
        "unsafe_quote_in_executable" in error
        for error in gate["evidence"]["errors"]
    )


def test_any_order_authority_in_session_evidence_fails_closed(tmp_path: Path):
    root = _sealed_root(tmp_path, order_authority=True)
    snapshot = _authority_snapshot(tmp_path / "authority.json")
    report = certify_pr763_session(
        evidence_root=root,
        authority_snapshot_paths=[snapshot],
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert report["verdict"] == FAILED_VERDICT
    gate = next(
        gate
        for gate in report["gates"]
        if gate["gate_id"] == "READ_ONLY_NO_ORDER_AUTHORITY"
    )
    assert any(
        "order_authority=true" in violation
        for violation in gate["evidence"]["violations"]
    )


def test_empty_but_explicit_authority_snapshot_is_valid_for_zero_candidate_session(
    tmp_path: Path,
):
    root = _sealed_root(tmp_path)
    snapshot = tmp_path / "authority-empty.json"
    _write_json(
        snapshot,
        {
            "authority_snapshot": True,
            "top_executable": [],
            "top_advisory": [],
            "blocked_debug": [],
        },
    )
    report = certify_pr763_session(
        evidence_root=root,
        authority_snapshot_paths=[snapshot],
        generated_at="2026-08-03T00:00:00+00:00",
    )
    assert report["verdict"] == PASS_VERDICT
    authority_gate = next(
        gate
        for gate in report["gates"]
        if gate["gate_id"] == "RUNTIME_AUTHORITY_SNAPSHOTS"
    )
    assert authority_gate["evidence"]["authority_row_count"] == 0
    assert authority_gate["evidence"]["explicit_empty_snapshot_count"] == 1


def test_semantic_certificate_is_deterministic(tmp_path: Path):
    root = _sealed_root(tmp_path)
    snapshot = _authority_snapshot(tmp_path / "authority.json")
    kwargs = {
        "evidence_root": root,
        "authority_snapshot_paths": [snapshot],
        "generated_at": "2026-08-03T00:00:00+00:00",
    }
    first = certify_pr763_session(**kwargs)
    second = certify_pr763_session(**kwargs)
    assert first == second
    assert first["semantic_sha256"] == second["semantic_sha256"]
