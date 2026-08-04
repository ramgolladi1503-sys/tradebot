#!/usr/bin/env python3
import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone
import logging

sys.path.append(str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seal_capture")

def calculate_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Path to the capture run root directory")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        logger.error(f"Run directory {run_dir} does not exist.")
        sys.exit(1)

    logger.info(f"Sealing capture session: {run_dir}")

    # 1. Collect all files and calculate checksums
    checksums = {}
    total_bytes = 0
    file_count = 0

    checksums_dir = run_dir / "checksums"
    checksums_dir.mkdir(parents=True, exist_ok=True)
    manifest_txt_path = checksums_dir / "sha256_manifest.txt"

    with open(manifest_txt_path, "w", encoding="utf-8") as manifest_f:
        for p in sorted(run_dir.rglob("*")):
            if p.is_file() and "checksums" not in p.parts and p.name != "session_manifest.json":
                sha = calculate_sha256(p)
                rel_path = p.relative_to(run_dir)
                checksums[str(rel_path)] = sha
                total_bytes += p.stat().st_size
                file_count += 1
                manifest_f.write(f"{sha}  {rel_path}\n")

    # 2. Build and write final session_manifest.json
    manifest = {
        "run_id": run_dir.name,
        "date": run_dir.parent.name,
        "sealed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_files": file_count,
        "total_bytes": total_bytes,
        "checksums": checksums
    }

    manifest_json_path = run_dir / "session_manifest.json"
    with open(manifest_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # 3. Write session_manifest.sha256
    manifest_sha = calculate_sha256(manifest_json_path)
    manifest_sha_path = run_dir / "session_manifest.sha256"
    with open(manifest_sha_path, "w", encoding="utf-8") as f:
        f.write(manifest_sha + "\n")

    logger.info(f"Session manifest sealed successfully. Hash: {manifest_sha}")
    logger.info(f"Sealed {file_count} files ({total_bytes} bytes).")

if __name__ == "__main__":
    main()
