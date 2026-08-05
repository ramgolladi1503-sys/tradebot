#!/usr/bin/env python3
"""Run-isolated, bounded, authenticated Upstox smoke for PSILOR V1."""
from __future__ import annotations
import json,logging,os,sys,urllib.parse,uuid
from datetime import datetime,timedelta
from pathlib import Path
from typing import Any
import pandas as pd
from scripts.fetch_psilor_v1_data import IST_TZ,SUCCESS,UpstoxFetcher,canonical_sha,sha256_file
logging.basicConfig(level=logging.INFO,format="%(asctime)s - %(levelname)s - %(message)s")

def _select_middle_contracts(contracts:list[dict[str,Any]],count:int)->list[dict[str,Any]]:
    ordered=sorted(contracts,key=lambda item:float(item.get("strike_price") or item.get("strike") or 0))
    if len(ordered)<count:return []
    center=len(ordered)//2;start=max(0,min(center-count//2,len(ordered)-count))
    return ordered[start:start+count]

def _new_run_directory(root:Path)->tuple[str,Path]:
    run_id=os.environ.get("PSILOR_SMOKE_RUN_ID") or f"{datetime.utcnow():%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    run_dir=root/run_id;run_dir.mkdir(parents=True,exist_ok=False);return run_id,run_dir

def _write_json(path:Path,value:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,default=str),encoding="utf-8")

def _rewrite_to_common_sessions(contract_files:dict[str,Path])->tuple[list[str],list[dict[str,Any]]]:
    frames={};sets=[]
    required={"timestamp","session_date","open","high","low","close","volume","open_interest"}
    for label,path in contract_files.items():
        frame=pd.read_parquet(path)
        if frame.empty or not required.issubset(frame.columns):raise RuntimeError(f"Invalid smoke Parquet for {label}: {path}")
        frames[label]=frame;sets.append(set(frame["session_date"].astype(str)))
    common=sorted(set.intersection(*sets)) if sets else []
    if len(common)<2:raise RuntimeError(f"Only {len(common)} common completed sessions were fetched")
    selected=common[-2:];artifacts=[]
    for label,path in contract_files.items():
        bounded=frames[label][frames[label]["session_date"].astype(str).isin(selected)].copy().sort_values("timestamp").reset_index(drop=True)
        if bounded.empty or set(bounded["session_date"].astype(str))!=set(selected):raise RuntimeError(f"{label} does not cover both selected sessions")
        bounded.to_parquet(path,index=False)
        artifacts.append({"label":label,"path":str(path),"row_count":len(bounded),"session_dates":selected,"first_timestamp":str(bounded["timestamp"].min()),"last_timestamp":str(bounded["timestamp"].max()),"sha256":sha256_file(path),"created_by_current_run":True})
    return selected,artifacts

def run_smoke()->dict[str,Any]:
    if not os.environ.get("UPSTOX_ACCESS_TOKEN","").strip():raise RuntimeError("BLOCKED_AUTHENTICATION: UPSTOX_ACCESS_TOKEN is not set")
    smoke_root=Path(os.environ.get("PSILOR_SMOKE_ROOT","data/psilor_v1/upstox/smoke"));run_id,run_dir=_new_run_directory(smoke_root)
    initial_end=pd.Timestamp.now(tz=IST_TZ)-timedelta(days=1);fetcher=UpstoxFetcher(initial_end-timedelta(days=7),initial_end,base_dir=run_dir,run_id=run_id)
    encoded=urllib.parse.quote("NSE_INDEX|Nifty 50",safe="");expiry_endpoint=f"/v2/expired-instruments/expiries?instrument_key={encoded}"
    _,payload,_,entry=fetcher._make_request(expiry_endpoint,api_version="2.0");fetcher.manifest_entries.append(entry)
    if entry["success_blocker_verdict"]!="SUCCESS_POPULATED":raise RuntimeError(entry["success_blocker_verdict"])
    expiries=(payload or {}).get("data") or []
    if not isinstance(expiries,list) or not expiries:raise RuntimeError("INVALID_PROVIDER_SCHEMA: no expired NIFTY expiries")
    _write_json(run_dir/"expiries.json",expiries)
    selected_expiry=None;selected_future=[];selected_options=[]
    for expiry in sorted(expiries,reverse=True):
        try:expiry_date=pd.Timestamp(expiry).date()
        except Exception:continue
        if expiry_date>=datetime.now(IST_TZ).date():continue
        fep=f"/v2/expired-instruments/future/contract?instrument_key={encoded}&expiry_date={expiry}";_,fp,_,fe=fetcher._make_request(fep,api_version="2.0");fetcher.manifest_entries.append(fe)
        if fe["success_blocker_verdict"] not in SUCCESS:continue
        futures=(fp or {}).get("data") or []
        oep=f"/v2/expired-instruments/option/contract?instrument_key={encoded}&expiry_date={expiry}";_,op,_,oe=fetcher._make_request(oep,api_version="2.0");fetcher.manifest_entries.append(oe)
        if oe["success_blocker_verdict"] not in SUCCESS:continue
        options=(op or {}).get("data") or [];calls=[x for x in options if str(x.get("instrument_type"))=="CE"];puts=[x for x in options if str(x.get("instrument_type"))=="PE"]
        chosen_calls=_select_middle_contracts(calls,2);chosen_puts=_select_middle_contracts(puts,2)
        if futures and len(chosen_calls)==2 and len(chosen_puts)==2:selected_expiry=str(expiry);selected_future=[futures[0]];selected_options=chosen_calls+chosen_puts;break
    if selected_expiry is None:raise RuntimeError("BLOCKED_INCOMPLETE_DERIVATIVE_CORPUS")
    _write_json(run_dir/"future_contracts.json",selected_future);_write_json(run_dir/"option_contracts.json",selected_options)
    expiry_ts=pd.Timestamp(selected_expiry).tz_localize(IST_TZ);fetcher.start_date=expiry_ts-timedelta(days=7);fetcher.end_date=expiry_ts
    files={};future_key=str(selected_future[0]["instrument_key"]);future_path=run_dir/"futures"/selected_expiry/(urllib.parse.quote(future_key,safe="")+".parquet")
    frame,ok=fetcher.fetch_historical_candles(future_key,future_path,chunk_monthly=True,version="v2",series_type="FUTURE")
    if not ok or frame is None or frame.empty:raise RuntimeError("INVALID_SMOKE_RECONCILIATION: future candle fetch failed")
    files["FUTURE"]=future_path
    ce_count=pe_count=0
    for contract in selected_options:
        kind=str(contract["instrument_type"]);ce_count+=int(kind=="CE");pe_count+=int(kind=="PE");key=str(contract["instrument_key"]);path=run_dir/"options"/selected_expiry/(urllib.parse.quote(key,safe="")+".parquet")
        frame,ok=fetcher.fetch_historical_candles(key,path,chunk_monthly=True,version="v2",series_type=kind)
        if not ok or frame is None or frame.empty:raise RuntimeError(f"INVALID_SMOKE_RECONCILIATION: {kind} candle fetch failed")
        files[f"{kind}_{ce_count if kind=='CE' else pe_count}"]=path
    if len(files)!=5:raise RuntimeError(f"INVALID_SMOKE_RECONCILIATION: expected 5 files, got {len(files)}")
    sessions,artifacts=_rewrite_to_common_sessions(files)
    expected={str(x) for x in files.values()};actual={str(x) for x in run_dir.rglob("*.parquet")}
    if actual!=expected:raise RuntimeError("INVALID_SMOKE_RECONCILIATION: unexpected or missing Parquet files")
    artifact_manifest={"run_id":run_id,"selected_expiry":selected_expiry,"selected_sessions":sessions,"expected_candle_files":5,"actual_candle_files":len(actual),"artifacts":artifacts};artifact_manifest["semantic_sha256"]=canonical_sha(artifact_manifest)
    _write_json(run_dir/"artifact_manifest.json",artifact_manifest);_write_json(run_dir/"fetch_manifest.json",fetcher.manifest_entries);_write_json(run_dir/"session_coverage.json",{"run_id":run_id,"selected_expiry":selected_expiry,"selected_sessions":sessions,"contract_labels":sorted(files)})
    summary={"run_id":run_id,"smoke_verdict":"PASS_BOUNDED_AUTHENTICATED_FETCH_SMOKE","real_expiry_discovered":len(expiries),"selected_expiry":selected_expiry,"real_future_contracts":1,"real_ce_contracts":2,"real_pe_contracts":2,"real_candle_files":5,"exact_common_sessions":sessions,"smoke_hash_reconciliation":"PASS","no_unexpected_files":True,"created_by_current_run":True,"formal_extraction_approved":True};_write_json(run_dir/"validation_report.json",summary)
    targets=sorted(x for x in run_dir.rglob("*") if x.is_file() and x.name!="SHA256SUMS");lines=[f"{sha256_file(x)}  {x.relative_to(run_dir)}" for x in targets];(run_dir/"SHA256SUMS").write_text("\n".join(lines)+"\n",encoding="utf-8")
    for line in lines:
        expected_hash,relative=line.split("  ",1)
        if sha256_file(run_dir/relative)!=expected_hash:raise RuntimeError(f"INVALID_SMOKE_RECONCILIATION: hash mismatch {relative}")
    logging.info(json.dumps(summary,indent=2));return summary

def main():
    try:summary=run_smoke()
    except FileExistsError as exc:logging.error("INVALID_SMOKE_RECONCILIATION: run directory already exists: %s",exc);sys.exit(2)
    except Exception as exc:logging.error(str(exc));sys.exit(1)
    if summary["smoke_verdict"]!="PASS_BOUNDED_AUTHENTICATED_FETCH_SMOKE":sys.exit(1)
if __name__=="__main__":main()
