from __future__ import annotations

import importlib


def test_feed_fd_trace_sampling_and_reset(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADEBOT_FEED_FD_TRACE", "1")
    monkeypatch.setenv("TRADEBOT_FEED_FD_TRACE_PATH", str(tmp_path / "fd_trace.jsonl"))
    monkeypatch.setenv("TRADEBOT_FEED_FD_TRACE_EVERY_N", "2")
    monkeypatch.setenv("TRADEBOT_FEED_FD_TRACE_DELTA", "5")
    monkeypatch.setenv("TRADEBOT_FEED_FD_TRACE_HIGH", "20")

    module = importlib.import_module("core.feed_fd_trace")
    module = importlib.reload(module)

    module.reset_trace(baseline_fd=10, path=tmp_path / "fd_trace.jsonl")

    assert module.should_sample(row_index=2, fd_count=10)
    assert not module.should_sample(row_index=1, fd_count=10)
    assert module.should_sample(row_index=1, fd_count=15)

    event = module.record_trace("test.stage", row_index=2, extra={"ok": True})
    assert event is not None
    assert event.stage == "test.stage"
    assert event.row_index == 2

    text = (tmp_path / "fd_trace.jsonl").read_text(encoding="utf-8").strip()
    assert text
