#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.upstox_depth_shadow_capture_v2.dataset_registry import (
    update_dataset_registry,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update the immutable development/holdout registry for Upstox depth-shadow sessions."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(".runtime/research/upstox_depth_shadow_v2"),
    )
    parser.add_argument("--development-target", type=int, default=60)
    parser.add_argument("--holdout-target", type=int, default=20)
    args = parser.parse_args()

    payload = update_dataset_registry(
        args.output_root,
        development_target=args.development_target,
        holdout_target=args.holdout_target,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
