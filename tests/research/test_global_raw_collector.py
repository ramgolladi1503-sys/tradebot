import hashlib
import json
import pytest

from research.global_v1.raw_collector import collect_raw_artifact


def test_raw_collector_binds_sha_and_provenance(tmp_path):
    path = tmp_path / "dxy.json"
    path.write_text(json.dumps({"observed_at": "2026-08-12T08:00:00Z", "value": 100.0}), encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    artifact = collect_raw_artifact(path, source_name="DXY", provider="offline_fixture", expected_sha256=sha)
    assert artifact.sha256 == sha
    assert artifact.source_name == "DXY"


def test_raw_collector_rejects_tamper_and_missing_identity(tmp_path):
    path = tmp_path / "vix.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA_MISMATCH"):
        collect_raw_artifact(path, source_name="VIX", provider="offline", expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="PROVENANCE"):
        collect_raw_artifact(path, source_name="", provider="offline", expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
