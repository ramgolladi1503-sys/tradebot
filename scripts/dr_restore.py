import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, help="Path to backup zip")
    parser.add_argument("--target", required=True, help="Restore target directory")
    args = parser.parse_args()

    bundle = Path(args.bundle)
    target = Path(args.target)
    if not bundle.exists():
        print("ERROR:DR_BUNDLE_MISSING bundle not found", file=sys.stderr)
        raise SystemExit(2)

    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(bundle, "r") as zf:
        if "manifest.json" not in zf.namelist():
            print("ERROR:DR_MANIFEST_MISSING manifest.json missing", file=sys.stderr)
            raise SystemExit(2)
        manifest = json.loads(zf.read("manifest.json"))
        zf.extractall(target)

    # Verify checksums
    for rel, expected in manifest.get("checksums", {}).items():
        path = target / rel
        if not path.exists():
            print(f"ERROR:DR_RESTORE_MISSING {rel}", file=sys.stderr)
            raise SystemExit(2)
        actual = _sha256(path)
        if actual != expected:
            print(f"ERROR:DR_CHECKSUM_MISMATCH {rel}", file=sys.stderr)
            raise SystemExit(2)

    print(f"DR restore complete: {target}")


if __name__ == "__main__":
    main()
