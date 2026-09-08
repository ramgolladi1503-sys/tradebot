from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.macd_futures_participation_regime_v1.canonical_authority import (  # noqa: E402
    CanonicalAuthorityBlocked,
    as_dict,
    resolve_canonical_authority,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--output-json")
    args = parser.parse_args()

    try:
        result = as_dict(
            resolve_canonical_authority(
                Path(args.evidence_root),
                Path(args.repo_root) if args.repo_root else None,
            )
        )
    except (CanonicalAuthorityBlocked, OSError) as exc:
        result = {
            "status": "BLOCKED",
            "blocker": f"{type(exc).__name__}:{exc}",
            "structural_edge_certified": False,
            "broker_write_authority": False,
            "order_authority": False,
        }

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        Path(args.output_json).write_text(payload)
    print(payload, end="")
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
