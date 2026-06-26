from __future__ import annotations


def test_fetch_option_chain_logs_error_on_live_failure(monkeypatch, tmp_path):
    import core.option_chain as oc
    from config import config as cfg

    # Route logs_dir() to a temp dir.
    monkeypatch.setattr(oc, "logs_dir", lambda: tmp_path, raising=False)

    # Force LIVE + require live quotes, and force a failure inside fetch_option_chain.
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)

    class _KC:
        def ensure(self):
            raise RuntimeError("boom")

        kite = None

    monkeypatch.setattr(oc, "kite_client", _KC(), raising=False)
    monkeypatch.setattr(oc, "_OPTION_CHAIN_ERROR_LAST_TS", {}, raising=False)

    chain = oc.fetch_option_chain("NIFTY", 100.0, strikes_around=1, force_synthetic=False, market_context={"execution_mode": "LIVE"})
    assert chain == []

    p = tmp_path / "option_chain_errors.jsonl"
    assert p.exists()
    txt = p.read_text(encoding="utf-8")
    assert "boom" in txt

