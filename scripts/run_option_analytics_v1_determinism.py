from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.option_analytics_v1.evidence import run_determinism


def main() -> int:
    payload = run_determinism(ROOT)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
