from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.analytics import candidate_ml_v2 as mod


def test_input_manifest_rejects_mutation_and_path_escape(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    outcomes = tmp_path / "outcomes.json"
    events.write_text('{"event_id":"e1"}\n{"event_id":"e2"}\n', encoding="utf-8")
    outcomes.write_text(json.dumps([{"event_ref_id": "e1"}, {"event_ref_id": "e2"}]), encoding="utf-8")

    manifest = mod.build_input_manifest(
        {"events": events, "outcomes": outcomes},
        allowed_root=tmp_path,
        code_sha="abc123",
    )
    mod.verify_input_manifest(manifest)
    assert manifest["sources"]["events"]["records"] == 2
    assert manifest["sources"]["outcomes"]["records"] == 2
    assert manifest["allowed_for_live_execution"] is False

    events.write_text('{"event_id":"changed"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="input_manifest_sha_mismatch:events"):
        mod.verify_input_manifest(manifest)

    outside = tmp_path.parent / "outside-candidate-ml.json"
    outside.write_text('[]', encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="source_path_escape"):
            mod.inspect_source_file(outside, role="events", allowed_root=tmp_path)
    finally:
        outside.unlink(missing_ok=True)


def test_input_manifest_rejects_symlink(tmp_path: Path):
    target = tmp_path / "events.json"
    link = tmp_path / "events-link.json"
    target.write_text('[]', encoding="utf-8")
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unsupported")
    with pytest.raises(ValueError, match="source_symlink_rejected"):
        mod.inspect_source_file(link, role="events", allowed_root=tmp_path)
