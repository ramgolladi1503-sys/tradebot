from __future__ import annotations

from core import candidate_soft_reject as csr
from config import config as cfg


def test_unknown_reject_not_critical_by_default(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_UNKNOWN_CRITICAL", False, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS", "missing_symbol,unknown_reject", raising=False)
    critical = csr.critical_reject_reasons()

    assert "unknown_reject" not in critical
    assert csr.is_critical_reject_reason("unknown_reject", critical) is False


def test_unknown_reject_can_be_marked_critical_when_configured(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_UNKNOWN_CRITICAL", True, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS", "missing_symbol,unknown_reject", raising=False)
    critical = csr.critical_reject_reasons()

    assert "unknown_reject" in critical
    assert csr.is_critical_reject_reason("unknown_reject", critical) is True


def test_build_soft_reject_candidate_unknown_is_rankable():
    cand = csr.build_soft_reject_candidate(
        {"symbol": "NIFTY"},
        reject_reason="unknown_reject",
        reject_source="orchestrator",
        gate_reasons=["unknown_reject"],
        base_candidate={"candidate_type": "directional"},
        execution_mode="SIM",
    )

    assert cand is not None
    assert cand["execution_status"] == "advisory_only"
    assert cand["confidence_final"] is not None and cand["confidence_final"] > 0.0
    assert cand["rank_score"] is not None
    assert cand["reject_reason_source"] == "fallback_unknown"
    assert cand["instrument_type"] == "OPT"
    assert cand["option_type"] == "CE"
