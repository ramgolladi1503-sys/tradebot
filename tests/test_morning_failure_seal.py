import json

import pytest

from core.morning_failure_seal import seal_partial


def test_partial_seal_preserves_hashes_and_is_not_normal_shutdown(tmp_path):
    (tmp_path / "runtime.log").write_text("evidence\n")
    payload = seal_partial(session_root=tmp_path, reason="unexpected_process_exit", pid=123)
    assert payload["seal_type"] == "FORENSIC_PARTIAL"
    assert payload["governed_shutdown_completed"] is False
    assert payload["originals_mutated"] is False
    assert payload["files"][0]["sha256"]
    assert json.loads((tmp_path / "FORENSIC_PARTIAL.json").read_text())["orders_placed"] == 0


def test_partial_seal_is_idempotency_guarded(tmp_path):
    seal_partial(session_root=tmp_path, reason="first")
    with pytest.raises(FileExistsError, match="forensic_partial_already_sealed"):
        seal_partial(session_root=tmp_path, reason="second")
