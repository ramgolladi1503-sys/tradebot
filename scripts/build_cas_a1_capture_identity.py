from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.cas_a1_capture_identity import (
    CasA1CaptureIdentityError,
    build_capture_identity_contract,
)
from aixion_trade_intelligence.storage import atomic_write_json


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build frozen CAS-A1 capture identity from current MEG universe + broker master")
    parser.add_argument("--live-universe", type=Path, required=True)
    parser.add_argument("--instrument-master", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        live_universe = _read(args.live_universe)
        instrument_master = _read(args.instrument_master)
        if not isinstance(live_universe, dict):
            raise CasA1CaptureIdentityError("live universe must be a JSON object")
        contract = build_capture_identity_contract(
            live_universe=live_universe,
            broker_instrument_master=instrument_master,
        )
    except (OSError, json.JSONDecodeError, CasA1CaptureIdentityError) as exc:
        print(json.dumps({
            "status": "CAS_A1_CAPTURE_IDENTITY_BLOCKED",
            "reason": str(exc),
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        }, sort_keys=True))
        return 2

    atomic_write_json(args.output, contract)
    print(json.dumps({
        "status": "CAS_A1_CAPTURE_IDENTITY_READY",
        "constituent_count": len(contract["constituents"]),
        "requires_supplemental_capture": contract["requires_supplemental_capture"],
        "supplemental_symbols": [row["symbol"] for row in contract["supplemental_constituents"]],
        "ignored_current_symbols": contract["ignored_current_symbols"],
        "output": str(args.output),
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
