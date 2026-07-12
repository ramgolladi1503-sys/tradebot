from __future__ import annotations

import json
from pathlib import Path


def test_one_replay_event_naturally_reaches_candidate_emission():
    handoff_path = Path(".runtime/runtime_candidate_handoff_latest.json")
    ranked_path = Path(".runtime/opportunities/ranked_pipeline_latest.json")
    assert handoff_path.exists(), "missing runtime candidate handoff artifact"
    assert ranked_path.exists(), "missing ranked pipeline artifact"

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    ranked = json.loads(ranked_path.read_text(encoding="utf-8")).get("payload", {})

    trade_id = handoff.get("top_reportable_executable_trade_id")
    snapshot = handoff.get("top_reportable_executable_snapshot") or {}

    assert trade_id == "NIFTY-2026-07-07-24150-PE-mean-reversion-1782975597"
    assert snapshot.get("trade_id") == trade_id
    assert snapshot.get("candidate_status") == "executable"
    assert snapshot.get("execution_allowed") is True
    assert snapshot.get("reportable_executable") is True

    reports = ranked.get("reports") or []
    assert reports, "ranked pipeline artifact did not persist any reports"
    report = next((item for item in reports if item.get("symbol") == "NIFTY"), reports[0])

    assert report["raw_candidate_count"] >= 1
    assert report["candidate_pool"]["candidate_count"] >= 1
    assert report["candidate_pool"]["candidates"][0]["strategy_id"] == "no_trade_engine_v1"
    assert report["ranking"]["rank_count"] == 0
    assert "global_feed_unhealthy" in report["ranking"]["blockers"]

