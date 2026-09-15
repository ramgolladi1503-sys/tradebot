import json

import pytest

from core.certified_release_store import ReleaseStoreError
from scripts.release_manager import _manifest


def test_primitive_manifest_rejects_legacy_caller_pass_json(tmp_path):
    path = tmp_path / "gates.json"; path.write_text(json.dumps({"gates": {"source_identity": {"pass": True}}}))
    with pytest.raises(ReleaseStoreError, match="primitive_manifest_invalid"):
        _manifest(path)


def test_primitive_manifest_keeps_only_gate_to_primitive_mapping(tmp_path):
    path = tmp_path / "manifest.json"; path.write_text(json.dumps({"source_identity": "source.json"}))
    assert _manifest(path) == {"source_identity": "source.json"}
