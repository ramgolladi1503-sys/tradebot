from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from config import config as cfg
from core.opening_range_retest_emission_store import (
    DeliveryResult,
    LeaseResult,
    OpeningRangeRetestEmissionStore,
    OpeningRangeRetestProposal,
    PublicationResult,
    create_isolated_replay_store,
)


def _utc_iso(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> str:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _proposal(
    *,
    setup_id: str = "setup-1",
    candidate_payload: dict[str, object] | None = None,
    boundary_value: float = 25321.25,
    breakout_ts: str = "2026-07-14T04:20:00Z",
    created_at: str = "2026-07-14T04:25:00Z",
    candidate_fingerprint: str = "fingerprint-1",
    history_hash: str = "a" * 64,
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
        breakout_timestamp_iso=breakout_ts,
        history_hash=history_hash,
        candidate_fingerprint=candidate_fingerprint,
        candidate_payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        created_at_iso=created_at,
    )


def _table_columns(db_path: str, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _fetch_row(db_path: str, table: str, setup_id: str):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(f"SELECT * FROM {table} WHERE setup_id=?", (setup_id,)).fetchone()


def test_schema_initialization_and_idempotency(tmp_path):
    db_path = tmp_path / "opening_range_retest_owner.sqlite"
    store = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    store.init_schema()
    store.init_schema()

    assert store.is_available is True
    assert store.initialization_classification is None
    assert store.initialization_error is None

    assert db_path.exists()
    assert {
        "setup_id",
        "strategy_id",
        "contract_version",
        "schema_version",
        "source_component",
        "symbol",
        "session_date",
        "direction",
        "boundary_type",
        "normalized_boundary_value",
        "breakout_timestamp_iso",
        "history_hash",
        "candidate_fingerprint",
        "state",
        "created_at_iso",
        "emitted_at_iso",
        "invalidated_at_iso",
        "expired_at_iso",
    }.issubset(_table_columns(str(db_path), "opening_range_retest_lineage"))
    assert {
        "outbox_id",
        "setup_id",
        "candidate_payload_json",
        "candidate_fingerprint",
        "publication_state",
        "publication_attempts",
        "created_at_iso",
        "next_attempt_at_iso",
        "published_at_iso",
        "last_attempt_at_iso",
        "last_error",
        "lease_token",
        "lease_owner_id",
        "lease_acquired_at_iso",
        "lease_expires_at_iso",
        "schema_version",
    }.issubset(_table_columns(str(db_path), "opening_range_retest_outbox"))


def test_first_atomic_acceptance_rolls_back_lineage_and_outbox_together(tmp_path, monkeypatch):
    store = OpeningRangeRetestEmissionStore(db_path=tmp_path / "store.sqlite", lease_seconds=30)
    proposal = _proposal(setup_id="rollback-1")

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "_insert_outbox_row", _boom)

    result = store.accept_candidate_proposal(proposal)
    assert result.result == "ERROR"
    assert "boom" in (result.detail or "")

    assert store.get_lineage("rollback-1") is None
    assert store.get_outbox_record("rollback-1") is None


def test_first_atomic_acceptance_and_duplicate_handling(tmp_path):
    store = OpeningRangeRetestEmissionStore(db_path=tmp_path / "store.sqlite", lease_seconds=30)
    proposal = _proposal(setup_id="dup-1")

    accepted = store.accept_candidate_proposal(proposal)
    assert isinstance(accepted, PublicationResult)
    assert accepted.result == "ACCEPTED_FOR_PUBLICATION"
    assert accepted.lineage_state == "EMITTED"
    assert accepted.publication_state == "PENDING"
    assert accepted.publication_attempts == 0

    lineage = store.get_lineage("dup-1")
    outbox = store.get_outbox_record("dup-1")
    assert lineage is not None
    assert outbox is not None
    assert lineage.state == "EMITTED"
    assert outbox.publication_state == "PENDING"
    assert outbox.publication_attempts == 0
    assert outbox.candidate_payload_json == proposal.candidate_payload_json

    duplicate = store.accept_candidate_proposal(proposal)
    assert duplicate.result == "ALREADY_EMITTED"
    assert duplicate.lineage_state == "EMITTED"
    assert duplicate.publication_state == "PENDING"
    assert store.get_outbox_record("dup-1").candidate_payload_json == proposal.candidate_payload_json


def test_immutable_conflict_does_not_overwrite_existing_rows(tmp_path):
    store = OpeningRangeRetestEmissionStore(db_path=tmp_path / "store.sqlite", lease_seconds=30)
    proposal = _proposal(setup_id="conflict-1", candidate_fingerprint="fingerprint-a")
    store.accept_candidate_proposal(proposal)

    conflict = replace(
        proposal,
        normalized_boundary_value=proposal.normalized_boundary_value + 1.0,
        candidate_payload_json=json.dumps(
            {
                "strategy_id": "opening_range_retest_v1",
                "symbol": "NIFTY",
                "direction": "BUY_CALL",
                "history_hash": proposal.history_hash,
                "note": "changed",
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    result = store.accept_candidate_proposal(conflict)
    assert result.result == "OWNER_STATE_CONFLICT"

    lineage = store.get_lineage("conflict-1")
    outbox = store.get_outbox_record("conflict-1")
    assert lineage is not None and outbox is not None
    assert lineage.normalized_boundary_value == proposal.normalized_boundary_value
    assert outbox.candidate_payload_json == proposal.candidate_payload_json


def test_publication_attempts_and_delivery_transitions(tmp_path):
    store = OpeningRangeRetestEmissionStore(db_path=tmp_path / "store.sqlite", lease_seconds=30)
    proposal = _proposal(setup_id="lease-1")
    store.accept_candidate_proposal(proposal)

    lease = store.acquire_delivery_lease(setup_id="lease-1", lease_owner_id="owner-a", now_iso="2026-07-14T05:00:00Z")
    assert isinstance(lease, LeaseResult)
    assert lease.result == "LEASE_GRANTED"
    assert lease.publication_state == "LEASED"
    assert lease.publication_attempts == 0
    assert lease.stale_lease_reclaimed is False
    assert lease.lease_token

    outbox = store.get_outbox_record("lease-1")
    assert outbox is not None
    assert outbox.publication_state == "LEASED"
    assert outbox.publication_attempts == 0

    start = store.record_delivery_start(
        setup_id="lease-1",
        lease_token=lease.lease_token or "",
        lease_owner_id="owner-a",
        now_iso="2026-07-14T05:00:10Z",
    )
    assert isinstance(start, DeliveryResult)
    assert start.result == "DELIVERY_STARTED"
    assert start.publication_attempts == 1

    outbox = store.get_outbox_record("lease-1")
    assert outbox is not None
    assert outbox.publication_attempts == 1
    assert outbox.last_attempt_at_iso == "2026-07-14T05:00:10Z"

    success = store.record_delivery_success(
        setup_id="lease-1",
        lease_token=lease.lease_token or "",
        lease_owner_id="owner-a",
        now_iso="2026-07-14T05:00:20Z",
    )
    assert success.result == "DELIVERED"
    outbox = store.get_outbox_record("lease-1")
    assert outbox is not None
    assert outbox.publication_state == "PUBLISHED"
    assert outbox.publication_attempts == 1
    assert outbox.lease_token is None
    assert outbox.last_error is None
    assert outbox.published_at_iso == "2026-07-14T05:00:20Z"

    repeated = store.record_delivery_success(
        setup_id="lease-1",
        lease_token=lease.lease_token or "",
        lease_owner_id="owner-a",
        now_iso="2026-07-14T05:00:30Z",
    )
    assert repeated.result == "ALREADY_PUBLISHED"
    assert store.get_outbox_record("lease-1").publication_attempts == 1


def test_retryable_and_terminal_failure_paths(tmp_path):
    store = OpeningRangeRetestEmissionStore(db_path=tmp_path / "store.sqlite", lease_seconds=30)

    retry_proposal = _proposal(setup_id="retry-1")
    store.accept_candidate_proposal(retry_proposal)
    retry_lease = store.acquire_delivery_lease(setup_id="retry-1", lease_owner_id="owner-r", now_iso="2026-07-14T05:10:00Z")
    store.record_delivery_start(
        setup_id="retry-1",
        lease_token=retry_lease.lease_token or "",
        lease_owner_id="owner-r",
        now_iso="2026-07-14T05:10:05Z",
    )
    retry = store.record_retryable_failure(
        setup_id="retry-1",
        lease_token=retry_lease.lease_token or "",
        lease_owner_id="owner-r",
        last_error="transient",
        next_attempt_at_iso="2026-07-14T05:11:00Z",
        now_iso="2026-07-14T05:10:06Z",
    )
    assert retry.result == "RETRYABLE_FAILED"
    assert retry.next_attempt_at_iso == "2026-07-14T05:11:00Z"
    outbox = store.get_outbox_record("retry-1")
    assert outbox is not None
    assert outbox.publication_state == "RETRYABLE_FAILED"
    assert outbox.publication_attempts == 1
    assert outbox.lease_token is None
    assert outbox.next_attempt_at_iso == "2026-07-14T05:11:00Z"

    reclaimed = store.acquire_delivery_lease(setup_id="retry-1", lease_owner_id="owner-r", now_iso="2026-07-14T05:11:01Z")
    assert reclaimed.result == "LEASE_GRANTED"

    final_proposal = _proposal(setup_id="final-1")
    store.accept_candidate_proposal(final_proposal)
    final_lease = store.acquire_delivery_lease(setup_id="final-1", lease_owner_id="owner-f", now_iso="2026-07-14T05:20:00Z")
    store.record_delivery_start(
        setup_id="final-1",
        lease_token=final_lease.lease_token or "",
        lease_owner_id="owner-f",
        now_iso="2026-07-14T05:20:01Z",
    )
    terminal = store.record_terminal_failure(
        setup_id="final-1",
        lease_token=final_lease.lease_token or "",
        lease_owner_id="owner-f",
        last_error="fatal",
        now_iso="2026-07-14T05:20:02Z",
    )
    assert terminal.result == "FAILED_FINAL"
    outbox = store.get_outbox_record("final-1")
    assert outbox is not None
    assert outbox.publication_state == "FAILED_FINAL"
    assert outbox.last_error == "fatal"

    repeated_final = store.record_terminal_failure(
        setup_id="final-1",
        lease_token=final_lease.lease_token or "",
        lease_owner_id="owner-f",
        last_error="fatal",
        now_iso="2026-07-14T05:20:03Z",
    )
    assert repeated_final.result == "FAILED_FINAL"
    assert store.get_outbox_record("final-1").publication_attempts == 1


def test_invalid_lease_config_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "OPENING_RANGE_RETEST_PUBLICATION_LEASE_SECONDS", 0, raising=False)
    with pytest.raises(ValueError, match="invalid_publication_lease_seconds"):
        OpeningRangeRetestEmissionStore(db_path=tmp_path / "store.sqlite")


def test_replay_store_isolation_and_cleanup():
    with create_isolated_replay_store() as store_a:
        with create_isolated_replay_store() as store_b:
            assert store_a.db_path != store_b.db_path
            assert store_a.db_path != Path(str(getattr(cfg, "TRADE_DB_PATH", "")))

            proposal_a = _proposal(setup_id="isolation-a")
            proposal_b = _proposal(setup_id="isolation-b")
            assert store_a.accept_candidate_proposal(proposal_a).result == "ACCEPTED_FOR_PUBLICATION"
            assert store_b.accept_candidate_proposal(proposal_b).result == "ACCEPTED_FOR_PUBLICATION"

            assert store_a.get_lineage("isolation-a") is not None
            assert store_b.get_lineage("isolation-b") is not None
            assert store_a.get_lineage("isolation-b") is None
            assert store_b.get_lineage("isolation-a") is None

        assert store_b.db_path.exists() is False
    assert store_a.db_path.exists() is False


def test_multi_connection_smoke_test(tmp_path):
    db_path = tmp_path / "shared.sqlite"
    store_a = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    store_b = OpeningRangeRetestEmissionStore(db_path=db_path, lease_seconds=30)
    proposal = _proposal(setup_id="shared-1")
    assert store_a.accept_candidate_proposal(proposal).result == "ACCEPTED_FOR_PUBLICATION"
    assert store_b.get_lineage("shared-1") is not None
    assert store_b.get_outbox_record("shared-1") is not None


def test_proposal_validation_rejects_noncanonical_json():
    with pytest.raises(ValueError, match="non_canonical_json:candidate_payload_json"):
        OpeningRangeRetestProposal(
            setup_id="bad-json",
            strategy_id="opening_range_retest_v1",
            contract_version="opening_range_retest_protocol_v1",
            schema_version=1,
            source_component="strategies.movement.opening_range_breakout.generate_opening_range_retest_candidates",
            symbol="NIFTY",
            session_date="2026-07-14",
            direction="BUY_CALL",
            boundary_type="ORB_HIGH",
            normalized_boundary_value=25321.25,
            breakout_timestamp_iso="2026-07-14T04:20:00Z",
            history_hash="a" * 64,
            candidate_fingerprint="fingerprint-1",
            candidate_payload_json='{"b":2, "a":1}',
            created_at_iso="2026-07-14T04:25:00Z",
        )
