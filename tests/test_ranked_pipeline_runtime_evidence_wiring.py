from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import core.orchestrator as orchestrator
import core.runtime_snapshot_producer as snapshot_producer
from core.runtime_snapshot_store import build_snapshot_envelope
from dashboard.readers.snapshot_reader import read_snapshot_payload


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
        feed_truth_payload={
            "feed_truth_state": "",
            "feed_truth_reason_code": "",
            "canonical_feed_truth": {"state": "VERIFIED_HEALTHY", "reason_code": "LIVE"},
        },
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
    assert report["feed_truth_state"] == "VERIFIED_HEALTHY"
    assert report["feed_truth_reason_code"] == "LIVE"


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


def test_canonical_ranked_snapshot_emits_dashboard_alias_keys_and_reads_back(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class _FakeOutcome:
        entry_price = 101.5
        confidence_score = 0.91

    class _FakeRank:
        def __init__(self, *, rank: int, strategy_id: str, bucket: str, executable_candidate: bool) -> None:
            self.rank = rank
            self.strategy_id = strategy_id
            self.symbol = "NIFTY"
            self.direction = "BUY_CALL"
            self.movement_type = "COMPRESSION_BREAKOUT"
            self.final_score = 0.91 if executable_candidate else 0.73
            self.bucket = bucket
            self.score_eligibility = "SCORE_ELIGIBLE" if executable_candidate else "NEEDS_CONFIRMATION"
            self.executable_candidate = executable_candidate
            self.rank_reason = "unit_test_rank"
            self.downgrade_reasons = ()
            self.blockers = ()
            self.warnings = ()
            self.safety_flags = ()
            self.directional_warnings = ()
            self.sort_key = (0, -self.final_score)
            self.outcome_contract = _FakeOutcome()
            self.candidate_id = f"{strategy_id}-candidate"
            self.lineage_id = f"{strategy_id}-lineage"

        def to_dict(self) -> dict:
            return {
                "rank": self.rank,
                "candidate_id": self.candidate_id,
                "lineage_id": self.lineage_id,
                "strategy_id": self.strategy_id,
                "symbol": self.symbol,
                "direction": self.direction,
                "movement_type": self.movement_type,
                "final_score": self.final_score,
                "bucket": self.bucket,
                "score_eligibility": self.score_eligibility,
                "executable_candidate": self.executable_candidate,
                "rank_reason": self.rank_reason,
                "downgrade_reasons": [],
                "blockers": [],
                "warnings": [],
                "safety_flags": [],
                "directional_warnings": [],
                "sort_key": list(self.sort_key),
                "outcome_contract": {"entry_price": self.outcome_contract.entry_price, "confidence_score": self.outcome_contract.confidence_score},
            }

    class _FakeRanking:
        ranked_report_id = "ranked-report-1"
        ranks = (
            _FakeRank(rank=1, strategy_id="opening_range_retest_v1", bucket="EXECUTABLE_CANDIDATE", executable_candidate=True),
            _FakeRank(rank=2, strategy_id="trend_pullback_v1", bucket="NEAR_EXECUTABLE_CANDIDATE", executable_candidate=False),
        )

    class _FakeReport:
        generated_epoch = 1_000.0
        ranking = _FakeRanking()
        ranked_candidate_count = 2
        top_rank_strategy_id = "opening_range_retest_v1"

        def to_dict(self) -> dict:
            return {
                "ranked_candidate_count": self.ranked_candidate_count,
                "top_rank_strategy_id": self.top_rank_strategy_id,
                "generated_epoch": self.generated_epoch,
            }

    monkeypatch.setattr(snapshot_producer, "_strategy_context_from_market_symbol", lambda sym, data: SimpleNamespace(symbol=sym), raising=False)
    monkeypatch.setattr(snapshot_producer, "build_ranked_opportunity_report", lambda *args, **kwargs: _FakeReport(), raising=True)
    monkeypatch.setattr(
        snapshot_producer,
        "write_ranked_pipeline_snapshot",
        lambda *, payload, producer: captured.update({"payload": payload, "producer": producer}),
        raising=True,
    )

    market_payload = {"symbols": {"NIFTY": {"ohlc": {"close": 101.5}}}}
    advisory_payload = {"rows": []}

    snapshot_producer._build_and_write_canonical_ranked_snapshot(market_payload, "unit-test", advisory_payload)

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["source"] == "ranked_opportunity_pipeline_v1"
    assert payload["top_executable"] == payload["top_executable_opportunities"]
    assert payload["top_advisory"] == payload["top_advisory_opportunities"]
    assert payload["top_blocked_opportunities"] == []
    assert payload["top_executable_count"] == 1
    assert payload["top_advisory_count"] == 1

    snapshot_path = tmp_path / "ranked_pipeline_latest.json"
    snapshot_path.write_text(
        json.dumps(build_snapshot_envelope(payload=payload, producer="unit-test")),
        encoding="utf-8",
    )
    normalized = read_snapshot_payload(snapshot_path)
    normalized_payload = normalized["payload"]

    assert normalized["state"] == "ok"
    assert "top_executable_opportunities" in normalized_payload
    assert "top_advisory_opportunities" in normalized_payload
    assert "top_opportunity_truth_report" in normalized_payload
