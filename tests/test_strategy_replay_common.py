from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from research.strategy_replay.common import (
    StrategyReplayError,
    canonical_json_bytes,
    canonical_session_key,
    load_canonical_json,
    partition_assignment,
    recompute_candidate_hash,
    selection_summary,
    validate_evidence_envelope,
    validate_ledger,
    write_canonical_json,
)
from research.strategy_replay.git_state import capture_git_execution_state


def _record(symbol: str, session_date: str, logical_path: str, sha: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "session_date": session_date,
        "logical_path": logical_path,
        "sha256": sha,
        "selected_via": "inventory_verified_repo_relative",
    }


def _ledger_entry(symbol: str, session_date: str, setup_id: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "session_date": session_date,
        "direction": "BUY_CALL",
        "proposal_ready_at_iso": f"{session_date}T09:19:00+05:30",
        "setup_id": setup_id,
        "history_hash": f"history-{setup_id}",
    }


def test_canonical_json_and_session_key_are_stable() -> None:
    record = _record("NIFTY", "2026-07-14", "runtime/x.parquet", "a" * 64)
    assert canonical_json_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
    assert canonical_session_key(record) == canonical_session_key(dict(reversed(list(record.items()))))


def test_shard_assignment_and_universe_hash_are_order_independent() -> None:
    ordered = [
        _record("BANKNIFTY", "2026-07-15", "runtime/b.parquet", "b" * 64),
        _record("NIFTY", "2026-07-14", "runtime/a.parquet", "a" * 64),
        _record("SENSEX", "2026-07-16", "runtime/c.parquet", "c" * 64),
    ]
    reversed_records = list(reversed(ordered))
    assert selection_summary(ordered)["semantic_hash"] == selection_summary(reversed_records)["semantic_hash"]
    expected_union: set[tuple[str, str, str, str]] = set()
    for shard_index in range(3):
        shard = {
            (
                str(record["symbol"]),
                str(record["session_date"]),
                str(record["logical_path"]),
                str(record["sha256"]),
            )
            for record in ordered
            if partition_assignment(record, shard_count=3) == shard_index
        }
        assert expected_union.isdisjoint(shard)
        expected_union.update(shard)
    assert expected_union == {
        ("BANKNIFTY", "2026-07-15", "runtime/b.parquet", "b" * 64),
        ("NIFTY", "2026-07-14", "runtime/a.parquet", "a" * 64),
        ("SENSEX", "2026-07-16", "runtime/c.parquet", "c" * 64),
    }


def test_write_and_load_canonical_json_with_tamper_rejection(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    write_canonical_json(path, {"a": 1})
    assert load_canonical_json(path) == {"a": 1}
    path.write_text('{"a":2}\n', encoding="utf-8")
    with pytest.raises(StrategyReplayError, match="artifact_sidecar_hash_mismatch"):
        load_canonical_json(path)


def test_validate_ledger_recomputes_hash_and_rejects_missing_fields() -> None:
    ledger = [_ledger_entry("NIFTY", "2026-07-14", "setup-1")]
    expected = recompute_candidate_hash(ledger)
    assert validate_ledger(ledger, expected_candidate_hash=expected) == expected
    with pytest.raises(StrategyReplayError, match="ledger_entry_missing_fields"):
        validate_ledger([{"symbol": "NIFTY"}])


def test_validate_ledger_hash_is_order_independent_and_rejects_duplicate_identity() -> None:
    ledger = [
        _ledger_entry("BANKNIFTY", "2026-07-15", "setup-b"),
        _ledger_entry("NIFTY", "2026-07-14", "setup-a"),
    ]
    reversed_ledger = tuple(reversed(ledger))
    expected = recompute_candidate_hash(ledger)

    assert recompute_candidate_hash(reversed_ledger) == expected
    assert validate_ledger(reversed_ledger, expected_candidate_hash=expected) == expected
    with pytest.raises(StrategyReplayError, match="ledger_entry_duplicate_identity"):
        validate_ledger([ledger[0], dict(ledger[0])])


def test_validate_evidence_envelope_rejects_unsafe_values() -> None:
    payload = {
        "mode": "RESEARCH_REPLAY_ARTIFACT",
        "candidate_id": "x",
        "decision": "READY",
        "reason": "ok",
        "timestamp": "2026-07-14T09:19:00+05:30",
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "source": "test",
    }
    validate_evidence_envelope(payload)
    unsafe = dict(payload)
    unsafe["broker_api_called"] = True
    with pytest.raises(StrategyReplayError, match="broker_call_forbidden"):
        validate_evidence_envelope(unsafe)
    unsafe = dict(payload)
    unsafe["read_only"] = False
    with pytest.raises(StrategyReplayError, match="read_only_required"):
        validate_evidence_envelope(unsafe)
    unsafe = dict(payload)
    unsafe["append"] = True
    with pytest.raises(StrategyReplayError, match="append_forbidden"):
        validate_evidence_envelope(unsafe)
    unsafe = dict(payload)
    unsafe["allowed_for_live_execution"] = True
    with pytest.raises(StrategyReplayError, match="live_execution_forbidden"):
        validate_evidence_envelope(unsafe)


def test_capture_git_execution_state_is_checkout_path_independent_and_fail_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True, capture_output=True, text=True)
    (repo / "tracked.txt").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True, text=True)
    clean_a = capture_git_execution_state(repo, required_clean=True)
    clean_b = capture_git_execution_state(repo.resolve(), required_clean=True)
    assert clean_a.commit_sha == clean_b.commit_sha
    assert clean_a.worktree_clean is True
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(StrategyReplayError, match="dirty_worktree_rejected"):
        capture_git_execution_state(repo, required_clean=True)
