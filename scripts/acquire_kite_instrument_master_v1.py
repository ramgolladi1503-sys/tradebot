#!/usr/bin/env python3
"""Acquire or preserve a Kite NSE instrument master for live-universe mapping.

The live path uses only ``core.kite_client.kite_client.instruments``. A local
file mode exists for deterministic reruns without broker access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.time_utils import IST_TZ

BLOCKED_BY_KITE_AUTH = "BLOCKED_BY_KITE_AUTH"
BLOCKED_BY_KITE_INSTRUMENT_MASTER = "BLOCKED_BY_KITE_INSTRUMENT_MASTER"
PASS_KITE_INSTRUMENT_MASTER_ACQUIRED = "PASS_KITE_INSTRUMENT_MASTER_ACQUIRED"
SOURCE_METHOD = 'core.kite_client.kite_client.instruments(exchange="NSE", force=True)'
REQUIRED_FIELDS = (
    "instrument_token",
    "exchange_token",
    "tradingsymbol",
    "name",
    "exchange",
    "segment",
    "instrument_type",
)


def _stable_json_bytes(rows: list[Mapping[str, Any]]) -> bytes:
    return json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _load_local(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, Mapping):
        value = value.get("data") or value.get("instruments") or value.get("rows") or []
    if not isinstance(value, list):
        raise ValueError("local master is not a list")
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _validate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("empty Kite instruments response")
    fields = sorted({str(key) for row in rows for key in row.keys()})
    missing = [field for field in REQUIRED_FIELDS if field not in fields]
    if missing:
        raise ValueError(f"missing required Kite fields: {','.join(missing)}")
    valid_token_rows = 0
    for row in rows:
        try:
            token = int(row.get("instrument_token"))
        except Exception:
            continue
        if token > 0 and str(row.get("exchange") or "").upper() == "NSE":
            valid_token_rows += 1
    if valid_token_rows == 0:
        raise ValueError("no valid NSE Kite instrument_token rows")
    return {"row_count": len(rows), "schema_fields_observed": fields, "valid_nse_token_rows": valid_token_rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kite-instruments-file", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("runtime/reference/market_event_graph/kite_instruments"))
    args = parser.parse_args()

    retrieved_utc = datetime.now(timezone.utc)
    retrieved_ist = retrieved_utc.astimezone(IST_TZ)
    source_file = None
    try:
        if args.kite_instruments_file is not None:
            rows = _load_local(args.kite_instruments_file)
            source_file = str(args.kite_instruments_file)
            auth_authority = {"mode": "local_file", "secret_values_recorded": False}
        else:
            from core.kite_client import kite_client

            rows = kite_client.instruments(exchange="NSE", force=True)
            auth_authority = {
                "mode": "existing_authenticated_kite_client",
                "active_api_key_present": bool(getattr(kite_client, "_active_api_key", "")),
                "active_access_token_present": bool(getattr(kite_client, "_active_access_token", "")),
                "secret_values_recorded": False,
            }
    except Exception as exc:
        print(json.dumps({"verdict": BLOCKED_BY_KITE_AUTH, "error_type": type(exc).__name__}, sort_keys=True))
        return 2

    try:
        rows = [dict(row) for row in rows if isinstance(row, Mapping)]
        validation = _validate_rows(rows)
    except Exception as exc:
        print(json.dumps({"verdict": BLOCKED_BY_KITE_INSTRUMENT_MASTER, "error": str(exc)}, sort_keys=True))
        return 3

    raw = _stable_json_bytes(rows)
    raw_sha = hashlib.sha256(raw).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = args.output_dir / f"kite_nse_instruments_{raw_sha[:16]}.json"
    sidecar = {
        "verdict": PASS_KITE_INSTRUMENT_MASTER_ACQUIRED,
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "retrieval_utc": retrieved_utc.isoformat().replace("+00:00", "Z"),
        "retrieval_ist": retrieved_ist.isoformat(),
        "row_count": validation["row_count"],
        "raw_sha256": raw_sha,
        "schema_fields_observed": validation["schema_fields_observed"],
        "source_method": SOURCE_METHOD if source_file is None else "local_file_input",
        "source_file": source_file,
        "auth_authority_used": auth_authority,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "read_only_broker_metadata_endpoint_called": source_file is None,
        "allowed_for_live_execution": False,
    }
    sidecar_path = raw_path.with_suffix(".sidecar.json")
    if raw_path.exists():
        sidecar["already_preserved"] = True
    else:
        raw_path.write_bytes(raw)
    if not sidecar_path.exists():
        sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"verdict": PASS_KITE_INSTRUMENT_MASTER_ACQUIRED, "raw_path": str(raw_path), "sidecar_path": str(sidecar_path), "raw_sha256": raw_sha, "row_count": validation["row_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
