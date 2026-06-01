from __future__ import annotations

from core.runtime_ranking_quality_evidence import build_ranking_quality_evidence_payload


def test_score_compression_detected_for_real_candidates():
    rows = [
        {"trade_id": "T1", "symbol": "NIFTY", "final_score": 0.50, "execution_ok": True, "quote_source": "option_chain_live"},
        {"trade_id": "T2", "symbol": "NIFTY", "final_score": 0.505, "execution_ok": True, "quote_source": "option_chain_live"},
        {"trade_id": "T3", "symbol": "NIFTY", "final_score": 0.51, "execution_ok": True, "quote_source": "option_chain_live"},
    ]
    payload = build_ranking_quality_evidence_payload(
        candidates=rows,
        phase2_state="WATCHLIST",
        cycle_primary_reason=None,
        phase2_min_enter_score=0.70,
    )
    assert payload["score_compression_detected"] is True


def test_meaningful_separation_not_compressed():
    rows = [
        {"trade_id": "T1", "symbol": "NIFTY", "final_score": 0.20, "execution_ok": True, "quote_source": "option_chain_live"},
        {"trade_id": "T2", "symbol": "NIFTY", "final_score": 0.55, "execution_ok": True, "quote_source": "option_chain_live"},
        {"trade_id": "T3", "symbol": "NIFTY", "final_score": 0.90, "execution_ok": True, "quote_source": "option_chain_live"},
    ]
    payload = build_ranking_quality_evidence_payload(
        candidates=rows,
        phase2_state="WATCHLIST",
        cycle_primary_reason=None,
        phase2_min_enter_score=0.70,
    )
    assert payload["score_compression_detected"] is False
    assert payload["top_score_gap_to_enter_threshold"] < 0


def test_fallback_rows_counted_separately():
    rows = [
        {"trade_id": "T1", "symbol": "NIFTY", "final_score": 0.60, "execution_ok": True, "quote_source": "option_chain_live"},
        {"trade_id": "T2", "symbol": "NIFTY", "final_score": 0.10, "execution_ok": False, "quote_source": "fallback_quote"},
        {"trade_id": "T3", "symbol": "NIFTY", "final_score": 0.20, "execution_ok": False, "source_flags": {"recovered_fallback": True}},
    ]
    payload = build_ranking_quality_evidence_payload(
        candidates=rows,
        phase2_state="WATCHLIST",
        cycle_primary_reason=None,
        phase2_min_enter_score=0.70,
    )
    assert payload["fallback_row_count"] == 2
    dist = payload["fallback_vs_real_score_distribution"]
    assert dist["real_count"] == 1
    assert dist["fallback_count"] == 2

