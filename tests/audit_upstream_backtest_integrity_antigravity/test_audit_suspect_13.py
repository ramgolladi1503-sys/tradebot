import pytest
@pytest.mark.xfail(strict=True, reason="bug confirmed")
def test_suspect_13_false_wfa():
    import inspect
    from core.backtesting.wfa import WalkForwardAnalyzer
    from core.backtest_elite import VectorizedBacktestEngine
    
    engine_source = inspect.getsource(VectorizedBacktestEngine.generate_signals_vectorized)
    
    # Intended contract: Indicators must be calculated BEFORE splitting train/test, so we don't dropna() on test_df
    # OR the test_df must include warm-up data.
    # We assert that add_indicators is NOT called on the already-sliced test_df.
    assert 'add_indicators(self.data)' not in engine_source, "Intended contract: Must not compute indicators on disjoint test slice"
