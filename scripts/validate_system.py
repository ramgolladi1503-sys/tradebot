from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from core.replay_contract import assert_deterministic_runtime_replay


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonical system validation using ReplayEngine")
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    result = assert_deterministic_runtime_replay(
        runtime_root=args.runtime_root,
        symbol=args.symbol,
        start=args.start,
        end=args.end,
    )

    output = {
        "status": "PASS" if result["ok"] else "FAIL",
        "deterministic": result["ok"],
        "engine": result["canonical_engine"],
        "hash_a": result["first_hash"],
        "hash_b": result["second_hash"],
        "summary": result.get("summary", {}),
        "missing_artifacts": result.get("missing_artifacts", []),
        "notes": result.get("notes", []),
    }

    if args.out:
        Path(args.out).write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
