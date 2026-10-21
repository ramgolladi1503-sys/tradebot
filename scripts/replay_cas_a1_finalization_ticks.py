from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aixion_trade_intelligence.cas_a1_finalization_replay import (
    CasA1FinalizationReplayError,
    analyze_finalization_replay,
)
from aixion_trade_intelligence.storage import atomic_write_json


def _load(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    raise SystemExit(f"unsupported replay file: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit CAS-A1 sub-minute finalization ordering from raw replay ticks")
    parser.add_argument("--input", type=Path, action="append", required=True, help="Repeat for every raw replay parquet/csv/jsonl chunk")
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--index-key", default="NSE_INDEX|Nifty 50")
    parser.add_argument("--futures-key")
    parser.add_argument("--ce-key")
    parser.add_argument("--pe-key")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        frames = [_load(path) for path in args.input]
        frame = pd.concat(frames, ignore_index=True, sort=False)
        result = analyze_finalization_replay(
            frame.to_dict("records"),
            session_date=args.session_date,
            index_instrument_key=args.index_key,
            futures_instrument_key=args.futures_key,
            ce_instrument_key=args.ce_key,
            pe_instrument_key=args.pe_key,
        )
    except (OSError, ValueError, CasA1FinalizationReplayError) as exc:
        print(json.dumps({
            "status": "CAS_A1_FINALIZATION_REPLAY_BLOCKED",
            "session_date": args.session_date,
            "reason": str(exc),
            "official_final_cas_semantics_verified": False,
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False,
        }, sort_keys=True))
        return 2

    payload = result.to_dict()
    payload["status"] = "CAS_A1_FINALIZATION_REPLAY_PROXY_OBSERVED"
    payload["input_files"] = [str(path) for path in args.input]
    atomic_write_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
