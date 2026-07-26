from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.option_analytics_v1.evidence import publication_gate
from research.option_analytics_v1.packaged_evidence import REFERENCE_JSON, REFERENCE_PACKAGE, verify_committed_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", default="research/option_analytics_v1/evidence")
    args = parser.parse_args()
    evidence_dir = ROOT / args.evidence_dir
    if not (evidence_dir / REFERENCE_JSON).exists() and (evidence_dir / REFERENCE_PACKAGE).exists():
        payload = verify_committed_bundle(ROOT, evidence_dir)
    else:
        payload = publication_gate(ROOT, evidence_dir)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["verdict"] == "PASS_RESEARCH_SIDECAR_GATE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
