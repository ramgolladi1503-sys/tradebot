from types import SimpleNamespace

import core.orchestrator as orchestrator_mod


def _trade(**overrides):
    base = {
        "trade_id": "T-QUEUE-1",
        "symbol": "NIFTY",
        "strategy": "CORE",
        "instrument": "OPT",
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAR25000CE",
        "expiry": "2026-03-26",
        "expiry_date": "2026-03-26",
        "strike": 25000,
        "option_type": "CE",
        "right": "CE",
        "instrument_id": "NIFTY26MAR25000CE",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_queue_review_candidate_allows_valid_contract(monkeypatch):
    queued = []
    rejected = []

    monkeypatch.setattr(orchestrator_mod, "add_to_queue", lambda trade, queue_path=None, extra=None: queued.append((trade, queue_path, extra or {})))
    monkeypatch.setattr(orchestrator_mod, "append_reject_reasons", lambda **kwargs: rejected.append(dict(kwargs)))

    ok, prepared = orchestrator_mod._queue_review_candidate(
        _trade(),
        extra={"tier": "MAIN"},
        reject_source="unit_test_valid",
    )

    assert ok is True
    assert prepared.tradingsymbol == "NIFTY26MAR25000CE"
    assert len(queued) == 1
    assert rejected == []


def test_queue_review_candidate_attempts_enrichment_for_missing_tradingsymbol(monkeypatch):
    queued = []
    rejected = []
    calls = {"count": 0}

    def _enrich(entry):
        calls["count"] += 1
        enriched = dict(entry)
        enriched["tradingsymbol"] = "NIFTY26MAR25000CE"
        enriched["expiry_date"] = "2026-03-26"
        enriched["expiry"] = "2026-03-26"
        return enriched

    monkeypatch.setattr(orchestrator_mod, "_enrich_contract_identity", _enrich)
    monkeypatch.setattr(orchestrator_mod, "add_to_queue", lambda trade, queue_path=None, extra=None: queued.append((trade, queue_path, extra or {})))
    monkeypatch.setattr(orchestrator_mod, "append_reject_reasons", lambda **kwargs: rejected.append(dict(kwargs)))

    ok, prepared = orchestrator_mod._queue_review_candidate(
        _trade(tradingsymbol=None, expiry_date=None, expiry=None),
        reject_source="unit_test_enrich",
    )

    assert ok is True
    assert calls["count"] == 1
    assert prepared.tradingsymbol == "NIFTY26MAR25000CE"
    assert prepared.expiry_date == "2026-03-26"
    assert len(queued) == 1
    assert rejected == []


def test_queue_review_candidate_rejects_unresolved_contract_before_queue(monkeypatch):
    queued = []
    rejected = []

    monkeypatch.setattr(orchestrator_mod, "add_to_queue", lambda *args, **kwargs: queued.append((args, kwargs)))
    monkeypatch.setattr(orchestrator_mod, "append_reject_reasons", lambda **kwargs: rejected.append(dict(kwargs)))
    monkeypatch.setattr(orchestrator_mod, "_enrich_contract_identity", lambda entry: dict(entry))

    ok, prepared = orchestrator_mod._queue_review_candidate(
        _trade(tradingsymbol=None, expiry_date=None, expiry=None),
        reject_source="unit_test_reject",
    )

    assert ok is False
    assert prepared.instrument_token == 12345
    assert queued == []
    assert len(rejected) == 1
    assert rejected[0]["reasons"] == ["unresolved_contract"]
    assert rejected[0]["extra"]["missing_fields"] == ["tradingsymbol", "expiry_date"]
