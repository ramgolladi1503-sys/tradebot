import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.cas_evaluation_ledger import CASEvaluationLedger


SESSION = {"trading_date": "2026-09-29", "venue": "NSE",
    "calendar_id": "fixture-calendar", "calendar_version": "v1"}
KEY = "a" * 64
EVENTS = ["b" * 64, "c" * 64]
SOURCE_SHA = "d" * 40
DECISION = {"direction": "UP", "read_only": True, "broker_write_authority": False,
    "order_authority": False, "paper_authorized": False,
    "live_execution_authorized": False, "broker_order_calls": 0}


def ledger(path, **kwargs):
    return CASEvaluationLedger(path, session_identity=SESSION, **kwargs)


def claim(store, run="run-a", now=100.0):
    return store.claim(evaluation_identity_sha256=KEY, run_id=run,
        source_event_sha256s=EVENTS, source_sha=SOURCE_SHA, now_epoch=now)


def test_claim_completion_and_restart_are_idempotent(tmp_path):
    store = ledger(tmp_path)
    first = claim(store)
    assert first["status"] == "CLAIMED"
    pending = claim(ledger(tmp_path), run="run-b", now=101.0)
    assert pending["status"] == "DUPLICATE_IN_PROGRESS"

    completed = store.complete(evaluation_identity_sha256=KEY, run_id="run-a",
        claim_generation=first["claim_generation"], source_sha=SOURCE_SHA,
        source_event_sha256s=EVENTS, decision=DECISION, completed_epoch=102.0)
    assert completed["status"] == "COMPLETED"
    duplicate = claim(ledger(tmp_path), run="run-b", now=103.0)
    assert duplicate["status"] == "DUPLICATE_COMPLETED"
    assert duplicate["receipt"]["direction"] == "UP"
    assert duplicate["receipt"]["read_only"] is True
    assert duplicate["receipt"]["allowed_for_live_execution"] is False


def test_stale_incomplete_claim_can_be_recovered_without_completed_signal(tmp_path):
    store = ledger(tmp_path, lease_seconds=5)
    first = claim(store, now=100.0)
    recovered = claim(ledger(tmp_path, lease_seconds=5), run="run-b", now=106.0)
    assert recovered["status"] == "CLAIMED"
    assert recovered["claim_generation"] == first["claim_generation"] + 1
    assert claim(store, run="run-c", now=107.0)["status"] == "DUPLICATE_IN_PROGRESS"


def test_receipt_published_before_index_crash_is_recovered_idempotently(tmp_path, monkeypatch):
    store = ledger(tmp_path)
    first = claim(store)
    original_save = store._save

    def crash_after_receipt(_entries):
        raise OSError("simulated process interruption after immutable receipt")

    monkeypatch.setattr(store, "_save", crash_after_receipt)
    with pytest.raises(OSError, match="simulated process interruption"):
        store.complete(evaluation_identity_sha256=KEY, run_id="run-a",
            claim_generation=first["claim_generation"], source_sha=SOURCE_SHA,
            source_event_sha256s=EVENTS, decision=DECISION, completed_epoch=102.0)
    monkeypatch.setattr(store, "_save", original_save)

    recovered = claim(ledger(tmp_path), run="run-b", now=103.0)
    assert recovered["status"] == "DUPLICATE_COMPLETED"
    index = json.loads((tmp_path / "cas-evaluation-index-v1.json").read_text())
    assert index["entries"][0]["status"] == "COMPLETED"


def test_source_event_hash_conflict_fails_closed(tmp_path):
    store = ledger(tmp_path)
    first = claim(store)
    store.complete(evaluation_identity_sha256=KEY, run_id="run-a",
        claim_generation=first["claim_generation"], source_sha=SOURCE_SHA,
        source_event_sha256s=EVENTS, decision=DECISION, completed_epoch=102.0)
    result = store.claim(evaluation_identity_sha256=KEY, run_id="run-b",
        source_event_sha256s=["e" * 64, "f" * 64], source_sha=SOURCE_SHA, now_epoch=103.0)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "CAS_EVALUATION_SOURCE_IDENTITY_CONFLICT"


def test_concurrent_run_claims_have_one_owner(tmp_path):
    def submit(run_id):
        return claim(ledger(tmp_path), run=run_id, now=100.0)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("run-a", "run-b")))
    assert sorted(row["status"] for row in results) == ["CLAIMED", "DUPLICATE_IN_PROGRESS"]


def test_session_or_manifest_tamper_fails_closed(tmp_path):
    store = ledger(tmp_path)
    assert claim(store)["status"] == "CLAIMED"
    index_path = tmp_path / "cas-evaluation-index-v1.json"
    payload = json.loads(index_path.read_text())
    payload["entries"][0]["run_id"] = "tampered"
    index_path.write_text(json.dumps(payload))
    result = claim(ledger(tmp_path), run="run-b", now=101.0)
    assert result["status"] == "BLOCKED"
    assert "HASH_MISMATCH" in result["reason"]
