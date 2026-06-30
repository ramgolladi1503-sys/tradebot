import pytest
from config import config as cfg
import core.ci_finish_contracts as ci_finish

def test_strategy_no_signal_label(monkeypatch):
    
    # Enable fallback and LIVE mode
    orig_fallback = getattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_ENABLE", False)
    orig_exec = getattr(cfg, "EXECUTION_MODE", "SIM")
    orig_trade = getattr(cfg, "TRADING_MODE", "PAPER")
    
    setattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_ENABLE", True)
    setattr(cfg, "EXECUTION_MODE", "LIVE")
    setattr(cfg, "TRADING_MODE", "LIVE")
    
    try:
        # Install the actual patch
        ci_finish.install()
        
        from strategies.trade_builder import TradeBuilder
        import strategies.trade_builder as tb_module
        
        # We need a way to see the context. The real TradeBuilder has self._reject_ctx.
        tb_instance = TradeBuilder()
        tb_instance._reject_ctx = {}
        
        # monkeypatch the original build method to return None.
        # But wait, ci_finish.install() replaced TradeBuilder.build.
        # How do we bypass the INNER function to return None?
        # We can just monkeypatch tb_module._trade_builder_build or whatever it replaced.
        # But ci_finish uses a closure: `out = base_fn(self, market_data, *args, **kwargs)`
        # `base_fn` is bound inside the closure. We can't easily mock it.
        # Wait, we CAN mock `_derive_candidates` or whatever the real TradeBuilder.build calls
        # so that it returns an empty list, which causes `build()` to return `None`.
        
        # Let's mock `_is_executable` or something to force return None?
        # A simpler way: TradeBuilder.build returns None if there is no setup or if market is closed.
        
        market_data = {
            "execution_mode": "LIVE",
            "market_open": True,
            "symbol": "NIFTY",
            # missing a lot of things, real TradeBuilder will return None
        }
        
        # Calling the real patched build method
        res = tb_instance.build(market_data)
        
        assert res is None
        assert tb_instance._reject_ctx.get("reason") == "STRATEGY_NO_SIGNAL"
        assert tb_instance._reject_ctx.get("reason") != "lifecycle_gate_fail"
        
    finally:
        setattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_ENABLE", orig_fallback)
        setattr(cfg, "EXECUTION_MODE", orig_exec)
        setattr(cfg, "TRADING_MODE", orig_trade)
