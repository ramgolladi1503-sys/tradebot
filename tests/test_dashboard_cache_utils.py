from __future__ import annotations

import time
from pathlib import Path

from dashboard.ui.utils.cache_utils import (
    REFRESH_MODE_ALWAYS_UI,
    REFRESH_MODE_FEED_ACTIVE,
    REFRESH_MODE_MARKET_OPEN_ONLY,
    file_sig,
    should_trade_autorefresh,
)


def test_file_sig_stable_and_changes_on_update(tmp_path: Path):
    p = tmp_path / "sample.jsonl"
    missing_sig = file_sig(p)
    assert missing_sig == (False, 0, 0)

    p.write_text("one\n", encoding="utf-8")
    sig1 = file_sig(p)
    sig2 = file_sig(p)
    assert sig1 == sig2
    assert sig1[0] is True
    assert sig1[1] > 0

    time.sleep(0.002)
    p.write_text("one\ntwo\n", encoding="utf-8")
    sig3 = file_sig(p)
    assert sig3 != sig1
    assert sig3[1] > sig1[1]


def test_should_trade_autorefresh_modes():
    assert (
        should_trade_autorefresh(
            auto_refresh_enabled=True,
            refresh_mode=REFRESH_MODE_MARKET_OPEN_ONLY,
            feed_status="ACTIVE",
            market_status="OPEN",
        )
        is True
    )
    assert (
        should_trade_autorefresh(
            auto_refresh_enabled=True,
            refresh_mode=REFRESH_MODE_MARKET_OPEN_ONLY,
            feed_status="ACTIVE",
            market_status="CLOSED",
        )
        is False
    )
    assert (
        should_trade_autorefresh(
            auto_refresh_enabled=True,
            refresh_mode=REFRESH_MODE_ALWAYS_UI,
            feed_status="INACTIVE",
            market_status="CLOSED",
        )
        is True
    )
    assert (
        should_trade_autorefresh(
            auto_refresh_enabled=True,
            refresh_mode=REFRESH_MODE_FEED_ACTIVE,
            feed_status="ACTIVE",
            market_status="CLOSED",
        )
        is True
    )
    assert (
        should_trade_autorefresh(
            auto_refresh_enabled=False,
            refresh_mode=REFRESH_MODE_ALWAYS_UI,
            feed_status="ACTIVE",
            market_status="OPEN",
        )
        is False
    )
