import json

from core import campaign_raw_diagnostics as diagnostics


def test_predecode_and_callback_diagnostics_are_bounded_and_campaign_scoped(tmp_path, monkeypatch):
    root = tmp_path / "run"
    monkeypatch.setenv("UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE", "true")
    monkeypatch.setenv("UNIFIED_LIVE_VALIDATION_PR748_756_EVIDENCE_ROOT", str(root))
    monkeypatch.setenv("UNIFIED_LIVE_VALIDATION_PR748_756_RUN_ID", "run-1")
    monkeypatch.setenv("UNIFIED_LIVE_VALIDATION_PR748_756_SESSION_DATE", "2026-08-03")
    monkeypatch.setenv("UNIFIED_LIVE_VALIDATION_PR748_756_COMMIT_SHA", "a" * 40)

    diagnostics.observe_raw_message(b"binary", True)
    start = diagnostics.on_ticks_entry(2)
    diagnostics.on_ticks_exit(start)
    diagnostics.shutdown()

    path = root / "live" / "predecode_raw_message_timeline.jsonl"
    assert path.is_file()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows
    row = rows[-1]
    assert row["raw_message_count"] == 1
    assert row["binary_message_count"] == 1
    assert row["on_ticks_entry_count"] == 1
    assert row["on_ticks_exit_count"] == 1
    assert row["run_id"] == "run-1"
    assert "binary" not in row
