#!/usr/bin/env python3
"""
Fetch and cache Upstox instruments master file.

Usage:
  python scripts/fetch_upstox_instruments.py --url <download_url>

Notes:
  - Does not auto-download at runtime.
  - Stores to cfg.UPSTOX_INSTRUMENTS_PATH by default.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import time
import urllib.request
import gzip
from pathlib import Path
from datetime import datetime, timezone

try:
    from config import config as cfg
except Exception:
    cfg = None


def _sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _default_out_path() -> Path:
    if cfg is not None:
        raw = str(getattr(cfg, "UPSTOX_INSTRUMENTS_PATH", "") or "").strip()
        if raw:
            return Path(raw)
    return Path("data/upstox_instruments.json.gz")


def _write_payload(path: Path, payload: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wb") as f:
            f.write(payload)
        return path.stat().st_size
    path.write_bytes(payload)
    return path.stat().st_size


def _fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "tradebot_local/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Upstox instruments master file.")
    parser.add_argument("--url", help="Direct URL to Upstox instruments file.")
    parser.add_argument("--out", help="Output path (defaults to config UPSTOX_INSTRUMENTS_PATH).")
    args = parser.parse_args()

    url = args.url or os.getenv("UPSTOX_INSTRUMENTS_URL")
    if not url:
        print("Missing URL. Provide --url or set UPSTOX_INSTRUMENTS_URL.")
        return 2
    out_path = Path(args.out) if args.out else _default_out_path()

    started = time.time()
    payload = _fetch(url)
    sha = _sha256(payload)
    size = _write_payload(out_path, payload)
    elapsed = time.time() - started
    now = datetime.now(timezone.utc).isoformat()

    print(f"Saved Upstox instruments to: {out_path}")
    print(f"Bytes: {size}")
    print(f"SHA256: {sha}")
    print(f"Fetched at: {now}")
    print(f"Elapsed: {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
