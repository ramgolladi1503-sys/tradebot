from config import config as cfg
from types import SimpleNamespace
from strategies.trade_builder import TradeBuilder

def test_trade_builder_returns_borderline_candidate_when_no_signal():
    tb = TradeBuilder()
    md = {
        "symbol": "NIFTY",
        "ltp": 25010.0,
        "vwap": 25010.0,
        "atr": 0.0,
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25000CE",
                "instrument_token": 123456,
                "ltp": 102.0,
                "bid": 101.5,
                "ask": 102.5,
            }
        ],
    }
    out = tb.build(md)
    assert out is not None
    assert out.get("candidate_status") == "advisory_only"
    assert out.get("execution_status") == "advisory_only"
    assert out.get("rank_score") is None
    assert out.get("soft_reject_seed_confidence") is not None


def test_trade_builder_strict_mode_drops_no_signal_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    tb = TradeBuilder()
    md = {
        "symbol": "NIFTY",
        "ltp": 25010.0,
        "vwap": 25010.0,
        "atr": 0.0,
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25000CE",
                "instrument_token": 123456,
                "ltp": 102.0,
                "bid": 101.5,
                "ask": 102.5,
            }
        ],
    }
    out = tb.build(md)
    assert out is None


def test_set_last_ranked_candidates_drops_invalid_rows(monkeypatch):
    monkeypatch.setattr(cfg, "TRADE_BUILDER_INVALID_RANKED_CANDIDATE_SAMPLE_LIMIT", 2, raising=False)
    tb = TradeBuilder()
    tb._set_last_ranked_candidates(
        [
            None,
            {
                "trade_id": "BAD-1",
                "strategy_family": "breakout",
                "candidate_status": "executable",
                "confidence": 0.7,
                "rank_score": 0.6,
            },
            {
                "trade_id": "GOOD-1",
                "symbol": "NIFTY",
                "strategy_family": "breakout",
                "candidate_status": "executable",
                "confidence": 0.7,
                "rank_score": 0.6,
            },
        ]
    )

    assert len(tb._last_ranked_candidates) == 1
    assert tb._last_ranked_candidates[0]["trade_id"] == "GOOD-1"


def test_candidate_decision_payload_preserves_nested_provenance():
    candidate = SimpleNamespace(
        quality_detail={
            "setup_regime_alignment_score": 0.35,
            "setup_structure_score": 0.55,
            "setup_thesis_score": 0.62,
            "trigger_base_score": 0.61,
            "entry_invalidation_score": 0.66,
            "entry_overextension_score": 0.58,
            "entry_timing_quality_score": 0.63,
            "candidate_quality_score": 0.61,
            "family_consensus_score": 0.47,
            "family_consensus_components": {"regime_alignment": 0.5},
            "family_survival_score": 0.52,
            "family_survival_components": {"setup_score": 0.61},
        },
        score_breakdown={
            "candidate_quality_score": 0.61,
            "family_consensus_score": 0.47,
            "family_consensus_components": {"regime_alignment": 0.5},
            "family_survival_score": 0.52,
            "family_survival_components": {"setup_score": 0.61},
        }
    )
    source_flags = {
        "candidate_quality_score": 0.61,
        "family_consensus_score": 0.47,
        "family_consensus_components": {"regime_alignment": 0.5},
        "family_survival_score": 0.52,
        "family_survival_components": {"setup_score": 0.61},
        "quality_detail": {
            "setup_regime_alignment_score": 0.35,
            "setup_structure_score": 0.55,
            "setup_thesis_score": 0.62,
            "trigger_base_score": 0.61,
            "entry_invalidation_score": 0.66,
            "entry_overextension_score": 0.58,
            "entry_timing_quality_score": 0.63,
            "candidate_quality_score": 0.61,
            "family_consensus_score": 0.47,
            "family_consensus_components": {"regime_alignment": 0.5},
            "family_survival_score": 0.52,
            "family_survival_components": {"setup_score": 0.61},
        },
        "decision_trace": {"candidate_quality_score": 0.61},
    }
    decision_trace = {"candidate_quality_score": 0.61}

    payload = TradeBuilder._candidate_decision_telemetry_payload(
        candidate,
        source_flags,
        decision_trace,
        candidate.score_breakdown,
    )

    assert payload["source_flags"] == source_flags
    assert payload["score_breakdown"] == candidate.score_breakdown
    assert payload["decision_trace"] == decision_trace
    assert payload["candidate_quality_score"] == 0.61
    assert payload["family_consensus_score"] == 0.47
    assert payload["family_consensus_components"] == {"regime_alignment": 0.5}
    assert payload["family_survival_score"] == 0.52
    assert payload["family_survival_components"] == {"setup_score": 0.61}
    assert payload["quality_detail"]["setup_regime_alignment_score"] == 0.35


def test_candidate_decision_payload_derives_setup_quality_when_quality_detail_missing():
    candidate = SimpleNamespace(
        setup_score=0.35,
        trigger_score=0.52,
        entry_quality_score=0.18,
        regime_conf=0.90,
        signal_score=0.68,
        family_survival_score=0.50,
        score_breakdown={},
    )
    source_flags = {
        "orb_state": {
            "window_bars": 3,
            "required_bars": 5,
        }
        ,
        "strike_offset": 5,
    }
    payload = TradeBuilder._candidate_decision_telemetry_payload(candidate, source_flags, {}, {})

    assert payload["quality_detail_source"] == "derived_from_setup_proxies"
    assert payload["quality_detail"]["setup_regime_alignment_score"] == 0.645
    assert payload["quality_detail"]["setup_structure_score"] == 0.5175
    assert payload["quality_detail"]["setup_thesis_score"] == 0.575
    assert payload["quality_detail"]["trigger_base_score"] == 0.52
    assert payload["quality_detail"]["entry_invalidation_score"] == 0.171
    assert payload["quality_detail"]["entry_overextension_score"] == 0.162
    assert payload["quality_detail"]["entry_timing_quality_score"] == 0.198
