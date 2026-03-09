from __future__ import annotations

import importlib
import json
from pathlib import Path


def test_compute_config_fingerprint_is_stable(monkeypatch, tmp_path):
    import core.config_approval as mod

    importlib.reload(mod)

    key_file = tmp_path / "live_profile.txt"
    key_file.write_text("stable-config-v1\n", encoding="utf-8")

    monkeypatch.setattr(mod.cfg, "CONFIG_APPROVAL_KEY_FILES", str(key_file), raising=False)
    first = mod.compute_config_fingerprint(desk_id="DEFAULT")
    second = mod.compute_config_fingerprint(desk_id="DEFAULT")

    assert first["config_hash"] == second["config_hash"]


def test_approve_current_config_writes_logs_artifact(monkeypatch, tmp_path):
    import core.config_approval as mod

    importlib.reload(mod)

    approval_path = tmp_path / "logs" / "approved_config.json"
    key_file = tmp_path / "config_snapshot.txt"
    key_file.write_text("config-a\n", encoding="utf-8")

    monkeypatch.setattr(mod.cfg, "CONFIG_APPROVAL_KEY_FILES", str(key_file), raising=False)
    monkeypatch.setattr(mod.cfg, "CONFIG_APPROVAL_PATH", str(approval_path), raising=False)

    result = mod.approve_current_config(desk_id="DEFAULT", actor="tester")

    assert result["ok"] is True
    assert result["config_hash"]
    assert approval_path.exists()

    payload = json.loads(approval_path.read_text(encoding="utf-8"))
    record = ((payload.get("records") or {}).get("DEFAULT") or {})
    assert record.get("config_hash") == result["config_hash"]
    assert record.get("approved_by") == "tester"


def test_check_config_approval_detects_hash_mismatch(monkeypatch, tmp_path):
    import core.config_approval as mod

    importlib.reload(mod)

    approval_path = tmp_path / "logs" / "approved_config.json"
    key_file = tmp_path / "config_snapshot.txt"
    key_file.write_text("version-a\n", encoding="utf-8")

    monkeypatch.setattr(mod.cfg, "CONFIG_APPROVAL_KEY_FILES", str(key_file), raising=False)
    monkeypatch.setattr(mod.cfg, "CONFIG_APPROVAL_PATH", str(approval_path), raising=False)

    approved = mod.approve_current_config(desk_id="DEFAULT", actor="tester")
    assert approved["ok"] is True

    key_file.write_text("version-b\n", encoding="utf-8")

    status = mod.check_config_approval(desk_id="DEFAULT")
    assert status["ok"] is False
    assert status["reason"] == "approval_hash_mismatch"
    assert status["approved_hash"] != status["current_hash"]
