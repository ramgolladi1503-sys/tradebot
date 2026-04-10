from __future__ import annotations

from core import candidate_soft_reject as csr
from config import config as cfg


def test_soft_reject_confidence_penalizes_reason_codes(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CONFIDENCE", 0.2, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CONF_MIN", 0.05, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_PENALTY_PREMIUM", 0.05, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_PENALTY_SPREAD", 0.07, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_PENALTY_LATENCY", 0.1, raising=False)

    cand = csr.build_soft_reject_candidate(
        {"symbol": "NIFTY"},
        reject_reason="premium_band_fail",
        reject_source="orchestrator",
        gate_reasons=["premium_band_fail", "spread_pct", "latency_guard"],
        base_candidate={"candidate_type": "directional"},
        execution_mode="SIM",
    )

    assert cand is not None
    assert 0.05 <= float(cand["confidence_final"]) < 0.2


def test_soft_reject_hides_unknown_instrument(monkeypatch):
    monkeypatch.setattr(cfg, "ADVISORY_HIDE_UNKNOWN_INSTRUMENT", True, raising=False)
    monkeypatch.setattr(cfg, "ADVISORY_INSTRUMENT_TYPE_ASSUME_OPT_CANDIDATE_TYPES", "", raising=False)
    monkeypatch.setattr(cfg, "ADVISORY_INSTRUMENT_TYPE_FALLBACK", "UNKNOWN", raising=False)
    monkeypatch.setattr(cfg, "ADVISORY_OPTION_TYPE_FALLBACK", "", raising=False)

    cand = csr.build_soft_reject_candidate(
        {"symbol": "NIFTY"},
        reject_reason="unknown_reject",
        reject_source="orchestrator",
        gate_reasons=["unknown_reject"],
        base_candidate={"candidate_type": "unknown"},
        execution_mode="SIM",
    )

    assert cand is not None
    assert cand["instrument_type"] == "UNKNOWN"
    assert cand["advisory_visible"] is False


def test_soft_reject_candidate_queue_only_when_confident(monkeypatch):
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CONFIDENCE", 0.7, raising=False)
    monkeypatch.setattr(cfg, "CANDIDATE_SOFT_REJECT_CONF_MIN", 0.05, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_BORDERLINE_CONF_MIN", 0.18, raising=False)

    cand = csr.build_soft_reject_candidate(
        {"symbol": "NIFTY"},
        reject_reason="no_signal",
        reject_source="orchestrator",
        gate_reasons=["no_signal"],
        base_candidate={"candidate_type": "directional"},
        execution_mode="SIM",
    )

    assert cand is not None
    assert cand["execution_status"] == "scored"
    assert cand["candidate_status"] == "near_executable"
    assert cand["eligible_for_execution"] is True
    assert cand["execution_blocked"] is False
