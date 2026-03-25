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


def test_queue_review_candidate_allows_unresolved_contract_for_analytics(monkeypatch):
    queued = []
    rejected = []

    monkeypatch.setattr(orchestrator_mod, "add_to_queue", lambda trade, queue_path=None, extra=None: queued.append((trade, queue_path, extra or {})))
    monkeypatch.setattr(orchestrator_mod, "append_reject_reasons", lambda **kwargs: rejected.append(dict(kwargs)))
    monkeypatch.setattr(orchestrator_mod, "_enrich_contract_identity", lambda entry: dict(entry))

    ok, prepared = orchestrator_mod._queue_review_candidate(
        _trade(tradingsymbol=None, expiry_date=None, expiry=None),
        reject_source="unit_test_analytics",
        allow_unresolved_for_analytics=True,
        extra={"tier": "ANALYTICS"},
    )

    assert ok is True
    assert prepared.instrument_token == 12345
    assert len(queued) == 1
    assert queued[0][2]["tier"] == "ANALYTICS"
    assert rejected == []


def test_queue_rejected_candidate_for_analytics_queues_top_ranked_candidate(monkeypatch):
    captured = []

    def _append(paths, payload):
        captured.append((paths, payload))

    monkeypatch.setattr(orchestrator_mod, "_append_review_jsonl", _append)
    monkeypatch.setattr(orchestrator_mod, "rejected_candidates_paths", lambda: ["rejected.jsonl"])
    monkeypatch.setattr(
        orchestrator_mod,
        "project_advisory_row",
        lambda trade, extra=None: {"trade_id": trade.trade_id, "symbol": trade.symbol, **(extra or {})},
    )
    monkeypatch.setattr(orchestrator_mod.cfg, "QUEUE_REJECTED_CANDIDATES_ENABLE", True, raising=False)
    monkeypatch.setattr(orchestrator_mod.cfg, "QUEUE_REJECTED_CANDIDATES_FORCE_ADVISORY", True, raising=False)

    ok, prepared = orchestrator_mod._queue_rejected_candidate_for_analytics(
        [
            _trade(trade_id="T-RANKED-1"),
            _trade(trade_id="T-RANKED-2"),
        ],
        gate_reasons=["HIST_EMPTY"],
        reject_reason="no_trade_generated",
        reject_source="unit_test_ranked_reject",
        extra={"decision_stage": "trade_builder_gate"},
    )

    assert ok is True
    assert prepared["trade_id"] == "T-RANKED-1"
    assert len(captured) == 1
    assert captured[0][1]["decision_stage"] == "trade_builder_gate"
    assert captured[0][1]["execution_blocked"] is True
    assert captured[0][1]["execution_block_reason"] == "no_trade_generated"
    assert captured[0][1]["permission"] == "ADVISORY_ONLY"
    assert captured[0][1]["final_action"] == "ADVISORY_ONLY"
    assert captured[0][1]["analytics_only"] is True


def test_queue_rejected_candidate_for_analytics_skips_excluded_trade_ids(monkeypatch):
    captured = []

    def _append(paths, payload):
        captured.append((paths, payload))

    monkeypatch.setattr(orchestrator_mod, "_append_review_jsonl", _append)
    monkeypatch.setattr(orchestrator_mod, "rejected_candidates_paths", lambda: ["rejected.jsonl"])
    monkeypatch.setattr(
        orchestrator_mod,
        "project_advisory_row",
        lambda trade, extra=None: {"trade_id": trade.trade_id, "symbol": trade.symbol, **(extra or {})},
    )
    monkeypatch.setattr(orchestrator_mod.cfg, "QUEUE_REJECTED_CANDIDATES_ENABLE", True, raising=False)

    ok, prepared = orchestrator_mod._queue_rejected_candidate_for_analytics(
        [
            _trade(trade_id="T-RANKED-1"),
            _trade(trade_id="T-RANKED-2"),
        ],
        gate_reasons=["HIST_EMPTY"],
        reject_reason="no_trade_generated",
        reject_source="unit_test_ranked_reject",
        exclude_trade_ids={"T-RANKED-1"},
    )

    assert ok is True
    assert prepared["trade_id"] == "T-RANKED-2"
    assert len(captured) == 1


def test_queue_prebuilder_gate_candidate_for_analytics_builds_fallback_candidate(monkeypatch):
    queued = []

    def _queue(trade, **kwargs):
        queued.append((trade, kwargs))
        return True, trade

    monkeypatch.setattr(orchestrator_mod, "_queue_review_candidate", _queue)
    monkeypatch.setattr(orchestrator_mod.cfg, "QUEUE_PREBUILDER_GATE_CANDIDATES_ENABLE", True, raising=False)

    ok, prepared = orchestrator_mod._queue_prebuilder_gate_candidate_for_analytics(
        {
            "symbol": "SENSEX",
            "instrument": "OPT",
            "ltp": 7419.05,
        },
        gate_reasons=["HIST_EMPTY"],
        reject_reason="pre_builder_gate",
        reject_source="unit_test_prebuilder_gate",
    )

    assert ok is True
    assert prepared["symbol"] == "SENSEX"
    assert prepared["strategy_family"] == "fallback"
    assert prepared["candidate_type"] == "fallback"
    assert prepared["confidence"] == 0.1
    assert len(queued) == 1
    assert queued[0][1]["allow_unresolved_for_analytics"] is True
    assert queued[0][1]["reject_source"] == "unit_test_prebuilder_gate"
    assert queued[0][1]["extra"]["execution_blocked"] is True
    assert queued[0][1]["extra"]["execution_block_reason"] == "pre_builder_gate"
    assert queued[0][1]["extra"]["final_action"] == "ADVISORY_ONLY"


def test_queue_invalid_snapshot_candidate_for_analytics_builds_fallback_candidate(monkeypatch):
    queued = []

    def _queue(trade, **kwargs):
        queued.append((trade, kwargs))
        return True, trade

    monkeypatch.setattr(orchestrator_mod, "_queue_review_candidate", _queue)
    monkeypatch.setattr(orchestrator_mod.cfg, "QUEUE_INVALID_SNAPSHOT_CANDIDATES_ENABLE", True, raising=False)

    ok, prepared = orchestrator_mod._queue_invalid_snapshot_candidate_for_analytics(
        {
            "symbol": "BANKNIFTY",
            "instrument": "OPT",
            "invalid_reason": "historical_empty",
        },
        gate_reasons=["historical_empty", "invalid_market_snapshot"],
        reject_reason="historical_empty",
        reject_source="unit_test_invalid_snapshot",
    )

    assert ok is True
    assert prepared["symbol"] == "BANKNIFTY"
    assert prepared["strategy"] == "INVALID_SNAPSHOT_FALLBACK"
    assert prepared["strategy_family"] == "fallback"
    assert prepared["candidate_type"] == "fallback"
    assert prepared["setup_variant"] == "invalid_snapshot"
    assert prepared["trade_id"].startswith("INVALID_SNAPSHOT-BANKNIFTY-")
    assert len(queued) == 1
    assert queued[0][1]["allow_unresolved_for_analytics"] is True
    assert queued[0][1]["reject_source"] == "unit_test_invalid_snapshot"
    assert queued[0][1]["extra"]["decision_stage"] == "invalid_snapshot"
    assert queued[0][1]["extra"]["execution_blocked"] is True
    assert queued[0][1]["extra"]["execution_block_reason"] == "historical_empty"
