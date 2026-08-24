import json

from core.read_only_consumer_cycle import run_consumer_cycle


def test_consumer_cycle_fails_closed_without_candidates(tmp_path):
    result = run_consumer_cycle(
        runtime_outputs={"market_snapshot": {}, "advisory_latest": {"rows": []}},
        output_root=tmp_path, session_id="s1", source_sha="a" * 40,
    )
    assert result["consumers"]["candidate_pool"]["verdict"] == "PENDING"
    assert result["consumers"]["cas_v2"]["verdict"] == "PENDING"
    assert result["consumers"]["option_surface"]["verdict"] == "PENDING"
    assert result["broker_order_calls"] == 0
    assert not (tmp_path / "advisory_queue.jsonl").exists()


def test_consumer_cycle_rejects_invalid_candidate(tmp_path):
    result = run_consumer_cycle(
        runtime_outputs={"market_snapshot": {}, "advisory_latest": {"rows": [{"candidate_id": "bad"}]}},
        output_root=tmp_path, session_id="s1", source_sha="a" * 40,
    )
    assert result["consumers"]["candidate_pool"]["rejected_count"] == 1
    stored = json.loads((tmp_path / "consumer_cycle_latest.json").read_text())
    assert stored["live_execution_authorized"] is False

