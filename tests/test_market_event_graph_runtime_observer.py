from core.market_event_graph_breadth_producer import (
    frozen_threshold_metadata,
    initial_market_event_graph_runtime_state,
)
from core.market_event_graph_runtime_observer import observe_market_event_graph_runtime


def _returns(negative_count: int, total: int = 50, value: float = 0.001):
    return [-value] * negative_count + [value] * (total - negative_count)


def _bar(
    ts_epoch: float,
    source_bar_end_epoch: float,
    *,
    negative_count: int,
    index_ret1: float,
    session_date: str = "2026-07-30",
    total: int = 50,
    completed: bool = True,
):
    return {
        "ts_epoch": ts_epoch,
        "source_bar_end_epoch": source_bar_end_epoch,
        "session_date": session_date,
        "index_ret1": index_ret1,
        "constituent_ret1": _returns(negative_count, total=total),
        "completed": completed,
    }


def _metadata():
    return {
        **frozen_threshold_metadata(),
        "market_event_graph_runtime_state": initial_market_event_graph_runtime_state("2026-07-30"),
        "completed_constituent_bars": [
            _bar(100.0, 90.0, negative_count=40, index_ret1=-0.001),
            _bar(160.0, 150.0, negative_count=25, index_ret1=-0.004),
            _bar(220.0, 210.0, negative_count=5, index_ret1=0.001),
            _bar(280.0, 270.0, negative_count=20, index_ret1=0.001),
        ],
    }


def test_reports_missing_live_breadth_source_without_emission_authority():
    observation = observe_market_event_graph_runtime({}, context_ts=280.0)

    assert observation["status"] == "MISSING_SOURCE_BARS"
    assert observation["reason"] == "completed_constituent_bars_missing"
    assert observation["source_interval_count"] == 0
    assert observation["allowed_for_live_execution"] is False
    assert observation["is_order_action"] is False
    assert observation["broker_api_called"] is False


def test_reports_exact_graph_reaching_producer_and_adapter():
    observation = observe_market_event_graph_runtime(_metadata(), context_ts=280.0)

    assert observation["status"] == "GRAPH_READY"
    assert observation["reason"] == "producer_and_adapter_accepted_frozen_graph"
    assert observation["source_interval_count"] == 4
    assert observation["accepted_interval_count"] == 4
    assert observation["rejected_interval_count"] == 0
    assert observation["rejection_counts"] == {}
    assert observation["producer_status"] == "READY"
    assert observation["adapter_status"] == "READY"
    assert observation["adapter_row_count"] == 3
    assert observation["graph_trigger_count"] == 1
    assert observation["partial_sequence_labels"] == [
        "breadth_down_1:HIGH",
        "index_breadth_divergence:LOW",
        "breadth_down_1:LOW",
    ]
    assert observation["source_fresh"] is True
    assert observation["latest_source_age_sec"] == 10.0


def test_reports_partial_sequence_before_entry_bar_exists():
    metadata = _metadata()
    metadata["completed_constituent_bars"] = metadata["completed_constituent_bars"][:2]

    observation = observe_market_event_graph_runtime(metadata, context_ts=160.0)

    assert observation["status"] == "PARTIAL_SEQUENCE"
    assert observation["reason"] == "causal_partial_graph_observed"
    assert observation["partial_sequence_length"] == 2
    assert observation["partial_sequence_labels"] == [
        "breadth_down_1:HIGH",
        "index_breadth_divergence:LOW",
    ]
    assert observation["producer_status"] == "MISSING_OR_INVALID"
    assert observation["adapter_status"] == "MISSING_OR_INVALID"
    assert observation["graph_trigger_count"] == 0


def test_rejection_reasons_preserve_timestamp_and_coverage_failures():
    metadata = _metadata()
    metadata["completed_constituent_bars"] = [
        metadata["completed_constituent_bars"][0],
        _bar(100.0, 95.0, negative_count=25, index_ret1=-0.004),
        _bar(220.0, 210.0, negative_count=5, index_ret1=0.001, total=20),
    ]

    observation = observe_market_event_graph_runtime(metadata, context_ts=220.0)

    assert observation["status"] == "PARTIAL_SEQUENCE"
    assert observation["accepted_interval_count"] == 1
    assert observation["rejected_interval_count"] == 2
    assert observation["rejection_counts"] == {
        "constituent_coverage_below_minimum": 1,
        "timestamp_not_strictly_increasing": 1,
    }
    assert observation["partial_sequence_labels"] == ["breadth_down_1:HIGH"]
    assert observation["adapter_status"] == "MISSING_OR_INVALID"


def test_contract_mismatch_is_distinct_from_market_no_signal():
    metadata = _metadata()
    metadata["market_event_graph_dataset_sha256"] = "wrong"

    observation = observe_market_event_graph_runtime(metadata, context_ts=280.0)

    assert observation["status"] == "CONTRACT_INVALID"
    assert observation["reason"] == "frozen_contract_mismatch"
    assert observation["producer_status"] == "NOT_EVALUATED"
    assert observation["adapter_status"] == "NOT_EVALUATED"
    assert observation["graph_trigger_count"] == 0
