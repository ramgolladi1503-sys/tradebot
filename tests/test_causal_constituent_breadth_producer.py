from core.candidate_pool_orchestrator import build_candidate_pool_report
from core.causal_constituent_breadth_producer import (
    build_completed_constituent_breadth_snapshots,
    enrich_metadata_with_constituent_breadth,
)


def _bars(ts_epoch: float, *, down_count: int, total: int = 50):
    rows = []
    for index in range(total):
        previous = 100.0
        close = 99.0 if index < down_count else 101.0
        rows.append(
            {
                "symbol": f"C{index:02d}",
                "ts_epoch": ts_epoch,
                "previous_close": previous,
                "close": close,
                "completed": True,
            }
        )
    return rows


def _thresholds():
    return {
        "version": "frozen-discovery-v3",
        "breadth_down_high": 0.70,
        "breadth_down_low": 0.30,
        "index_breadth_divergence_low": -0.005,
    }


def test_builds_high_divergence_low_sequence_from_completed_synchronized_bars():
    constituent = []
    index = []
    for ts, down_count, index_close in (
        (100.0, 40, 100.0),
        (160.0, 25, 98.0),
        (220.0, 10, 100.0),
    ):
        constituent.extend(_bars(ts, down_count=down_count))
        index.append(
            {
                "symbol": "NIFTY",
                "ts_epoch": ts,
                "previous_close": 100.0,
                "close": index_close,
                "completed": True,
            }
        )

    result = build_completed_constituent_breadth_snapshots(
        {
            "completed_constituent_bars": constituent,
            "completed_index_bars": index,
            "market_event_graph_frozen_thresholds": _thresholds(),
        },
        context_ts=220.0,
    )
    labels = tuple(row["event_label"] for row in result["snapshots"])
    assert labels == (
        "breadth_down_1:HIGH",
        "index_breadth_divergence:LOW",
        "breadth_down_1:LOW",
    )
    assert result["status"] == "READY"
    assert result["is_order_action"] is False
    assert result["broker_api_called"] is False


def test_missing_frozen_thresholds_fails_closed():
    result = build_completed_constituent_breadth_snapshots(
        {"completed_constituent_bars": _bars(100.0, down_count=40)},
        context_ts=100.0,
    )
    assert result["status"] == "MISSING_THRESHOLDS"
    assert result["snapshots"] == []


def test_incomplete_and_low_coverage_bars_cannot_emit_events():
    rows = _bars(100.0, down_count=20, total=39)
    rows[0]["completed"] = False
    result = build_completed_constituent_breadth_snapshots(
        {
            "completed_constituent_bars": rows,
            "completed_index_bars": [
                {
                    "symbol": "NIFTY",
                    "ts_epoch": 100.0,
                    "previous_close": 100.0,
                    "close": 99.0,
                    "completed": True,
                }
            ],
            "market_event_graph_frozen_thresholds": _thresholds(),
        },
        context_ts=100.0,
    )
    assert result["snapshots"] == []
    assert result["metrics"]["rejected_low_coverage"] == 1


def test_enrichment_preserves_source_and_does_not_mutate_it():
    source = {"other": "value"}
    enriched = enrich_metadata_with_constituent_breadth(source, context_ts=100.0)
    assert source == {"other": "value"}
    assert enriched["other"] == "value"
    assert enriched["constituent_breadth_producer_status"] == "MISSING_THRESHOLDS"


def test_candidate_pool_dict_path_auto_builds_graph_and_emits_shadow_candidate():
    constituent = []
    index = []
    for ts, down_count, index_close in (
        (100.0, 40, 100.0),
        (160.0, 25, 98.0),
        (220.0, 10, 100.0),
    ):
        constituent.extend(_bars(ts, down_count=down_count))
        index.append(
            {
                "symbol": "NIFTY",
                "ts_epoch": ts,
                "previous_close": 100.0,
                "close": index_close,
                "completed": True,
            }
        )
    report = build_candidate_pool_report(
        {
            "symbol": "NIFTY",
            "ts_epoch": 220.0,
            "spot_ltp": 24500.0,
            "option_ce_ltp": 120.0,
            "option_pe_ltp": 100.0,
            "ce_spread_pct": 0.01,
            "pe_spread_pct": 0.01,
            "ce_depth": 1000.0,
            "pe_depth": 1000.0,
            "option_ltp_age_sec": 1.0,
            "quote_source": "realtime",
            "metadata": {
                "completed_constituent_bars": constituent,
                "completed_index_bars": index,
                "market_event_graph_frozen_thresholds": _thresholds(),
            },
        },
        include_no_trade_candidate=False,
    )
    assert tuple(candidate.strategy_id for candidate in report.candidates) == (
        "market_event_graph_reversal_v1",
    )
    assert report.metadata["constituent_breadth_producer_status"] == "READY"
    assert report.report_executable_eligible_count == 0
