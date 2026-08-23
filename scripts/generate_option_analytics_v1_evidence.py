from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.option_analytics_v1.evidence import write_complete_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="research/option_analytics_v1/evidence")
    parser.add_argument("--generated-at-utc", default="2026-07-26T06:28:13+00:00")
    args = parser.parse_args()
    result = write_complete_bundle(ROOT, ROOT / args.output_dir, generated_at_utc=args.generated_at_utc)
    summary = result["summary"]
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["reference_failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
