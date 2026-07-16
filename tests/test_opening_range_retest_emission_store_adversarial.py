from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.opening_range_retest_emission_store import (
    OpeningRangeRetestEmissionStore,
    OpeningRangeRetestProposal,
    create_isolated_replay_store,
)


def _utc_iso(y: int, m: int, d: int, hh: int, mm: int, ss: int = 0) -> str:
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _proposal(
    setup_id: str = "setup-1",
    *,
    boundary_value: float = 25321.25,
    history_hash: str = "a" * 64,
    candidate_fingerprint: str = "fingerprint-1",
    candidate_payload: dict[str, object] | None = None,
) -> OpeningRangeRetestProposal:
    payload = candidate_payload or {
        "strategy_id": "opening_range_retest_v1",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "history_hash": history_hash,
    }
    return OpeningRangeRetestProposal(
        setup_id=setup_id,
        strategy_id="opening_range_retest_v1",
        contract_version="opening_range_retest_protocol_v1",
        schema_version=1,
        source_component="strategies.movement.opening_range_breakout.generate_opening_range_retest_candidates",
        symbol="NIFTY",
        session_date="2026-07-14",
        direction="BUY_CALL",
        boundary_type="ORB_HIGH",
        normalized_boundary_value=boundary_value,
        breakout_timestamp_iso="2026-07-14T04:20:00Z",
        history_hash=history_hash,
        candidate_fingerprint=candidate_fingerprint,
        candidate_payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        created_at_iso="2026-07-14T04:25:00Z",
    )


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _fetch_count(db_path: Path, table: str, setup_id: str) -> int:
    with _connect(db_path) as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE setup_id=?", (setup_id,)).fetchone()
        return int(row[0] or 0)


def _fetch_row(db_path: Path, table: str, setup_id: str):
    with _connect(db_path) as conn:
        return conn.execute(f"SELECT * FROM {table} WHERE setup_id=?", (setup_id,)).fetchone()


@contextmanager
def _store(tmp_path: Path, name: str):
    db_path = tmp_path / name
    store = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    yield store, db_path


def test_atomic_rollback_on_outbox_insert_failure(tmp_path, monkeypatch):
    with _store(tmp_path, "atomic.sqlite") as (store, db_path):
        proposal = _proposal("atomic-1")

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(store, "_insert_outbox_row", _boom)

        result = store.accept_candidate_proposal(proposal)
        assert result.result == "ERROR"
        assert "boom" in (result.detail or "")
        assert _fetch_count(db_path, "opening_range_retest_lineage", "atomic-1") == 0
        assert _fetch_count(db_path, "opening_range_retest_outbox", "atomic-1") == 0


def test_sequential_duplicate_baseline(tmp_path):
    with _store(tmp_path, "duplicate.sqlite") as (store, db_path):
        proposal = _proposal("duplicate-1")
        first = store.accept_candidate_proposal(proposal)
        second = store.accept_candidate_proposal(proposal)
        assert first.result == "ACCEPTED_FOR_PUBLICATION"
        assert second.result == "ALREADY_EMITTED"
        assert _fetch_count(db_path, "opening_range_retest_lineage", "duplicate-1") == 1
        assert _fetch_count(db_path, "opening_range_retest_outbox", "duplicate-1") == 1
        row = _fetch_row(db_path, "opening_range_retest_outbox", "duplicate-1")
        assert int(row["publication_attempts"]) == 0
        assert str(row["candidate_payload_json"]) == proposal.candidate_payload_json


def test_concurrent_exact_duplicate_acceptance(tmp_path):
    outcome_counts: dict[str, int] = {}
    for iteration in range(20):
        with _store(tmp_path, f"concurrent-dup-{iteration}.sqlite") as (store_a, db_path):
            store_b = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
            proposal = _proposal(f"concurrent-dup-{iteration}")
            barrier = threading.Barrier(2)
            results: list[str] = []

            def _call(store: OpeningRangeRetestEmissionStore) -> str:
                barrier.wait(timeout=5)
                return store.accept_candidate_proposal(proposal).result

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(_call, store_a), pool.submit(_call, store_b)]
                for future in futures:
                    results.append(future.result(timeout=10))

            assert results.count("ACCEPTED_FOR_PUBLICATION") == 1
            assert results.count("ALREADY_EMITTED") == 1
            assert results.count("OWNER_STATE_CONFLICT") == 0
            assert _fetch_count(db_path, "opening_range_retest_lineage", f"concurrent-dup-{iteration}") == 1
            assert _fetch_count(db_path, "opening_range_retest_outbox", f"concurrent-dup-{iteration}") == 1
            for result in results:
                outcome_counts[result] = outcome_counts.get(result, 0) + 1
    assert outcome_counts["ACCEPTED_FOR_PUBLICATION"] == 20
    assert outcome_counts["ALREADY_EMITTED"] == 20


def test_concurrent_immutable_conflict(tmp_path):
    for iteration in range(20):
        with _store(tmp_path, f"concurrent-conflict-{iteration}.sqlite") as (store_a, db_path):
            store_b = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
            proposal_a = _proposal(
                f"conflict-{iteration}",
                boundary_value=25321.25,
                history_hash="a" * 64,
                candidate_fingerprint="fp-a",
            )
            proposal_b = _proposal(
                f"conflict-{iteration}",
                boundary_value=25322.25,
                history_hash="b" * 64,
                candidate_fingerprint="fp-b",
            )
            barrier = threading.Barrier(2)
            results: list[str] = []

            def _call(store: OpeningRangeRetestEmissionStore, proposal: OpeningRangeRetestProposal) -> str:
                barrier.wait(timeout=5)
                return store.accept_candidate_proposal(proposal).result

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(_call, store_a, proposal_a), pool.submit(_call, store_b, proposal_b)]
                for future in futures:
                    results.append(future.result(timeout=10))

            assert "ACCEPTED_FOR_PUBLICATION" in results
            assert "OWNER_STATE_CONFLICT" in results or results.count("OWNER_BUSY") == 1
            assert _fetch_count(db_path, "opening_range_retest_lineage", f"conflict-{iteration}") == 1
            assert _fetch_count(db_path, "opening_range_retest_outbox", f"conflict-{iteration}") == 1


def test_delivery_start_repeated_call_increments_attempts_only_once(tmp_path):
    with _store(tmp_path, "delivery-repeat.sqlite") as (store, db_path):
        proposal = _proposal("delivery-repeat-1")
        assert store.accept_candidate_proposal(proposal).result == "ACCEPTED_FOR_PUBLICATION"
        lease = store.acquire_delivery_lease(setup_id="delivery-repeat-1", lease_owner_id="owner-a", now_iso="2026-07-14T05:00:00Z")
        assert lease.result == "LEASE_GRANTED"
        downstream_delivery_count = 0
        first = store.record_delivery_start(
            setup_id="delivery-repeat-1",
            lease_token=lease.lease_token or "",
            lease_owner_id="owner-a",
            now_iso="2026-07-14T05:00:01Z",
        )
        if first.result == "DELIVERY_STARTED":
            downstream_delivery_count += 1
        row_after_first = _fetch_row(db_path, "opening_range_retest_outbox", "delivery-repeat-1")
        second = store.record_delivery_start(
            setup_id="delivery-repeat-1",
            lease_token=lease.lease_token or "",
            lease_owner_id="owner-a",
            now_iso="2026-07-14T05:00:02Z",
        )
        if second.result == "DELIVERY_STARTED":
            downstream_delivery_count += 1
        row_after_second = _fetch_row(db_path, "opening_range_retest_outbox", "delivery-repeat-1")
        assert first.result == "DELIVERY_STARTED"
        assert first.publication_attempts == 1
        assert first.last_attempt_at_iso == "2026-07-14T05:00:01Z"
        assert second.result == "ALREADY_DELIVERY_STARTED"
        assert second.publication_attempts == 1
        assert second.last_attempt_at_iso == "2026-07-14T05:00:01Z"
        assert row_after_first is not None and row_after_first["publication_state"] == "LEASED"
        assert row_after_second is not None and int(row_after_second["publication_attempts"]) == 1
        assert row_after_second["last_attempt_at_iso"] == "2026-07-14T05:00:01Z"
        assert row_after_second["lease_token"] == lease.lease_token
        assert row_after_second["lease_owner_id"] == "owner-a"
        assert downstream_delivery_count == 1


def test_lease_token_and_owner_guards(tmp_path):
    with _store(tmp_path, "guards.sqlite") as (store, db_path):
        proposal = _proposal("guards-1")
        assert store.accept_candidate_proposal(proposal).result == "ACCEPTED_FOR_PUBLICATION"
        lease = store.acquire_delivery_lease(setup_id="guards-1", lease_owner_id="owner-a", now_iso="2026-07-14T05:00:00Z")
        assert lease.result == "LEASE_GRANTED"
        wrong_token = store.record_delivery_start(
            setup_id="guards-1",
            lease_token="wrong",
            lease_owner_id="owner-a",
            now_iso="2026-07-14T05:00:01Z",
        )
        wrong_owner = store.record_delivery_start(
            setup_id="guards-1",
            lease_token=lease.lease_token or "",
            lease_owner_id="wrong-owner",
            now_iso="2026-07-14T05:00:01Z",
        )
        assert wrong_token.result == "OWNER_STATE_CONFLICT"
        assert wrong_owner.result == "OWNER_STATE_CONFLICT"
        row = _fetch_row(db_path, "opening_range_retest_outbox", "guards-1")
        assert int(row["publication_attempts"]) == 0


def test_restart_reopen_states_and_crash_timing(tmp_path):
    db_path = tmp_path / "restart.sqlite"
    proposal = _proposal("restart-1")

    store = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    assert store.accept_candidate_proposal(proposal).result == "ACCEPTED_FOR_PUBLICATION"
    lease = store.acquire_delivery_lease(setup_id="restart-1", lease_owner_id="owner-a", now_iso="2026-07-14T05:00:00Z")
    assert lease.result == "LEASE_GRANTED"
    del store

    reopened = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    assert reopened.acquire_delivery_lease(setup_id="restart-1", lease_owner_id="owner-b", now_iso="2026-07-14T05:00:10Z").result == "LEASE_HELD"
    start = reopened.record_delivery_start(
        setup_id="restart-1",
        lease_token=lease.lease_token or "",
        lease_owner_id="owner-a",
        now_iso="2026-07-14T05:00:11Z",
    )
    assert start.result == "DELIVERY_STARTED"
    del reopened

    reopened2 = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    row = _fetch_row(db_path, "opening_range_retest_outbox", "restart-1")
    assert row is not None and int(row["publication_attempts"]) == 1
    assert reopened2.acquire_delivery_lease(setup_id="restart-1", lease_owner_id="owner-c", now_iso="2026-07-14T05:00:12Z").result == "LEASE_HELD"


def test_reclaimed_lease_resets_delivery_marker_and_advances_attempt_count(tmp_path):
    db_path = tmp_path / "reclaim.sqlite"
    proposal = _proposal("reclaim-1")

    store = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    assert store.accept_candidate_proposal(proposal).result == "ACCEPTED_FOR_PUBLICATION"
    lease1 = store.acquire_delivery_lease(setup_id="reclaim-1", lease_owner_id="owner-a", now_iso="2026-07-14T05:00:00Z")
    assert lease1.result == "LEASE_GRANTED"
    first = store.record_delivery_start(
        setup_id="reclaim-1",
        lease_token=lease1.lease_token or "",
        lease_owner_id="owner-a",
        now_iso="2026-07-14T05:00:01Z",
    )
    row_after_first = _fetch_row(db_path, "opening_range_retest_outbox", "reclaim-1")
    assert first.result == "DELIVERY_STARTED"
    assert int(row_after_first["publication_attempts"]) == 1
    assert str(row_after_first["last_attempt_at_iso"]) == "2026-07-14T05:00:01Z"

    reopened = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    lease2 = reopened.acquire_delivery_lease(setup_id="reclaim-1", lease_owner_id="owner-b", now_iso="2026-07-14T05:00:40Z")
    row_after_reclaim = _fetch_row(db_path, "opening_range_retest_outbox", "reclaim-1")
    assert lease2.result == "LEASE_GRANTED"
    assert row_after_reclaim is not None and row_after_reclaim["last_attempt_at_iso"] is None

    second = reopened.record_delivery_start(
        setup_id="reclaim-1",
        lease_token=lease2.lease_token or "",
        lease_owner_id="owner-b",
        now_iso="2026-07-14T05:00:41Z",
    )
    row_after_second = _fetch_row(db_path, "opening_range_retest_outbox", "reclaim-1")
    assert second.result == "DELIVERY_STARTED"
    assert int(row_after_second["publication_attempts"]) == 2
    assert str(row_after_second["last_attempt_at_iso"]) == "2026-07-14T05:00:41Z"


def test_real_owner_busy_and_unavailable_classification(tmp_path):
    db_path = tmp_path / "busy.sqlite"
    lock_conn = sqlite3.connect(str(db_path))
    lock_conn.execute("BEGIN EXCLUSIVE")
    try:
        busy_store = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
        assert busy_store.is_available is False
        assert busy_store.initialization_classification == "OWNER_BUSY"
        assert busy_store.initialization_error is not None
        result = busy_store.accept_candidate_proposal(_proposal("busy-1"))
        assert result.result == "OWNER_BUSY"
        assert busy_store.get_lineage("busy-1") is None
        assert busy_store.get_outbox_record("busy-1") is None
    finally:
        lock_conn.rollback()
        lock_conn.close()

    unavailable = tmp_path / "missing-owner-db"
    unavailable.mkdir()
    store = OpeningRangeRetestEmissionStore(db_path=unavailable, lease_seconds=30)
    assert store.is_available is False
    assert store.initialization_classification == "OWNER_UNAVAILABLE"
    assert store.initialization_error is not None
    result = store.accept_candidate_proposal(_proposal("unavailable-1"))
    assert result.result in {"OWNER_UNAVAILABLE", "ERROR"}
    assert store.get_lineage("unavailable-1") is None
    assert store.get_outbox_record("unavailable-1") is None


def test_schema_conflict_initialization_is_explicit(tmp_path):
    db_path = tmp_path / "schema-conflict.sqlite"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE opening_range_retest_lineage (setup_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE opening_range_retest_outbox (setup_id TEXT PRIMARY KEY)")
        conn.commit()

    store = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    assert store.is_available is False
    assert store.initialization_classification == "OWNER_STATE_CONFLICT"
    assert store.initialization_error is not None
    assert "schema mismatch" in store.initialization_error.message or "no such column" in store.initialization_error.message

    calls: list[str] = []

    def _boom(*args, **kwargs):
        calls.append("called")
        raise AssertionError("unexpected connection attempt")

    store._connect = _boom  # type: ignore[method-assign]
    assert store.accept_candidate_proposal(_proposal("schema-conflict-1")).result == "OWNER_STATE_CONFLICT"
    assert store.acquire_delivery_lease(setup_id="schema-conflict-1", lease_owner_id="owner-a", now_iso="2026-07-14T05:00:00Z").result == "OWNER_STATE_CONFLICT"
    assert store.record_delivery_start(
        setup_id="schema-conflict-1",
        lease_token="t",
        lease_owner_id="owner-a",
        now_iso="2026-07-14T05:00:00Z",
    ).result == "OWNER_STATE_CONFLICT"
    assert store.record_delivery_success(
        setup_id="schema-conflict-1",
        lease_token="t",
        lease_owner_id="owner-a",
        now_iso="2026-07-14T05:00:00Z",
    ).result == "OWNER_STATE_CONFLICT"
    assert store.record_retryable_failure(
        setup_id="schema-conflict-1",
        lease_token="t",
        lease_owner_id="owner-a",
        last_error="err",
        now_iso="2026-07-14T05:00:00Z",
    ).result == "OWNER_STATE_CONFLICT"
    assert store.record_terminal_failure(
        setup_id="schema-conflict-1",
        lease_token="t",
        lease_owner_id="owner-a",
        last_error="err",
        now_iso="2026-07-14T05:00:00Z",
    ).result == "OWNER_STATE_CONFLICT"
    assert store.get_lineage("schema-conflict-1") is None
    assert store.get_outbox_record("schema-conflict-1") is None
    assert calls == []


def test_schema_and_state_corruption_fail_closed(tmp_path):
    db_path = tmp_path / "corrupt.sqlite"
    store = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    proposal = _proposal("corrupt-1")
    assert store.accept_candidate_proposal(proposal).result == "ACCEPTED_FOR_PUBLICATION"

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA ignore_check_constraints=ON")
        conn.execute("UPDATE opening_range_retest_lineage SET state='BROKEN' WHERE setup_id='corrupt-1'")
        conn.commit()

    reopened = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    assert reopened.get_lineage("corrupt-1") is not None
    lease = reopened.acquire_delivery_lease(setup_id="corrupt-1", lease_owner_id="owner-a", now_iso="2026-07-14T05:00:00Z")
    assert lease.result == "OWNER_STATE_CONFLICT"


def test_connection_lifecycle_and_replay_isolation(tmp_path):
    with create_isolated_replay_store() as store_a:
        with create_isolated_replay_store() as store_b:
            proposal_a = _proposal("replay-a")
            proposal_b = _proposal("replay-b")
            assert store_a.accept_candidate_proposal(proposal_a).result == "ACCEPTED_FOR_PUBLICATION"
            assert store_b.accept_candidate_proposal(proposal_b).result == "ACCEPTED_FOR_PUBLICATION"
            assert store_a.get_lineage("replay-a") is not None
            assert store_b.get_lineage("replay-b") is not None
            assert store_a.get_lineage("replay-b") is None
            assert store_b.get_lineage("replay-a") is None


def test_lease_and_delivery_state_matrix(tmp_path):
    db_path = tmp_path / "matrix.sqlite"
    store = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    proposal = _proposal("matrix-1")
    assert store.accept_candidate_proposal(proposal).result == "ACCEPTED_FOR_PUBLICATION"
    assert store.acquire_delivery_lease(setup_id="matrix-1", lease_owner_id="owner-a", now_iso="2026-07-14T05:00:00Z").result == "LEASE_GRANTED"
    row = _fetch_row(db_path, "opening_range_retest_outbox", "matrix-1")
    assert row is not None and row["publication_state"] == "LEASED"
