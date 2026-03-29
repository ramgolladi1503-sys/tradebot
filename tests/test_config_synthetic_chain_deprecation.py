from __future__ import annotations

import importlib
import logging


def test_allow_synthetic_chain_remains_effective_when_deprecated_flag_is_set(monkeypatch, caplog):
    import config.config as mod

    monkeypatch.setenv("ALLOW_SYNTHETIC_CHAIN", "false")
    monkeypatch.setenv("FORCE_SYNTH_CHAIN_ON_FAIL", "true")

    with caplog.at_level(logging.WARNING):
        importlib.reload(mod)

    assert mod.ALLOW_SYNTHETIC_CHAIN is False
    assert mod.FORCE_SYNTH_CHAIN_ON_FAIL is True
    assert "CONFIG_DEPRECATED key=FORCE_SYNTH_CHAIN_ON_FAIL" in caplog.text
    assert "effective_runtime_control=ALLOW_SYNTHETIC_CHAIN" in caplog.text


def test_allow_synthetic_chain_true_is_honored_even_if_deprecated_flag_disagrees(monkeypatch, caplog):
    import config.config as mod

    monkeypatch.setenv("ALLOW_SYNTHETIC_CHAIN", "true")
    monkeypatch.setenv("FORCE_SYNTH_CHAIN_ON_FAIL", "false")

    with caplog.at_level(logging.WARNING):
        importlib.reload(mod)

    assert mod.ALLOW_SYNTHETIC_CHAIN is True
    assert mod.FORCE_SYNTH_CHAIN_ON_FAIL is False
    assert "CONFIG_DEPRECATED key=FORCE_SYNTH_CHAIN_ON_FAIL" in caplog.text
