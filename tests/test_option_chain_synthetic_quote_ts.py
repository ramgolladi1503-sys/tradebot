from __future__ import annotations

from config import config as cfg
from core.option_chain import fetch_option_chain


def test_synthetic_chain_sets_quote_timestamps(monkeypatch):
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", True, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)

    chain = fetch_option_chain(
        "NIFTY",
        25000.0,
        force_synthetic=True,
        market_context={"execution_mode": "PAPER", "market_open": False},
    )

    assert chain
    assert all(row.get("quote_ts_epoch") is not None for row in chain)
    assert all(float(row.get("quote_age_sec")) == 0.0 for row in chain)


def test_synthetic_chain_nested_context_marks_planning_source(monkeypatch):
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", True, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    chain = fetch_option_chain(
        "NIFTY",
        25000.0,
        force_synthetic=True,
        market_context={"market_context": {"execution_mode": "PAPER", "market_open": True}},
    )

    assert chain
    assert all(row.get("quote_ts_epoch") is not None for row in chain)
    assert all(float(row.get("quote_age_sec")) == 0.0 for row in chain)
    assert all(str(row.get("quote_source")) == "synthetic_offhours" for row in chain)
    assert all(bool(row.get("planning_only")) is True for row in chain)
