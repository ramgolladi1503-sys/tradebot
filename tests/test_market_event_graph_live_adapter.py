from core.candidate_pool_orchestrator import get_default_candidate_generators
from core.market_event_graph_live_adapter import (
    attach_market_event_graph_history,
    build_market_event_graph_history,
)


def _rows():
    return [
        {"event_label": "breadth_down_1:HIGH", "ts_epoch": 100.0, "completed": True},
        {"event_label": "index_breadth_divergence:LOW", "ts_epoch": 160.0, "completed": True},
        {"event_label": "breadth_down_1:LOW", "ts_epoch": 220.0, "completed": True},
    ]


def test_builds_canonical_history_from_completed_snapshots():
    history = build_market_event_graph_history(
        {"completed_constituent_breadth_snapshots": _rows()}
    )
    assert [row["event_label"] for row in history] == [
        "breadth_down_1:HIGH",
        "index_breadth_divergence:LOW",
        "breadth_down_1:LOW",
    ]
    assert all(row["completed"] is True for row in history)


def test_rejects_incomplete_unknown_and_missing_timestamp_rows():
    history = build_market_event_graph_history(
        {
            "completed_constituent_breadth_snapshots": [
                {"event_label": "breadth_down_1:HIGH", "ts_epoch": 100.0, "completed": False},
                {"event_label": "UNKNOWN", "ts_epoch": 160.0, "completed": True},
                {"event_label": "breadth_down_1:LOW", "completed": True},
            ]
        }
    )
    assert history == []


def test_attach_marks_ready_and_copies_metadata():
    source = {"other": "value", "completed_constituent_breadth_snapshots": _rows()}
    metadata = attach_market_event_graph_history(source)
    assert metadata["other"] == "value"
    assert metadata["market_event_graph_history_status"] == "READY"
    assert len(metadata["market_event_graph_history"]) == 3
    assert "market_event_graph_history" not in source


def test_default_candidate_pool_contains_shadow_graph_generator():
    names = {generator.__name__ for generator in get_default_candidate_generators()}
    assert "generate_market_event_graph_reversal_candidates" in names
