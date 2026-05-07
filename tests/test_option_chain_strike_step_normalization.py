import types


def test_option_chain_infer_atm_strike_step_none_does_not_throw(monkeypatch):
    """
    Regression: LIVE option chain was returning [] due to a TypeError:
      "'<=' not supported between instances of 'NoneType' and 'int'"
    Root cause: step=None reaching _infer_atm_strike and compared with <=.
    """
    from core import option_chain

    # Force config to contain an explicit None (integration/config regressions can do this).
    monkeypatch.setattr(option_chain.cfg, "STRIKE_STEP_BY_SYMBOL", {"NIFTY": None}, raising=False)
    monkeypatch.setattr(option_chain.cfg, "STRIKE_STEP", 50, raising=False)

    step = option_chain._normalize_strike_step("NIFTY", None)
    assert step == 50

    atm = option_chain._infer_atm_strike(24368.25, step)
    assert atm == 24350


def test_option_chain_normalize_step_invalid_returns_none(monkeypatch):
    from core import option_chain

    monkeypatch.setattr(option_chain.cfg, "STRIKE_STEP_BY_SYMBOL", {"NIFTY": "nope"}, raising=False)
    monkeypatch.setattr(option_chain.cfg, "STRIKE_STEP", None, raising=False)

    assert option_chain._normalize_strike_step("NIFTY", None) is None

