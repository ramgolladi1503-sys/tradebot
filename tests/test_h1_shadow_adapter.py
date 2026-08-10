from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research.hypothesis_factory.h1_shadow_adapter import (
    H1ShadowAdapterConfig,
    NoOrderShadowAuthority,
    merge_h1_completed_bar_csvs,
    normalise_kite_intraday_csv,
)


def test_normalise_kite_intraday_csv_converts_utc_to_ist_window(tmp_path: Path) -> None:
    raw = tmp_path / "raw_kite.csv"
    raw.write_text(
        "\n".join(
            [
                "timestamp,symbol,open,high,low,close,volume",
                "2026-08-10 03:40:00+00:00,NIFTY 50,1,2,1,2,0",
                "2026-08-10 03:45:00+00:00,NIFTY 50,24581.25,24607.95,24557.95,24602.7,0",
                "2026-08-10 04:30:00+00:00,NIFTY 50,24536.35,24551.4,24530.25,24538.5,0",
                "2026-08-10 06:30:00+00:00,NIFTY 50,24588.9,24589.15,24584.35,24584.8,0",
                "2026-08-10 06:35:00+00:00,NIFTY 50,1,2,1,2,0",
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "completed.csv"

    report = normalise_kite_intraday_csv(
        raw,
        out,
        H1ShadowAdapterConfig(observation_date="2026-08-10"),
    )

    frame = pd.read_csv(out)
    assert report["rows_out"] == 3
    assert frame["datetime"].tolist() == [
        "2026-08-10 09:15:00",
        "2026-08-10 10:00:00",
        "2026-08-10 12:00:00",
    ]
    assert set(frame["completed_bar"].astype(str).str.lower()) == {"true"}
    assert set(frame["timezone"]) == {"Asia/Kolkata"}
    assert report["orders_created"] == 0
    assert report["broker_writes_created"] == 0
    assert report["predicate_changed"] is False


def test_no_order_shadow_authority_rejects_any_enabled_flag() -> None:
    NoOrderShadowAuthority().assert_safe()
    with pytest.raises(ValueError, match="UNSAFE_H1_SHADOW_AUTHORITY"):
        NoOrderShadowAuthority(order_authority=True).assert_safe()


def test_merge_h1_completed_bar_csvs_deduplicates_and_keeps_latest(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    columns = "datetime,open,high,low,close,volume_optional,source,completed_bar,timezone\n"
    first.write_text(
        columns
        + "2026-08-10 09:15:00,100,110,90,105,0,A,true,Asia/Kolkata\n"
        + "2026-08-10 09:20:00,105,106,99,100,0,A,true,Asia/Kolkata\n",
        encoding="utf-8",
    )
    second.write_text(
        columns
        + "2026-08-10 09:20:00,105,107,98,101,0,B,true,Asia/Kolkata\n"
        + "2026-08-10 12:00:00,101,102,99,100,0,B,true,Asia/Kolkata\n",
        encoding="utf-8",
    )

    out = tmp_path / "merged.csv"
    report = merge_h1_completed_bar_csvs(
        [first, second],
        out,
        H1ShadowAdapterConfig(observation_date="2026-08-10"),
    )

    merged = pd.read_csv(out)
    assert report["rows_out"] == 3
    assert merged["datetime"].tolist() == [
        "2026-08-10 09:15:00",
        "2026-08-10 09:20:00",
        "2026-08-10 12:00:00",
    ]
    # Duplicate 09:20 should keep the later file's value.
    assert float(merged.loc[merged["datetime"] == "2026-08-10 09:20:00", "close"].iloc[0]) == 101.0
    assert report["authority_flags_all_false"] is True
