from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.cas_a1_meg_source import (
    CasA1MegSourceError,
    build_completed_bar_bundle,
    load_jsonl,
)
from aixion_trade_intelligence.storage import atomic_write_json


def _read_object(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{path}: expected JSON object")
    return raw


def _normalize_runtime_availability(rows: list[dict]) -> list[dict]:
    """Convert only the runtime writer's explicit epoch metadata to ISO time.

    This does not alter bar timestamps or infer market times. It gives the generic
    PR790 adapter an ISO representation of the already-recorded persistence time.
    """
    out: list[dict] = []
    for source in rows:
        row = dict(source)
        if not row.get("export_timestamp_utc") and not row.get("event_timestamp_utc"):
            raw = row.get("source_generated_at_epoch")
            if raw not in (None, ""):
                try:
                    epoch = float(raw)
                except (TypeError, ValueError) as exc:
                    raise CasA1MegSourceError("source_generated_at_epoch must be numeric") from exc
                row["export_timestamp_utc"] = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
        out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build CAS-A1 exact completed-minute evidence from governed MEG captured_metadata.jsonl"
    )
    parser.add_argument("--captured-metadata", type=Path, required=True)
    parser.add_argument("--identity-contract", type=Path, required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        rows = _normalize_runtime_availability(load_jsonl(args.captured_metadata))
        identity = _read_object(args.identity_contract)
        bundle = build_completed_bar_bundle(
            captured_metadata_rows=rows,
            identity_contract=identity,
            session_date=args.session_date,
        )
    except (CasA1MegSourceError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "status": "CAS_A1_MEG_COMPLETED_BAR_BUNDLE_BLOCKED",
            "session_date": args.session_date,
            "reason": str(exc),
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        }, sort_keys=True))
        return 2

    atomic_write_json(args.output, bundle)
    print(json.dumps({
        "status": "CAS_A1_MEG_COMPLETED_BAR_BUNDLE_READY",
        "session_date": args.session_date,
        "constituent_count": bundle["constituent_count"],
        "completed_minute_bar_count": len(bundle["completed_minute_bars"]),
        "output": str(args.output),
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
