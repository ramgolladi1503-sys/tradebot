#!/usr/bin/env python3
"""Independent, read-only verifier for governed external runtime storage."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_storage_authority import StorageAuthorityError, assert_same_device, establish


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--volume", type=Path, default=Path("/Volumes/TradeBotData"))
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    try:
        authority = establish(volume=args.volume, runtime_root=args.runtime_root)
        assert_same_device(authority, *args.paths)
        result = {"verdict": "PASS", "volume": str(authority.volume), "runtime_root": str(authority.runtime_root), "device_id": authority.device_id, "paths_checked": len(args.paths)}
    except StorageAuthorityError as exc:
        result = {"verdict": "BLOCKED", "reason": str(exc)}
        print(json.dumps(result, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
