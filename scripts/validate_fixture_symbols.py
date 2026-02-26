#!/usr/bin/env python3
"""Migration note:
Validate replay fixture option_chain rows for tradingsymbol completeness.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.fixture_validator import ensure_tradingsymbols, validate_fixture_payload


def _iter_fixture_paths(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(p for p in root.glob("*.json") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate replay fixture tradingsymbols.")
    parser.add_argument(
        "--root",
        default="fixtures/snapshots",
        help="Fixture directory or file.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write back auto-filled tradingsymbols to fixtures.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    paths = _iter_fixture_paths(root)
    if not paths:
        print(f"No fixtures found under {root}")
        return 1

    failures = 0
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if args.write:
            updates = ensure_tradingsymbols(payload, fixture_name=path.stem)
            if updates:
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                print(f"{path}: filled {updates} missing tradingsymbols")
            continue
        errors = validate_fixture_payload(payload)
        if errors:
            failures += 1
            print(f"{path}: {len(errors)} issues")
            for line in errors[:5]:
                print(f"  - {line}")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

