import pandas as pd

from dashboard.streamlit_app_runtime import (
    build_chart,
    build_dual_axis_figure,
    build_option_series,
    detect_stale_points,
    _collect_chart_marker_rows,
)


def _sample_candles() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "time_ms": 1700000000000,
                "open": 100.0,
                "high": 102.0,
                "low": 99.5,
                "close": 101.0,
                "volume": 1000.0,
            },
            {
                "time_ms": 1700000300000,
                "open": 101.0,
                "high": 103.0,
                "low": 100.5,
                "close": 102.5,
                "volume": 1200.0,
            },
        ]
    )


def test_build_chart_renders_candles_and_trade_overlays():
    trade = {
        "symbol": "NIFTY",
        "side": "BUY",
        "status": "ACTIVE",
        "confidence": 0.84,
        "entry": 101.25,
        "stop": 99.75,
        "target": 104.0,
        "timestamp_epoch_ms": 1700000300000,
        "ltp": 102.5,
        "bid": 102.4,
        "ask": 102.6,
        "mark_price": 102.5,
        "quote_age_sec": 1.2,
        "spread_pct": 0.00195,
    }
    fig = build_chart(trade, _sample_candles())

    assert len(fig.data) >= 2
    assert fig.data[0].type == "candlestick"
    assert any(trace.type == "scatter" and trace.name == "Trade timestamp" for trace in fig.data)
    assert len(fig.layout.shapes or ()) >= 3
    ann_text = " ".join(str(a.text) for a in (fig.layout.annotations or ()))
    assert "status:" in ann_text
    assert "confidence:" in ann_text
    assert "mark_price:" in ann_text


def test_build_chart_handles_missing_candles_gracefully():
    empty = pd.DataFrame(columns=["time_ms", "open", "high", "low", "close", "volume"])
    fig = build_chart({"symbol": "BANKNIFTY", "entry": 100.0}, empty)
    assert len(fig.data) == 0
    ann_text = " ".join(str(a.text) for a in (fig.layout.annotations or ()))
    assert "No candle data available" in ann_text


def test_collect_chart_marker_rows_filters_symbol_and_caps_size():
    rows = pd.DataFrame(
        [
            {
                "symbol": "NIFTY",
                "status": "PLANNING",
                "reject_reason": "spread_high",
                "entry": 100.0,
                "timestamp_epoch_ms": 1700000000000,
                "quote_age_sec": 2.0,
                "spread_pct": 0.02,
            },
            {
                "symbol": "NIFTY",
                "status": "ACTIVE",
                "entry": 101.0,
                "timestamp_epoch_ms": 1700000001000,
                "quote_age_sec": 1.0,
                "spread_pct": 0.01,
            },
            {
                "symbol": "BANKNIFTY",
                "status": "PLANNING",
                "entry": 200.0,
                "timestamp_epoch_ms": 1700000002000,
            },
        ]
    )
    out = _collect_chart_marker_rows(rows, underlying="NIFTY", max_markers=1)
    assert len(out) == 1
    assert out[0]["marker_kind"] in {"active", "rejected"}
    assert out[0]["chart_trade_key"]


def test_build_chart_adds_rejected_and_active_marker_traces():
    trade = {
        "symbol": "NIFTY",
        "side": "BUY",
        "status": "ACTIVE",
        "entry": 101.25,
        "timestamp_epoch_ms": 1700000300000,
    }
    markers = [
        {
            "symbol": "NIFTY",
            "chart_trade_key": "NIFTY|2026-02-27|23000|CE|BUY",
            "marker_kind": "rejected",
            "reject_reason": "quote_stale",
            "quote_age_sec": 4.0,
            "spread_pct": 0.025,
            "entry": 100.5,
            "timestamp_epoch_ms": 1700000000000,
        },
        {
            "symbol": "NIFTY",
            "chart_trade_key": "NIFTY|2026-02-27|23100|PE|SELL",
            "marker_kind": "active",
            "quote_age_sec": 1.2,
            "spread_pct": 0.01,
            "entry": 101.2,
            "timestamp_epoch_ms": 1700000001000,
        },
    ]
    fig = build_chart(trade, _sample_candles(), marker_rows=markers)

    names = [trace.name for trace in fig.data]
    assert "Rejected/Advisory" in names
    assert "Active Trades" in names
    rejected_trace = next(t for t in fig.data if t.name == "Rejected/Advisory")
    active_trace = next(t for t in fig.data if t.name == "Active Trades")
    assert rejected_trace.marker.symbol == "circle"
    assert active_trace.marker.symbol == "diamond"
    assert any("reject_reason: quote_stale" in txt for txt in rejected_trace.text)


def test_build_option_series_mark_mid_ltp_and_timestamp_normalization():
    src = pd.DataFrame(
        [
            {
                "time_ms": 1700000000000,
                "bid": 99.0,
                "ask": 101.0,
                "ltp": 100.0,
                "mark_price": None,
                "quote_age_sec": 1.0,
            },
            {
                "timestamp": "2026-02-27T04:30:00Z",
                "ltp": 102.0,
                "bid": None,
                "ask": None,
                "quote_age_sec": 2.0,
            },
        ]
    )
    mark_df = build_option_series(src, "mark")
    mid_df = build_option_series(src, "mid")
    ltp_df = build_option_series(src, "ltp")

    assert not mark_df.empty
    assert mark_df["time_ms"].dtype.kind in {"i", "u"}
    first_mark = float(mark_df.iloc[0]["opt_price"])
    assert first_mark == 100.0
    second_mark = float(mark_df.iloc[1]["opt_price"])
    assert second_mark == 102.0
    assert pd.isna(mid_df.iloc[1]["opt_price"])
    assert float(ltp_df.iloc[1]["opt_price"]) == 102.0


def test_detect_stale_points_flags_quote_age_and_outside_bid_ask():
    option_df = pd.DataFrame(
        [
            {"time_ms": 1700000000000, "opt_price": 100.0, "ltp": 100.0, "bid": 99.5, "ask": 100.5, "quote_age_sec": 12.0, "spread_pct": 0.01},
            {"time_ms": 1700000005000, "opt_price": 110.0, "ltp": 110.0, "bid": 99.0, "ask": 101.0, "quote_age_sec": 1.0, "spread_pct": 0.02},
        ]
    )
    mask, reasons = detect_stale_points(
        option_df,
        thresholds={"quote_age_sec_max": 8.0, "ltp_outside_band_pct": 0.01, "spread_pct_max": 0.05},
    )
    assert list(mask.astype(bool)) == [True, True]
    assert "quote_age_sec>" in reasons[0]
    assert "ltp_outside_bid_ask_band" in reasons[1]


def test_build_dual_axis_figure_places_candles_on_y_and_option_on_y2():
    trade = {
        "symbol": "NIFTY",
        "status": "ACTIVE",
        "side": "BUY",
        "entry": 101.0,
        "stop": 99.0,
        "target": 104.0,
        "timestamp_epoch_ms": 1700000000000,
    }
    option_df = pd.DataFrame(
        [
            {
                "time_ms": 1700000000000,
                "opt_price": 100.0,
                "ltp": 100.0,
                "bid": 99.5,
                "ask": 100.5,
                "mark_price": 100.0,
                "quote_age_sec": 1.0,
                "spread_pct": 0.01,
                "source": "option_snapshot",
            },
            {
                "time_ms": 1700000300000,
                "opt_price": 101.0,
                "ltp": 101.0,
                "bid": 100.5,
                "ask": 101.5,
                "mark_price": 101.0,
                "quote_age_sec": 1.0,
                "spread_pct": 0.01,
                "source": "option_snapshot",
            },
        ]
    )
    fig = build_dual_axis_figure(
        underlying_df=_sample_candles(),
        option_df=option_df,
        trade=trade,
        markers_df=[],
        option_mode="mark",
        show_quote_diagnostics=True,
    )

    assert fig.data[0].type == "candlestick"
    opt_trace = next(t for t in fig.data if str(t.name).startswith("Option"))
    assert opt_trace.yaxis == "y2"
    y2_shapes = [s for s in (fig.layout.shapes or ()) if getattr(s, "yref", "") == "y2"]
    assert len(y2_shapes) >= 3
