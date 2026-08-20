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
from strategies.strategy_registry import load_strategy_registry
from strategies.shadow.h1_trapped_push_snapback import (
    FROZEN_PREDICATE,
    STRATEGY_ID,
    generate_h1_shadow_trade_intents,
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


def _h1_fixture_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["2026-08-10 09:15:00", 24581.25, 24607.95, 24557.95, 24602.70],
            ["2026-08-10 09:20:00", 24602.85, 24620.95, 24590.00, 24590.35],
            ["2026-08-10 09:25:00", 24589.95, 24592.40, 24553.55, 24553.55],
            ["2026-08-10 09:30:00", 24557.90, 24560.90, 24533.05, 24533.05],
            ["2026-08-10 09:35:00", 24534.25, 24536.15, 24511.10, 24528.05],
            ["2026-08-10 09:40:00", 24528.85, 24530.35, 24512.95, 24521.15],
            ["2026-08-10 09:45:00", 24521.75, 24538.80, 24518.45, 24527.60],
            ["2026-08-10 09:50:00", 24529.30, 24542.80, 24524.55, 24527.90],
            ["2026-08-10 09:55:00", 24528.25, 24538.20, 24525.05, 24534.25],
        ],
        columns=["datetime", "open", "high", "low", "close"],
    )


def test_h1_shadow_strategy_emits_buy_put_intent_without_routeable_order_fields() -> None:
    intents = generate_h1_shadow_trade_intents(_h1_fixture_bars(), run_id="TEST_RUN", source_file_or_feed="fixture")
    assert len(intents) == 1
    intent = intents[0]
    assert intent["strategy_id"] == STRATEGY_ID
    assert intent["candidate_id"] == "H1_TRAPPED_PUSH_SNAPBACK"
    assert intent["shadow_trade_action"] == "BUY_PUT_SHADOW"
    assert intent["emission_mode"] == "SHADOW_TRADE_INTENT_ONLY_NO_ORDER"
    assert intent["routeable_order"] is False
    assert intent["orders_created"] == 0
    assert intent["broker_writes_created"] == 0
    assert intent["paper_authorized"] is False
    assert intent["live_authorized"] is False
    assert intent["order_authority"] is False
    assert intent["broker_write_authority"] is False
    assert intent["execution_viable"] is False
    assert intent["structural_edge_certified"] is False
    assert intent["edge_claimed"] is False
    assert intent["down_ret_horizon_bps"] == pytest.approx(7.860370496323046)
    forbidden_routeable_fields = {
        "broker_order_id",
        "exchange_order_id",
        "order_type",
        "product_type",
        "quantity",
        "tradingsymbol",
        "instrument_token",
    }
    assert forbidden_routeable_fields.isdisjoint(intent.keys())


def test_h1_shadow_strategy_registered_without_superseding_existing_strategies() -> None:
    registry = load_strategy_registry()
    assert STRATEGY_ID in registry
    h1_entry = registry[STRATEGY_ID]
    assert h1_entry.strategy_kind == "shadow_trade_intent_strategy"
    assert h1_entry.certification_track == "offline_shadow_certification_only"
    assert "no broker" in h1_entry.blocked_reason.lower() or "no broker writes" in h1_entry.blocked_reason.lower()

    # Existing strategy entries are not qualified/superseded by this H1 work.
    assert "SIMPLE_ORB" in registry
    assert "MARKET_EVENT_GRAPH_REVERSAL" in registry
    assert registry["MARKET_EVENT_GRAPH_REVERSAL"].certification_supported is False
    assert FROZEN_PREDICATE == "(range_bps[t-1] > 12.0) & (upper_wick_bps[t-1] > 4.0) & (body_bps[t] < -2.0)"
