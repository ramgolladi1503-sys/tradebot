"""Behavioral tests for persistence only; these are not live certification."""
import json
from pathlib import Path

import pytest

from core.certified_release_store import ReleaseStore, ReleaseStoreError


def select(store, sha, expected=None):
    return store.record_verified_selection(candidate_sha=sha * 40, evidence_sha256="e" * 64, expected_event=expected)


def test_initial_state_and_history_preservation(tmp_path):
    store = ReleaseStore(tmp_path)
    assert store.read() is None
    first = select(store, "a")
    history = tmp_path / "history" / (first["event_sha256"] + ".json")
    original = history.read_bytes()
    second = select(store, "b", first["event_sha256"])
    assert store.read() == second
    assert second["fallback_live_sha"] == "a" * 40
    assert history.read_bytes() == original
    assert len(list((tmp_path / "history").glob("*.json"))) == 2


def test_stale_compare_and_swap_preserves_current(tmp_path):
    store = ReleaseStore(tmp_path)
    first = select(store, "a")
    with pytest.raises(ReleaseStoreError, match="concurrent_selection_changed"):
        select(store, "b")
    assert store.read() == first


@pytest.mark.parametrize("sha", ["main", "a" * 39, "A" * 40, "../foo", None])
def test_invalid_sha_never_creates_pointer(tmp_path, sha):
    store = ReleaseStore(tmp_path)
    with pytest.raises(ReleaseStoreError):
        store.record_verified_selection(candidate_sha=sha, evidence_sha256="e" * 64, expected_event=None)
    assert not store.pointer.exists()


def test_corrupt_ancestor_blocks_read_and_selection(tmp_path):
    store = ReleaseStore(tmp_path)
    first = select(store, "a")
    second = select(store, "b", first["event_sha256"])
    (store.history / (first["event_sha256"] + ".json")).write_text('{}')
    with pytest.raises(ReleaseStoreError):
        store.read()
    before = store.pointer.read_bytes()
    with pytest.raises(ReleaseStoreError):
        select(store, "c", second["event_sha256"])
    assert store.pointer.read_bytes() == before


def test_interrupted_pointer_update_retains_previous(tmp_path, monkeypatch):
    import core.certified_release_store as module
    store = ReleaseStore(tmp_path)
    first = select(store, "a")
    def fail(*args):
        raise OSError("simulated pointer failure")
    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(OSError):
        select(store, "b", first["event_sha256"])
    assert store.read() == first


def test_duplicate_selection_rejected(tmp_path):
    store = ReleaseStore(tmp_path)
    first = select(store, "a")
    with pytest.raises(ReleaseStoreError, match="already_selected"):
        select(store, "a", first["event_sha256"])


def test_missing_history_fails_closed(tmp_path):
    store = ReleaseStore(tmp_path)
    first = select(store, "a")
    (store.history / (first["event_sha256"] + ".json")).unlink()
    with pytest.raises(ReleaseStoreError):
        store.read()


def test_contention_does_not_hang(tmp_path):
    store = ReleaseStore(tmp_path)
    with store._lock():
        with pytest.raises(ReleaseStoreError, match="store_busy_retry"):
            select(ReleaseStore(tmp_path), "a")


def test_symlink_history_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "state"
    root.mkdir()
    (root / "history").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ReleaseStoreError, match="symlink_history"):
        select(ReleaseStore(root), "a")
    assert not list(outside.iterdir())
