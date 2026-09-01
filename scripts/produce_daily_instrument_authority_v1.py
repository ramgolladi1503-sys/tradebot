#!/usr/bin/env python3
"""Produce a dated, fail-closed DAILY_INSTRUMENT_AUTHORITY_V1 artifact."""
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from core.daily_instrument_authority import produce_authority

def main():
    p=argparse.ArgumentParser(); p.add_argument("--master",required=True,type=Path); p.add_argument("--output",required=True,type=Path); p.add_argument("--session-date",required=True); p.add_argument("--source-sha",required=True); p.add_argument("--required-tokens",required=True,type=Path); p.add_argument("--reviewed-pass",action="store_true"); a=p.parse_args()
    contract=json.loads(a.required_tokens.read_text()); tokens=[int(contract["index_instrument_token"])] + [int(x["instrument_token"]) for x in contract["constituents"]]
    result=produce_authority(master_path=a.master,output_path=a.output,session_date=a.session_date,source_sha=a.source_sha,required_tokens=tokens,reviewed_pass=a.reviewed_pass)
    print(json.dumps(result,sort_keys=True)); return 0 if result["authority_verdict"] == "PASS" else 2
if __name__ == "__main__": raise SystemExit(main())
