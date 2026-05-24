from __future__ import annotations

from datetime import datetime, timezone
import json

from core.runtime_snapshot_store import build_snapshot_envelope
from dashboard.readers.snapshot_reader import read_snapshot_payload


def _fresh_generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _row(
    trade_id: str,
    *,
    execution_entry=101.5,
    execution_entry_source="ask",
    execution_entry_status="executable",
    display_entry=101.5,
    display_entry_source="ask",
    quote_source="tick_store",
    is_executable=True,
    execution_status="executable",
    readiness="READY",
    permission="EXECUTE",
) -> dict:
    return {
        "trade_id": trade_id,
        "execution_entry": execution_entry,
        "execution_entry_source": execution_entry_source,
        "execution_entry_status": execution_entry_status,
        "display_entry": display_entry,
        "display_entry_source": display_entry_source,
        "entry": display_entry,
        "entry_source": display_entry_source,
        "quote_source": quote_source,
        "is_executable": is_executable,
        "execution_status": execution_status,
        "readiness": readiness,
        "permission": permission,
        "final_action": "EXECUTE" if permission == "EXECUTE" else "ADVISORY_ONLY",
    }


def _write_snapshot(tmp_path, payload: dict) -> str:
    path = tmp_path / "top_opportunities_latest.json"
    path.write_text(
        json.dumps(
            build_snapshot_envelope(
                payload=payload,
                producer="test",
                generated_at=_fresh_generated_at(),
            )
        ),
        encoding="utf-8",
    )
    return str(path)


def test_snapshot_reader_demotes_display_only_top_executable_row(tmp_path):
    path = _write_snapshot(
        tmp_path,
        {
            "top_executable_opportunities": [
                _row(
                    "T-DISPLAY-ONLY",
                    execution_entry=None,
                    execution_entry_source="none",
                    execution_entry_status="missing",
                    display_entry=77.5,
                    display_entry_source="mark",
                    is_executable=True,
                    execution_status="executable",
                    readiness="READY",
                    permission="EXECUTE",
                )
            ],
            "top_advisory_opportunities": [],
        },
    )

    result = read_snapshot_payload(path)
    payload = result["payload"]

    assert result["state"] == "ok"
    assert payload["top_executable_opportunities"] == []
    assert payload["top_advisory_opportunities"][0]["trade_id"] == "T-DISPLAY-ONLY"
    assert payload["top_advisory_opportunities"][0]["is_executable"] is False
    assert payload["top_advisory_opportunities"][0]["top_opportunity_truth_reason"] == "display_only_missing_execution_entry"
    assert payload["top_opportunity_truth_report"]["demoted_count"] == 1


def test_snapshot_reader_preserves_canonical_top_executable_row(tmp_path):
    path = _write_snapshot(
        tmp_path,
        {
            "top_executable_opportunities": [_row("T-TRUE")],
            "top_advisory_opportunities": [],
        },
    )

    result = read_snapshot_payload(path)
    payload = result["payload"]

    assert [row["trade_id"] for row in payload["top_executable_opportunities"]] == ["T-TRUE"]
    assert payload["top_advisory_opportunities"] == []
    assert payload["top_opportunity_truth_report"]["top_executable_count"] == 1
    assert payload["top_opportunity_truth_report"]["is_order_action"] is False
    assert payload["top_opportunity_truth_report"]["broker_api_called"] is False


def test_snapshot_reader_demotes_fallback_top_executable_row(tmp_path):
    path = _write_snapshot(
        tmp_path,
        {
            "top_executable_opportunities": [
                _row(
                    "T-FALLBACK",
                    execution_entry=88.0,
                    execution_entry_source="last",
                    execution_entry_status="executable",
                    display_entry=88.0,
                    display_entry_source="recovered_fallback",
                    quote_source="rest_fallback",
                    is_executable=True,
                    execution_status="executable",
                    readiness="READY",
                    permission="EXECUTE",
                )
            ],
            "top_advisory_opportunities": [],
        },
    )

    result = read_snapshot_payload(path)
    payload = result["payload"]

    assert payload["top_executable_count"] == 0
    assert payload["top_advisory_count"] == 1
    assert payload["top_advisory_opportunities"][0]["permission"] == "ADVISORY_ONLY"
    assert payload["top_advisory_opportunities"][0]["top_opportunity_truth_reason"] == "fallback_source_advisory_only"
    assert "fallback_demoted_from_top_executable" in payload["top_opportunity_truth_report"]["warnings"]


def test_snapshot_reader_leaves_unrelated_snapshot_payload_unchanged(tmp_path):
    original_payload = {"rows": [{"trade_id": "T-1"}], "status": "ok"}
    path = _write_snapshot(tmp_path, original_payload)

    result = read_snapshot_payload(path)

    assert result["payload"] == original_payload
