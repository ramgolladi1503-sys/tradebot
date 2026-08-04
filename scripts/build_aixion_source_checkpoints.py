#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aixion_trade_intelligence.source_checkpoint_builder import (
    SourceFileSpec,
    build_source_checkpoint_bundle,
)


def _read_specs(path: Path) -> list[SourceFileSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("source_checkpoint_config_must_be_object")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("source_checkpoint_config_sources_missing")
    specs: list[SourceFileSpec] = []
    for value in sources:
        if not isinstance(value, Mapping):
            raise ValueError("source_checkpoint_config_row_not_object")
        specs.append(SourceFileSpec.from_mapping(value))
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build provenance-aware source continuity checkpoints.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    bundle = build_source_checkpoint_bundle(_read_specs(args.config))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle.to_record(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"bundle_id": bundle.bundle_id, "output": args.output.as_posix()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
