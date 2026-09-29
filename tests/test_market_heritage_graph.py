import hashlib
import json
import os
import fcntl
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.market_heritage_graph import (
    MAX_NODE_BYTES,
    MAX_INDEX_BYTES,
    HeritageGraph,
    SessionHeritageIndex,
    evaluate_prerequisite_readiness,
    load_verified_t1_prerequisites,
    load_same_session_cas_references,
    index_legacy_session_runs,
    publish_verified_heritage_manifest,
    publish_same_session_cas_manifest,
    rolling_source_row_hash,
    make_node,
    resolve_previous_eligible_session,
    verify_rolling_close_series,
    verify_manifest,
)
from core.market_heritage_verifier import verify_market_heritage_manifest


SOURCE_HASH = hashlib.sha256(b"fixture source").hexdigest()
SESSION = {"trading_date": "2026-09-29", "venue": "NSE", "calendar_id": "fixture-calendar", "calendar_version": "v1"}


def node(key="n1", *, available=10.0, payload=None):
    return make_node(
        logical_key=key,
        payload={"value": 1.0} if payload is None else payload,
        source_ref="fixture://source-row/1",
        source_sha256=SOURCE_HASH,
        session={"trading_date": "2026-09-29", "venue": "NSE", "calendar_version": "fixture-v1"},
        instrument={"symbol": "NIFTY", "token": 1},
        contract_id="fixture-contract-v1",
        source_event_epoch=9.0,
        receive_epoch=9.1,
        available_epoch=available,
        status="OBSERVED",
        coverage={"gap": False},
    )


def test_hash_bound_nodes_edges_and_deterministic_topology():
    graph = HeritageGraph()
    parent, child = node("parent"), node("child")
    graph.add_node(parent)
    graph.add_node(child)
    graph.add_edge(parent_id=parent["node_id"], child_id=child["node_id"],
                   requirement="fixture dependency", parent_hash=parent["node_id"])
    report = graph.verify(decision_epoch=11)
    assert report["verdict"] == "PASS"
    assert report["topological_order"] == [parent["node_id"], child["node_id"]]
    assert report["read_only"] is True
    assert report["is_order_action"] is False
    assert report["broker_api_called"] is False


def test_rejects_node_and_parent_hash_tampering():
    graph = HeritageGraph()
    source, derived = node("source"), node("derived")
    graph.add_node(source)
    damaged = dict(derived)
    damaged["payload"] = {"value": 2.0}
    with pytest.raises(ValueError, match="NODE_HASH_MISMATCH"):
        graph.add_node(damaged)
    graph.add_node(derived)
    with pytest.raises(ValueError, match="PARENT_HASH_MISMATCH"):
        graph.add_edge(parent_id=source["node_id"], child_id=derived["node_id"],
                       requirement="bad", parent_hash="0" * 64)


def test_node_payload_size_is_bounded():
    with pytest.raises(ValueError, match="NODE_PAYLOAD_BOUND_EXCEEDED"):
        node(payload={"blob": "x" * (MAX_NODE_BYTES + 1)})


def test_unresolved_ancestors_cycles_and_unverified_edges_fail_closed():
    graph = HeritageGraph()
    first, second = node("first"), node("second")
    with pytest.raises(ValueError, match="UNRESOLVED_ANCESTOR"):
        graph.add_edge(parent_id=first["node_id"], child_id=second["node_id"],
                       requirement="missing", parent_hash=first["node_id"])
    graph.add_node(first)
    graph.add_node(second)
    graph.add_edge(parent_id=first["node_id"], child_id=second["node_id"],
                   requirement="forward", parent_hash=first["node_id"])
    with pytest.raises(ValueError, match="DEPENDENCY_CYCLE"):
        graph.add_edge(parent_id=second["node_id"], child_id=first["node_id"],
                       requirement="cycle", parent_hash=second["node_id"])
    blocked = HeritageGraph()
    a, b = node("a"), node("b")
    blocked.add_node(a)
    blocked.add_node(b)
    blocked.add_edge(parent_id=a["node_id"], child_id=b["node_id"],
                     requirement="blocked", parent_hash=a["node_id"],
                     outcome="BLOCKED", reason="source missing")
    assert blocked.verify()["verdict"] == "BLOCKED"


def test_conflicting_logical_key_and_future_information_are_not_ready():
    graph = HeritageGraph()
    graph.add_node(node("same-key", payload={"value": 1}))
    graph.add_node(node("same-key", payload={"value": 2}))
    report = graph.verify(decision_epoch=9)
    assert report["verdict"] == "BLOCKED"
    assert any(row["code"] == "LOGICAL_KEY_CONFLICT" for row in report["errors"])
    assert any(row["code"] == "FUTURE_INFORMATION" for row in report["errors"])


def test_publication_is_content_addressed_idempotent_and_independently_verified(tmp_path):
    graph = HeritageGraph()
    graph.add_node(node())
    manifest = graph.publish(tmp_path, session_identity=SESSION)
    assert manifest == graph.publish(tmp_path, session_identity=SESSION)
    assert verify_market_heritage_manifest(manifest, decision_epoch=11)["verdict"] == "PASS"
    report = verify_manifest(manifest, decision_epoch=11)
    assert report["verdict"] == "PASS"
    assert len(report["manifest_sha256"]) == 64
    payload = json.loads(manifest.read_text())
    payload["nodes"][0]["payload"]["value"] = 999
    manifest.write_text(json.dumps(payload))
    broken = verify_manifest(manifest, decision_epoch=11)
    assert broken["verdict"] == "BLOCKED"
    assert any(row["code"] in {"NODE_HASH_MISMATCH", "GRAPH_HASH_MISMATCH"}
               for row in broken["errors"])


def test_separate_verifier_detects_manifest_node_and_future_time_mutation(tmp_path):
    graph = HeritageGraph()
    graph.add_node(node(available=10))
    manifest = graph.publish(tmp_path, session_identity=SESSION)
    assert verify_market_heritage_manifest(manifest, decision_epoch=10)["verdict"] == "PASS"
    payload = json.loads(manifest.read_text())
    payload["nodes"][0]["available_epoch"] = 11
    manifest.write_text(json.dumps(payload))
    result = verify_market_heritage_manifest(manifest, decision_epoch=10)
    assert result["verdict"] == "BLOCKED"
    assert {item["code"] for item in result["errors"]} >= {"NODE_HASH_MISMATCH", "FUTURE_INFORMATION"}


def test_published_path_cannot_be_overwritten_with_other_payload(tmp_path):
    first = HeritageGraph()
    first.add_node(node("first"))
    path = first.publish(tmp_path, session_identity=SESSION)
    path.write_text("occupied")
    second = HeritageGraph()
    second.add_node(node("first", payload={"value": 8}))
    # A different graph has a different content-addressed destination.
    assert second.publish(tmp_path, session_identity=SESSION) != path
    assert path.read_text() == "occupied"


def test_session_index_resolves_only_verified_same_session_manifests(tmp_path):
    session = {"trading_date": "2026-09-29", "venue": "NSE", "calendar_id": "NSE-HIST", "calendar_version": "fixture-v1"}
    graph = HeritageGraph()
    graph.add_node(node())
    manifest = graph.publish(tmp_path, session_identity=session)
    index = SessionHeritageIndex(tmp_path, session=session)
    registered = index.register(manifest, run_id="run-a", session=session)
    assert registered["run_id"] == "run-a"
    assert index.resolve(run_id="run-a")[0]["manifest_sha256"] == registered["manifest_sha256"]
    with pytest.raises(ValueError, match="WRONG_TRADING_SESSION"):
        index.register(manifest, run_id="run-b", session={**session, "trading_date": "2026-09-30"})


def test_session_index_detects_manifest_tamper_and_run_id_conflict(tmp_path):
    session = {"trading_date": "2026-09-29", "venue": "NSE", "calendar_id": "NSE-HIST", "calendar_version": "fixture-v1"}
    graph = HeritageGraph()
    graph.add_node(node())
    manifest = graph.publish(tmp_path, session_identity=session)
    index = SessionHeritageIndex(tmp_path, session=session)
    entry = index.register(manifest, run_id="run-a", session=session)
    with pytest.raises(ValueError, match="RUN_ID_MANIFEST_CONFLICT"):
        other = HeritageGraph()
        other.add_node(node("other"))
        index.register(other.publish(tmp_path, session_identity=session), run_id="run-a", session=session)
    manifest.write_text(manifest.read_text() + " ")
    with pytest.raises(ValueError, match="INDEXED_MANIFEST_CHANGED_OR_UNVERIFIED"):
        index.resolve(run_id="run-a")


def test_session_index_refuses_to_extend_a_tampered_index(tmp_path):
    session = {"trading_date": "2026-09-29", "venue": "NSE", "calendar_id": "NSE-HIST", "calendar_version": "fixture-v1"}
    graph = HeritageGraph()
    graph.add_node(node())
    first = graph.publish(tmp_path, session_identity=session)
    index = SessionHeritageIndex(tmp_path, session=session)
    index.register(first, run_id="run-a", session=session)
    payload = json.loads(index.index_path.read_text())
    payload["entries"][0]["manifest_sha256"] = "0" * 64
    index.index_path.write_text(json.dumps(payload))
    another = HeritageGraph()
    another.add_node(node("run-b"))
    with pytest.raises(ValueError, match="INDEX_HASH_MISMATCH"):
        index.register(another.publish(tmp_path, session_identity=session), run_id="run-b", session=session)


def test_session_index_is_bounded_and_lock_timeout_fails_closed(tmp_path):
    session = {"trading_date": "2026-09-29", "venue": "NSE", "calendar_version": "fixture-v1"}
    index = SessionHeritageIndex(tmp_path, session=session, max_entries=1)
    fd = os.open(index.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(TimeoutError, match="HERITAGE_INDEX_LOCK_TIMEOUT"):
            index.register(tmp_path / "unused.json", run_id="run-a", session=session)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_session_index_recovers_after_lock_owner_process_exits(tmp_path):
    graph = HeritageGraph()
    graph.add_node(node())
    manifest = graph.publish(tmp_path, session_identity=SESSION)
    index = SessionHeritageIndex(tmp_path, session=SESSION, lock_timeout_seconds=1)
    script = (
        "import fcntl,os,sys; fd=os.open(sys.argv[1],os.O_CREAT|os.O_RDWR,0o600); "
        "fcntl.flock(fd,fcntl.LOCK_EX); os._exit(0)"
    )
    subprocess.run([sys.executable, "-c", script, str(index.lock_path)], check=True, timeout=5)
    result = index.register(manifest, run_id="recovered-run", session=SESSION)
    assert result["run_id"] == "recovered-run"
    assert len(index.resolve()) == 1


def test_legacy_indexer_is_bounded_read_only_and_never_promotes_authority(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    legacy_root = sessions / "session_2026-09-29" / "2026-09-29"
    run = legacy_root / "legacy-run-a"
    run.mkdir(parents=True)
    raw = run / "native_pulse_stream.jsonl"
    raw_bytes = b'{"pulse":1}\n' * 200000
    raw.write_bytes(raw_bytes)
    selected_ticks = run / "meg_selected_tick_events.jsonl"
    selected_tick_bytes = b'{"selected_tick_event_id":"fixture:1"}\n'
    selected_ticks.write_bytes(selected_tick_bytes)
    oversized = run / "candidate_pool.jsonl"
    oversized.write_bytes(b"x" * 4_000_000)
    output = tmp_path / "offline-evidence"
    session = {**SESSION}
    read_bytes = Path.read_bytes

    def reject_bulk_legacy_read(path):
        if path == raw:
            raise AssertionError("legacy source must be streamed")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_bulk_legacy_read)

    result = index_legacy_session_runs(sessions_root=sessions,
        legacy_session_root=legacy_root, destination_root=output,
        session_identity=session, max_file_bytes=3_000_000)

    assert result["status"] == "INVENTORIED_UNVERIFIED"
    assert result["legacy_authority"] == "LEGACY_UNVERIFIED"
    assert result["read_only"] is True and result["append"] is False
    manifest = json.loads(Path(result["inventory_path"]).read_text())
    files = {item["path"]: item for run_item in manifest["runs"] for item in run_item["files"]}
    assert files["legacy-run-a/native_pulse_stream.jsonl"]["status"] == "LEGACY_UNVERIFIED"
    assert files["legacy-run-a/native_pulse_stream.jsonl"]["sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert files["legacy-run-a/meg_selected_tick_events.jsonl"]["status"] == "LEGACY_UNVERIFIED"
    assert files["legacy-run-a/meg_selected_tick_events.jsonl"]["sha256"] == hashlib.sha256(selected_tick_bytes).hexdigest()
    assert files["legacy-run-a/candidate_pool.jsonl"]["reason"] == "FILE_SIZE_BOUND_EXCEEDED"
    with raw.open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").digest() == hashlib.sha256(raw_bytes).digest()


def test_legacy_indexer_rejects_destination_inside_protected_session_root(tmp_path):
    sessions = tmp_path / "sessions"
    legacy_root = sessions / "session_2026-09-29" / "2026-09-29"
    legacy_root.mkdir(parents=True)
    result = index_legacy_session_runs(sessions_root=sessions,
        legacy_session_root=legacy_root, destination_root=legacy_root / "index",
        session_identity=SESSION)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "INDEX_DESTINATION_INSIDE_PROTECTED_SESSIONS"


def test_session_index_concurrent_writers_preserve_both_manifests(tmp_path):
    manifests = []
    for key in ("writer-a", "writer-b"):
        graph = HeritageGraph()
        graph.add_node(node(key))
        manifests.append(graph.publish(tmp_path, session_identity=SESSION))
    index = SessionHeritageIndex(tmp_path, session=SESSION, lock_timeout_seconds=2)

    def register(item):
        return index.register(item[1], run_id=item[0], session=SESSION)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, zip(("writer-a", "writer-b"), manifests)))

    assert {row["run_id"] for row in results} == {"writer-a", "writer-b"}
    assert {row["run_id"] for row in index.resolve()} == {"writer-a", "writer-b"}


def test_session_index_rejects_oversized_serialized_index_before_read(tmp_path):
    index = SessionHeritageIndex(tmp_path, session=SESSION)
    index.index_path.write_bytes(b" " * (MAX_INDEX_BYTES + 1))
    with pytest.raises(ValueError, match="INDEX_SIZE_BOUND_EXCEEDED"):
        index.resolve()


def test_previous_eligible_session_skips_calendar_gaps_without_date_arithmetic():
    target = {"trading_date": "2026-09-29", "calendar_id": "NSE-HIST", "calendar_version": "v4",
              "venue": "NSE", "instrument_id": "NIFTY50-SPOT"}
    eligible = [
        {**target, "trading_date": "2026-09-25", "eligible": True, "verified": True},
        {**target, "trading_date": "2026-09-28", "eligible": False, "verified": True},
    ]
    result = resolve_previous_eligible_session(target_session=target, eligible_sessions=eligible,
        calendar_id="NSE-HIST", calendar_version="v4", venue="NSE", instrument_id="NIFTY50-SPOT")
    assert result["status"] == "RESOLVED"
    assert result["trading_date"] == "2026-09-25"


def test_previous_session_blocks_missing_calendar_and_ambiguous_identity():
    target = {"trading_date": "2026-09-29", "calendar_id": "NSE-HIST", "calendar_version": "v4",
              "venue": "NSE", "instrument_id": "NIFTY50-SPOT"}
    missing = resolve_previous_eligible_session(target_session=target, eligible_sessions=[],
        calendar_id="", calendar_version="v4", venue="NSE", instrument_id="NIFTY50-SPOT")
    assert missing["status"] == "BLOCKED"
    duplicate_rows = [{**target, "trading_date": "2026-09-25", "eligible": True, "verified": True} for _ in range(2)]
    ambiguous = resolve_previous_eligible_session(target_session=target, eligible_sessions=duplicate_rows,
        calendar_id="NSE-HIST", calendar_version="v4", venue="NSE", instrument_id="NIFTY50-SPOT")
    assert ambiguous["reason"] == "AMBIGUOUS_PREVIOUS_SESSION"


def test_strategy_readiness_is_field_local_and_asof_constrained():
    instrument = {"symbol": "NIFTY50", "basis": "INDEX"}
    session = {"trading_date": "2026-09-29", "venue": "NSE"}
    sha = hashlib.sha256(b"verified close").hexdigest()
    close = {"verification_status": "VERIFIED", "contract_id": "daily-close-v1",
             "instrument": instrument, "target_session": session, "available_epoch": 10,
             "content_sha256": sha}
    sma = {**close, "contract_id": "sma200-v1", "available_epoch": 20}
    ready = evaluate_prerequisite_readiness(strategy_id="S1", required_fields={
        "prev_close": "daily-close-v1", "prev_sma200": "sma200-v1"},
        verified_fields={"prev_close": close, "prev_sma200": sma}, decision_epoch=20,
        target_instrument=instrument, target_session=session)
    assert ready["status"] == "READY"
    assert ready["evaluation_eligible"] is True and ready["entry_eligible"] is False
    late = evaluate_prerequisite_readiness(strategy_id="S1", required_fields={
        "prev_close": "daily-close-v1", "prev_sma200": "sma200-v1"},
        verified_fields={"prev_close": close, "prev_sma200": {**sma, "available_epoch": 21}},
        decision_epoch=20, target_instrument=instrument, target_session=session)
    assert late["status"] == "BLOCKED"
    assert late["blockers"] == [{"field": "prev_sma200", "reason": "TEMPORALLY_INADMISSIBLE"}]


def test_strategy_readiness_rejects_wrong_instrument_and_missing_t1_field():
    session = {"trading_date": "2026-09-29", "venue": "NSE"}
    valid = {"verification_status": "VERIFIED", "contract_id": "futures-1529-v1",
             "instrument": {"contract_key": "NIFTY-SEP-FUT"}, "target_session": session,
             "available_epoch": 10, "content_sha256": SOURCE_HASH}
    result = evaluate_prerequisite_readiness(strategy_id="OPENING_DRIVE",
        required_fields={"prev_close_1529": "futures-1529-v1", "prev_contract_key": "futures-key-v1"},
        verified_fields={"prev_close_1529": valid}, decision_epoch=20,
        target_instrument={"contract_key": "NIFTY-OCT-FUT"}, target_session=session)
    assert result["status"] == "BLOCKED"
    assert {row["reason"] for row in result["blockers"]} == {"WRONG_INSTRUMENT", "MISSING"}


def _publish_t1_manifest(root, *, omit_calendar_edge=False, corrupt_contract=False,
                         target_date="2026-09-29", prior_date="2026-09-25",
                         mismatch_prior_contract=False, late_1529_bar=False,
                         wrong_1529_epoch=False, omit_rolling_row=False,
                         corrupt_rolling_hash=False, tamper_rolling_row=False,
                         publish=True):
    import math
    target = {**SESSION, "trading_date": target_date}
    prior = {**SESSION, "trading_date": prior_date}
    contracts = {
        "INTRADAY_OPENING_DRIVE_V1": "a" * 64,
        "S1_MOMENTUM_OVERNIGHT_V1": "b" * 64,
        "S4_MONDAY_OVERNIGHT_V1": "c" * 64,
    }
    instruments = {
        "INTRADAY_OPENING_DRIVE_V1": {"contract_key": "NIFTY-SEP-FUT"},
        "S1_MOMENTUM_OVERNIGHT_V1": {"symbol": "NIFTY50", "basis": "INDEX"},
        "S4_MONDAY_OVERNIGHT_V1": {"symbol": "NIFTY50", "basis": "INDEX"},
    }
    required = {
        "INTRADAY_OPENING_DRIVE_V1": {
            "opening_drive_prev_contract_key": contracts["INTRADAY_OPENING_DRIVE_V1"],
            "opening_drive_prev_close_1529": contracts["INTRADAY_OPENING_DRIVE_V1"],
        },
        "S1_MOMENTUM_OVERNIGHT_V1": {
            "overnight_prev_daily_close": contracts["S1_MOMENTUM_OVERNIGHT_V1"],
            "overnight_prev_sma200": contracts["S1_MOMENTUM_OVERNIGHT_V1"],
        },
        "S4_MONDAY_OVERNIGHT_V1": {
            "overnight_prev_daily_close": contracts["S4_MONDAY_OVERNIGHT_V1"],
            "overnight_prev_sma200": contracts["S4_MONDAY_OVERNIGHT_V1"],
        },
    }
    rolling_dates = []
    current = date.fromisoformat(prior_date)
    while len(rolling_dates) < 200:
        if current.weekday() < 5:
            rolling_dates.append(current.isoformat())
        current -= timedelta(days=1)
    rolling_dates.reverse()
    rolling_rows = [{
        "trading_date": day, "close": 22000.0,
        "verification_status": "VERIFIED", "instrument": instruments["S1_MOMENTUM_OVERNIGHT_V1"],
        "calendar_id": target["calendar_id"], "calendar_version": target["calendar_version"],
        "formula_id": "sma200-daily-close-v1", "eligible_session": True,
        "complete": True, "adjustment_id": "unadjusted-v1", "available_epoch": 50,
        "content_sha256": "",
    } for day in rolling_dates]
    for row in rolling_rows:
        row["content_sha256"] = rolling_source_row_hash(row)

    def build(key, payload, session, instrument, *, status="VERIFIED", available=50,
              contract="fixture-contract-v1", source_event_epoch=None):
        return make_node(logical_key=key, payload=payload,
            source_ref=f"fixture://{key}", source_sha256=SOURCE_HASH,
            session=session, instrument=instrument, contract_id=contract,
            source_event_epoch=available - 1 if source_event_epoch is None else source_event_epoch,
            receive_epoch=available,
            available_epoch=available, status=status)
    graph = HeritageGraph()
    calendar = build("calendar:2026-09-25->2026-09-29",
        {"record_type": "calendar_predecessor", "predecessor_session": prior,
                 "target_session": target, "calendar_id": target["calendar_id"],
                 "calendar_version": target["calendar_version"],
                 "rolling_session_dates": rolling_dates,
                 "eligible": True, "verified": True},
        target, {"calendar": target["calendar_id"]})
    graph.add_node(calendar)
    for strategy, fields in required.items():
        for index, (field, contract_id) in enumerate(fields.items()):
            instrument = instruments[strategy]
            value = ("NIFTY-SEP-FUT" if field.endswith("contract_key") else
                     25000.5 if field.endswith("1529") else
                     24000.0 if field.endswith("daily_close") else 22000.0)
            if field.endswith("contract_key") and mismatch_prior_contract:
                value = "NIFTY-OCT-FUT"
            source_payload = {"field": field, "source": "verified-fixture"}
            source_event_epoch = None
            if field.endswith("contract_key"):
                source_payload = {"record_type": "FUTURES_CONTRACT_IDENTITY",
                    "contract_key": value}
            elif field.endswith("close_1529"):
                bar_timestamp = f"{prior_date}T15:{'28' if late_1529_bar else '29'}:00+05:30"
                source_payload = {"record_type": "FUTURES_BAR", "bar_interval": "1m",
                    "bar_timestamp_semantics": "BAR_END", "bar_timestamp_ist": bar_timestamp,
                    "bar_status": "COMPLETE", "close": value}
                source_event_epoch = datetime.fromisoformat(bar_timestamp).timestamp()
                if wrong_1529_epoch:
                    source_event_epoch += 1.0
            elif field.endswith("daily_close"):
                source_payload = {"record_type": "NIFTY50_DAILY_CLOSE",
                    "trading_date": prior_date, "close": value}
            elif field.endswith("sma200"):
                fixture_rows = [dict(row) for row in
                    (rolling_rows[:-1] if omit_rolling_row else rolling_rows)]
                if tamper_rolling_row and fixture_rows:
                    fixture_rows[0]["close"] = float(fixture_rows[0]["close"]) + 1
                source_payload = {"field": field, "source": "verified-fixture",
                    "rolling_close_rows": fixture_rows}
            source = build(f"source:{strategy}:{field}",
                source_payload, prior, instrument, source_event_epoch=source_event_epoch)
            graph.add_node(source)
            payload = {
                "strategy_id": strategy, "field": field,
                "contract_id": ("f" * 64 if corrupt_contract and index == 0 else contract_id),
                "value": value, "verification_status": "VERIFIED",
                "instrument": instrument, "target_session": target,
                "source_session": prior, "available_epoch": 80,
                "content_sha256": source["node_id"],
                "source_contract_id": source["contract_id"],
            }
            if field.endswith("sma200"):
                rolling = verify_rolling_close_series(rows=rolling_rows,
                    target_session=target_date, instrument=instrument,
                    calendar_id=target["calendar_id"], calendar_version=target["calendar_version"],
                    formula_id="sma200-daily-close-v1", expected_session_dates=rolling_dates,
                    window=200, decision_epoch=100, expected_adjustment_id="unadjusted-v1")
                payload.update(rolling_formula_id="sma200-daily-close-v1",
                    rolling_adjustment_id="unadjusted-v1",
                    rolling_computation_sha256=rolling["computation_sha256"])
                if corrupt_rolling_hash:
                    payload["rolling_computation_sha256"] = "0" * 64
            derived = build(f"prerequisite:{strategy}:{field}", payload,
                target, instrument, available=80, contract=contract_id)
            graph.add_node(derived)
            graph.add_edge(parent_id=source["node_id"], child_id=derived["node_id"],
                requirement=contract_id, parent_hash=source["node_id"])
            if not omit_calendar_edge:
                graph.add_edge(parent_id=calendar["node_id"], child_id=derived["node_id"],
                    requirement="PREVIOUS_ELIGIBLE_SESSION", parent_hash=calendar["node_id"])
    if publish:
        path = graph.publish(root, session_identity=target)
        return path, target, required, instruments
    return graph, target, required, instruments


def test_verified_heritage_publisher_independently_checks_then_indexes(tmp_path):
    graph, target, required, instruments = _publish_t1_manifest(
        tmp_path, publish=False)
    root = tmp_path / "session-2026-09-29"
    result = publish_verified_heritage_manifest(
        graph=graph, approved_root=root, session_identity=target,
        run_id="target-session-run", decision_epoch=100)
    assert result["status"] == "PUBLISHED_VERIFIED"
    assert result["independent_verification"]["verdict"] == "PASS"
    assert result["read_only"] is True
    assert result["is_order_action"] is False
    resolved = SessionHeritageIndex(root, session=target).resolve(
        run_id="target-session-run")
    assert len(resolved) == 1
    assert resolved[0]["manifest_sha256"] == result["manifest_sha256"]
    t1 = load_verified_t1_prerequisites(
        manifest_path=result["manifest_path"],
        expected_manifest_sha256=result["manifest_sha256"],
        approved_root=root, target_session=target, decision_epoch=100,
        required_fields=required, target_instruments=instruments)
    assert t1["heritage_verification"]["status"] == "VERIFIED"


def test_verified_heritage_publisher_does_not_publish_future_dependency(tmp_path):
    graph, target, _, _ = _publish_t1_manifest(tmp_path, publish=False)
    result = publish_verified_heritage_manifest(
        graph=graph, approved_root=tmp_path / "blocked-session",
        session_identity=target, run_id="future-source-run", decision_epoch=40)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "GRAPH_PREFLIGHT_FAILED"
    assert not (tmp_path / "blocked-session").exists()


def test_heritage_verifiers_reject_nonfinite_decision_epoch(tmp_path):
    path, target, _, _ = _publish_t1_manifest(tmp_path)
    result = publish_verified_heritage_manifest(
        graph=HeritageGraph(), approved_root=tmp_path / "invalid-time",
        session_identity=target, run_id="invalid-time-run", decision_epoch=float("nan"))
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "INVALID_DECISION_EPOCH"
    independent = verify_market_heritage_manifest(path, decision_epoch=float("nan"))
    assert independent["verdict"] == "BLOCKED"
    assert independent["errors"][0]["id"] == "INVALID_DECISION_EPOCH"


def test_runtime_prerequisite_loader_requires_pinned_manifest_and_calendar_ancestor(tmp_path):
    path, target, required, instruments = _publish_t1_manifest(tmp_path)
    loaded = load_verified_t1_prerequisites(manifest_path=path,
        expected_manifest_sha256=__import__("hashlib").sha256(path.read_bytes()).hexdigest(),
        approved_root=tmp_path, target_session=target, decision_epoch=100,
        required_fields=required, target_instruments=instruments)
    assert loaded["heritage_verification"]["status"] == "VERIFIED"
    assert loaded["opening_drive_prev_contract_key"] == "NIFTY-SEP-FUT"
    assert loaded["opening_drive_prev_close_1529"] == 25000.5
    assert loaded["overnight_prev_daily_close"] == 24000.0
    assert loaded["overnight_prev_sma200"] == 22000.0
    assert loaded["heritage_verification"]["read_only"] is True
    assert loaded["heritage_verification"]["allowed_for_live_execution"] is False
    assert verify_market_heritage_manifest(path, decision_epoch=100)["verdict"] == "PASS"

    unpinned = load_verified_t1_prerequisites(manifest_path=path,
        expected_manifest_sha256=None, approved_root=tmp_path, target_session=target,
        decision_epoch=100, required_fields=required, target_instruments=instruments)
    assert unpinned["opening_drive_prev_close_1529"] is None
    assert unpinned["heritage_verification"]["reason"] == "PINNED_HERITAGE_MANIFEST_REQUIRED"


@pytest.mark.parametrize("case,reason", [
    ("no_calendar", "VERIFIED_CALENDAR_PREDECESSOR_REQUIRED"),
    ("wrong_pin", "PINNED_MANIFEST_HASH_MISMATCH"),
    ("wrong_session", "TARGET_SESSION_MISMATCH"),
    ("outside_root", "MANIFEST_OUTSIDE_APPROVED_ROOT"),
])
def test_runtime_prerequisite_loader_blocks_unpinned_or_unclosed_heritage(tmp_path, case, reason):
    path, target, required, instruments = _publish_t1_manifest(
        tmp_path / "root", omit_calendar_edge=(case == "no_calendar"))
    pin = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    kwargs = {"manifest_path": path, "expected_manifest_sha256": pin,
              "approved_root": tmp_path / "root", "target_session": target,
              "decision_epoch": 100, "required_fields": required,
              "target_instruments": instruments}
    if case == "wrong_pin":
        kwargs["expected_manifest_sha256"] = "0" * 64
    elif case == "wrong_session":
        kwargs["target_session"] = {**target, "trading_date": "2026-09-30"}
    elif case == "outside_root":
        kwargs["approved_root"] = tmp_path / "elsewhere"
    loaded = load_verified_t1_prerequisites(**kwargs)
    if case == "no_calendar":
        assert loaded["heritage_verification"]["strategy_readiness"]["INTRADAY_OPENING_DRIVE_V1"]["status"] == "BLOCKED"
        assert any(blocker["reason"] == reason for blocker in loaded["heritage_verification"]["strategy_readiness"]["INTRADAY_OPENING_DRIVE_V1"]["blockers"])
    else:
        assert loaded["opening_drive_prev_close_1529"] is None
        assert reason in loaded["heritage_verification"]["reason"]


@pytest.mark.parametrize("case,strategy,field,reason", [
    ("wrong_contract", "INTRADAY_OPENING_DRIVE_V1", "opening_drive_prev_contract_key", "CONTRACT_MISMATCH"),
    ("bar_1528", "INTRADAY_OPENING_DRIVE_V1", "opening_drive_prev_close_1529", "EXACT_1529_REGULAR_SESSION_FUTURES_BAR_REQUIRED"),
    ("bar_event_epoch", "INTRADAY_OPENING_DRIVE_V1", "opening_drive_prev_close_1529", "EXACT_1529_REGULAR_SESSION_FUTURES_BAR_REQUIRED"),
    ("rolling_199", "S1_MOMENTUM_OVERNIGHT_V1", "overnight_prev_sma200", "SMA200_COMPLETE_200_SESSION_ANCESTRY_REQUIRED"),
    ("rolling_hash", "S1_MOMENTUM_OVERNIGHT_V1", "overnight_prev_sma200", "SMA200_INDEPENDENT_RECOMPUTATION_MISMATCH"),
    ("rolling_row_hash", "S1_MOMENTUM_OVERNIGHT_V1", "overnight_prev_sma200", "SOURCE_ROW_HASH_MISMATCH"),
])
def test_runtime_prerequisite_loader_rejects_inexact_bar_contract_or_rolling_history(
        tmp_path, case, strategy, field, reason):
    path, target, required, instruments = _publish_t1_manifest(tmp_path,
        mismatch_prior_contract=case == "wrong_contract",
        late_1529_bar=case == "bar_1528",
        wrong_1529_epoch=case == "bar_event_epoch",
        omit_rolling_row=case == "rolling_199",
        corrupt_rolling_hash=case == "rolling_hash",
        tamper_rolling_row=case == "rolling_row_hash")
    loaded = load_verified_t1_prerequisites(manifest_path=path,
        expected_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        approved_root=tmp_path, target_session=target, decision_epoch=100,
        required_fields=required, target_instruments=instruments)
    readiness = loaded["heritage_verification"]["strategy_readiness"][strategy]
    assert readiness["status"] == "BLOCKED"
    assert any(item["field"] == field and item["reason"] == reason
        for item in readiness["blockers"])
    if field == "opening_drive_prev_close_1529":
        assert loaded["opening_drive_prev_close_1529"] is None
    independent = verify_market_heritage_manifest(path, decision_epoch=100)
    assert independent["verdict"] == "BLOCKED"
    expected_codes = {
        "wrong_contract": "T1_FUTURES_CONTRACT_CONTINUITY_MISMATCH",
        "bar_1528": "T1_EXACT_1529_FUTURES_BAR_REQUIRED",
        "bar_event_epoch": "T1_EXACT_1529_FUTURES_BAR_REQUIRED",
        "rolling_199": "T1_COMPLETE_SMA200_ANCESTRY_REQUIRED",
        "rolling_hash": "T1_SMA200_INDEPENDENT_RECOMPUTATION_MISMATCH",
        "rolling_row_hash": "T1_SMA200_SERIES_INVALID_OR_INCOMPLETE",
    }
    assert expected_codes[case] in {item["code"] for item in independent["errors"]}


def _capture_cas_pair(root, *, run_id, source_sha, session_date, first_price=25000.0):
    from core.cas_primitive_producer import CASPrimitiveStore

    def make_tick(price, epoch):
        payload = {"instrument_token": 256265, "underlying_symbol": "NIFTY",
            "last_price": price, "volume": 10, "oi": 20,
            "source_timestamp_field": "exchange_timestamp",
            "source_timestamp_epoch": epoch}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True,
            separators=(",", ":"), default=str).encode()).hexdigest()
        return {**payload, "timestamp_epoch": epoch,
            "timestamp_authority": "EXCHANGE_TIMESTAMP",
            "timestamp_source_field": "exchange_timestamp",
            "receive_timestamp_epoch": epoch, "timestamp_fallback_used": False,
            "source_event_id": f"feed:{run_id}:1:256265:{digest[:16]}",
            "source_event_sha256": digest, "source_event_payload": payload}

    session = {"trading_date": session_date, "venue": "NSE",
        "calendar_id": "fixture-calendar", "calendar_version": "v1"}
    p915 = datetime.fromisoformat(f"{session_date}T09:15:00+05:30").timestamp()
    p1000 = datetime.fromisoformat(f"{session_date}T10:00:00+05:30").timestamp()
    store = CASPrimitiveStore(root / run_id / "cas.json", session_id=run_id,
        source_sha=source_sha, underlying_token=256265)
    store.capture("0915", p915, make_tick(first_price, p915 + 0.5), capture_timestamp_ist="capture-0915")
    store.capture("1000", p1000, make_tick(first_price + 10, p1000 + 0.5), capture_timestamp_ist="capture-1000")
    return session, store


def test_same_session_cas_restart_inherits_only_verified_immutable_references(tmp_path):
    source_sha = "1" * 40
    session, store = _capture_cas_pair(tmp_path, run_id="run-a", source_sha=source_sha,
        session_date="2026-09-29")
    heritage_root = tmp_path / "same-session" / "heritage"
    published = publish_same_session_cas_manifest(heritage_root=heritage_root,
        session_identity=session, run_id="run-a", source_sha=source_sha,
        underlying_token=256265, primitives=store.rows)
    assert published["status"] == "PUBLISHED"

    resolved = load_same_session_cas_references(heritage_root=heritage_root,
        session_identity=session, current_run_id="run-b", source_sha=source_sha,
        underlying_token=256265)
    assert resolved["status"] == "VERIFIED"
    assert resolved["primitives"]["0915"]["lineage"]["lineage_status"] == "INHERITED_VERIFIED"
    assert resolved["primitives"]["0915"]["primitive"]["capture_status"] == "CAPTURED"
    assert resolved["primitives"]["0915"]["primitive"]["session_id"] == "run-a"

    from core.cas_primitive_producer import build_inherited_cas_input
    inherited = build_inherited_cas_input(resolved["primitives"], current_run_id="run-b",
        source_sha=source_sha, cycle_id="run-b:1", underlying_token=256265,
        session_identity=session, decision_epoch=datetime.fromisoformat(
            "2026-09-29T10:01:00+05:30").timestamp())
    assert inherited is not None
    assert inherited["session_id"] == "run-b"
    assert inherited["source_run_ids"] == ["run-a"]
    assert inherited["lineage_status"] == "INHERITED_VERIFIED"
    assert inherited["read_only"] is True and inherited["allowed_for_live_execution"] is False

    next_day = {**session, "trading_date": "2026-09-30"}
    crossed = load_same_session_cas_references(heritage_root=heritage_root,
        session_identity=next_day, current_run_id="run-c", source_sha=source_sha,
        underlying_token=256265)
    assert crossed["status"] == "BLOCKED"
    assert crossed["primitives"] == {}


def test_same_session_cas_conflicting_valid_captures_are_blocked(tmp_path):
    source_sha = "1" * 40
    session, first = _capture_cas_pair(tmp_path, run_id="run-a", source_sha=source_sha,
        session_date="2026-09-29")
    root = tmp_path / "same-session" / "heritage"
    assert publish_same_session_cas_manifest(heritage_root=root, session_identity=session,
        run_id="run-a", source_sha=source_sha, underlying_token=256265,
        primitives=first.rows)["status"] == "PUBLISHED"
    _, conflict = _capture_cas_pair(tmp_path, run_id="run-b", source_sha=source_sha,
        session_date="2026-09-29", first_price=25100.0)
    assert publish_same_session_cas_manifest(heritage_root=root, session_identity=session,
        run_id="run-b", source_sha=source_sha, underlying_token=256265,
        primitives=conflict.rows)["status"] == "PUBLISHED"
    resolved = load_same_session_cas_references(heritage_root=root,
        session_identity=session, current_run_id="run-c", source_sha=source_sha,
        underlying_token=256265)
    assert resolved["status"] == "BLOCKED"
    assert resolved["primitives"] == {}
    assert {item["reason"] for item in resolved["blockers"]} == {"CONFLICTING_SAME_SESSION_CAS_SOURCES"}


def test_independent_verifier_rejects_self_consistent_manifest_with_tampered_cas_event(tmp_path):
    import hashlib

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    source_sha = "1" * 40
    session, store = _capture_cas_pair(tmp_path, run_id="run-a", source_sha=source_sha,
        session_date="2026-09-29")
    root = tmp_path / "independent-cas" / "heritage"
    published = publish_same_session_cas_manifest(heritage_root=root,
        session_identity=session, run_id="run-a", source_sha=source_sha,
        underlying_token=256265, primitives=store.rows)
    assert published["status"] == "PUBLISHED"
    path = Path(published["manifest_path"])
    manifest = json.loads(path.read_text())
    baseline = verify_market_heritage_manifest(path)
    assert baseline["verdict"] == "PASS"

    node_row = next(row for row in manifest["nodes"]
        if row.get("payload", {}).get("record_type") == "cas_primitive")
    primitive = node_row["payload"]["primitive"]
    primitive["source_event_payload"]["last_price"] += 1
    primitive["record_sha256"] = digest({key: value for key, value in primitive.items()
        if key != "record_sha256"})
    node_row["node_id"] = digest({key: value for key, value in node_row.items()
        if key != "node_id"})
    manifest["nodes"].sort(key=lambda row: row["node_id"])
    manifest["graph_sha256"] = digest({"session_identity": manifest["session_identity"],
        "nodes": sorted(row["node_id"] for row in manifest["nodes"]),
        "edges": sorted(manifest["edges"], key=lambda row: (row["parent_id"],
            row["child_id"], row["requirement"]))})
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")

    result = verify_market_heritage_manifest(path)
    assert result["verdict"] == "BLOCKED"
    assert "CAS_PRIMITIVE_SOURCE_EVENT_BINDING_INVALID" in {
        row["code"] for row in result["errors"]}


def test_three_process_epochs_merge_distinct_same_day_targets_without_cross_day_bleed(tmp_path):
    from core.cas_primitive_producer import build_inherited_cas_input

    source_sha = "1" * 40
    session, morning = _capture_cas_pair(tmp_path, run_id="process-a",
        source_sha=source_sha, session_date="2026-09-29")
    root = tmp_path / "three-process" / "heritage"
    assert publish_same_session_cas_manifest(heritage_root=root,
        session_identity=session, run_id="process-a", source_sha=source_sha,
        underlying_token=256265, primitives={"0915": morning.rows["0915"]})["status"] == "PUBLISHED"

    _, later = _capture_cas_pair(tmp_path, run_id="process-b",
        source_sha=source_sha, session_date="2026-09-29", first_price=25010.0)
    assert publish_same_session_cas_manifest(heritage_root=root,
        session_identity=session, run_id="process-b", source_sha=source_sha,
        underlying_token=256265, primitives={"1000": later.rows["1000"]})["status"] == "PUBLISHED"

    resolved = load_same_session_cas_references(heritage_root=root,
        session_identity=session, current_run_id="process-c", source_sha=source_sha,
        underlying_token=256265)
    assert resolved["status"] == "VERIFIED"
    inherited = build_inherited_cas_input(resolved["primitives"],
        current_run_id="process-c", source_sha=source_sha, cycle_id="process-c:1",
        underlying_token=256265, session_identity=session,
        decision_epoch=datetime.fromisoformat("2026-09-29T10:01:00+05:30").timestamp())
    assert inherited is not None
    assert inherited["source_run_ids"] == ["process-a", "process-b"]
    assert inherited["lineage"]["0915"]["source_run_id"] == "process-a"
    assert inherited["lineage"]["1000"]["source_run_id"] == "process-b"

    next_day = {**session, "trading_date": "2026-09-30"}
    crossed = load_same_session_cas_references(heritage_root=root,
        session_identity=next_day, current_run_id="process-d", source_sha=source_sha,
        underlying_token=256265)
    assert crossed["status"] == "BLOCKED"
    assert crossed["primitives"] == {}


def test_consecutive_sessions_three_process_epochs_per_day_handoff_only_t1(tmp_path):
    """Six run epochs prove same-day CAS and synthetic T-1 separation over two days."""
    from core.cas_primitive_producer import build_inherited_cas_input

    source_sha = "1" * 40
    day1_heritage = tmp_path / "multi-day" / "2026-09-28" / "heritage"
    day1, first_run = _capture_cas_pair(tmp_path, run_id="d1-process-a",
        source_sha=source_sha, session_date="2026-09-28")
    assert publish_same_session_cas_manifest(heritage_root=day1_heritage,
        session_identity=day1, run_id="d1-process-a", source_sha=source_sha,
        underlying_token=256265,
        primitives={"0915": first_run.rows["0915"]})["status"] == "PUBLISHED"
    _, second_run = _capture_cas_pair(tmp_path, run_id="d1-process-b",
        source_sha=source_sha, session_date="2026-09-28", first_price=25010.0)
    assert publish_same_session_cas_manifest(heritage_root=day1_heritage,
        session_identity=day1, run_id="d1-process-b", source_sha=source_sha,
        underlying_token=256265,
        primitives={"1000": second_run.rows["1000"]})["status"] == "PUBLISHED"
    day1_resolved = load_same_session_cas_references(heritage_root=day1_heritage,
        session_identity=day1, current_run_id="d1-process-c", source_sha=source_sha,
        underlying_token=256265)
    day1_input = build_inherited_cas_input(day1_resolved["primitives"],
        current_run_id="d1-process-c", source_sha=source_sha, cycle_id="d1-c:1",
        underlying_token=256265, session_identity=day1,
        decision_epoch=datetime.fromisoformat("2026-09-28T10:01:00+05:30").timestamp())
    assert day1_input is not None
    assert day1_input["source_run_ids"] == ["d1-process-a", "d1-process-b"]

    # The next eligible session receives only explicitly typed cross-day
    # prerequisites through its pinned calendar-ancestor graph.
    t1_path, day2, required, instruments = _publish_t1_manifest(
        tmp_path / "day2-t1", target_date="2026-09-29", prior_date="2026-09-28")
    t1 = load_verified_t1_prerequisites(manifest_path=t1_path,
        expected_manifest_sha256=hashlib.sha256(t1_path.read_bytes()).hexdigest(),
        approved_root=t1_path.parent, target_session=day2, decision_epoch=100,
        required_fields=required, target_instruments=instruments)
    assert t1["heritage_verification"]["status"] == "VERIFIED"
    assert t1["opening_drive_prev_close_1529"] == 25000.5

    day2_heritage = tmp_path / "multi-day" / "2026-09-29" / "heritage"
    _, day2_first = _capture_cas_pair(tmp_path, run_id="d2-process-a",
        source_sha=source_sha, session_date="2026-09-29", first_price=25030.0)
    assert publish_same_session_cas_manifest(heritage_root=day2_heritage,
        session_identity=day2, run_id="d2-process-a", source_sha=source_sha,
        underlying_token=256265,
        primitives={"0915": day2_first.rows["0915"]})["status"] == "PUBLISHED"
    _, day2_second = _capture_cas_pair(tmp_path, run_id="d2-process-b",
        source_sha=source_sha, session_date="2026-09-29", first_price=25020.0)
    assert publish_same_session_cas_manifest(heritage_root=day2_heritage,
        session_identity=day2, run_id="d2-process-b", source_sha=source_sha,
        underlying_token=256265,
        primitives={"1000": day2_second.rows["1000"]})["status"] == "PUBLISHED"
    day2_resolved = load_same_session_cas_references(heritage_root=day2_heritage,
        session_identity=day2, current_run_id="d2-process-c", source_sha=source_sha,
        underlying_token=256265)
    day2_input = build_inherited_cas_input(day2_resolved["primitives"],
        current_run_id="d2-process-c", source_sha=source_sha, cycle_id="d2-c:1",
        underlying_token=256265, session_identity=day2,
        decision_epoch=datetime.fromisoformat("2026-09-29T10:01:00+05:30").timestamp())
    assert day2_input is not None
    assert day2_input["source_run_ids"] == ["d2-process-a", "d2-process-b"]
    assert all(run_id.startswith("d2-") for run_id in day2_input["source_run_ids"])
    assert day2_input["signal_input_09_15"] == day2_first.rows["0915"]["price"]
    assert day2_input["signal_input_09_15"] != day1_input["signal_input_09_15"]


def test_same_session_index_publishes_and_resolves_coverage_without_cas_promotion(tmp_path):
    source_sha = "1" * 40
    report = {"schema_version": 1, "run_id": "run-a",
        "session_identity": SESSION, "run_started_epoch": 100.0,
        "run_ended_epoch": 200.0, "intended_token_count": 1,
        "intended_tokens": [256265],
        "per_token": {"256265": {"coverage_status": "OBSERVED_INTERVAL_ONLY"}},
        "read_only": True, "append": False, "is_order_action": False,
        "broker_api_called": False, "broker_write_authority": False,
        "order_authority": False, "paper_authorized": False,
        "live_authorized": False, "allowed_for_live_execution": False}
    root = tmp_path / "coverage-only"
    published = publish_same_session_cas_manifest(heritage_root=root,
        session_identity=SESSION, run_id="run-a", source_sha=source_sha,
        underlying_token=256265, primitives={}, coverage_report=report)
    assert published["status"] == "PUBLISHED"
    assert published["primitive_count"] == 0
    assert published["coverage_published"] is True

    resolved = load_same_session_cas_references(heritage_root=root,
        session_identity=SESSION, current_run_id="run-b", source_sha=source_sha,
        underlying_token=256265)
    assert resolved["status"] == "PARTIAL"
    assert resolved["primitives"] == {}
    assert len(resolved["coverage"]) == 1
    assert resolved["coverage"][0]["status"] == "VERIFIED_SAME_SESSION_RUN_COVERAGE"
    assert resolved["coverage"][0]["source_run_id"] == "run-a"


def _daily_row(day, close, *, available=10, adjustment="unadjusted-v1"):
    row = {"trading_date": day, "close": close, "verification_status": "VERIFIED",
            "instrument": {"symbol": "NIFTY50", "basis": "INDEX"},
            "calendar_id": "NSE-HIST", "calendar_version": "v4",
            "formula_id": "sma200-daily-close-v1", "eligible_session": True,
            "complete": True, "adjustment_id": adjustment, "available_epoch": available,
            "content_sha256": ""}
    row["content_sha256"] = rolling_source_row_hash(row)
    return row


def test_rolling_sma_recomputes_complete_verified_series_independently():
    rows = [_daily_row(f"2025-01-{day:02d}", float(day)) for day in range(1, 6)]
    result = verify_rolling_close_series(rows=rows, target_session="2025-01-06",
        instrument={"symbol": "NIFTY50", "basis": "INDEX"}, calendar_id="NSE-HIST",
        calendar_version="v4", formula_id="sma200-daily-close-v1",
        expected_session_dates=[f"2025-01-{day:02d}" for day in range(1, 6)], window=5,
        decision_epoch=10, expected_adjustment_id="unadjusted-v1")
    assert result["status"] == "VERIFIED"
    assert result["value"] == 3.0
    assert result["window"] == 5
    assert len(result["computation_sha256"]) == 64


def test_rolling_sma_requires_exact_authoritative_session_sequence():
    rows = [_daily_row(f"2025-01-{day:02d}", float(day)) for day in (1, 2, 4, 5, 6)]
    result = verify_rolling_close_series(rows=rows, target_session="2025-01-07",
        instrument={"symbol": "NIFTY50", "basis": "INDEX"}, calendar_id="NSE-HIST",
        calendar_version="v4", formula_id="sma200-daily-close-v1",
        expected_session_dates=[f"2025-01-{day:02d}" for day in range(1, 6)], window=5,
        decision_epoch=10, expected_adjustment_id="unadjusted-v1")
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "ROLLING_SESSION_SEQUENCE_MISMATCH"


@pytest.mark.parametrize("mutator,reason", [
    (lambda rows: rows.pop(), "ROLLING_COVERAGE_COUNT_MISMATCH"),
    (lambda rows: rows.__setitem__(2, {**rows[2], "complete": False}), "INCOMPLETE_OR_INELIGIBLE_SESSION"),
    (lambda rows: rows.__setitem__(2, {**rows[2], "instrument": {"symbol": "NIFTY-FUT"}}), "WRONG_INSTRUMENT_OR_CONTRACT"),
    (lambda rows: rows.__setitem__(2, {**rows[2], "available_epoch": 11}), "FUTURE_INFORMATION"),
    (lambda rows: rows.__setitem__(2, {**rows[2], "adjustment_id": "unknown-roll"}), "ADJUSTMENT_OR_ROLL_AMBIGUITY"),
    (lambda rows: rows.__setitem__(2, {**rows[2], "close": 999.0}), "SOURCE_ROW_HASH_MISMATCH"),
])
def test_rolling_sma_rejects_incomplete_or_ambiguous_ancestors(mutator, reason):
    rows = [_daily_row(f"2025-01-{day:02d}", float(day)) for day in range(1, 6)]
    mutator(rows)
    result = verify_rolling_close_series(rows=rows, target_session="2025-01-06",
        instrument={"symbol": "NIFTY50", "basis": "INDEX"}, calendar_id="NSE-HIST",
        calendar_version="v4", formula_id="sma200-daily-close-v1",
        expected_session_dates=[f"2025-01-{day:02d}" for day in range(1, 6)], window=5,
        decision_epoch=10, expected_adjustment_id="unadjusted-v1")
    assert result["status"] == "BLOCKED"
    assert result["reason"] == reason
