#!/usr/bin/env python3
"""Audit sealed unified campaign evidence without importing runtime logic."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_root")
    args = parser.parse_args()
    root = Path(args.evidence_root)
    manifest_path = root / "artifact_manifest.json"
    sealed_path = root / "SEALED"
    result = {"evidence_root": str(root), "sealed": sealed_path.exists(), "errors": []}
    if not manifest_path.exists():
        result["errors"].append("artifact_manifest_missing")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest.get("artifacts", []):
            path = root / item["path"]
            if not path.exists():
                result["errors"].append(f"missing:{item['path']}")
            elif _sha(path) != item["sha256"]:
                result["errors"].append(f"sha_mismatch:{item['path']}")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["sealed"] and not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

