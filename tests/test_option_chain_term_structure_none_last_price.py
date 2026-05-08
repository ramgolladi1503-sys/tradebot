from __future__ import annotations


def test_option_chain_term_structure_tolerates_none_last_price(monkeypatch):
    """
    Regression: LIVE/SIM quote payloads can occasionally include last_price=None for some instruments.
    Term-structure enrichment must not crash on `None <= 0`.
    """
    import core.option_chain as oc

    monkeypatch.setattr(oc.cfg, "KITE_USE_API", True, raising=False)
    monkeypatch.setattr(oc.cfg, "ENABLE_TERM_STRUCTURE", True, raising=False)
    monkeypatch.setattr(oc.cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(oc.cfg, "OPTION_CHAIN_LIVE_USE_WS_QUOTES", False, raising=False)

    # Minimal registry with one current-expiry strike + one next-expiry strike.
    curr = {"tradingsymbol": "CURRCE", "strike": 100.0, "instrument_type": "CE", "instrument_token": 111, "expiry": "2026-05-12"}
    nxt = {"tradingsymbol": "NEXTCE", "strike": 100.0, "instrument_type": "CE", "instrument_token": 112, "expiry": "2026-05-19"}

    monkeypatch.setattr(
        oc,
        "build_option_registry",
        lambda **kwargs: {
            "segment": "NFO-OPT",
            "instruments": [curr, nxt],
            "available_expiries": [],
        },
        raising=False,
    )
    monkeypatch.setattr(oc, "_choose_expiry_by_mode", lambda *a, **k: oc._coerce_expiry_date("2026-05-12"), raising=False)
    monkeypatch.setattr(oc, "select_registry_next_expiry", lambda *a, **k: oc._coerce_expiry_date("2026-05-19"), raising=False)

    class _KC:
        kite = object()

        def ensure(self):
            return None

        def instruments_cached(self, exchange, ttl_sec=3600):
            return [curr, nxt]

        def quote(self, tradingsymbols):
            out = {}
            for ts in tradingsymbols:
                if ts.endswith(":CURRCE"):
                    out[ts] = {
                        "last_price": 10.0,
                        "depth": {"buy": [{"price": 9.9, "quantity": 1}], "sell": [{"price": 10.1, "quantity": 1}]},
                        "timestamp": 1000.0,
                    }
                else:
                    # The regression: last_price can be None on some legs.
                    out[ts] = {"last_price": None, "depth": {}, "timestamp": 1000.0}
            return out

    monkeypatch.setattr(oc, "kite_client", _KC(), raising=False)

    chain = oc.fetch_option_chain("NIFTY", 24200.0, strikes_around=0, force_synthetic=False, market_context={"execution_mode": "SIM"})
    assert isinstance(chain, list)

