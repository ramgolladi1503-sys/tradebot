from __future__ import annotations

import logging

from strategies import trade_builder


def test_option_chain_debug_logging_disabled_by_default(monkeypatch, caplog):
    monkeypatch.delenv("TRADEBOT_DEBUG_OPTION_CHAIN", raising=False)
    caplog.set_level(logging.DEBUG)

    trade_builder._log_option_chain_debug("option_chain_debug_message")

    assert "option_chain_debug_message" not in caplog.text


def test_option_chain_debug_logging_enabled_with_env_flag(monkeypatch, caplog):
    monkeypatch.setenv("TRADEBOT_DEBUG_OPTION_CHAIN", "1")
    caplog.set_level(logging.DEBUG)

    trade_builder._log_option_chain_debug("option_chain_debug_message")

    assert "option_chain_debug_message" in caplog.text


def test_advisory_debug_logging_enabled_with_env_flag(monkeypatch, caplog):
    monkeypatch.setenv("TRADEBOT_DEBUG_ADVISORY", "true")
    caplog.set_level(logging.DEBUG)

    trade_builder._log_advisory_debug("advisory_debug_message")

    assert "advisory_debug_message" in caplog.text
