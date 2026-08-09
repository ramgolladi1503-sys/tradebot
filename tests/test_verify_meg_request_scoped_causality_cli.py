import json
import subprocess
import sys
from pathlib import Path

from core.meg_request_scoped_causality import append_primitives


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_meg_request_scoped_causality_v1.py"


def _run(root: Path):
    return subprocess.run([sys.executable, str(SCRIPT), "--evidence-root", str(root)], text=True, capture_output=True)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "sealed"; root.mkdir()
    (root / "SEALED").write_text("sealed\n"); (root / "manifest.json").write_text("{}\n")
    common = dict(session_id="s1", producer_commit_sha="c1")
    append_primitives(root, **common, request=dict(request_event_id="re1", request_id="r1", request_generation=1, request_success_timestamp=10, feed_session_id="f", reconnect_generation=2, expected_instrument_token=101, expected_symbol="NIFTY"))
    append_primitives(root, **common, tick=dict(selected_tick_event_id="te1", cycle_id="cy1", request_id="r1", request_generation=1, selected_tick_id="t1", selected_tick_receipt_timestamp=11, selected_tick_feed_session_id="f", selected_tick_reconnect_generation=2, selected_tick_instrument_token=101, selected_tick_symbol="NIFTY"), accepted=dict(cycle_id="cy1", accepted=True), persisted=dict(cycle_id="cy1", persistence_identity="p1"))
    return root


def test_cli_passes_valid_sealed_root(tmp_path):
    result = _run(_root(tmp_path))
    assert result.returncode == 0
    assert "PASS_MEG_REQUEST_SCOPED_CAUSALITY" in result.stdout


def test_cli_returns_incomplete_for_missing_or_unsealed_root(tmp_path):
    missing = _run(tmp_path / "missing")
    assert missing.returncode == 2
    root = _root(tmp_path); (root / "SEALED").unlink()
    assert _run(root).returncode == 1


def test_cli_returns_incomplete_for_tampered_evidence(tmp_path):
    root = _root(tmp_path)
    path = root / "meg_selected_tick_events.jsonl"
    path.write_text(path.read_text().replace('"selected_tick_id":"t1"', '"selected_tick_id":"tampered"'))
    result = _run(root)
    assert result.returncode == 2
    assert "INCOMPLETE_MEG_REQUEST_SCOPED_CAUSALITY_EVIDENCE" in result.stdout
