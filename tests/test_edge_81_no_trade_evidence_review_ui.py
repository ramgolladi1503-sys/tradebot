from __future__ import annotations

import pandas as pd

from core.no_trade_oracle import (
    FEED_HEALTH_BLOCKED_REASON,
    NO_TRADE_REQUIRED,
    NoTradeOracleReport,
    NoTradeReason,
)
from dashboard.ui.no_trade_evidence import (
    NO_TRADE_REVIEW_SOURCE,
    build_no_trade_review_rows,
    build_no_trade_review_table_payload,
)
from dashboard.ui.table_model import select_display_df

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


def _sample_oracle_report() -> NoTradeOracleReport:
    return NoTradeOracleReport(
        schema_version=1,
        read_only=True,
        append=False,
        source="no_trade_oracle_v1",
        status=NO_TRADE_REQUIRED,
        no_trade_required=True,
        primary_reason=FEED_HEALTH_BLOCKED_REASON,
        reasons=(
            NoTradeReason(
                category="feed",
                reason_code=FEED_HEALTH_BLOCKED_REASON,
                severity=90,
                message="Canonical feed health is not OK.",
                evidence={"reason_code": "websocket_disconnected"},
            ),
        ),
        blockers=(FEED_HEALTH_BLOCKED_REASON,),
        warnings=(),
        evidence_sources=("feed_health_truth", "feed_hold_gate"),
        metadata={"oracle": "no_trade_oracle_v1"},
        generated_epoch=1772202600.0,
    )


def test_no_trade_review_rows_surface_primary_reason_without_actions():
    rows = build_no_trade_review_rows(_sample_oracle_report(), candidate_id="cand-1")

    assert len(rows) == 1
    row = rows[0]
    assert row["candidate_id"] == "cand-1"
    assert row["status"] == "NO_TRADE"
    assert row["candidate_class"] == "NO_TRADE_EVIDENCE"
    assert row["no_trade_required"] is True
    assert row["no_trade_primary_reason"] == FEED_HEALTH_BLOCKED_REASON
    assert row["no_trade_evidence_sources"] == "feed_health_truth | feed_hold_gate"
    assert row["read_only"] is True
    assert row["append"] is False
    assert row[_ACTION_KEY] is False
    assert row[_BROKER_KEY] is False
    assert row["live_order_action"] is False
    assert row["broker_order_action"] is False


def test_no_trade_review_table_payload_is_read_only_and_non_action():
    payload = build_no_trade_review_table_payload([_sample_oracle_report()])

    assert payload["source"] == NO_TRADE_REVIEW_SOURCE
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["row_count"] == 1
    assert payload[_ACTION_KEY] is False
    assert payload[_BROKER_KEY] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_no_trade_review_rows_accept_json_payload_without_oracle_import_requirement():
    report = _sample_oracle_report().to_json()

    rows = build_no_trade_review_rows(report)

    assert len(rows) == 1
    assert rows[0]["no_trade_primary_reason"] == FEED_HEALTH_BLOCKED_REASON
    assert rows[0]["source"] == NO_TRADE_REVIEW_SOURCE


def test_no_trade_review_rows_can_render_in_existing_review_table_model():
    rows = build_no_trade_review_rows(_sample_oracle_report(), candidate_id="cand-ui")
    df = pd.DataFrame(rows)

    display = select_display_df(df, "review")

    assert len(display) == 1
    assert display.iloc[0]["status"] == "NO_TRADE"
    assert display.iloc[0]["trade_key"]


def test_no_trade_review_rows_ignore_unparseable_payloads():
    rows = build_no_trade_review_rows([None, "not-json", {"status": "NO_TRADE_REQUIRED"}])

    assert len(rows) == 1
    assert rows[0]["status"] == "NO_TRADE"
    assert rows[0]["no_trade_primary_reason"] == "no_no_trade_blockers"
