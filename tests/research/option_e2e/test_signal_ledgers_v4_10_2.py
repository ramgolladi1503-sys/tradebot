from __future__ import annotations

from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2.ledger_builder import build_signal_ledgers


def test_v4_10_2_returns_source_blocked_with_exhaustive_evidence() -> None:
    records, summary, detail = build_signal_ledgers(Path("."))

    assert records == []
    assert summary["oracle_verdict"] == "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE"
    assert summary["execution_status"] == "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE"
    assert detail["execution"]["status"] == "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE"
    assert detail["contract_report"]["valid"] is True
    assert detail["source_manifest"]["conclusion"] == "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE"
    assert detail["source_manifest"]["search_hit_count"] > 0
    assert detail["execution"]["broker_api_called"] is False
    assert detail["execution"]["is_order_action"] is False
    assert detail["execution"]["allowed_for_live_execution"] is False


def test_v4_10_2_source_manifest_records_real_search_scope() -> None:
    _, _, detail = build_signal_ledgers(Path("."))
    manifest = detail["source_manifest"]

    assert "/Users/madhuram/tradebot-data" in manifest["search_scope"]
    assert "/Users/madhuram/tradebot-ml-evidence" in manifest["search_scope"]
    assert any("session_manifest" in hit["path"] for hit in manifest["search_hits"])
    assert manifest["search_hit_count"] >= len(manifest["search_hits"])
