#!/usr/bin/env python3
from __future__ import annotations
import argparse,gzip,hashlib,json,logging,math,os,re,time,urllib.error,urllib.parse,urllib.request,uuid
from datetime import datetime,timedelta
from pathlib import Path
from typing import Any
import pandas as pd
import pytz
from dateutil.relativedelta import relativedelta

UPSTOX_BASE_URL="https://api.upstox.com"
IST_TZ=pytz.timezone("Asia/Kolkata")
SUCCESS={"SUCCESS_POPULATED","SUCCESS_VALID_EMPTY"}
FATAL=["INVALID_FETCH_IMPLEMENTATION","INVALID_PROVIDER_SCHEMA","BLOCKED_AUTHENTICATION","BLOCKED_UPSTOX_PLUS_REQUIRED","BLOCKED_PROVIDER_PERMISSION","BLOCKED_PROVIDER_PERMISSION_UNKNOWN","BLOCKED_PROVIDER_UNAVAILABLE","BLOCKED_NETWORK_FAILURE","BLOCKED_RATE_LIMIT_EXHAUSTED"]
logging.basicConfig(level=logging.INFO,format="%(asctime)s - %(levelname)s - %(message)s")

class UpstoxDataError(Exception): pass

def is_proxy_entry_eligible(row)->bool:
    try:return float(row.get("volume",0))>0
    except (TypeError,ValueError):return False

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def canonical_sha(value:Any)->str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

class UpstoxFetcher:
    def __init__(self,start_date,end_date,base_dir=Path("data/psilor_v1/upstox"),reference_dir=Path("data/psilor_v1/reference"),run_id=None):
        self.start_date=self._ist(start_date);self.end_date=self._ist(end_date)
        if self.end_date<self.start_date:raise ValueError("end_date precedes start_date")
        self.base_dir=Path(base_dir);self.base_dir.mkdir(parents=True,exist_ok=True)
        self.ref_dir=Path(reference_dir);self.run_id=run_id or f"psilor-{datetime.utcnow():%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        self.token=os.getenv("UPSTOX_ACCESS_TOKEN","").strip()
        self.user_agent=os.getenv("UPSTOX_USER_AGENT","Upstox-Python-SDK/2.0 TradeBot-PSILOR-Research/1.0").strip()
        self.manifest_entries=[];self.artifact_entries=[];self.validation_errors=[];self.blockers=set()
        self.session_coverage={};self.constituent_coverage={};self.authority_ranges=[];self.constituent_authority_ranges=self.authority_ranges
        self.metrics={k:0 for k in [
            "OPTION_METADATA_DISCOVERED","OPTION_CONTRACTS_REQUESTED","OPTION_REQUEST_CHUNKS_ATTEMPTED","OPTION_REQUEST_CHUNKS_POPULATED","OPTION_REQUEST_CHUNKS_VALID_EMPTY","OPTION_REQUEST_CHUNKS_FAILED","OPTION_CONTRACTS_FULLY_RECONCILED","OPTION_CONTRACTS_PARTIAL","OPTION_OUTPUT_FILES_PRESENT","OPTION_OUTPUT_FILES_MISSING","OPTION_HASH_FAILURES",
            "FUTURE_METADATA_DISCOVERED","FUTURE_CONTRACTS_REQUESTED","FUTURE_REQUEST_CHUNKS_ATTEMPTED","FUTURE_REQUEST_CHUNKS_POPULATED","FUTURE_REQUEST_CHUNKS_VALID_EMPTY","FUTURE_REQUEST_CHUNKS_FAILED","FUTURE_CONTRACTS_FULLY_RECONCILED","FUTURE_CONTRACTS_PARTIAL","FUTURE_OUTPUT_FILES_PRESENT","FUTURE_OUTPUT_FILES_MISSING","FUTURE_HASH_FAILURES"]}
        self.metrics.update({"RUN_ID":self.run_id,"INDEX_FETCH":"FAIL","VIX_FETCH":"FAIL","CONSTITUENT_MEMBERSHIP_AUTHORITY":"FAIL","CONSTITUENT_FETCH":"FAIL","EXPIRED_EXPIRY_DISCOVERY":"FAIL","EXPIRED_FUTURE_DISCOVERY":"FAIL","EXPIRED_OPTION_DISCOVERY":"FAIL","EXPIRED_CANDLE_FETCH":"FAIL","METADATA_UNIVERSE_COMPLETENESS":"FAIL","CANDLE_UNIVERSE_COMPLETENESS":"FAIL","EXACT_DORL_OVERLAPPING_SESSIONS":0,"EXACT_PSILOR_OVERLAPPING_SESSIONS":0,"DATA_ADMISSION_VERDICT":"INVALID_FETCH_IMPLEMENTATION","FORMAL_EXTRACTION_APPROVED":False})
    @staticmethod
    def _ist(v):
        t=pd.Timestamp(v)
        return t.tz_localize(IST_TZ) if t.tzinfo is None else t.tz_convert(IST_TZ)
    @staticmethod
    def _provider_error(body):
        text=body.decode(errors="replace") if isinstance(body,bytes) else str(body)
        try:
            d=json.loads(text);e=(d.get("errors") or [{}])[0]
            return str(e.get("errorCode") or e.get("code") or "") or None,str(e.get("message") or e.get("error") or "") or None
        except Exception:
            if re.search(r"\b1010\b",text) and "browser" in text.lower():return "1010","Provider WAF rejected client signature"
            return None,None
    def _map_http_error(self,code,body):
        ec,_=self._provider_error(body)
        if code==401:return "BLOCKED_AUTHENTICATION"
        if code==403:
            if ec=="UDAPI1149":return "BLOCKED_UPSTOX_PLUS_REQUIRED"
            if ec and ec!="1010":return "BLOCKED_PROVIDER_PERMISSION"
            return "BLOCKED_PROVIDER_PERMISSION_UNKNOWN"
        if code==429:return "BLOCKED_RATE_LIMIT_EXHAUSTED"
        if code>=500:return "BLOCKED_PROVIDER_UNAVAILABLE"
        return "INVALID_PROVIDER_SCHEMA"
    def _request_headers(self,version):
        h={"Accept":"application/json","Api-Version":version,"User-Agent":self.user_agent}
        if self.token:h["Authorization"]=f"Bearer {self.token}"
        return h
    def _make_request(self,endpoint,api_version="3.0",max_retries=3,method="GET",out_file=None):
        url=UPSTOX_BASE_URL+endpoint;p=urllib.parse.urlparse(url);q=urllib.parse.parse_qs(p.query)
        e={"run_id":self.run_id,"request_id":str(uuid.uuid4()),"endpoint_family":p.path,"url_without_token":url,"attempt_count":0,"http_status":0,"upstox_error_code":None,"provider_message":None,"response_row_count":0,"first_timestamp":None,"last_timestamp":None,"output_file":str(out_file) if out_file else None,"response_sha256":None,"success_blocker_verdict":None,"instrument_key":(q.get("instrument_key") or [None])[0],"expiry_date":(q.get("expiry_date") or [None])[0],"from_date":None,"to_date":None}
        parts=[x for x in p.path.split("/") if x]
        if "historical-candle" in parts:
            try:i=parts.index("historical-candle");e.update({"instrument_key":urllib.parse.unquote(parts[i+1]),"interval":parts[i+2],"to_date":parts[i+3],"from_date":parts[i+4]})
            except Exception:pass
        last=None
        for n in range(max_retries):
            e["attempt_count"]+=1
            try:
                req=urllib.request.Request(url,method=method,headers=self._request_headers(api_version))
                with urllib.request.urlopen(req,timeout=60) as r:
                    b=r.read();e["http_status"]=r.status;e["response_sha256"]=hashlib.sha256(b).hexdigest()
                    try:d=json.loads(b.decode())
                    except Exception:self.blockers.add("INVALID_PROVIDER_SCHEMA");e["success_blocker_verdict"]="INVALID_PROVIDER_SCHEMA";return r.status,None,b,e
                    data=d.get("data") if isinstance(d,dict) else None
                    empty=(isinstance(data,dict) and "candles" in data and not data["candles"]) or data in (None,[],{})
                    e["success_blocker_verdict"]="SUCCESS_VALID_EMPTY" if empty else "SUCCESS_POPULATED"
                    return r.status,d,b,e
            except urllib.error.HTTPError as x:
                b=x.read();ec,msg=self._provider_error(b);e.update({"http_status":x.code,"upstox_error_code":ec,"provider_message":msg,"response_sha256":hashlib.sha256(b).hexdigest()})
                if x.code in (429,) or x.code>=500:
                    if n<max_retries-1:
                        delay=x.headers.get("Retry-After") if x.code==429 else None
                        try:delay=int(delay) if delay else 2**n
                        except Exception:delay=2**n
                        time.sleep(delay);continue
                v=self._map_http_error(x.code,b.decode(errors="replace"));self.blockers.add(v);e["success_blocker_verdict"]=v;return x.code,None,b,e
            except Exception as x:
                last=x
                if n<max_retries-1:time.sleep(2**n);continue
        self.blockers.add("BLOCKED_NETWORK_FAILURE");e["success_blocker_verdict"]="BLOCKED_NETWORK_FAILURE";e["provider_message"]=str(last);return 0,None,b"",e
    def validate_candles(self,candles,instrument_key):
        out=[];seen={}
        for c in candles:
            if len(c)<6:raise UpstoxDataError("INVALID_PROVIDER_SCHEMA")
            try:ts=pd.to_datetime(c[0],utc=True);o,h,l,cl,v=map(float,c[1:6]);oi=float(c[6]) if len(c)>6 else 0.
            except Exception as x:raise UpstoxDataError("INVALID_PROVIDER_SCHEMA") from x
            nums=(o,h,l,cl,v,oi)
            if any(math.isnan(x) for x in nums):raise UpstoxDataError("NaN value in candle")
            if any(math.isinf(x) for x in nums):raise UpstoxDataError("Inf value in candle")
            if min(o,h,l,cl)<=0:raise UpstoxDataError("Negative or zero OHLC in candle")
            if v<0 or oi<0:raise UpstoxDataError("Negative volume/OI in candle")
            if h<max(o,cl,l) or l>min(o,cl,h):raise UpstoxDataError("OHLC bounds violation")
            vals=(o,h,l,cl,v,oi)
            if ts in seen:
                if seen[ts]==vals:continue
                self.metrics["DUPLICATE_CONFLICTS"]=self.metrics.get("DUPLICATE_CONFLICTS",0)+1
                raise UpstoxDataError(f"Duplicate candle conflict for {instrument_key} at {ts}")
            seen[ts]=vals;out.append({"timestamp":ts,"session_date":ts.tz_convert(IST_TZ).strftime("%Y-%m-%d"),"open":o,"high":h,"low":l,"close":cl,"volume":v,"open_interest":oi})
        out.sort(key=lambda x:x["timestamp"])
        return out,(out[0]["timestamp"] if out else None),(out[-1]["timestamp"] if out else None)
    def _chunk_metrics(self,series,a,p,e,f):
        prefix="OPTION" if series in {"OPTION","CE","PE"} else ("FUTURE" if series=="FUTURE" else None)
        if prefix:
            self.metrics[f"{prefix}_REQUEST_CHUNKS_ATTEMPTED"]+=a;self.metrics[f"{prefix}_REQUEST_CHUNKS_POPULATED"]+=p;self.metrics[f"{prefix}_REQUEST_CHUNKS_VALID_EMPTY"]+=e;self.metrics[f"{prefix}_REQUEST_CHUNKS_FAILED"]+=f
    def _coverage(self,df,series,symbol):
        for d in df.session_date.unique():
            c=self.session_coverage.setdefault(str(d),{"nifty":False,"vix":False,"future":False,"ce":set(),"pe":set()})
            if series=="NIFTY":c["nifty"]=True
            elif series=="VIX":c["vix"]=True
            elif series=="FUTURE":c["future"]=True
            elif series=="CE":c["ce"].add(symbol)
            elif series=="PE":c["pe"].add(symbol)
            elif series=="CONSTITUENT":self.constituent_coverage.setdefault(str(d),set()).add(symbol)
    def fetch_historical_candles(self,symbol,out_path,chunk_monthly=False,interval="1minute",version="v3",series_type="OTHER"):
        key=urllib.parse.quote(symbol,safe="");rows=[];attempted=populated=empty=failed=0;cur=self.start_date
        while cur<=self.end_date:
            nxt=cur+relativedelta(months=1) if chunk_monthly else cur+timedelta(days=1);end=min(self.end_date,nxt-timedelta(days=1)) if chunk_monthly else cur
            f=cur.strftime("%Y-%m-%d");t=end.strftime("%Y-%m-%d")
            ep=f"/v3/historical-candle/{key}/minutes/1/{t}/{f}" if version=="v3" else f"/v2/expired-instruments/historical-candle/{key}/{interval}/{t}/{f}"
            attempted+=1;_,d,_,m=self._make_request(ep,api_version="3.0" if version=="v3" else "2.0",out_file=out_path);v=m["success_blocker_verdict"]
            if v=="SUCCESS_POPULATED":
                cs=((d or {}).get("data") or {}).get("candles")
                if not isinstance(cs,list):failed+=1;m["success_blocker_verdict"]="INVALID_PROVIDER_SCHEMA";self.blockers.add("INVALID_PROVIDER_SCHEMA")
                else:
                    try:
                        r,first,last=self.validate_candles(cs,symbol)
                        if r:rows+=r;populated+=1;m.update({"response_row_count":len(r),"first_timestamp":first.isoformat(),"last_timestamp":last.isoformat()})
                        else:empty+=1;m["success_blocker_verdict"]="SUCCESS_VALID_EMPTY"
                    except UpstoxDataError as x:failed+=1;m["success_blocker_verdict"]="FAILED_VALIDATION";self.validation_errors.append(str(x))
            elif v=="SUCCESS_VALID_EMPTY":empty+=1
            else:failed+=1
            self.manifest_entries.append(m);cur=nxt
        self._chunk_metrics(series_type,attempted,populated,empty,failed);df=None;verified=False
        if rows:
            dedup={}
            for r in sorted(rows,key=lambda x:x["timestamp"]):
                k=r["timestamp"];vals=tuple(r[x] for x in ("open","high","low","close","volume","open_interest"))
                if k in dedup and dedup[k][0]!=vals:raise UpstoxDataError(f"Duplicate candle conflict for {symbol} at {k}")
                dedup[k]=(vals,r)
            df=pd.DataFrame([x[1] for x in dedup.values()]).sort_values("timestamp").reset_index(drop=True);out_path=Path(out_path);out_path.parent.mkdir(parents=True,exist_ok=True);df.to_parquet(out_path,index=False)
            h=sha256_file(out_path);verified=out_path.exists() and sha256_file(out_path)==h
            self.artifact_entries.append({"run_id":self.run_id,"instrument_key":symbol,"series_type":series_type,"output_file":str(out_path),"row_count":len(df),"session_dates":sorted(df.session_date.unique().tolist()),"sha256":h,"hash_verified":verified})
            self._coverage(df,series_type,symbol)
        prefix="OPTION" if series_type in {"OPTION","CE","PE"} else ("FUTURE" if series_type=="FUTURE" else None)
        if prefix:self.metrics[f"{prefix}_OUTPUT_FILES_PRESENT" if df is not None and verified else f"{prefix}_OUTPUT_FILES_MISSING"]+=1
        reconciled=attempted>0 and attempted==populated+empty+failed and failed==0 and populated>0 and df is not None and not df.empty and verified
        return df,reconciled
    def fetch_indices(self):
        a,ok=self.fetch_historical_candles("NSE_INDEX|Nifty 50",self.base_dir/"index/nifty_50_1m.parquet",chunk_monthly=True,series_type="NIFTY");self.metrics["INDEX_FETCH"]="PASS" if a is not None and ok else "FAIL"
        a,ok=self.fetch_historical_candles("NSE_INDEX|India VIX",self.base_dir/"vix/india_vix_1m.parquet",chunk_monthly=True,series_type="VIX");self.metrics["VIX_FETCH"]="PASS" if a is not None and ok else "FAIL"
    def _load_authority(self):
        out=[]
        for p in sorted(self.ref_dir.glob("nifty_constituents_*.json")):
            try:
                d=json.loads(p.read_text())
                if d.get("historical_authority") is True and len(d.get("constituents") or [])>=45:out.append({"from":pd.Timestamp(d["effective_from"]).date(),"to":pd.Timestamp(d["effective_to"]).date(),"constituents":d["constituents"],"path":str(p)})
            except Exception as x:self.validation_errors.append(f"Invalid constituent manifest {p}: {x}")
        return out
    def _authority(self,date):
        d=pd.Timestamp(date).date();ranges=getattr(self,"constituent_authority_ranges",self.authority_ranges)
        def bounds(x):return x.get("from",x.get("effective_from")),x.get("to",x.get("effective_to"))
        m=[x for x in ranges if bounds(x)[0]<=d<=bounds(x)[1]];return m[-1] if m else None
    def fetch_constituents(self):
        self.authority_ranges=self._load_authority();self.constituent_authority_ranges=self.authority_ranges
        if not self.authority_ranges:return
        self.metrics["CONSTITUENT_MEMBERSHIP_AUTHORITY"]="PASS";symbols={str(c["instrument_key"]) for a in self.authority_ranges for c in a["constituents"] if c.get("instrument_key")}
        for s in sorted(symbols):self.fetch_historical_candles(s,self.base_dir/"constituents"/(urllib.parse.quote(s,safe="")+".parquet"),chunk_monthly=True,series_type="CONSTITUENT")
        counts=[len(x) for x in self.constituent_coverage.values()];self.metrics["CONSTITUENT_FETCH"]="PASS" if any(x>=45 for x in counts) else ("PARTIAL" if counts else "FAIL")
    def audit_pr719_corpus(self):
        root=Path("research/psilor_v1");root.mkdir(parents=True,exist_ok=True);dirs=[Path("data/upstox_expired_options"),Path("runtime/upstox_expired_options"),Path(".runtime/upstox_expired_options"),Path("research/upstox_expired_options/data")]
        pointers=materialized=valid=0
        for d in dirs:
            if not d.exists():continue
            for p in d.rglob("*"):
                if not p.is_file():continue
                if p.read_bytes()[:100].startswith(b"version https://git-lfs.github.com/spec/v1"):pointers+=1
                elif p.suffix==".parquet":
                    materialized+=1
                    try:valid+=int(not pd.read_parquet(p).empty)
                    except Exception:pass
        verdict="REUSABLE_MATERIALIZED_CORPUS" if materialized and valid==materialized else "NOT_MATERIALIZED_OR_NOT_VALIDATED"
        (root/"existing_corpus_inventory.json").write_text(json.dumps({"lfs_pointers_found":pointers,"materialized_parquet_files":materialized,"valid_parquet_files":valid,"authority_verdict":verdict},indent=2))
        (root/"existing_corpus_authority_report.json").write_text(json.dumps({"authority_verdict":verdict,"lfs_pointer_is_not_data":True,"files_reused_by_this_run":0},indent=2))
        (root/"new_fetch_delta_plan.json").write_text(json.dumps({"strategy":"REUSE_VALIDATED_FILES_THEN_FETCH_MISSING" if verdict.startswith("REUSABLE") else "FETCH_REQUIRED_CORPUS_WITHOUT_CLAIMING_PR719_REUSE"},indent=2))
    def fetch_expired_derivatives(self):
        root=self.base_dir/"expired";root.mkdir(parents=True,exist_ok=True);u=urllib.parse.quote("NSE_INDEX|Nifty 50",safe="");_,d,_,m=self._make_request(f"/v2/expired-instruments/expiries?instrument_key={u}",api_version="2.0");self.manifest_entries.append(m)
        if m["success_blocker_verdict"]!="SUCCESS_POPULATED":return
        expiries=(d or {}).get("data") or []
        if not expiries:self.blockers.add("INVALID_PROVIDER_SCHEMA");return
        (root/"expiries.json").write_text(json.dumps(expiries,indent=2));self.metrics["EXPIRED_EXPIRY_DISCOVERY"]="PASS";meta_calls=meta_fail=0
        for expiry in expiries:
            try:ed=pd.Timestamp(expiry).date()
            except Exception:continue
            if not (self.start_date.date()<=ed<=(self.end_date+timedelta(days=31)).date()):continue
            for kind in ("future","option"):
                ep=f"/v2/expired-instruments/{kind}/contract?instrument_key={u}&expiry_date={expiry}";meta_calls+=1;_,payload,_,entry=self._make_request(ep,api_version="2.0");self.manifest_entries.append(entry)
                if entry["success_blocker_verdict"] not in SUCCESS:meta_fail+=1;continue
                contracts=(payload or {}).get("data") or []
                if not contracts:continue
                prefix="FUTURE" if kind=="future" else "OPTION";self.metrics[f"EXPIRED_{prefix}_DISCOVERY"]="PASS";self.metrics[f"{prefix}_METADATA_DISCOVERED"]+=len(contracts);droot=root/f"{kind}s"/str(expiry);droot.mkdir(parents=True,exist_ok=True);(droot/"contracts.json").write_text(json.dumps(contracts,indent=2))
                for c in contracts:
                    key=c.get("instrument_key");series="FUTURE" if kind=="future" else str(c.get("instrument_type") or "")
                    if not key or series not in {"FUTURE","CE","PE"}:continue
                    self.metrics[f"{prefix}_CONTRACTS_REQUESTED"]+=1;_,ok=self.fetch_historical_candles(str(key),droot/(urllib.parse.quote(str(key),safe="")+".parquet"),chunk_monthly=True,version="v2",series_type=series);self.metrics[f"{prefix}_CONTRACTS_FULLY_RECONCILED" if ok else f"{prefix}_CONTRACTS_PARTIAL"]+=1
        self.metrics["METADATA_UNIVERSE_COMPLETENESS"]="COMPLETE_RECONCILED" if meta_calls and not meta_fail and self.metrics["FUTURE_METADATA_DISCOVERED"] and self.metrics["OPTION_METADATA_DISCOVERED"] else "PARTIAL_DECLARED"
        fc=self.metrics["FUTURE_CONTRACTS_REQUESTED"]>0 and self.metrics["FUTURE_CONTRACTS_FULLY_RECONCILED"]==self.metrics["FUTURE_CONTRACTS_REQUESTED"] and not self.metrics["FUTURE_REQUEST_CHUNKS_FAILED"] and not self.metrics["FUTURE_OUTPUT_FILES_MISSING"]
        oc=self.metrics["OPTION_CONTRACTS_REQUESTED"]>0 and self.metrics["OPTION_CONTRACTS_FULLY_RECONCILED"]==self.metrics["OPTION_CONTRACTS_REQUESTED"] and not self.metrics["OPTION_REQUEST_CHUNKS_FAILED"] and not self.metrics["OPTION_OUTPUT_FILES_MISSING"]
        self.metrics["CANDLE_UNIVERSE_COMPLETENESS"]="COMPLETE_RECONCILED" if fc and oc else "PARTIAL_DECLARED";self.metrics["EXPIRED_CANDLE_FETCH"]="PASS" if fc and oc else "FAIL"
    def _sets(self):
        dorl=[];psilor=[];excluded=[]
        for d,c in sorted(self.session_coverage.items()):
            miss=[x for x,ok in (("MISSING_NIFTY",c["nifty"]),("MISSING_VIX",c["vix"]),("MISSING_FUTURE",c["future"]),("MISSING_CE",bool(c["ce"])),("MISSING_PE",bool(c["pe"]))) if not ok]
            if miss:excluded.append({"session_date":d,"lane":"DORL","reasons":miss});continue
            dorl.append(d);n=len(self.constituent_coverage.get(d,set()));a=self._authority(d)
            if a and n>=45:psilor.append(d)
            else:excluded.append({"session_date":d,"lane":"PSILOR","reasons":(["MISSING_POINT_IN_TIME_CONSTITUENT_AUTHORITY"] if not a else [])+(["CONSTITUENT_COVERAGE_BELOW_45"] if n<45 else []),"constituent_count":n})
        return dorl,psilor,excluded
    def compute_verdict(self):
        dorl,psilor,_=self._sets();self.metrics["EXACT_DORL_OVERLAPPING_SESSIONS"]=len(dorl);self.metrics["EXACT_PSILOR_OVERLAPPING_SESSIONS"]=len(psilor)
        for b in FATAL:
            if b in self.blockers:self.metrics["DATA_ADMISSION_VERDICT"]=b;self.metrics["FORMAL_EXTRACTION_APPROVED"]=False;return b
        v="BLOCKED_INCOMPLETE_DERIVATIVE_CORPUS" if self.metrics["EXPIRED_CANDLE_FETCH"]!="PASS" else ("DATA_READY_FOR_PSILOR_PROXY_VALIDATION" if len(psilor)>=30 else ("DATA_READY_FOR_DORL_ONLY" if len(dorl)>=30 else "BLOCKED_INSUFFICIENT_OVERLAP"))
        self.metrics["DATA_ADMISSION_VERDICT"]=v;self.metrics["FORMAL_EXTRACTION_APPROVED"]=v.startswith("DATA_READY_");return v
    def generate_reports(self):
        dorl,psilor,ex=self._sets();self.compute_verdict();self.metrics["semantic_manifest_sha256"]=canonical_sha([{k:v for k,v in x.items() if k not in {"request_id","run_id"}} for x in self.manifest_entries])
        for name,obj in {"fetch_manifest.json":self.manifest_entries,"artifact_manifest.json":self.artifact_entries,"validation_report.json":self.metrics,"session_sets.json":{"dorl_sessions":dorl,"psilor_sessions":psilor},"overlapping_sessions.json":{"exact_dorl_overlapping_sessions":dorl,"exact_psilor_overlapping_sessions":psilor},"session_exclusion_ledger.json":ex,"session_derivative_coverage.json":{d:{"nifty":c["nifty"],"vix":c["vix"],"future":c["future"],"ce_eligible_count":len(c["ce"]),"pe_eligible_count":len(c["pe"])} for d,c in self.session_coverage.items()}}.items():(self.base_dir/name).write_text(json.dumps(obj,indent=2,default=str))
    def run(self):
        self.audit_pr719_corpus();self.fetch_indices();self.fetch_constituents();self.fetch_expired_derivatives();self.generate_reports()

def main():
    p=argparse.ArgumentParser();now=pd.Timestamp.now(tz=IST_TZ);p.add_argument("--start-date",default=(now-relativedelta(months=6)).strftime("%Y-%m-%d"));p.add_argument("--end-date",default=now.strftime("%Y-%m-%d"));p.add_argument("--base-dir",default="data/psilor_v1/upstox");a=p.parse_args();UpstoxFetcher(pd.Timestamp(a.start_date).tz_localize(IST_TZ),pd.Timestamp(a.end_date).tz_localize(IST_TZ),Path(a.base_dir)).run()
if __name__=="__main__":main()
