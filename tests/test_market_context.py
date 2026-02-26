from config import config as cfg
from core.market_context import derive_market_context, is_offhours


def test_derive_market_context_uses_nested_market_context_payload(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "OFFHOURS_FORCE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "OFFHOURS_FORCE_DISABLE", False, raising=False)

    ctx = derive_market_context(
        {
            "market_context": {
                "execution_mode": "PAPER",
                "market_open": False,
                "segment": "NSE_FNO",
            }
        }
    )

    assert ctx.mode == "PAPER"
    assert ctx.planning_only is True
    assert ctx.allow_stale_quotes is True
    assert ctx.require_live_quotes is False


def test_is_offhours_respects_nested_live_closed_payload(monkeypatch):
    monkeypatch.setattr(cfg, "OFFHOURS_FORCE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "OFFHOURS_FORCE_DISABLE", False, raising=False)

    payload = {
        "market_context": {
            "execution_mode": "LIVE",
            "market_open": False,
            "segment": "NSE_FNO",
        }
    }
    ctx = derive_market_context(payload)

    assert ctx.mode == "OFFHOURS"
    assert is_offhours(payload) is True
    assert ctx.require_live_quotes is False


def test_top_level_context_overrides_nested_market_context(monkeypatch):
    monkeypatch.setattr(cfg, "OFFHOURS_FORCE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "OFFHOURS_FORCE_DISABLE", False, raising=False)

    ctx = derive_market_context(
        {
            "execution_mode": "LIVE",
            "market_open": True,
            "segment": "NSE_FNO",
            "market_context": {
                "execution_mode": "PAPER",
                "market_open": False,
                "segment": "NSE_CASH",
            },
        }
    )

    assert ctx.mode == "LIVE"
    assert ctx.is_market_open is True
    assert ctx.require_live_quotes is True
