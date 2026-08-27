import json
import pytest
from core.read_only_consumer_cycle import run_consumer_cycle

SHA = "a" * 40

def ranked(*, cycle_id="s:1:x", session_id="s", source_sha=SHA, candidates=None):
    return {"cycle_provenance": {"cycle_id": cycle_id, "session_id": session_id, "source_sha": source_sha, "session_date": "2026-08-27"}, "reports": [{"candidate_pool": {"regime": {"primary_regime": "RANGE"}, "candidates": list(candidates or [])}}]}

def run(tmp_path, pipeline):
    return run_consumer_cycle(runtime_outputs={"ranked_pipeline_latest": pipeline, "advisory_latest": {"rows": [{"stale": True}]}}, output_root=tmp_path, session_id="s", source_sha=SHA, cycle_context={"cycle_id": "s:1:x", "causal_data_cutoff": "2026-08-27T09:15:00Z"})

def test_current_cycle_reports_are_the_only_input(tmp_path):
    result = run(tmp_path, ranked())
    assert result["current_cycle_input"]["stale_advisory_fallback_used"] is False
    assert result["consumers"]["regime"]["verdict"] == "PASS"
    assert result["consumers"]["strategies"]["candidate_count"] == 0
    assert result["broker_order_calls"] == 0

def test_missing_current_reports_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="CURRENT_CYCLE_RANKED_REPORTS_MISSING"):
        run(tmp_path, {"cycle_provenance": ranked()["cycle_provenance"], "reports": []})

def test_provenance_mismatch_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="CURRENT_CYCLE_PROVENANCE_MISMATCH"):
        run(tmp_path, ranked(source_sha="b" * 40))

def test_stale_advisory_rows_are_not_used(tmp_path):
    result = run(tmp_path, ranked())
    assert result["consumers"]["candidate_pool"]["candidate_count"] == 0
    assert not (tmp_path / "advisory_queue.jsonl").exists()
    stored = json.loads((tmp_path / "consumer_cycle_latest.json").read_text())
    assert stored["current_cycle_input"]["report_count"] == 1
