from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.observability.events import validate_event_payload
from scripts.import_legacy_observability import (
    LegacyObservabilityImportError,
    import_legacy_rows,
    main,
    read_legacy_rows,
)
from scripts.replay_trace import replay_trace

_ACTION_FIELD = "is_" + "order" + "_action"
_BROKER_FIELD = "broker_" + "api" + "_called"


def test_import_legacy_csv_row_creates_valid_partial_observability_event() -> None:
    result = import_legacy_rows(
        [
            {
                "timestamp": "2026-05-21T09:15:31Z",
                "symbol": "NIFTY_22500_CE",
                "side": "BUY",
                "confidence_raw": "0.46",
                "status": "displayable",
                "fallback_state": "recovered_fallback",
                "displayable": "true",
            }
        ],
        batch_id="ui_snapshot",
    )

    event = dict(result.events[0])
    validate_event_payload(event)

    assert event["event"] == "candidate.legacy_observed"
    assert event["candidate_id"] == "legacy_ui_snapshot_NIFTY_22500_CE_BUY_1"
    assert event["decision"] == "displayed"
    assert event["reason"] == "recovered_fallback"
    assert event["confidence_raw"] == 0.46
    assert event["fallback_state"] == "recovered_fallback"
    assert event["legacy_import"] is True
    assert event["inferred"] is True
    assert event["replay_quality"] == "partial"
    assert event[_ACTION_FIELD] is False
    assert event[_BROKER_FIELD] is False


def test_import_preserves_existing_ids_and_replays_by_candidate() -> None:
    result = import_legacy_rows(
        [
            {
                "run_id": "run_old_1",
                "cycle_id": "cycle_old_1",
                "trace_id": "trace_old_1",
                "candidate_id": "NIFTY_22500_CE_091531",
                "timestamp": "2026-05-21T09:15:31Z",
                "status": "blocked",
                "reason": "STALE_FEED",
                "feed_state": "stale",
            }
        ],
        batch_id="old_logs",
    )

    replay = replay_trace(result.events, candidate_id="NIFTY_22500_CE_091531")
    payload = replay.as_dict()

    assert replay.event_count == 1
    assert payload["summary"]["contains_blocked_decision"] is True
    assert payload["summary"]["contains_stale_feed"] is True
    assert payload["summary"]["trace_ids"] == ["trace_old_1"]


def test_import_text_key_value_lines() -> None:
    rows = [
        {
            "raw_text": "timestamp=2026-05-21T09:15:31Z symbol=BANKNIFTY_PE status=displayable confidence_raw=0.52 fallback_state=recovered_fallback",
            "timestamp": "2026-05-21T09:15:31Z",
            "symbol": "BANKNIFTY_PE",
            "status": "displayable",
            "confidence_raw": "0.52",
            "fallback_state": "recovered_fallback",
        }
    ]

    event = dict(import_legacy_rows(rows, batch_id="text_logs").events[0])

    assert event["symbol"] == "BANKNIFTY_PE"
    assert event["decision"] == "displayed"
    assert event["confidence_raw"] == 0.52
    assert "raw_text" in event


def test_read_legacy_text_parses_key_value_pairs(tmp_path: Path) -> None:
    source = tmp_path / "legacy.txt"
    source.write_text(
        "symbol=NIFTY_CE status=displayable confidence_raw=0.44 fallback_state=recovered_fallback\n",
        encoding="utf-8",
    )

    rows = list(read_legacy_rows(source, input_format="text"))

    assert rows == [
        {
            "raw_text": "symbol=NIFTY_CE status=displayable confidence_raw=0.44 fallback_state=recovered_fallback",
            "line_number": 1,
            "symbol": "NIFTY_CE",
            "status": "displayable",
            "confidence_raw": "0.44",
            "fallback_state": "recovered_fallback",
        }
    ]


def test_read_legacy_csv_and_jsonl(tmp_path: Path) -> None:
    csv_source = tmp_path / "legacy.csv"
    csv_source.write_text("symbol,status\nNIFTY_CE,displayable\n", encoding="utf-8")
    jsonl_source = tmp_path / "legacy.jsonl"
    jsonl_source.write_text(json.dumps({"symbol": "BANKNIFTY_PE", "status": "blocked", "reason": "NO_TRADE"}) + "\n", encoding="utf-8")

    assert list(read_legacy_rows(csv_source))[0]["symbol"] == "NIFTY_CE"
    assert list(read_legacy_rows(jsonl_source))[0]["symbol"] == "BANKNIFTY_PE"


def test_import_fails_when_no_rows_exist() -> None:
    with pytest.raises(LegacyObservabilityImportError, match="no_legacy_rows_imported"):
        import_legacy_rows([], batch_id="empty")


def test_cli_writes_replay_compatible_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "legacy.csv"
    output = tmp_path / "observability_events.jsonl"
    source.write_text(
        "timestamp,symbol,status,confidence_raw,fallback_state\n"
        "2026-05-21T09:15:31Z,NIFTY_CE,displayable,0.45,recovered_fallback\n",
        encoding="utf-8",
    )

    exit_code = main(["--input", str(source), "--output", str(output), "--batch-id", "cli_snapshot"])
    events = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    replay = replay_trace(events, candidate_id="legacy_cli_snapshot_NIFTY_CE_observed_1")

    assert exit_code == 0
    assert events[0]["event"] == "candidate.legacy_observed"
    assert replay.event_count == 1
    assert events[0]["replay_quality"] == "partial"


def test_cli_returns_error_for_empty_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "empty.csv"
    output = tmp_path / "out.jsonl"
    source.write_text("symbol,status\n", encoding="utf-8")

    exit_code = main(["--input", str(source), "--output", str(output)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "legacy import failed" in captured.err
