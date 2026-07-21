import pytest
@pytest.mark.xfail(strict=True, reason="bug confirmed")
def test_suspect_12_timeout_mismatch():
    import inspect
    from core.option_backtest.engine import OptionBacktestEngine
    
    source_code = inspect.getsource(OptionBacktestEngine._simulate_exit)
    
    # Intended contract: It must NOT create a fake candle by overwriting the timestamp of an old candle.
    assert 'timeout_candle["timestamp"] = max_exit_ts' not in source_code, "Intended contract: Must not overwrite timestamp of stale prices"
