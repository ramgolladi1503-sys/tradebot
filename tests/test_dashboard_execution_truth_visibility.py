from __future__ import annotations

import pandas as pd

from dashboard.ui.table_model import select_display_df


def _row(**overrides):
    row = {
        "trade_id": "T-1",
        "timestamp": "2026-07-26T03:30:00+00:00",
        "symbol": "NIFTY",
        "instrument_type": "OPT",
        "tradingsymbol": "NIFTY26JUL23000CE",
        "expiry_date": "2026-07-30",
        "strike": 23000,
        "option_type": "CE",
        "side": "BUY",
        "status": "ADVISORY_ONLY",
        "candidate_class": "ADVISORY",
        "final_score": 0.55,
        "entry": 100.0,
        "display_entry": 100.0,
        "display_entry_source": "last",
        "display_entry_status": "displayable",
        "execution_entry": None,
        "execution_entry_source": "none",
        "execution_entry_status": "missing",
        "quote_source": "tick_store",
        "readiness": "ADVISORY_ONLY",
        "execution_status": "advisory_only",
        "is_executable": False,
        "confidence_raw": 0.52,
        "confidence_final": 0.48,
    }
    row.update(overrides)
    return row


def test_fallback_row_cannot_visually_masquerade_as_executable() -> None:
    row = _row(
        status="READY",
        readiness="READY",
        execution_status="executable",
        is_executable=True,
        execution_entry=99.5,
        execution_entry_source="recovered_fallback",
        execution_entry_status="executable",
        quote_source="recovered_fallback",
        fallback_candidate=True,
    )

    display = select_display_df(pd.DataFrame([row]), "advisory")
    rendered = display.iloc[0]

    assert bool(rendered["ui_execution_truth"]) is False
    assert rendered["ui_execution_truth_reason"] == "fallback_source_advisory_only"
    assert bool(rendered["is_executable"]) is True
    assert rendered["execution_entry_source"] == "recovered_fallback"
    assert rendered["quote_source"] == "recovered_fallback"
    assert float(rendered["display_entry"]) == 100.0
    assert float(rendered["execution_entry"]) == 99.5


def test_canonical_ask_entry_and_explicit_flag_show_operator_executable_truth() -> None:
    row = _row(
        status="READY",
        readiness="READY",
        execution_status="executable",
        is_executable=True,
        execution_entry=101.25,
        execution_entry_source="ask",
        execution_entry_status="executable",
        display_entry=101.25,
        display_entry_source="ask",
        quote_source="tick_store",
    )

    display = select_display_df(pd.DataFrame([row]), "advisory")
    rendered = display.iloc[0]

    assert bool(rendered["ui_execution_truth"]) is True
    assert rendered["ui_execution_truth_reason"] == "canonical_execution_entry_truth"
    assert rendered["execution_entry_source"] == "ask"
    assert float(rendered["execution_entry"]) == 101.25


def test_canonical_entry_does_not_override_explicit_advisory_status() -> None:
    row = _row(
        execution_entry=100.0,
        execution_entry_source="ask",
        execution_entry_status="executable",
        display_entry_source="ask",
        quote_source="tick_store",
        is_executable=False,
    )

    display = select_display_df(pd.DataFrame([row]), "advisory")
    rendered = display.iloc[0]

    assert bool(rendered["ui_execution_truth"]) is False
    assert (
        rendered["ui_execution_truth_reason"]
        == "canonical_entry_but_row_not_marked_executable"
    )


def test_advisory_table_exposes_display_and_execution_truth_columns() -> None:
    display = select_display_df(pd.DataFrame([_row()]), "advisory")

    required = {
        "ui_execution_truth",
        "ui_execution_truth_reason",
        "is_executable",
        "quote_source",
        "execution_entry",
        "execution_entry_status",
        "execution_entry_source",
        "display_entry",
        "display_entry_status",
        "display_entry_source",
    }
    assert required.issubset(display.columns)
