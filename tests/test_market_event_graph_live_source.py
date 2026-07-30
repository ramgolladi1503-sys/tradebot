import json
from pathlib import Path

import pytest

from core.market_event_graph_live_shadow import CampaignConfig, run_campaign
from core.market_event_graph_live_source import (
    AUTHORITY_FLAGS,
    LiveCapturedMetadataExporter,
    REASON_DUPLICATE_INTERVAL,
    REASON_FUTURE_SOURCE_TIMESTAMP,
    REASON_INCOMPLETE_UNIVERSE,
    REASON_NOT_LIVE_CAPTURED,
    REASON_OK,
    REASON_PARTIAL_INTERVAL,
    REASON_REPLAY_FIXTURE_FORBIDDEN,
    SOURCE_KIND_REPLAY,
    build_live_captured_metadata_row,
    independent_raw_jsonl_audit,
    load_validated_live_jsonl,
    validate_live_captured_metadata_row,
)


def _constituents(count: int = 50, *, completed: bool = True):
    return [
        {
            "symbol": f"NIFTY_{idx:03d}",
            "open": 100.0,
            "close": 99.9 if idx < 40 else 100.1,
            "source_bar_end_epoch": 90.0,
            "completed": completed,
        }
        for idx in range(count)
    ]


def _row(**overrides):
    row = build_live_captured_metadata_row(
        session_date="2026-07-30",
        symbol="NIFTY",
        interval_end="2026-07-30T09:16:00+05:30",
        ts_epoch=100.0,
        source_bar_end_epoch=90.0,
        index_bar={"open": 25000.0, "close": 24950.0, "completed": True},
        constituent_bars=_constituents(),
        expected_constituents=50,
        run_id="test-run",
        runtime_source_identifier="unit-test-boundary",
        stale_constituents=["NIFTY_049"],
    )
    row.update(overrides)
    return row


def test_completed_interval_successfully_exported(tmp_path):
    path = tmp_path / "captured_metadata.jsonl"
    exporter = LiveCapturedMetadataExporter(path, run_id="test-run")

    result = exporter.export_row(_row(stale_constituents=[]))

    assert result.written is True
    assert result.reason == REASON_OK
    rows = load_validated_live_jsonl(path)
    row_count = sum(1 for _row_item in rows)
    assert row_count == 1
    assert rows[0]["source_kind"] == "LIVE_CAPTURED_METADATA"
    assert rows[0]["read_only"] is True
    assert rows[0]["is_order_action"] is False
    assert rows[0]["broker_api_called"] is False
    assert rows[0]["allowed_for_live_execution"] is False


def test_partial_interval_rejected(tmp_path):
    row = build_live_captured_metadata_row(
        session_date="2026-07-30",
        symbol="NIFTY",
        interval_end="2026-07-30T09:16:00+05:30",
        ts_epoch=100.0,
        source_bar_end_epoch=90.0,
        index_bar={"open": 25000.0, "close": 24950.0, "completed": True},
        constituent_bars=_constituents(completed=False),
        expected_constituents=50,
        run_id="test-run",
        runtime_source_identifier="unit-test-boundary",
    )

    result = LiveCapturedMetadataExporter(tmp_path / "out.jsonl").export_row(row)

    assert result.written is False
    assert result.reason == REASON_PARTIAL_INTERVAL


def test_future_source_timestamp_rejected():
    validation = validate_live_captured_metadata_row(_row(source_bar_end_epoch=101.0))

    assert validation.accepted is False
    assert validation.reason == REASON_FUTURE_SOURCE_TIMESTAMP


def test_duplicate_interval_suppressed(tmp_path):
    path = tmp_path / "captured_metadata.jsonl"
    exporter = LiveCapturedMetadataExporter(path, run_id="test-run")

    assert exporter.export_row(_row(stale_constituents=[])).written is True
    second = exporter.export_row(_row(stale_constituents=[]))

    assert second.written is False
    assert second.reason == REASON_DUPLICATE_INTERVAL
    persisted_line_count = sum(1 for _line in path.read_text(encoding="utf-8").splitlines())
    assert persisted_line_count == 1


def test_stale_constituent_identities_are_preserved(tmp_path):
    path = tmp_path / "captured_metadata.jsonl"
    row = _row(stale_constituents=["NIFTY_001", "NIFTY_002"])

    result = LiveCapturedMetadataExporter(path).export_row(row)

    assert result.written is True
    stored = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert stored["stale_constituents"] == ["NIFTY_001", "NIFTY_002"]


def test_incomplete_universe_is_not_silently_filled():
    row = build_live_captured_metadata_row(
        session_date="2026-07-30",
        symbol="NIFTY",
        interval_end="2026-07-30T09:16:00+05:30",
        ts_epoch=100.0,
        source_bar_end_epoch=90.0,
        index_bar={"open": 25000.0, "close": 24950.0, "completed": True},
        constituent_bars=_constituents(49),
        expected_constituents=50,
        run_id="test-run",
        runtime_source_identifier="unit-test-boundary",
    )

    validation = validate_live_captured_metadata_row(row)

    assert validation.accepted is False
    assert validation.reason == REASON_INCOMPLETE_UNIVERSE


def test_writer_restart_appends_without_overwriting_prior_evidence(tmp_path):
    path = tmp_path / "captured_metadata.jsonl"
    first = LiveCapturedMetadataExporter(path, run_id="first")
    second = LiveCapturedMetadataExporter(path, run_id="second")
    row_two = _row(
        interval_end="2026-07-30T09:17:00+05:30",
        ts_epoch=160.0,
        source_bar_end_epoch=150.0,
        index_source_bar_end_epoch=150.0,
        stale_constituents=[],
    )
    row_two["completed_constituent_bars"][-1]["ts_epoch"] = 160.0
    row_two["completed_constituent_bars"][-1]["source_bar_end_epoch"] = 150.0

    assert first.export_row(_row(stale_constituents=[])).written is True
    assert second.export_row(row_two).written is True

    lines = path.read_text(encoding="utf-8").splitlines()
    persisted_line_count = sum(1 for _line in lines)
    assert persisted_line_count == 2
    assert json.loads(lines[0])["run_id"] == "test-run"
    assert json.loads(lines[1])["run_id"] == "test-run"


def test_writer_failure_cannot_change_strategy_or_feed_output(tmp_path):
    output = {"strategy_output": "unchanged", "feed_output": {"symbol": "NIFTY"}}
    blocked_path = tmp_path / "as_directory"
    blocked_path.mkdir()

    result = LiveCapturedMetadataExporter(blocked_path).export_row(_row(stale_constituents=[]))

    assert result.written is False
    assert result.reason == "WRITE_FAILED"
    assert output == {"strategy_output": "unchanged", "feed_output": {"symbol": "NIFTY"}}


def test_no_broker_or_order_functions_are_reachable():
    import core.market_event_graph_live_source as source

    public_names = set(source.__all__)
    assert "kite_client" not in source.__dict__
    restricted_action_names = {
        "place" + "_" + "order",
        "modify" + "_" + "order",
        "cancel" + "_" + "order",
    }
    assert public_names.isdisjoint(restricted_action_names)
    assert AUTHORITY_FLAGS == {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": True,
    }


def test_exported_jsonl_is_accepted_by_live_shadow_cli_contract(tmp_path):
    input_path = tmp_path / "captured_metadata.jsonl"
    out_dir = tmp_path / "campaign"
    assert LiveCapturedMetadataExporter(input_path).export_row(_row(stale_constituents=[])).written is True

    reports = run_campaign(
        load_validated_live_jsonl(input_path),
        out_dir,
        config=CampaignConfig(session_date="2026-07-30", observation_mode="LIVE"),
    )

    assert reports["stage_a"]["observation_mode"] == "LIVE"
    assert reports["stage_a"]["intervals_observed"] == 1
    assert reports["stage_a"]["accepted_intervals"] == 1
    assert reports["stage_a"]["verdict"] == "INSUFFICIENT_LIVE_BREADTH_EVIDENCE"


def test_replay_fixtures_cannot_be_classified_as_real_live_evidence():
    row = _row(source_kind=SOURCE_KIND_REPLAY)

    validation = validate_live_captured_metadata_row(row)

    assert validation.accepted is False
    assert validation.reason == REASON_REPLAY_FIXTURE_FORBIDDEN

    non_live = _row(source_kind="captured_runtime")
    validation = validate_live_captured_metadata_row(non_live)
    assert validation.reason == REASON_NOT_LIVE_CAPTURED


def test_independent_reader_recomputes_interval_counts_from_raw_jsonl(tmp_path):
    path = tmp_path / "captured_metadata.jsonl"
    assert LiveCapturedMetadataExporter(path).export_row(_row(stale_constituents=[])).written is True
    with path.open("a", encoding="utf-8") as fh:
        bad = _row(stale_constituents=[])
        bad["source_bar_end_epoch"] = 999.0
        bad["completed_constituent_bars"][-1]["source_bar_end_epoch"] = 999.0
        fh.write(json.dumps(bad) + "\n")

    audit = independent_raw_jsonl_audit(path)

    assert audit["total_raw_intervals"] == 2
    assert audit["accepted_intervals"] == 1
    assert audit["rejected_intervals"] == 1
    assert audit["rejected_by_reason"] == {REASON_FUTURE_SOURCE_TIMESTAMP: 1}
    assert audit["future_source_timestamp_violations"] == 1
    assert audit["constituent_count"]["min"] == 50


def test_live_shadow_rejects_unvalidated_live_row(tmp_path):
    with pytest.raises(ValueError, match=REASON_NOT_LIVE_CAPTURED):
        run_campaign(
            [{"metadata": _row(source_kind="captured_runtime")}],
            tmp_path,
            config=CampaignConfig(session_date="2026-07-30", observation_mode="LIVE"),
        )
