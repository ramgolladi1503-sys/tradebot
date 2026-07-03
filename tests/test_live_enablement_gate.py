from __future__ import annotations

from pathlib import Path

from config import config as cfg
from core.market_context import MarketContext
from scripts import live_enablement_gate


def test_live_enablement_gate_strict_if_live_fails_on_degraded_acceptance(monkeypatch, tmp_path):
    monkeypatch.setattr(
        live_enablement_gate,
        "derive_market_context",
        lambda *_a, **_k: MarketContext(
            mode="LIVE",
            is_market_open=True,
            require_live_quotes=True,
            allow_stale_quotes=False,
            planning_only=False, session_state="NORMAL_OPEN",
        ),
    )
    monkeypatch.setattr(live_enablement_gate, "check_trade_identity_schema", lambda: (True, "ok"))
    monkeypatch.setattr(live_enablement_gate, "evaluate_slo_status", lambda **_k: {"ok": True, "reasons": [], "warnings": [], "status": "OK"})
    monkeypatch.setattr(
        live_enablement_gate,
        "evaluate_acceptance_gate",
        lambda **_k: {"status": "DEGRADED", "blockers": ["TRUTH_DATASET_MISSING"]},
    )
    monkeypatch.setattr(cfg, "LIVE_ENABLEMENT_AUDIT_PATH", str(tmp_path / "live_enablement_audit_latest.json"), raising=False)
    payload = live_enablement_gate.run_gate(strict=False, strict_if_live=True, enforce_failover=False)
    assert payload["status"] == "FAIL"
    assert "acceptance:TRUTH_DATASET_MISSING" in payload["blockers"]
    assert Path(payload["audit_path"]).exists()


def test_live_enablement_gate_non_live_degrades_without_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(
        live_enablement_gate,
        "derive_market_context",
        lambda *_a, **_k: MarketContext(
            mode="PAPER",
            is_market_open=False,
            require_live_quotes=False,
            allow_stale_quotes=True,
            planning_only=True, session_state="CLOSED",
        ),
    )
    monkeypatch.setattr(live_enablement_gate, "check_trade_identity_schema", lambda: (True, "ok"))
    monkeypatch.setattr(live_enablement_gate, "evaluate_slo_status", lambda **_k: {"ok": True, "reasons": [], "warnings": [], "status": "OK"})
    monkeypatch.setattr(
        live_enablement_gate,
        "evaluate_acceptance_gate",
        lambda **_k: {"status": "DEGRADED", "blockers": ["TRUTH_DATASET_MISSING"]},
    )
    monkeypatch.setattr(cfg, "LIVE_ENABLEMENT_AUDIT_PATH", str(tmp_path / "live_enablement_audit_latest.json"), raising=False)
    payload = live_enablement_gate.run_gate(strict=False, strict_if_live=True, enforce_failover=False)
    assert payload["status"] == "DEGRADED"
    assert not payload["blockers"]
    assert "acceptance:TRUTH_DATASET_MISSING" in payload["warnings"]


def test_live_enablement_gate_live_statistical_gate_is_hard_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(
        live_enablement_gate,
        "derive_market_context",
        lambda *_a, **_k: MarketContext(
            mode="LIVE",
            is_market_open=True,
            require_live_quotes=True,
            allow_stale_quotes=False,
            planning_only=False, session_state="NORMAL_OPEN",
        ),
    )
    monkeypatch.setattr(live_enablement_gate, "check_trade_identity_schema", lambda: (True, "ok"))
    monkeypatch.setattr(live_enablement_gate, "evaluate_slo_status", lambda **_k: {"ok": True, "reasons": [], "warnings": [], "status": "OK"})
    monkeypatch.setattr(
        live_enablement_gate,
        "evaluate_acceptance_gate",
        lambda **_k: {"status": "DEGRADED", "blockers": ["OUTCOME_ROWS_INSUFFICIENT"]},
    )
    monkeypatch.setattr(cfg, "LIVE_ENABLEMENT_REQUIRE_STATISTICAL_PASS", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_ENABLEMENT_AUDIT_PATH", str(tmp_path / "live_enablement_audit_latest.json"), raising=False)

    payload = live_enablement_gate.run_gate(strict=False, strict_if_live=False, enforce_failover=False)
    assert payload["status"] == "FAIL"
    assert "stat_gate:OUTCOME_ROWS_INSUFFICIENT" in payload["blockers"]
