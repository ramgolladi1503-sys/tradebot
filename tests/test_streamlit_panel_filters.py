import pandas as pd

from dashboard.streamlit_app_runtime import (
    _concat_frames_safely,
    _derive_final_blocker,
    _derive_permission_bucket,
    _enforce_executable_entry_display,
    _partition_trade_universe,
    _prepare_trade_display_df,
    _table_display_cell,
    filter_trades_for_panel,
)


def test_filter_trades_for_panel_strict_statuses():
    df = pd.DataFrame(
        [
            {"symbol": "NIFTY", "status": "ACTIVE"},
            {"symbol": "BANKNIFTY", "status": "PLANNING"},
            {"symbol": "SENSEX", "status": "PROPOSED"},
            {"symbol": "MIDCPNIFTY", "status": "QUEUED_REVIEW"},
            {"symbol": "FINNIFTY", "status": "REVIEW"},
            {"symbol": "NIFTYJR", "status": "ADVISORY_ONLY"},
            {"symbol": "NIFTYNEXT", "status": "READY"},
            {"symbol": "SENSEXJR", "status": "BLOCKED_APPROVAL"},
            {"symbol": "BANKEX", "status": "BLOCKED_CONTRACT"},
        ]
    )

    active = filter_trades_for_panel(df, "active")
    suggested = filter_trades_for_panel(df, "suggested")
    review = filter_trades_for_panel(df, "review")

    assert set(active["symbol"]) == {"NIFTY"}
    assert set(suggested["symbol"]) == {"BANKNIFTY", "SENSEX", "NIFTYJR", "NIFTYNEXT"}
    assert set(review["symbol"]) == {"MIDCPNIFTY", "SENSEXJR", "BANKEX"}


def test_partition_trade_universe_enforces_state_and_source_separation():
    df = pd.DataFrame(
        [
            {"symbol": "A", "status": "ACTIVE", "source_bucket": "suggested_quick"},
            {"symbol": "B", "status": "PLANNING", "source_bucket": "suggested_quick"},
            {"symbol": "C", "status": "PROPOSED", "source_bucket": "suggested_scalp"},
            {"symbol": "D", "status": "ADVISORY_ONLY", "source_bucket": "advisory_20"},
            {"symbol": "E", "status": "QUEUED_REVIEW", "source_bucket": "review_queue"},
            {"symbol": "H", "status": "BLOCKED_APPROVAL", "source_bucket": "review_queue"},
            {"symbol": "F", "status": "REVIEW", "source_bucket": "review_queue"},
            {"symbol": "G", "status": "QUEUED_REVIEW", "source_bucket": "suggested_quick"},
        ]
    )

    active, review, suggested, advisory = _partition_trade_universe(df)

    assert set(active["symbol"]) == {"A"}
    assert set(review["symbol"]) == {"E", "H"}
    assert set(suggested["symbol"]) == {"B", "C"}
    assert set(advisory["symbol"]) == {"D"}
    assert "A" not in set(suggested["symbol"])


def test_concat_frames_safely_skips_empty_and_all_na():
    frames = [
        pd.DataFrame(),
        pd.DataFrame([{"symbol": None, "status": None}]),
        pd.DataFrame([{"symbol": "NIFTY", "status": "PLANNING"}]),
    ]
    merged = _concat_frames_safely(frames)
    assert not merged.empty
    assert len(merged) == 1
    assert merged.iloc[0]["symbol"] == "NIFTY"


def test_prepare_trade_display_df_does_not_inject_placeholder_columns():
    df = pd.DataFrame(
        [
            {"trade_key": "A", "last_seen_ts": "2026-03-02T08:20:00+00:00", "entry": 100.0, "status": "PLANNING"},
            {"trade_key": "A", "last_seen_ts": "2026-03-02T08:10:00+00:00", "entry": 90.0, "status": "PLANNING"},
        ]
    )
    out = _prepare_trade_display_df(df)
    assert len(out) == 1
    assert "symbol" not in out.columns
    assert float(out.iloc[0]["entry"]) == 100.0


def test_table_display_cell_masks_null_markers():
    assert _table_display_cell(None) == "—"
    assert _table_display_cell(float("nan")) == "—"
    assert _table_display_cell("None") == "—"
    assert _table_display_cell("nan") == "—"
    assert _table_display_cell("N/A") == "—"
    assert _table_display_cell("CE") == "CE"


def test_enforce_executable_entry_display_masks_stale_entries():
    df = pd.DataFrame(
        [
            {"trade_key": "ok", "entry_status": "OK", "entry": 101.5},
            {"trade_key": "mismatch", "entry_status": "PRICE_MISMATCH", "entry": 565.0},
            {"trade_key": "stale", "entry_status": "STALE_PRICE", "entry": 202.0},
            {"trade_key": "no_token", "entry_status": "NO_TOKEN", "entry": 303.0},
            {"trade_key": "unknown", "entry_status": "", "entry": 404.0},
        ]
    )
    out = _enforce_executable_entry_display(df)
    assert float(out.loc[out["trade_key"] == "ok", "entry"].iloc[0]) == 101.5
    assert float(out.loc[out["trade_key"] == "mismatch", "entry"].iloc[0]) == 565.0
    assert pd.isna(out.loc[out["trade_key"] == "stale", "entry"].iloc[0])
    assert pd.isna(out.loc[out["trade_key"] == "no_token", "entry"].iloc[0])
    assert float(out.loc[out["trade_key"] == "unknown", "entry"].iloc[0]) == 404.0


def test_enforce_executable_entry_display_preserves_canonical_advisory_rows():
    df = pd.DataFrame(
        [
            {
                "trade_key": "canon-1",
                "entry_status": "STALE_OPTION_LTP",
                "entry": 72.5,
                "advisory_visible": True,
                "execution_status": "advisory_only",
                "hard_blockers": [],
                "soft_penalties": ["STALE_OPTION_LTP"],
                "warnings": [],
                "confidence_final": 0.71,
                "entry_source": "tick_store",
            }
        ]
    )

    out = _enforce_executable_entry_display(df)

    assert float(out.iloc[0]["entry"]) == 72.5


def test_derive_final_blocker_prefers_decision_trace_reason():
    df = pd.DataFrame(
        [
            {"decision_trace": {"final_blocker": "quote_age_exceeded"}},
            {"decision_trace": {"gating_reason": "permission_ADVISORY_ONLY"}},
            {"entry_status": "STALE_OPTION_LTP"},
        ]
    )
    out = _derive_final_blocker(df)
    assert str(out.iloc[0]) == "quote_age_exceeded"
    assert str(out.iloc[1]) == "permission_ADVISORY_ONLY"
    assert str(out.iloc[2]) == "STALE_OPTION_LTP"


def test_permission_bucket_marks_high_execute_when_eligible():
    df = pd.DataFrame(
        [
            {
                "permission": "EXECUTE",
                "final_action": "EXECUTE",
                "entry_status": "OK",
                "global_conf": 0.92,
            },
            {
                "permission": "EXECUTE",
                "final_action": "EXECUTE",
                "entry_status": "STALE_OPTION_LTP",
                "global_conf": 0.92,
            },
        ]
    )
    bucket = _derive_permission_bucket(df)
    assert str(bucket.iloc[0]) == "HIGH_EXECUTE"
    assert str(bucket.iloc[1]) == "EXECUTE"
