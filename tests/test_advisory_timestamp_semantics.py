from __future__ import annotations

import pandas as pd

import dashboard.streamlit_app_runtime as runtime
from core import advisory_schema
from core.advisory_row_integrity import CANONICAL_ROW_KIND
from dashboard.ui import table_model


def _row(**overrides):
    payload = {
        "trade_id": "T-TS-1",
        "strategy_id": "CORE",
        "advisory_id": "ADV-TS-1",
        "symbol": "NIFTY",
        "strategy_name": "CORE",
        "timestamp": "2026-03-23T10:00:00+00:00",
        "instrument_type": "OPT",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "non_executable",
        "display_entry": 120.0,
        "display_entry_source": "last",
        "display_entry_status": "displayable",
        "entry_reason": "display_from_last",
        "entry_clear_reason": None,
        "entry": 120.0,
        "entry_status": "displayable",
        "entry_source": "last",
        "confidence": 0.6,
        "readiness": "ADVISORY_ONLY",
        "permission": "ADVISORY_ONLY",
        "final_action": "ADVISORY_ONLY",
        "execution_status": "advisory_only",
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
        "quote_source": "tick_store",
        "quote_age_sec": 1.0,
        "decision_explain": [],
        "market_open": False,
        "side": "BUY",
        "row_kind": CANONICAL_ROW_KIND,
        "stop": 100.0,
        "stop_loss": 100.0,
        "target": 150.0,
    }
    payload.update(overrides)
    return payload


def test_decision_timestamp_drives_display_over_snapshot_and_last_seen():
    row = advisory_schema.serialize_advisory_row(
        _row(
            decision_ts_epoch=1700000000.0,
            snapshot_ts_epoch=1700000010.0,
            last_seen_ts="2026-03-23T15:00:00+00:00",
        )
    )

    assert row["display_ts_epoch"] == 1700000000.0
    assert row["display_ts_source"] == "decision_ts_epoch"


def test_snapshot_timestamp_used_when_decision_missing():
    payload = {
        "snapshot_ts_epoch": 1700000010.0,
    }
    out = advisory_schema._apply_explicit_display_timestamps(payload, derived_ts_epoch=1700000020.0)
    assert out["display_ts_epoch"] == 1700000010.0
    assert out["display_ts_source"] == "snapshot_ts_epoch"


def test_advisory_schema_preserves_display_ts_epoch():
    row = advisory_schema.serialize_advisory_row(
        _row(
            display_ts_epoch=123.0,
            display_ts_source="upstream",
            decision_ts_epoch=456.0,
            snapshot_ts_epoch=789.0,
        )
    )

    assert row["display_ts_epoch"] == 123.0
    assert row["display_ts_source"] == "upstream"


def test_advisory_schema_preserves_decision_ts_epoch():
    row = advisory_schema.serialize_advisory_row(
        _row(
            decision_ts_epoch=456.0,
            timestamp="2026-03-23T09:00:00+00:00",
        )
    )

    assert row["decision_ts_epoch"] == 456.0
    assert row["decision_ts_source"] == "preserved"


def test_legacy_timestamp_backfills_decision_and_display():
    row = advisory_schema.serialize_advisory_row(
        _row(
            timestamp="2026-03-23T09:00:00+00:00",
        )
    )

    assert row["decision_ts_epoch"] == advisory_schema._coerce_ts_epoch("2026-03-23T09:00:00+00:00")
    assert row["display_ts_epoch"] == row["decision_ts_epoch"]


def test_dashboard_sort_uses_display_ts_epoch_not_last_seen_ts():
    df = pd.DataFrame(
        [
            {
                "trade_id": "OLDER-DISPLAY",
                "display_ts_epoch": 100.0,
                "display_ts_utc": "1970-01-01T00:01:40+00:00",
                "last_seen_ts": "2026-03-23T12:00:00+00:00",
            },
            {
                "trade_id": "NEWER-DISPLAY",
                "display_ts_epoch": 200.0,
                "display_ts_utc": "1970-01-01T00:03:20+00:00",
                "last_seen_ts": "2026-03-23T11:00:00+00:00",
            },
        ]
    )

    sorted_df = runtime._safe_sort_by_last_seen(df)

    assert list(sorted_df["trade_id"]) == ["NEWER-DISPLAY", "OLDER-DISPLAY"]


def test_table_model_backfills_display_ts_from_decision_ts():
    df = pd.DataFrame(
        [
            {
                "trade_id": "DECISION-ONLY",
                "decision_ts_epoch": 300.0,
                "symbol": "NIFTY",
                "expiry_date": "2026-03-26",
                "strike": 23000,
                "opt_type": "CE",
                "side": "BUY",
            }
        ]
    )

    normalized = table_model.normalize_df(df)

    assert normalized.loc[0, "display_ts_epoch"] == 300.0


def test_table_model_does_not_promote_last_seen_as_display_ts():
    df = pd.DataFrame(
        [
            {
                "trade_id": "LAST-SEEN-ONLY",
                "last_seen_ts": "2026-03-23T12:00:00+00:00",
                "symbol": "NIFTY",
                "expiry_date": "2026-03-26",
                "strike": 23000,
                "opt_type": "CE",
                "side": "BUY",
            }
        ]
    )

    normalized = table_model.normalize_df(df)

    assert pd.isna(normalized.loc[0, "display_ts_epoch"])


def test_table_model_sort_stable_when_display_ts_ties():
    df = pd.DataFrame(
        [
            {
                "trade_id": "FIRST",
                "display_ts_epoch": 100.0,
                "symbol": "NIFTY",
                "expiry_date": "2026-03-26",
                "strike": 23000,
                "opt_type": "CE",
                "side": "BUY",
            },
            {
                "trade_id": "SECOND",
                "display_ts_epoch": 100.0,
                "symbol": "NIFTY",
                "expiry_date": "2026-03-26",
                "strike": 23500,
                "opt_type": "PE",
                "side": "BUY",
            },
        ]
    )

    deduped = table_model.dedupe(df)

    assert list(deduped["trade_id"])[:2] == ["FIRST", "SECOND"]


def test_table_model_uses_display_ts_ist_for_visible_timestamp():
    df = pd.DataFrame(
        [
            {
                "display_ts_epoch": 1700000010.0,
                "display_ts_utc": advisory_schema._utc_timestamp_from_epoch(1700000010.0),
                "display_ts_ist": advisory_schema._ist_timestamp_from_epoch(1700000010.0),
                "last_seen_ts": "2026-03-23T12:00:00+00:00",
                "symbol": "NIFTY",
                "expiry_date": "2026-03-26",
                "strike": 23000,
                "opt_type": "CE",
                "side": "BUY",
            }
        ]
    )

    view = table_model.select_display_df(table_model.normalize_df(df), view="advisory")

    assert "display_ts_ist" in view.columns
    assert "last_seen_ts" not in view.columns
