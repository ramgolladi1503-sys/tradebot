from __future__ import annotations

from core.top_opportunity_executable_truth import (
    classify_top_opportunity_row,
    normalize_top_opportunity_payload,
)


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
):
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


def test_classifies_canonical_execution_entry_as_top_executable_truth():
    decision = classify_top_opportunity_row(_row("T-EXEC"), source_list="top_executable")

    assert decision.trade_id == "T-EXEC"
    assert decision.executable_truth is True
    assert decision.destination_list == "top_executable"
    assert decision.reason == "canonical_execution_entry_truth"
    assert decision.execution_entry == 101.5


def test_demotes_display_only_legacy_executable_claim_from_top_executable():
    payload, report = normalize_top_opportunity_payload(
        {
            "top_executable_opportunities": [
                _row(
                    "T-DISPLAY-ONLY",
                    execution_entry=None,
                    execution_entry_source="none",
                    execution_entry_status="missing",
                    display_entry=99.0,
                    display_entry_source="mark",
                    quote_source="tick_store",
                    is_executable=True,
                    execution_status="executable",
                    readiness="READY",
                    permission="EXECUTE",
                )
            ],
            "top_advisory_opportunities": [],
        }
    )

    assert payload["top_executable_opportunities"] == []
    assert payload["top_advisory_opportunities"][0]["trade_id"] == "T-DISPLAY-ONLY"
    assert payload["top_advisory_opportunities"][0]["is_executable"] is False
    assert payload["top_advisory_opportunities"][0]["execution_status"] == "advisory_only"
    assert payload["top_advisory_opportunities"][0]["top_opportunity_truth_reason"] == "display_only_missing_execution_entry"
    assert report.demoted_count == 1
    assert report.rejection_reasons == ("display_only_missing_execution_entry",)
    assert "legacy_executable_claim_demoted" in report.warnings


def test_demotes_fallback_source_even_when_execution_fields_claim_executable():
    payload, report = normalize_top_opportunity_payload(
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
        }
    )

    assert payload["top_executable_count"] == 0
    assert payload["top_advisory_count"] == 1
    assert payload["top_advisory_opportunities"][0]["trade_id"] == "T-FALLBACK"
    assert payload["top_advisory_opportunities"][0]["permission"] == "ADVISORY_ONLY"
    assert report.records[0].reason == "fallback_source_advisory_only"
    assert "fallback_demoted_from_top_executable" in report.warnings


def test_keeps_advisory_source_rows_advisory_even_with_executable_truth():
    advisory_row = _row("T-ADV-WITH-ASK", is_executable=True, execution_status="executable")

    payload, report = normalize_top_opportunity_payload(
        {
            "top_executable_opportunities": [],
            "top_advisory_opportunities": [advisory_row],
        }
    )

    assert payload["top_executable_opportunities"] == []
    assert payload["top_advisory_opportunities"][0]["trade_id"] == "T-ADV-WITH-ASK"
    assert report.records[0].destination_list == "top_advisory"
    assert report.records[0].reason == "source_list_advisory_not_promoted"


def test_preserves_true_executable_and_demotes_false_executable_in_same_payload():
    payload, report = normalize_top_opportunity_payload(
        {
            "top_executable_opportunities": [
                _row("T-TRUE"),
                _row(
                    "T-FALSE",
                    execution_entry=None,
                    execution_entry_source="none",
                    execution_entry_status="missing",
                    display_entry=74.0,
                    display_entry_source="mark",
                ),
            ],
            "top_advisory_opportunities": [_row("T-ADVISORY", is_executable=False, execution_status="advisory_only", readiness="ADVISORY_ONLY", permission="ADVISORY_ONLY")],
        }
    )

    assert [row["trade_id"] for row in payload["top_executable_opportunities"]] == ["T-TRUE"]
    assert [row["trade_id"] for row in payload["top_advisory_opportunities"]] == ["T-FALSE", "T-ADVISORY"]
    assert report.source_executable_count == 2
    assert report.source_advisory_count == 1
    assert report.top_executable_count == 1
    assert report.top_advisory_count == 2
    assert report.metadata["is_order_action"] is False
    assert report.metadata["broker_api_called"] is False
