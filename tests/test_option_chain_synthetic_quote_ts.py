from __future__ import annotations

from config import config as cfg
from core.kite_client import kite_client
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


def test_synthetic_chain_in_sim_does_not_resolve_broker_expiry(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setattr(cfg, "ALLOW_SYNTHETIC_CHAIN", True, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(
        kite_client,
        "next_available_expiry",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("synthetic chain must not query broker expiry in SIM")),
    )

    chain = fetch_option_chain(
        "NIFTY",
        25000.0,
        force_synthetic=True,
        market_context={"execution_mode": "SIM", "market_open": False},
    )

    assert chain
    assert all(row.get("expiry") == row.get("expiry_date") for row in chain)
