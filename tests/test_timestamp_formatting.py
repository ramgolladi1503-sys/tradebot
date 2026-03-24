from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from dashboard.ui.table_model import normalize_df
from dashboard.ui.table_model import select_display_df


def test_iso_ist_input_is_formatted() -> None:
    df = pd.DataFrame(
        [
            {
                "decision_ts_ist": "2026-03-23T20:47:02.802935+05:30",
            }
        ]
    )
    out = normalize_df(df)
    assert out.loc[0, "display_ts_ist"] == "2026-03-23 20:47:02 IST"


def test_utc_input_converts_to_ist() -> None:
    df = pd.DataFrame(
        [
            {
                "decision_ts_utc": "2026-03-23T15:17:02Z",
            }
        ]
    )
    out = normalize_df(df)
    assert out.loc[0, "display_ts_ist"] == "2026-03-23 20:47:02 IST"


def test_epoch_input_converts_to_ist() -> None:
    dt_ist = datetime(2026, 3, 23, 20, 47, 2, tzinfo=ZoneInfo("Asia/Kolkata"))
    df = pd.DataFrame(
        [
            {
                "decision_ts_epoch": dt_ist.timestamp(),
            }
        ]
    )
    out = normalize_df(df)
    assert out.loc[0, "display_ts_ist"] == "2026-03-23 20:47:02 IST"


def test_display_ts_ist_visible_column_is_formatted() -> None:
    df = pd.DataFrame(
        [
            {
                "display_ts_epoch": 1700000010.0,
                "symbol": "NIFTY",
                "expiry_date": "2026-03-26",
                "strike": 23000,
                "opt_type": "CE",
                "side": "BUY",
            }
        ]
    )
    view = select_display_df(normalize_df(df), view="advisory")
    assert view.loc[0, "display_ts_ist"] == "2023-11-15 03:43:30 IST"
