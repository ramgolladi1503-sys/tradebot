from __future__ import annotations

import json

import pytest

import core.orchestrator as orch


def test_top_opportunities_rows_include_classification_fields(monkeypatch, tmp_path):
    logs_root = tmp_path / "logs"
    runtime_root = tmp_path / "runtime"
    logs_root.mkdir(parents=True, exist_ok=True)
    runtime_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))

    # Seed notrade_reason_truth_latest.json so cycle_primary_reason is present.
    (logs_root / "notrade_reason_truth_latest.json").write_text(
        json.dumps({"primary_reason": "market_closed"}, indent=2),
        encoding="utf-8",
    )

    def _fake_run_engine_phase2(_cands, **_kwargs):
        selected = {"trade_id": "T1", "symbol": "NIFTY", "execution_ok": True, "quote_source": "option_chain_live"}
        ranked = [
            selected,
            {
                "trade_id": "T2",
                "symbol": "NIFTY",
                "execution_ok": False,
                "candidate_status": "near_executable",
                "quote_source": "option_chain_live",
            },
        ]
        return {"state": "ENTER", "reason": "test", "selected": selected, "ranked": ranked, "next_active_trade": None}

    monkeypatch.setattr(orch, "run_engine_phase2", _fake_run_engine_phase2, raising=True)

    payload = orch._build_top_opportunities_payload(
        candidates=[{"trade_id": "T1", "symbol": "NIFTY"}],
        executable_top_n=1,
        advisory_top_n=1,
        active_trade=None,
        cycle_primary_reason="market_closed",
    )
    assert payload["cycle_primary_reason"] == "market_closed"
    assert payload["top_executable_opportunities"]
    row = payload["top_executable_opportunities"][0]
    for key in (
        "row_class",
        "operator_status",
        "is_executable",
        "is_near_executable",
        "is_advisory",
        "is_debug",
        "primary_reason",
        "execution_block_reason",
        "quote_source",
        "quote_age_sec",
        "spread_pct",
        "recovered_fallback",
    ):
        assert key in row

