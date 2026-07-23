#!/usr/bin/env python3
"""Build explicit proxy ticker to Upstox instrument resolution records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def load_master(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    if path.suffix == ".gz":
        return pd.read_json(path, compression="gzip")
    if path.suffix == ".json":
        return pd.read_json(path)
    return pd.read_csv(path)


def build(accepted_manifest: Path, instrument_master: Path, output_dir: Path) -> dict[str, int]:
    rows = json.loads(accepted_manifest.read_text())
    master = load_master(instrument_master)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    unresolved = []
    ambiguous = []
    for row in rows:
        symbol = str(row["symbol"]).upper()
        candidates = pd.DataFrame()
        if not master.empty:
            for col in ["trading_symbol", "tradingsymbol", "symbol"]:
                if col in master:
                    candidates = master[master[col].astype(str).str.upper() == symbol]
                    if not candidates.empty:
                        break
            if symbol == "NIFTY":
                index_candidates = master[
                    master.get("instrument_key", pd.Series(dtype=str)).astype(str).eq("NSE_INDEX|Nifty 50")
                    | master.get("asset_key", pd.Series(dtype=str)).astype(str).eq("NSE_INDEX|Nifty 50")
                ]
                if not index_candidates.empty:
                    candidates = index_candidates.head(1)
            elif not candidates.empty and "segment" in candidates:
                nse_eq = candidates[candidates["segment"].astype(str).eq("NSE_EQ")]
                if not nse_eq.empty:
                    candidates = nse_eq
        if master.empty:
            records.append({"proxy_ticker": symbol, "resolved_trading_symbol": symbol, "instrument_key": row.get("instrument_key") or "", "ISIN": "", "effective_from": row.get("from_date"), "effective_to": row.get("to_date"), "mapping_source": "accepted_raw_manifest", "mapping_reason": "raw file already fetched for symbol; instrument master unavailable", "confidence": "medium"})
        elif len(candidates) == 1:
            c = candidates.iloc[0]
            records.append({"proxy_ticker": symbol, "resolved_trading_symbol": c.get("trading_symbol", c.get("tradingsymbol", symbol)), "instrument_key": c.get("instrument_key", row.get("instrument_key") or ""), "ISIN": c.get("isin", c.get("ISIN", "")), "effective_from": row.get("from_date"), "effective_to": row.get("to_date"), "mapping_source": str(instrument_master), "mapping_reason": "exact trading symbol match", "confidence": "high"})
        elif len(candidates) > 1:
            ambiguous.append({"proxy_ticker": symbol, "candidate_count": len(candidates)})
        else:
            unresolved.append({"proxy_ticker": symbol, "reason": "no verified instrument master match"})
    pd.DataFrame(records).drop_duplicates().to_csv(output_dir / "ticker_resolution.csv", index=False)
    pd.DataFrame(unresolved).to_csv(output_dir / "unresolved_tickers.csv", index=False)
    pd.DataFrame(ambiguous).to_csv(output_dir / "ambiguous_tickers.csv", index=False)
    return {"resolved": len(records), "unresolved": len(unresolved), "ambiguous": len(ambiguous)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-manifest", type=Path, required=True)
    parser.add_argument("--instrument-master", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.accepted_manifest, args.instrument_master, args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
