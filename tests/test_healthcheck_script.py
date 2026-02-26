from __future__ import annotations

from types import SimpleNamespace

from scripts import healthcheck


def test_healthcheck_downgrades_non_live_readiness_blockers(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(healthcheck, "ensure_trade_log_exists", lambda: tmp_path / "logs" / "trade_log.jsonl")
    monkeypatch.setattr(healthcheck, "_check_config", lambda: (True, []))
    monkeypatch.setattr(healthcheck, "_check_db_writable", lambda: (True, "ok"))
    monkeypatch.setattr(healthcheck, "_check_clock_sanity", lambda: (True, "ok"))
    monkeypatch.setattr(healthcheck, "evaluate_slo_status", lambda enforce_failover=False: {"ok": True, "reasons": [], "warnings": [], "status": "OK"})
    monkeypatch.setattr(
        healthcheck,
        "assess_outcome_truth",
        lambda strict=False: {"status": "PASS", "blockers": [], "warnings": []},
    )
    monkeypatch.setattr(
        healthcheck,
        "derive_market_context",
        lambda: SimpleNamespace(
            mode="PAPER",
            is_market_open=False,
            require_live_quotes=False,
            allow_stale_quotes=True,
            planning_only=True,
        ),
    )
    monkeypatch.setattr(
        healthcheck,
        "run_readiness_state",
        lambda write_log=False: SimpleNamespace(
            state=SimpleNamespace(value="BLOCKED"),
            can_trade=False,
            blockers=["kite_auth_failed"],
            warnings=[],
        ),
    )

    payload = healthcheck.run_healthcheck()
    assert payload["status"] == "DEGRADED"
    assert any(str(w).startswith("downgraded:") for w in payload["warnings"])


def test_healthcheck_fails_on_hard_local_preflight(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(healthcheck, "ensure_trade_log_exists", lambda: tmp_path / "logs" / "trade_log.jsonl")
    monkeypatch.setattr(healthcheck, "_check_config", lambda: (True, []))
    monkeypatch.setattr(healthcheck, "_check_db_writable", lambda: (False, "db_not_writable:readonly"))
    monkeypatch.setattr(healthcheck, "_check_clock_sanity", lambda: (True, "ok"))
    monkeypatch.setattr(healthcheck, "evaluate_slo_status", lambda enforce_failover=False: {"ok": True, "reasons": [], "warnings": [], "status": "OK"})
    monkeypatch.setattr(
        healthcheck,
        "assess_outcome_truth",
        lambda strict=False: {"status": "PASS", "blockers": [], "warnings": []},
    )
    monkeypatch.setattr(
        healthcheck,
        "derive_market_context",
        lambda: SimpleNamespace(
            mode="PAPER",
            is_market_open=False,
            require_live_quotes=False,
            allow_stale_quotes=True,
            planning_only=True,
        ),
    )
    monkeypatch.setattr(
        healthcheck,
        "run_readiness_state",
        lambda write_log=False: SimpleNamespace(
            state=SimpleNamespace(value="READY"),
            can_trade=True,
            blockers=[],
            warnings=[],
        ),
    )

    payload = healthcheck.run_healthcheck()
    assert payload["status"] == "FAIL"


def test_healthcheck_data_truth_degrades_non_live(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(healthcheck, "ensure_trade_log_exists", lambda: tmp_path / "logs" / "trade_log.jsonl")
    monkeypatch.setattr(healthcheck, "_check_config", lambda: (True, []))
    monkeypatch.setattr(healthcheck, "_check_db_writable", lambda: (True, "ok"))
    monkeypatch.setattr(healthcheck, "_check_clock_sanity", lambda: (True, "ok"))
    monkeypatch.setattr(
        healthcheck,
        "evaluate_slo_status",
        lambda enforce_failover=False: {"ok": True, "reasons": [], "warnings": [], "status": "OK"},
    )
    monkeypatch.setattr(
        healthcheck,
        "derive_market_context",
        lambda: SimpleNamespace(
            mode="PAPER",
            is_market_open=False,
            require_live_quotes=False,
            allow_stale_quotes=True,
            planning_only=True,
        ),
    )
    monkeypatch.setattr(
        healthcheck,
        "run_readiness_state",
        lambda write_log=False: SimpleNamespace(
            state=SimpleNamespace(value="READY"),
            can_trade=True,
            blockers=[],
            warnings=[],
        ),
    )
    monkeypatch.setattr(
        healthcheck,
        "assess_outcome_truth",
        lambda strict=False: {"status": "DEGRADED", "blockers": ["OUTCOME_ROWS_INSUFFICIENT"], "warnings": []},
    )

    payload = healthcheck.run_healthcheck()
    assert payload["status"] == "DEGRADED"
    assert any(str(w).startswith("data_truth:") for w in payload["warnings"])


def test_healthcheck_data_truth_blocks_live_when_enabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(healthcheck, "ensure_trade_log_exists", lambda: tmp_path / "logs" / "trade_log.jsonl")
    monkeypatch.setattr(healthcheck, "_check_config", lambda: (True, []))
    monkeypatch.setattr(healthcheck, "_check_db_writable", lambda: (True, "ok"))
    monkeypatch.setattr(healthcheck, "_check_clock_sanity", lambda: (True, "ok"))
    monkeypatch.setattr(
        healthcheck,
        "evaluate_slo_status",
        lambda enforce_failover=False: {"ok": True, "reasons": [], "warnings": [], "status": "OK"},
    )
    monkeypatch.setattr(
        healthcheck,
        "derive_market_context",
        lambda: SimpleNamespace(
            mode="LIVE",
            is_market_open=True,
            require_live_quotes=True,
            allow_stale_quotes=False,
            planning_only=False,
        ),
    )
    monkeypatch.setattr(
        healthcheck,
        "run_readiness_state",
        lambda write_log=False: SimpleNamespace(
            state=SimpleNamespace(value="READY"),
            can_trade=True,
            blockers=[],
            warnings=[],
        ),
    )
    monkeypatch.setattr(
        healthcheck,
        "assess_outcome_truth",
        lambda strict=False: {"status": "DEGRADED", "blockers": ["SHADOW_ROWS_INSUFFICIENT"], "warnings": []},
    )
    monkeypatch.setattr(healthcheck.cfg, "HEALTHCHECK_ENFORCE_DATA_TRUTH_LIVE", True, raising=False)

    payload = healthcheck.run_healthcheck()
    assert payload["status"] == "FAIL"
    assert any(str(b).startswith("data_truth:") for b in payload["blockers"])
