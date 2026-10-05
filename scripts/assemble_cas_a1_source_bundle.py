from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.storage import atomic_write_json


def _obj(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected JSON object")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble exact CAS-A1 source bundle from validated completed bars and point marks")
    parser.add_argument("--completed-bars", type=Path, required=True)
    parser.add_argument("--identity-contract", type=Path, required=True)
    parser.add_argument("--analytics-contract", type=Path, required=True)
    parser.add_argument("--point-marks", type=Path, required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        bars = _obj(args.completed_bars)
        identity = _obj(args.identity_contract)
        analytics = _obj(args.analytics_contract)
        points = _obj(args.point_marks)

        if bars.get("evidence_kind") != "CAS_A1_MEG_COMPLETED_BAR_BUNDLE":
            raise ValueError("completed-bar evidence kind mismatch")
        if str(bars.get("session_date") or "") != args.session_date:
            raise ValueError("completed-bar session mismatch")
        if str(points.get("session_date") or "") != args.session_date:
            raise ValueError("point-mark session mismatch")
        marks = points.get("point_marks")
        if not isinstance(marks, list):
            raise ValueError("point_marks must be a list")
        index = identity.get("index")
        if not isinstance(index, dict):
            raise ValueError("identity contract index missing")
        index_key = str(index.get("instrument_key") or "").strip()
        futures_key = str(points.get("futures_instrument") or "").strip()
        if not index_key or not futures_key:
            raise ValueError("index/futures instrument identity missing")
        required = {
            (index_key, "FINAL_CAS"),
            (futures_key, "15:29"),
            (futures_key, "15:39"),
        }
        observed = {
            (str(row.get("instrument_key") or "").strip(), str(row.get("label") or "").strip())
            for row in marks if isinstance(row, dict)
        }
        if observed != required:
            raise ValueError(f"point-mark identity mismatch required={sorted(required)} observed={sorted(observed)}")
        providers = {str(row.get("source_provider") or "").strip().upper() for row in marks if isinstance(row, dict)}
        providers.add(str(bars.get("source_provider") or "").strip().upper())
        providers.discard("")
        if len(providers) != 1:
            raise ValueError(f"mixed providers rejected: {sorted(providers)}")

        contract = analytics.get("analytics_contract") if isinstance(analytics.get("analytics_contract"), dict) else analytics
        if not isinstance(contract, dict) or not isinstance(contract.get("cas_a1"), dict):
            raise ValueError("analytics_contract.cas_a1 missing")
        frozen = contract["cas_a1"].get("frozen_constituents")
        expected_keys = [str(row.get("instrument_key") or "").strip() for row in identity.get("constituents") or []]
        if frozen != expected_keys:
            raise ValueError("analytics frozen constituents do not exactly match capture identity")

        payload = {
            "session_id": str(points.get("session_id") or args.session_date),
            "session_date": args.session_date,
            "index_instrument": index_key,
            "futures_instrument": futures_key,
            "analytics_contract": contract,
            "completed_minute_bars": bars["completed_minute_bars"],
            "point_marks": marks,
            "source_bundle_provenance": {
                "meg_run_id": bars.get("run_id"),
                "identity_contract_sha256": identity.get("identity_contract_sha256"),
                "point_mark_evidence_kind": points.get("evidence_kind"),
            },
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        }
        atomic_write_json(args.output, payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "status": "CAS_A1_SOURCE_BUNDLE_BLOCKED",
            "session_date": args.session_date,
            "reason": str(exc),
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        }, sort_keys=True))
        return 2

    print(json.dumps({
        "status": "CAS_A1_SOURCE_BUNDLE_READY",
        "session_date": args.session_date,
        "output": str(args.output),
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
