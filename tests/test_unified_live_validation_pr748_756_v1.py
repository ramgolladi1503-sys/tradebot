from pathlib import Path

import pytest

from core.unified_live_validation_pr748_756.campaign_contract import (
    ENABLE_ENV,
    PR_HEADS,
    build_campaign_identity,
    build_composition_manifest,
    campaign_enabled,
    enrich_row,
    require_campaign_enabled,
)
from core.unified_live_validation_pr748_756.recorder import AppendOnlyRecorder
from core.unified_live_validation_pr748_756.seal import seal_evidence_root
from core.unified_live_validation_pr748_756.validators import (
    scan_preoutcome_fields,
    validate_jsonl_file,
)


def test_campaign_is_disabled_by_default_and_requires_explicit_env():
    assert campaign_enabled({}) is False
    with pytest.raises(RuntimeError):
        require_campaign_enabled({})
    assert campaign_enabled({ENABLE_ENV: "true"}) is True


def test_manifest_preserves_pr_heads_and_read_only_authority():
    manifest = build_composition_manifest(origin_main_sha="abc", integrated_commit_sha="def")

    assert manifest["read_only"] is True
    assert manifest["is_order_action"] is False
    assert manifest["broker_api_called"] is False
    assert manifest["allowed_for_live_execution"] is False
    assert manifest["selected_live_constituent_producer"] == (
        "pr_749_constituent_source_feeds_pr_748_validator_exporter"
    )
    assert manifest["pr_heads"]["750"] == PR_HEADS[750]
    assert "composition_manifest_sha256" in manifest


def test_enrich_row_overwrites_unsafe_inputs_fail_closed(tmp_path):
    identity = build_campaign_identity(
        evidence_root=tmp_path,
        campaign_commit_sha="abc",
        composition_manifest_sha="f" * 64,
        nonce="test",
    )
    row = enrich_row(
        identity,
        {
            "symbol": "NIFTY",
            "read_only": False,
            "is_order_action": True,
            "broker_api_called": True,
            "allowed_for_live_execution": True,
        },
        pr_number=748,
    )

    assert row["run_id"] == "unified-pr748-756-20260731-ffffffffffff-test"
    assert row["read_only"] is True
    assert row["is_order_action"] is False
    assert row["broker_api_called"] is False
    assert row["allowed_for_live_execution"] is False


def test_recorder_appends_jsonl_and_validator_checks_safety(tmp_path):
    identity = build_campaign_identity(
        evidence_root=tmp_path,
        campaign_commit_sha="abc",
        composition_manifest_sha="1" * 64,
        nonce="n",
    )
    recorder = AppendOnlyRecorder(identity)
    path = recorder.append(
        "live/heartbeat.jsonl",
        {"source_timestamp": "2026-07-31T09:16:00+05:30", "symbol": "NIFTY"},
        pr_number=750,
    )

    result = validate_jsonl_file(path, expected_run_id=identity.run_id)
    assert result["pass"] is True
    assert result["rows"] == 1
    assert result["unsafe_rows"] == 0


def test_preoutcome_field_scan_blocks_future_authority_terms():
    bad = scan_preoutcome_fields({"next_minute_entry": 1, "safe_feature": 2, "pnl_label": 3})

    assert bad == ["next_minute_entry", "pnl_label"]


def test_seal_writes_manifest_hash_and_prevents_reseal(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    (root / "live.jsonl").write_text("{}\n", encoding="utf-8")

    manifest = seal_evidence_root(root)

    assert manifest["artifact_count"] == 1
    assert (root / "SHA256SUMS").exists()
    assert (root / "SEALED").exists()
    with pytest.raises(RuntimeError):
        seal_evidence_root(root)

