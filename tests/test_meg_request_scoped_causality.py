import json
from pathlib import Path

from core.meg_request_scoped_causality import append_meg_cycle_primitives, append_primitives, verify_root


def _root(tmp_path: Path):
    root = tmp_path / "sealed"
    root.mkdir()
    (root / "SEALED").write_text("sealed\n")
    (root / "manifest.json").write_text("{}\n")
    common = dict(session_id="s1", producer_commit_sha="c1")
    append_primitives(root, **common, request=dict(request_event_id="re1", request_id="r1", request_generation=1, request_success_timestamp=10, feed_session_id="f", reconnect_generation=2, expected_instrument_token=101, expected_symbol="NIFTY"))
    append_primitives(root, **common, tick=dict(selected_tick_event_id="te1", cycle_id="cy1", request_id="r1", request_generation=1, selected_tick_id="t1", selected_tick_receipt_timestamp=11, selected_tick_feed_session_id="f", selected_tick_reconnect_generation=2, selected_tick_instrument_token=101, selected_tick_symbol="NIFTY"), accepted=dict(cycle_id="cy1", accepted=True), persisted=dict(cycle_id="cy1", persistence_identity="p1"))
    return root


def test_valid_complete_session_passes(tmp_path):
    assert verify_root(_root(tmp_path))["verdict"] == "PASS_MEG_REQUEST_SCOPED_CAUSALITY"


def test_wrong_token_and_causality_fail(tmp_path):
    root = _root(tmp_path)
    path = root / "meg_selected_tick_events.jsonl"
    row = json.loads(path.read_text().splitlines()[0]); row["selected_tick_instrument_token"] = 999; row["selected_tick_receipt_timestamp"] = 9
    path.write_text(json.dumps(row) + "\n")
    assert verify_root(root)["verdict"] == "INCOMPLETE_MEG_REQUEST_SCOPED_CAUSALITY_EVIDENCE"


def test_missing_persistence_fails(tmp_path):
    root = _root(tmp_path); (root / "meg_persisted_cycles.jsonl").unlink()
    assert verify_root(root)["accepted_cycle_persistence_mismatch"] == 1


def test_mixed_sessions_fail_closed(tmp_path):
    root = _root(tmp_path)
    path = root / "meg_request_events.jsonl"; row = json.loads(path.read_text().splitlines()[0]); row["session_id"] = "s2"
    path.write_text(path.read_text() + json.dumps(row) + "\n")
    assert verify_root(root)["verdict"] == "INCOMPLETE_MEG_REQUEST_SCOPED_CAUSALITY_EVIDENCE"


def test_runtime_projection_is_idempotent(tmp_path):
    root = tmp_path / "sealed"; root.mkdir()
    (root / "SEALED").write_text("sealed\n"); (root / "manifest.json").write_text("{}\n")
    evidence = {"token_lifecycle": {"101": {
        "request_id": "r1", "request_generation": 1, "subscribe_call_succeeded_epoch": 10,
        "feed_session_id": "f", "reconnect_generation": 2, "instrument_token": 101,
        "symbol": "NIFTY", "selected_post_request_tick_id": "t1",
        "first_post_request_tick_epoch": 11,
    }}}
    for _ in range(2):
        append_meg_cycle_primitives(root, session_id="s1", producer_commit_sha="c1",
                                    cycle_id="cy1", accepted=True,
                                    subscription_evidence=evidence)
    assert verify_root(root)["verdict"] == "PASS_MEG_REQUEST_SCOPED_CAUSALITY"
