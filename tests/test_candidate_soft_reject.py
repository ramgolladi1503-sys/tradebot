from __future__ import annotations

from core.candidate_soft_reject import build_soft_reject_candidate, is_critical_reject_reason


def test_soft_reject_candidate_builds_minimum_fields():
    payload = build_soft_reject_candidate(
        {"symbol": "NIFTY"},
        reject_reason="spread_too_wide",
        reject_source="unit_test",
        gate_reasons=["spread_too_wide"],
    )

    assert payload is not None
    assert payload["symbol"] == "NIFTY"
    assert payload["candidate_status"] == "advisory_only"
    assert payload["final_action"] == "ADVISORY_ONLY"
    assert payload["entry"] is None
    assert payload["entry_status"] == "missing"
    assert "spread_too_wide" in payload["soft_penalties"]


def test_soft_reject_marks_critical_reasons():
    assert is_critical_reject_reason("missing_symbol", {"missing_symbol"}) is True


def test_unknown_reject_is_non_critical_by_default(monkeypatch):
    from core import candidate_soft_reject as csr

    monkeypatch.setattr(csr.cfg, "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS", "missing_symbol", raising=False)
    assert csr.is_critical_reject_reason("unknown_reject") is False


def test_unknown_reject_candidate_is_rankable():
    payload = build_soft_reject_candidate(
        {"symbol": "NIFTY"},
        reject_reason="unknown_reject",
        reject_source="orchestrator_trade_builder_reject",
        gate_reasons=["unknown_reject"],
    )

    assert payload is not None
    assert payload["reject_reason"] == "unknown_reject"
    assert payload["reject_reason_source"] == "fallback_unknown"
    assert payload["candidate_status"] == "advisory_only"
    assert payload["execution_status"] == "advisory_only"
    assert payload["rank_score"] is not None
