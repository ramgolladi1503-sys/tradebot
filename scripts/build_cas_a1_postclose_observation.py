from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.cas_a1_source_adapter import (
    CasA1SourceAdapterError,
    build_cas_a1_observation_payload,
)
from aixion_trade_intelligence.storage import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the frozen CAS-A1 finalizer input from exact completed-minute/post-close evidence"
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        raw = json.loads(args.bundle.read_text())
        if not isinstance(raw, dict):
            raise CasA1SourceAdapterError("source bundle must be a JSON object")
        payload = build_cas_a1_observation_payload(raw)
    except (OSError, json.JSONDecodeError, CasA1SourceAdapterError) as exc:
        print(json.dumps({
            "status": "CAS_A1_POSTCLOSE_OBSERVATION_BLOCKED",
            "reason": str(exc),
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        }, sort_keys=True))
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output, payload)
    print(json.dumps({
        "status": "CAS_A1_POSTCLOSE_OBSERVATION_BUILT",
        "output": str(args.output),
        "session_id": payload["session_id"],
        "source_provider": payload["source_provider"],
        "constituent_count": len(payload["constituent_marks"]),
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
