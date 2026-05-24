from __future__ import annotations

from core.directional_bias_audit import audit_directional_bias


def _row(
    trade_id: str,
    *,
    action="BUY",
    option_type="CE",
    source="tick_store",
    source_list_marker="executable",
    is_executable=True,
):
    return {
        "trade_id": trade_id,
        "action": action,
        "option_type": option_type,
        "quote_source": source,
        "execution_status": source_list_marker,
        "is_executable": is_executable,
    }


def test_balanced_ce_pe_executable_candidates_produce_no_bias_warning():
    report = audit_directional_bias(
        {
            "top_executable_opportunities": [
                _row("T-CE", option_type="CE"),
                _row("T-PE", option_type="PE"),
            ],
            "top_advisory_opportunities": [],
        }
    )

    assert report.total_rows == 2
    assert report.executable_rows == 2
    assert report.executable_option_side_counts == {"CE": 1, "PE": 1}
    assert report.executable_composite_direction_counts == {"BUY_CE": 1, "BUY_PE": 1}
    assert not [warning for warning in report.warnings if warning.startswith("directional_skew")]
    assert report.metadata["is_order_action"] is False
    assert report.metadata["broker_api_called"] is False
    assert report.metadata["live_order_action"] is False
    assert report.metadata["broker_order_action"] is False


def test_all_buy_call_candidates_produce_directional_skew_warning():
    report = audit_directional_bias(
        {
            "top_executable_opportunities": [
                _row("T-1", option_type="CALL"),
                _row("T-2", option_type="CE"),
                _row("T-3", option_type="CE"),
            ]
        }
    )

    assert report.executable_rows == 3
    assert report.executable_action_counts == {"BUY": 3}
    assert report.executable_option_side_counts == {"CE": 3}
    assert report.executable_composite_direction_counts == {"BUY_CE": 3}
    assert "directional_skew:option_side:CE:3/3" in report.warnings
    assert "directional_skew:composite_direction:BUY_CE:3/3" in report.warnings
    assert "directional_skew:action:BUY:3/3" in report.warnings


def test_mixed_fallback_and_advisory_candidates_are_counted_separately_from_executable():
    report = audit_directional_bias(
        {
            "top_executable_opportunities": [
                _row("T-EXEC", option_type="PE"),
                _row("T-FALLBACK", option_type="PE", source="recovered_fallback"),
            ],
            "top_advisory_opportunities": [
                _row(
                    "T-ADVISORY",
                    option_type="CE",
                    source_list_marker="advisory_only",
                    is_executable=False,
                )
            ],
        }
    )

    assert report.executable_rows == 1
    assert report.fallback_rows == 1
    assert report.advisory_rows == 1
    assert report.executable_composite_direction_counts == {"BUY_PE": 1}
    assert report.fallback_composite_direction_counts == {"BUY_PE": 1}
    assert report.advisory_composite_direction_counts == {"BUY_CE": 1}
    assert "fallback_rows_contribute_directional_bias:BUY_PE" in report.warnings
    assert "advisory_rows_directional_concentration:BUY_CE" in report.warnings


def test_unknown_or_missing_direction_fails_closed_into_audit_warning_not_execution_truth():
    report = audit_directional_bias(
        {
            "top_executable_opportunities": [
                {
                    "trade_id": "T-UNKNOWN",
                    "quote_source": "tick_store",
                    "execution_status": "executable",
                    "is_executable": True,
                }
            ]
        }
    )

    assert report.unknown_direction_rows == 1
    assert report.records[0].action == "UNKNOWN"
    assert report.records[0].option_side == "UNKNOWN"
    assert report.records[0].composite_direction == "UNKNOWN"
    assert "missing_or_unknown_direction_fail_closed" in report.warnings
    assert report.is_order_action is False
    assert report.broker_api_called is False
    assert report.live_order_action is False
    assert report.broker_order_action is False


def test_inconsistent_direction_labels_fail_closed_into_warning():
    report = audit_directional_bias(
        [
            {
                "trade_id": "T-BAD",
                "action": "BUY",
                "side": "SELL",
                "option_type": "CE",
                "contract_type": "PE",
                "execution_status": "executable",
            }
        ]
    )

    assert report.inconsistent_direction_rows == 1
    assert report.records[0].action == "UNKNOWN"
    assert report.records[0].option_side == "UNKNOWN"
    assert "inconsistent_direction_labels_fail_closed" in report.warnings


def test_audit_output_is_deterministic_except_generated_epoch():
    payload = {
        "top_executable_opportunities": [
            _row("T-1", option_type="CE"),
            _row("T-2", option_type="PE"),
            _row("T-3", option_type="CE", source="rest_fallback"),
        ]
    }

    first = audit_directional_bias(payload).to_dict()
    second = audit_directional_bias(payload).to_dict()
    first.pop("generated_epoch")
    second.pop("generated_epoch")

    assert first == second


def test_accepts_flat_candidate_rows_without_payload_wrapper():
    report = audit_directional_bias(
        [
            {"candidate_id": "C-1", "direction": "BUY_PE", "readiness": "READY"},
            {"candidate_id": "C-2", "direction": "BUY_CE", "readiness": "READY"},
        ]
    )

    assert report.total_rows == 2
    assert report.executable_composite_direction_counts == {"BUY_CE": 1, "BUY_PE": 1}
    assert report.unknown_direction_rows == 0
