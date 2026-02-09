from types import SimpleNamespace

import pytest

from core.trade_schema import build_instrument_id, validate_trade_identity


def test_trade_identity_requires_fields():
    ok, reason = validate_trade_identity("NIFTY", "OPT", None, 22000, "CE")
    assert ok is False
    assert reason == "missing_expiry"


def test_build_instrument_id_ok():
    inst = build_instrument_id("NIFTY", "OPT", "2026-02-14", 22000, "CE")
    assert inst == "NIFTY|2026-02-14|22000|CE"
