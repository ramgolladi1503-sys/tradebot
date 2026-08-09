import json
import hashlib
from types import SimpleNamespace
from pathlib import Path

from core.meg_request_scoped_causality import append_meg_cycle_primitives, append_primitives, verify_root
from core.kite_read_only_observation_runtime import write_meg_wiring_evidence


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


def test_real_observation_persistence_path_seals_and_verifies(tmp_path):
    root = tmp_path / "session"; root.mkdir()
    source = root / "source.jsonl"
    source.write_text(json.dumps({"constituent_bar_details": [{"symbol": "NIFTY"}]}) + "\n")
    lifecycle = {"101": {
        "request_id": "r1", "request_generation": 1, "subscribe_call_succeeded_epoch": 10,
        "feed_session_id": "feed-1", "reconnect_generation": 2, "instrument_token": 101,
        "symbol": "NIFTY", "selected_post_request_tick_id": "tick-1",
        "first_post_request_tick_epoch": 11,
    }}
    contract = SimpleNamespace(canonical_sha256="universe-1", index_symbol="NIFTY",
                               index_instrument_token=101, constituent_symbols=[])
    bridge = SimpleNamespace(
        exporter=SimpleNamespace(path=source),
        _load_universe_contract=lambda: (contract, None),
    )
    result = SimpleNamespace(attempted=True, exported=True, reason="OK",
                             accepted_constituent_count=1,
                             audit={"subscription_evidence": {"feed_session_id": "feed-1",
                                 "reconnect_generation": 2, "token_lifecycle": lifecycle}})
    write_meg_wiring_evidence(bridge=bridge, result=result, output_path=root / "summary.json",
                              cycle_count=1, session_date="2026-08-10", run_id="session-1",
                              interval_end_epoch=100, producer_commit="commit-1")
    files = sorted(path for path in root.iterdir() if path.is_file() and path.name != "SEALED")
    checksums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files)
    (root / "SHA256SUMS").write_text(checksums)
    (root / "manifest.json").write_text(json.dumps({"session_id": "session-1", "files": [p.name for p in files]}))
    (root / "SEALED").write_text("sealed\n")
    verified = verify_root(root)
    assert verified["verdict"] == "PASS_MEG_REQUEST_SCOPED_CAUSALITY"
    assert verified["request_event_count"] > 0
    assert verified["selected_tick_event_count"] > 0
    assert verified["accepted_cycle_count"] == 1
