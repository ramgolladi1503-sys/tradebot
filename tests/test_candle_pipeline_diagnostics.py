import json
from datetime import datetime, timezone


def test_diagnostics_are_bounded_and_compact(tmp_path, monkeypatch):
    import core.candle_pipeline_diagnostics as diag

    target = tmp_path / "diagnostics" / "trace.jsonl"
    monkeypatch.setattr(diag, "TRACE_PATH", target)
    diag.reset_diagnostic_dedupe_for_tests()

    kwargs = dict(
        symbol="NIFTY", timeframe="1m", stage="T3_IN_PROGRESS_BAR",
        source_event_ts=datetime.now(timezone.utc), bar_ts="2026-08-12T05:30:00Z",
        bar_state="IN_PROGRESS", bar_count=3, producer="test",
    )
    assert diag.emit_candle_pipeline_event(**kwargs) is True
    assert diag.emit_candle_pipeline_event(**kwargs) is False

    row = json.loads(target.read_text().strip())
    assert row["read_only"] is True
    assert row["is_order_action"] is False
    assert row["symbol"] == "NIFTY"
    assert "open" not in row and "high" not in row and "close" not in row


def test_ohlc_results_are_unchanged_by_diagnostics(monkeypatch):
    from core.ohlc_buffer import OhlcBuffer

    class Noop:
        def __call__(self, **kwargs):
            return False

    monkeypatch.setattr("core.candle_pipeline_diagnostics.emit_candle_pipeline_event", Noop())
    buffer = OhlcBuffer()
    first = buffer.update_tick("NIFTY", 100.0, ts=1_700_000_000.0)
    second = buffer.update_tick("NIFTY", 101.0, ts=1_700_000_061.0)
    assert first["accepted"] is True
    assert second["accepted"] is True
    assert [bar["close"] for bar in buffer.get_bars("NIFTY")] == [100.0, 101.0]
