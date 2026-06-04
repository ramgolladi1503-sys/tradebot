from __future__ import annotations

from pathlib import Path

import core.orchestrator as orchestrator


def test_write_ranked_pipeline_runtime_evidence_invokes_writer_with_read_only_report(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setattr(orchestrator, "logs_dir", lambda: tmp_path, raising=False)

    def _fake_writer(ranked_report, *, output_dir=None, now=None):
        calls["report"] = ranked_report
        calls["output_dir"] = output_dir
        calls["now"] = now
        return {"latest_path": str(Path(output_dir or tmp_path) / "ranked_pipeline_runtime_latest.json")}

    monkeypatch.setattr(orchestrator, "write_ranked_pipeline_evidence", _fake_writer, raising=True)

    report = orchestrator._write_ranked_pipeline_runtime_evidence(
        top_payload={
            "phase2_selected_trade_id": "BANKNIFTY_CALL",
            "phase2_state": "ENTER",
            "phase2_reason": "top_ranked",
            "phase2_ranked_count": 2,
            "top_executable_count": 1,
            "top_advisory_count": 1,
        },
        cycle_ranked_candidates=[
            {"trade_id": "BANKNIFTY_CALL", "symbol": "BANKNIFTY"},
            {"trade_id": "SENSEX_PUT", "symbol": "SENSEX"},
        ],
        market_open=True,
        feed_truth_payload={"feed_truth_state": "LIVE", "feed_truth_reason_code": "ok"},
        indicator_payload={"indicator_readiness_state": "READY", "indicator_readiness_reason_code": "ok"},
        cycle_blockers={"RISK_HALT": 1},
    )

    assert calls["output_dir"] == tmp_path
    assert calls["report"] == report
    assert report["read_only"] is True
    assert report["is_order_action"] is False
    assert report["append"] is False
    assert report["ranked_candidate_count"] == 2
    assert report["phase2_input_candidate_count"] == 2
    assert report["top_rank_strategy_id"] == "BANKNIFTY_CALL"
    assert report["metadata"]["orchestrator"] == "ranked_opportunity_pipeline_v1"
    assert report["metadata"]["producer"] == "orchestrator"
    assert report["blocker_counts"] == {"RISK_HALT": 1}


def test_write_ranked_pipeline_runtime_evidence_does_not_touch_broker_or_order_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "logs_dir", lambda: tmp_path, raising=False)
    monkeypatch.setattr(
        orchestrator,
        "write_ranked_pipeline_evidence",
        lambda ranked_report, *, output_dir=None, now=None: {"ok": True},
        raising=True,
    )
    monkeypatch.setattr(orchestrator.kite_client, "ensure", lambda: (_ for _ in ()).throw(AssertionError("broker_called")), raising=False)

    result = orchestrator._write_ranked_pipeline_runtime_evidence(
        top_payload={"phase2_state": "NO_TRADE", "phase2_reason": "none"},
        cycle_ranked_candidates=[{"trade_id": "BANKNIFTY_CALL"}],
        market_open=True,
        feed_truth_payload={},
        indicator_payload={},
        cycle_blockers={},
    )

    assert result["read_only"] is True
    assert result["is_order_action"] is False
