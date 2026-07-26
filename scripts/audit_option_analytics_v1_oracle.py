from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.option_analytics_v1.evidence import generate_reference_evidence


def main() -> int:
    payload = generate_reference_evidence()
    print(json.dumps({
        "input_case_count": payload["input_case_count"],
        "parity_case_count": payload["parity_case_count"],
        "iv_identifiable_case_count": payload["iv_identifiable_case_count"],
        "failure_count": payload["failure_count"],
        "semantic_sha256": payload["semantic_sha256"],
    }, sort_keys=True))
    return 0 if payload["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
