from __future__ import annotations

from config import config as cfg


def test_health_gate_includes_cost_gate(monkeypatch, tmp_path):
    import core.health_gate as health_gate_mod

    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setenv("COST_GATE_ENABLED", "true")
    monkeypatch.setattr(cfg, "COST_GATE_ENABLED", True, raising=False)
    monkeypatch.setattr(health_gate_mod.cfg, "COST_GATE_ENABLED", True, raising=False)

    monkeypatch.setattr(health_gate_mod, "_path_contract_violations", lambda: [])
    monkeypatch.setattr(
        health_gate_mod,
        "run_golden_path",
        lambda desk, run_id: {"ok": True, "run_id": run_id, "desk": desk},
    )
    monkeypatch.setattr(
        health_gate_mod,
        "run_one_trade_can_build",
        lambda desk, run_id: {"ok": True, "run_id": run_id, "desk": desk},
    )
    monkeypatch.setattr(
        health_gate_mod,
        "read_events",
        lambda run_id=None, **kwargs: [
            {"type": "trade_intent_created"},
            {"type": "order_submitted"},
            {"type": "fill"},
        ],
    )
    monkeypatch.setattr(
        health_gate_mod,
        "build_recon",
        lambda events: {"trade_count": 1, "status": "ok", "symbols": ["NIFTY"], "trades": events},
    )
    monkeypatch.setattr(health_gate_mod, "write_json_atomic", lambda path, payload: path)
    monkeypatch.setattr(health_gate_mod, "load_execution_analytics", lambda: {"status": "ok"})
    monkeypatch.setattr(health_gate_mod, "load_reconciliation_summary", lambda: {"status": "ok"})
    monkeypatch.setattr(health_gate_mod, "load_depth_status", lambda db_path=None: {"status": "ok", "db_path": db_path})
    monkeypatch.setattr(
        health_gate_mod,
        "run_cost_gate",
        lambda desk: (
            "FAIL",
            {
                "breaches": [{"code": "MAX_P95_SPREAD_BPS"}],
                "totals": {"p95_spread_bps": 50.0},
                "report_json_path": str(logs_root / "cost_kpis.json"),
                "report_md_path": str(logs_root / "cost_kpis.md"),
            },
        ),
    )

    report = health_gate_mod.run_health_gate(desk="DEFAULT", strict=True, run_id="HG_COST_TEST")
    codes = {str(item.get("code")) for item in report.get("issues", [])}
    assert "COST_GATE_P0" in codes or "COST_GATE_ERROR_P0" in codes
    assert "cost_gate" in list(report.get("checks", []))
