import json

import pytest

from scripts.morning_readonly_observer import load_manifest


def test_manifest_requires_external_read_only_contract(tmp_path):
    root = tmp_path / "session"
    (root / "preflight").mkdir(parents=True)
    (root / "preflight" / "session_root_manifest.json").write_text(json.dumps({
        "root": str(root), "repository_local_live_writers": 0,
        "broker_write_authority": False, "order_authority": False,
        "paper_authorized": False, "live_authorized": False,
    }))
    assert load_manifest(root)["root"] == str(root)


def test_manifest_rejects_authority_escalation(tmp_path):
    root = tmp_path / "session"
    (root / "preflight").mkdir(parents=True)
    (root / "preflight" / "session_root_manifest.json").write_text(json.dumps({
        "root": str(root), "repository_local_live_writers": 0,
        "broker_write_authority": True, "order_authority": False,
        "paper_authorized": False, "live_authorized": False,
    }))
    with pytest.raises(RuntimeError, match="READ_ONLY_AUTHORITY_MANIFEST_FAILED"):
        load_manifest(root)
