from __future__ import annotations
import json
from pathlib import Path
import tempfile
from core import market_session_memory_sidecar as sidecar

def test_preflight_and_independent_verifier():
    with tempfile.TemporaryDirectory() as root:
        root_path = Path(root)
        sidecar.AUTHORITY = str(root_path)
        result = sidecar.capture_preflight(session_id="s1", source_sha="a", core_sha="b", sidecar_sha="c", storage_epoch="e", storage_writable=True, session_memory_available=True, output_root=root_path)
        assert result["outcome"] == "PASS"
        assert sidecar.verify_evidence(root_path, session_id="s1")["status"] == "PASS"

def test_blocked_preflight_and_replay_negative_control():
    with tempfile.TemporaryDirectory() as root:
        root_path = Path(root)
        sidecar.AUTHORITY = str(root_path)
        result = sidecar.capture_preflight(session_id="s2", source_sha="a", core_sha="b", sidecar_sha="c", storage_epoch="e", storage_writable=False, session_memory_available=False, output_root=root_path)
        assert result["outcome"] == "BLOCKED"
        assert sidecar.verify_evidence(root_path, session_id="s2")["status"] == "BLOCKED"
    mismatch = sidecar.compare_replay(original={"bars": 1}, replay={"bars": 2})
    assert mismatch["status"] == "REPLAY_MISMATCH"
    assert mismatch["first_divergent_primitive"] == "bars"


def test_path_containment_rejects_sibling_parent_and_symlink_escape(tmp_path):
    authority = tmp_path / "TradeBotData"
    authority.mkdir()
    sidecar.AUTHORITY = str(authority)
    assert sidecar.evidence_dir("ok", root=authority / "session").parents[2] == authority / "session"
    for invalid in (tmp_path / "TradeBotData_evil", authority / ".." / "other"):
        try:
            sidecar.evidence_dir("bad", root=invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("path escaped governed authority")
    escape = authority / "escape"
    escape.symlink_to(tmp_path)
    try:
        sidecar.evidence_dir("bad", root=escape)
    except ValueError:
        pass
    else:
        raise AssertionError("symlink escaped governed authority")


def test_checkpoint_persistence_requires_monotonic_sequence(tmp_path):
    authority = tmp_path / "TradeBotData"
    authority.mkdir()
    sidecar.AUTHORITY = str(authority)

    class Store:
        def build_context(self, symbol, *, as_of):
            return {"bars": {"1m": 1, "5m": 1, "15m": 1, "30m": 1, "60m": 1},
                    "authoritative_up_to_ist": str(as_of), "missing_1m_bars": []}

    sidecar.capture_preflight(session_id="s3", source_sha="a", core_sha="b", sidecar_sha="c",
                              storage_epoch="e", storage_writable=True,
                              session_memory_available=True, output_root=authority)
    sidecar.persist_checkpoint(store=Store(), symbol="NIFTY", as_of="2026-09-07T09:15:00+05:30",
                               session_id="s3", source_sha="a", core_sha="b", sidecar_sha="c",
                               storage_epoch="e", seq=0, output_root=authority)
    assert sidecar.verify_evidence(authority, session_id="s3")["status"] == "PASS"
    try:
        sidecar.persist_checkpoint(store=Store(), symbol="NIFTY", as_of="2026-09-07T09:16:00+05:30",
                                   session_id="s3", source_sha="a", core_sha="b", sidecar_sha="c",
                                   storage_epoch="e", seq=0, output_root=authority, previous_seq=0)
    except ValueError as exc:
        assert str(exc) == "checkpoint_sequence_not_monotonic"
    else:
        raise AssertionError("duplicate checkpoint sequence accepted")


def test_replay_compares_authoritative_primitives():
    original = {"bars": ["09:15"], "derived_5m": ["09:15"], "core_seal_sha256": "a"}
    replay = {"bars": ["09:15"], "derived_5m": ["09:20"], "core_seal_sha256": "a"}
    result = sidecar.compare_replay(original=original, replay=replay)
    assert result["status"] == "REPLAY_MISMATCH"
    assert result["first_divergent_primitive"] == "derived_5m"
