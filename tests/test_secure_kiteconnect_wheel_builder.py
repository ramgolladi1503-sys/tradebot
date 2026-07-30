from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import zipfile

import pytest

from scripts.build_secure_kiteconnect_wheel import (
    AUTOBAN_RANGE,
    PATCHED_VERSION,
    build_patched_wheel,
)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_upstream_wheel(path):
    dist_info = "kiteconnect-5.2.0.dist-info"
    files = {
        "kiteconnect/__init__.py": b"from .__version__ import __version__\n",
        "kiteconnect/__version__.py": b'__version__ = "5.2.0"\n',
        f"{dist_info}/METADATA": (
            "Metadata-Version: 2.1\n"
            "Name: kiteconnect\n"
            "Version: 5.2.0\n"
            "Requires-Dist: requests (>=2.18.4)\n"
            "Requires-Dist: autobahn[twisted] (==19.11.2)\n"
        ).encode("utf-8"),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nTag: py3-none-any\n",
        f"{dist_info}/RECORD": b"",
    }
    with zipfile.ZipFile(path, "w") as wheel:
        for name, payload in files.items():
            wheel.writestr(name, payload)
    return _hash(path)


def _decode_record_hash(value):
    encoded = value.removeprefix("sha256=")
    encoded += "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded)


def test_secure_wheel_rewrites_only_version_dependency_and_provenance(tmp_path):
    upstream = tmp_path / "kiteconnect-5.2.0-py3-none-any.whl"
    upstream_hash = _fake_upstream_wheel(upstream)

    output, manifest = build_patched_wheel(
        upstream,
        expected_sha256=upstream_hash,
        output_dir=tmp_path / "out",
    )

    assert output.name == f"kiteconnect-{PATCHED_VERSION}-py3-none-any.whl"
    assert manifest["upstream_sha256"] == upstream_hash
    assert manifest["patch"]["before"] == "==19.11.2"
    assert manifest["patch"]["after"] == AUTOBAN_RANGE

    with zipfile.ZipFile(output) as wheel:
        names = set(wheel.namelist())
        metadata_path = f"kiteconnect-{PATCHED_VERSION}.dist-info/METADATA"
        record_path = f"kiteconnect-{PATCHED_VERSION}.dist-info/RECORD"
        assert "kiteconnect-5.2.0.dist-info/METADATA" not in names
        assert metadata_path in names
        assert record_path in names
        metadata = wheel.read(metadata_path).decode("utf-8")
        assert f"Version: {PATCHED_VERSION}" in metadata
        assert f"Requires-Dist: autobahn[twisted] ({AUTOBAN_RANGE})" in metadata
        assert "==19.11.2" not in metadata
        assert PATCHED_VERSION in wheel.read("kiteconnect/__version__.py").decode("utf-8")
        patch = json.loads(
            wheel.read("kiteconnect/TRADEBOT_SECURITY_PATCH.json").decode("utf-8")
        )
        assert patch["upstream_sha256"] == upstream_hash


def test_secure_wheel_record_hashes_every_payload(tmp_path):
    upstream = tmp_path / "kiteconnect-5.2.0-py3-none-any.whl"
    upstream_hash = _fake_upstream_wheel(upstream)
    output, _manifest = build_patched_wheel(
        upstream,
        expected_sha256=upstream_hash,
        output_dir=tmp_path / "out",
    )

    with zipfile.ZipFile(output) as wheel:
        record_path = f"kiteconnect-{PATCHED_VERSION}.dist-info/RECORD"
        rows = list(
            csv.reader(
                io.StringIO(wheel.read(record_path).decode("utf-8"))
            )
        )
        indexed = {row[0]: row[1:] for row in rows}
        assert indexed[record_path] == ["", ""]
        for name in wheel.namelist():
            if name == record_path:
                continue
            digest_text, size_text = indexed[name]
            payload = wheel.read(name)
            assert int(size_text) == len(payload)
            assert _decode_record_hash(digest_text) == hashlib.sha256(payload).digest()


def test_secure_wheel_rejects_upstream_hash_mismatch(tmp_path):
    upstream = tmp_path / "kiteconnect-5.2.0-py3-none-any.whl"
    _fake_upstream_wheel(upstream)

    with pytest.raises(RuntimeError, match="upstream_wheel_sha256_mismatch"):
        build_patched_wheel(
            upstream,
            expected_sha256="0" * 64,
            output_dir=tmp_path / "out",
        )


def test_secure_wheel_rejects_changed_upstream_dependency_contract(tmp_path):
    upstream = tmp_path / "kiteconnect-5.2.0-py3-none-any.whl"
    upstream_hash = _fake_upstream_wheel(upstream)
    with zipfile.ZipFile(upstream, "a") as wheel:
        wheel.writestr(
            "kiteconnect-5.2.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: kiteconnect\nVersion: 5.2.0\n"
            "Requires-Dist: autobahn[twisted] (==20.0.0)\n",
        )
    changed_hash = _hash(upstream)

    with pytest.raises(RuntimeError, match="upstream_autobahn_pin_match_count:0"):
        build_patched_wheel(
            upstream,
            expected_sha256=changed_hash,
            output_dir=tmp_path / "out",
        )
