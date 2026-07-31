#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


UPSTREAM_VERSION = "5.2.0"
PATCHED_VERSION = "5.2.0+tradebot.1"
UPSTREAM_URL = (
    "https://files.pythonhosted.org/packages/e8/a5/306de933a705fd65b336fda98b5c10a591e04e36aa46559f175bd3431498/"
    "kiteconnect-5.2.0-py3-none-any.whl"
)
UPSTREAM_SHA256 = "4601a48355aeeae4ac8857d44f292aef3847351840e0c18aa8f5d3c5afcf92a7"
AUTOBAN_RANGE = ">=25.10.2,<27"
OUTPUT_NAME = f"kiteconnect-{PATCHED_VERSION}-py3-none-any.whl"
_PATCH_FILE = "kiteconnect/TRADEBOT_SECURITY_PATCH.json"
_DIST_INFO_OLD = f"kiteconnect-{UPSTREAM_VERSION}.dist-info"
_DIST_INFO_NEW = f"kiteconnect-{PATCHED_VERSION}.dist-info"
_DEPENDENCY_RE = re.compile(
    r"^Requires-Dist:\s*autobahn\[twisted\]\s*(?:\(\s*==\s*19\.11\.2\s*\)|==\s*19\.11\.2)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "TradeBot-QA-Certification/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _urlsafe_digest(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("ascii")
    return encoded.rstrip("=")


def _rewrite_metadata(text: str) -> str:
    version_line = f"Version: {UPSTREAM_VERSION}"
    if version_line not in text:
        raise RuntimeError("upstream_metadata_version_missing")
    text = text.replace(version_line, f"Version: {PATCHED_VERSION}", 1)
    rewritten, count = _DEPENDENCY_RE.subn(
        f"Requires-Dist: autobahn[twisted] ({AUTOBAN_RANGE})",
        text,
    )
    if count != 1:
        raise RuntimeError(f"upstream_autobahn_pin_match_count:{count}")
    return rewritten


def _rewrite_version_module(text: str) -> str:
    rewritten, count = re.subn(
        r"(__version__\s*=\s*['\"])5\.2\.0(['\"])",
        rf"\g<1>{PATCHED_VERSION}\g<2>",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("upstream_version_module_pattern_missing")
    return rewritten


def _record_bytes(files: dict[str, bytes], record_path: str) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    for name in sorted(files):
        if name == record_path:
            continue
        payload = files[name]
        writer.writerow([name, f"sha256={_urlsafe_digest(payload)}", str(len(payload))])
    writer.writerow([record_path, "", ""])
    return buffer.getvalue().encode("utf-8")


def build_patched_wheel(
    upstream_wheel: Path,
    *,
    expected_sha256: str,
    output_dir: Path,
) -> tuple[Path, dict[str, object]]:
    actual_hash = _sha256(upstream_wheel)
    if actual_hash != expected_sha256:
        raise RuntimeError(
            f"upstream_wheel_sha256_mismatch:expected={expected_sha256}:actual={actual_hash}"
        )

    with zipfile.ZipFile(upstream_wheel, "r") as source:
        files = {
            name: source.read(name)
            for name in source.namelist()
            if not name.endswith("/")
        }

    old_metadata = f"{_DIST_INFO_OLD}/METADATA"
    old_record = f"{_DIST_INFO_OLD}/RECORD"
    old_version_module = "kiteconnect/__version__.py"
    for required in (old_metadata, old_record, old_version_module):
        if required not in files:
            raise RuntimeError(f"upstream_wheel_required_file_missing:{required}")

    renamed: dict[str, bytes] = {}
    for name, payload in files.items():
        if name == old_record:
            continue
        target = name.replace(f"{_DIST_INFO_OLD}/", f"{_DIST_INFO_NEW}/", 1)
        renamed[target] = payload

    metadata_path = f"{_DIST_INFO_NEW}/METADATA"
    record_path = f"{_DIST_INFO_NEW}/RECORD"
    renamed[metadata_path] = _rewrite_metadata(
        renamed[metadata_path].decode("utf-8")
    ).encode("utf-8")
    renamed[old_version_module] = _rewrite_version_module(
        renamed[old_version_module].decode("utf-8")
    ).encode("utf-8")

    patch_manifest = {
        "schema_version": 1,
        "distribution": "kiteconnect",
        "upstream_version": UPSTREAM_VERSION,
        "patched_version": PATCHED_VERSION,
        "upstream_url": UPSTREAM_URL,
        "upstream_sha256": expected_sha256,
        "patch": {
            "field": "Requires-Dist: autobahn[twisted]",
            "before": "==19.11.2",
            "after": AUTOBAN_RANGE,
            "reason": "remove known-vulnerable Autobahn pin while preserving official KiteConnect source",
        },
    }
    renamed[_PATCH_FILE] = (
        json.dumps(patch_manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    renamed[record_path] = _record_bytes(renamed, record_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_NAME
    fixed_time = (2026, 7, 30, 0, 0, 0)
    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as target:
        for name in sorted(renamed):
            info = zipfile.ZipInfo(name, date_time=fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            target.writestr(info, renamed[name])

    output_hash = _sha256(output_path)
    result = {
        **patch_manifest,
        "output_file": output_path.name,
        "output_sha256": output_hash,
        "output_size": output_path.stat().st_size,
    }
    (output_dir / "kiteconnect_patch_manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path, result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic KiteConnect wheel with secure Autobahn metadata."
    )
    parser.add_argument("--upstream-wheel", default="")
    parser.add_argument("--download-cache", default=".runtime/downloads")
    parser.add_argument("--output-dir", default=".runtime/wheels")
    args = parser.parse_args()

    if args.upstream_wheel:
        upstream = Path(args.upstream_wheel).resolve()
    else:
        cache_dir = Path(args.download_cache)
        upstream = cache_dir / f"kiteconnect-{UPSTREAM_VERSION}-py3-none-any.whl"
        if not upstream.exists():
            _download(UPSTREAM_URL, upstream)

    output, result = build_patched_wheel(
        upstream,
        expected_sha256=UPSTREAM_SHA256,
        output_dir=Path(args.output_dir),
    )
    print(f"SECURE_KITECONNECT_WHEEL={output}")
    print(f"SECURE_KITECONNECT_SHA256={result['output_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
