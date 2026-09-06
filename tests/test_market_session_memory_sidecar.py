from __future__ import annotations
import json
from pathlib import Path
import tempfile
import sys
sys.path.insert(0, "/Volumes/TradeBotData")
import msm_sidecar_stage as sidecar

def test_preflight_and_independent_verifier():
    with tempfile.TemporaryDirectory(dir="/Volumes/TradeBotData") as root:
        root_path = Path(root)
        result = sidecar.capture_preflight(session_id="s1", source_sha="a", core_sha="b", sidecar_sha="c", storage_epoch="e", storage_writable=True, session_memory_available=True, output_root=root_path)
        assert result["outcome"] == "PASS"
        assert sidecar.verify_evidence(root_path, session_id="s1")["status"] == "PASS"

def test_blocked_preflight_and_replay_negative_control():
    with tempfile.TemporaryDirectory(dir="/Volumes/TradeBotData") as root:
        root_path = Path(root)
        result = sidecar.capture_preflight(session_id="s2", source_sha="a", core_sha="b", sidecar_sha="c", storage_epoch="e", storage_writable=False, session_memory_available=False, output_root=root_path)
        assert result["outcome"] == "BLOCKED"
        assert sidecar.verify_evidence(root_path, session_id="s2")["status"] == "BLOCKED"
    mismatch = sidecar.compare_replay(original={"bars": 1}, replay={"bars": 2})
    assert mismatch["status"] == "REPLAY_MISMATCH"
    assert mismatch["first_divergent_primitive"] == "bars"
