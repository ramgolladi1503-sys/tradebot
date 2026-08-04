#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Sequence
import numpy as np
import pandas as pd

STUDY_ID="gravity_well_location_participation_v1"; IST="Asia/Kolkata"
INDEX={"NIFTY 50","NIFTY50","NSE_INDEX|NIFTY 50"}

@dataclass(frozen=True)
class FrozenSpec:
    event_bar_minutes:int=5; htf_minutes:tuple[int,int]=(15,30); center_length:int=20
    center_neighbours:tuple[int,int]=(15,30); atr_length:int=14; displacement_atr:float=1.5
    displacement_neighbour:float=2.0; escape_persistence_bars:int=2; cluster_lookback_bars:int=20
    cluster_tolerance_atr:float=.25; minimum_constituents:int=40; participation_threshold:float=.60
    option_hold_minutes:int=10; primary_friction_pct:float=1.; severe_friction_pct:float=1.5
    minimum_sessions:int=30; minimum_total_trades:int=200; minimum_test_trades:int=50

@dataclass(frozen=True)
class SourceInventory:
    path:str; sha256:str; size_bytes:int; rows:int; sessions:int; symbols:int
    start_timestamp:str|None; end_timestamp:str|None; timezone:str; index_rows:int; option_rows:int
    constituent_rows:int; positive_index_volume_rows:int; complete_market_sessions:int
    authority_grade:str; rejection_reasons:tuple[str,...]

def sha256_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def parse_timestamp(s:pd.Series)->pd.Series:
    n=pd.to_numeric(s,errors="coerce")
    x=pd.to_datetime(n,unit="s",utc=True,errors="coerce") if n.notna().mean()>.95 else pd.to_datetime(s,utc=True,errors="coerce")
    return x.dt.tz_convert(IST)

def classify_symbol(s:str)->str:
    u=str(s).strip().upper()
    if u in INDEX:return "NIFTY_INDEX"
    if u.startswith("NSE_EQ|"):return "NIFTY_CONSTITUENT_CANDIDATE"
    if u.startswith("NIFTY") and (u.endswith("CE") or u.endswith("PE") or " CE " in u or " PE " in u):return "NIFTY_OPTION"
    return "OTHER"

def canonicalise_ticks(raw:pd.DataFrame)->pd.DataFrame:
    names={str(c).lower():c for c in raw.columns}; aliases={
      "timestamp":("ts","timestamp","time"),"symbol":("symbol","instrument_key","tradingsymbol"),
      "ltp":("ltp","last_price","price"),"bid":("bid","bid_price","best_bid_price"),
      "ask":("ask","ask_price","best_ask_price"),"volume":("vol","volume")}
    d={}
    for k,opts in aliases.items():
        c=next((names[o] for o in opts if o in names),None)
        if c is None and k not in {"bid","ask","volume"}:raise ValueError(f"missing {k}")
        d[k]=raw[c] if c is not None else pd.Series(np.nan,index=raw.index)
    z=pd.DataFrame(d); z.timestamp=parse_timestamp(z.timestamp); z.symbol=z.symbol.astype(str).str.strip()
    for c in ("ltp","bid","ask","volume"):z[c]=pd.to_numeric(z[c],errors="coerce")
    z=z.dropna(subset=["timestamp","symbol","ltp"]); z=z[z.ltp>=0].copy()
    z["kind"]=z.symbol.map(classify_symbol); z["session"]=z.timestamp.dt.strftime("%Y-%m-%d")
    return z.sort_values("timestamp").reset_index(drop=True)

def market_session_is_complete(ts:pd.Series)->bool:
    if ts.empty:return False
    x=ts.dt.tz_convert(IST); return x.min().strftime("%H:%M")<="09:35" and x.max().strftime("%H:%M")>="15:20"

def inventory_source(p:Path,t:pd.DataFrame)->SourceInventory:
    i=t[t.kind=="NIFTY_INDEX"]; o=t[t.kind=="NIFTY_OPTION"]; c=t[t.kind=="NIFTY_CONSTITUENT_CANDIDATE"]
    complete=sum(market_session_is_complete(g.timestamp) for _,g in t.groupby("session")); r=[]
    if i.empty:r.append("NO_NIFTY_INDEX_ROWS")
    if not (i.volume.fillna(0)>0).any():r.append("NO_POSITIVE_NIFTY_INDEX_VOLUME")
    if c.empty:r.append("NO_NIFTY_CONSTITUENT_ROWS")
    if o.empty:r.append("NO_NIFTY_OPTION_ROWS")
    if not complete:r.append("NO_COMPLETE_MARKET_SESSION")
    return SourceInventory(str(p.resolve()),sha256_file(p),p.stat().st_size,len(t),t.session.nunique(),t.symbol.nunique(),
      t.timestamp.min().isoformat() if len(t) else None,t.timestamp.max().isoformat() if len(t) else None,IST,len(i),len(o),len(c),
      int((i.volume.fillna(0)>0).sum()),complete,"PRIMARY_ELIGIBLE" if not r else "DIAGNOSTIC_ONLY",tuple(r))

def resample_index_bars(t:pd.DataFrame,minutes:int=5)->pd.DataFrame:
    out=[]
    if t.empty:return pd.DataFrame()
    for s,d in t.set_index("timestamp").sort_index().groupby(lambda x:x.strftime("%Y-%m-%d")):
        q=d.ltp.resample(f"{minutes}min",label="right",closed="right").ohlc()
        q["volume"]=d.volume.resample(f"{minutes}min",label="right",closed="right").last(); q["tick_count"]=d.ltp.resample(f"{minutes}min",label="right",closed="right").count(); q["session"]=s
        out.append(q.dropna(subset=["open","high","low","close"]))
    return pd.concat(out).reset_index().sort_values("timestamp").reset_index(drop=True) if out else pd.DataFrame()

def resample_constituent_bars(t:pd.DataFrame,minutes:int=5)->pd.DataFrame:
    out=[]
    for (sym,s),d in t.groupby(["symbol","session"],sort=True):
        q=d.set_index("timestamp").sort_index().ltp.resample(f"{minutes}min",label="right",closed="right").ohlc().dropna(); q["symbol"]=sym; q["session"]=s; out.append(q.reset_index())
    return pd.concat(out,ignore_index=True) if out else pd.DataFrame(columns=["timestamp","symbol","open","high","low","close","session"])

def true_range(z):
    p=z.close.shift(); return pd.concat([z.high-z.low,(z.high-p).abs(),(z.low-p).abs()],axis=1).max(axis=1)

def add_causal_atr(z,length):
    q=z.copy();q["atr"]=true_range(q).ewm(alpha=1/length,adjust=False,min_periods=length).mean();return q

def add_volume_weighted_center(z,length):
    q=z.copy();v=pd.to_numeric(q.volume,errors="coerce");den=v.rolling(length,min_periods=length).sum()
    q["gravity_center"]=(q.close*v).rolling(length,min_periods=length).sum()/den.replace(0,np.nan)
    q["center_slope"]=q.gravity_center.diff();q["center_acceleration"]=q.center_slope.diff();q["displacement_atr"]=(q.close-q.gravity_center)/q.atr.replace(0,np.nan);return q

def completed_htf_levels(z,htf_minutes,lookback):
    out=[]
    for s,d in z.groupby("session",sort=True):
        d=d.set_index("timestamp").sort_index(); h=d[["open","high","low","close"]].resample(f"{htf_minutes}min",label="right",closed="right").agg({"open":"first","high":"max","low":"min","close":"last"}).dropna()
        h["prior_resistance"]=h.high.rolling(lookback,min_periods=2).max().shift();h["prior_support"]=h.low.rolling(lookback,min_periods=2).min().shift()
        m=pd.merge_asof(d.reset_index(),h[["prior_resistance","prior_support"]].reset_index(),on="timestamp",direction="backward");m["session"]=s;out.append(m)
    return pd.concat(out,ignore_index=True) if out else pd.DataFrame()

def participation_frame(c,b,n):
    if c.empty:
        q=b[["timestamp","session"]].copy();q["constituent_count"]=0;q["breadth_up"]=np.nan;q["breadth_down"]=np.nan;q["participation_available"]=False;return q
    z=c.sort_values(["symbol","timestamp"]).copy();z["ret1"]=z.groupby("symbol").close.pct_change()
    g=z.groupby(["timestamp","session"]).ret1.agg(constituent_count="count",breadth_up=lambda x:(x>0).mean(),breadth_down=lambda x:(x<0).mean()).reset_index();g["participation_available"]=g.constituent_count>=n
    return b[["timestamp","session"]].merge(g,on=["timestamp","session"],how="left").fillna({"constituent_count":0,"participation_available":False})

def generate_primary_events(b,c,s):
    if b.empty or c.empty or not (b.volume.fillna(0)>0).any():return pd.DataFrame()
    z=completed_htf_levels(add_volume_weighted_center(add_causal_atr(b,s.atr_length),s.center_length),15,s.cluster_lookback_bars)
    p=participation_frame(c,z,s.minimum_constituents);z=z.merge(p[["timestamp","session","constituent_count","breadth_up","breadth_down","participation_available"]],on=["timestamp","session"],how="left")
    up=z.participation_available.fillna(False)&(z.breadth_up>=s.participation_threshold);dn=z.participation_available.fillna(False)&(z.breadth_down>=s.participation_threshold)
    ou=z.displacement_atr>=s.displacement_atr;od=z.displacement_atr<=-s.displacement_atr;inside=z.displacement_atr.abs()<s.displacement_atr
    flags={
      "GW_ESCAPE_ACCEPTANCE":(ou&ou.shift(fill_value=False)&(z.center_slope>0)&(z.center_acceleration>=0)&up,od&od.shift(fill_value=False)&(z.center_slope<0)&(z.center_acceleration<=0)&dn),
      "GW_FAILED_ESCAPE":(od.shift(fill_value=False)&inside&(z.center_slope>=0)&up,ou.shift(fill_value=False)&inside&(z.center_slope<=0)&dn),
      "GW_CLUSTER_BREAK_ACCEPTANCE":(((z.close.shift()>z.prior_resistance.shift())&(z.close.shift(2)<=z.prior_resistance.shift(2))&(z.close>z.prior_resistance)&(z.center_slope>0)&up),((z.close.shift()<z.prior_support.shift())&(z.close.shift(2)>=z.prior_support.shift(2))&(z.close<z.prior_support)&(z.center_slope<0)&dn))}
    rows=[]
    for fam,(lf,sf) in flags.items():
      for side,f in (("LONG",lf),("SHORT",sf)):
       for _,r in z[f.fillna(False)].iterrows():rows.append({"family":fam,"side":side,"signal_time":r.timestamp.isoformat(),"session":r.session,"spot":float(r.close),"atr":float(r.atr),"authority":"PRIMARY_CAUSAL_EVENT"})
    return pd.DataFrame(rows)

def diagnostic_events(b,s):
    if b.empty:return pd.DataFrame()
    z=add_causal_atr(b,s.atr_length);z["center"]=z.close.ewm(span=s.center_length,adjust=False,min_periods=s.center_length).mean();z["slope"]=z.center.diff();z["acc"]=z.slope.diff();z["d"]=(z.close-z.center)/z.atr.replace(0,np.nan);z=completed_htf_levels(z,15,s.cluster_lookback_bars)
    ou=z.d>=s.displacement_atr;od=z.d<=-s.displacement_atr;inside=z.d.abs()<s.displacement_atr
    flags={"PRICE_ONLY_ESCAPE_CONTROL":(ou&(z.slope>0)&(z.acc>=0),od&(z.slope<0)&(z.acc<=0)),"PRICE_ONLY_FAILED_ESCAPE_CONTROL":(od.shift(fill_value=False)&inside,ou.shift(fill_value=False)&inside),"LOCATION_ONLY_CLUSTER_BREAK_CONTROL":((z.close>z.prior_resistance)&(z.close.shift()<=z.prior_resistance.shift()),(z.close<z.prior_support)&(z.close.shift()>=z.prior_support.shift()))}
    rows=[]
    for fam,(lf,sf) in flags.items():
      for side,f in (("LONG",lf),("SHORT",sf)):
       for _,r in z[f.fillna(False)].iterrows():rows.append({"family":fam,"side":side,"signal_time":r.timestamp.isoformat(),"session":r.session,"spot":float(r.close),"authority":"DIAGNOSTIC_ONLY_PRICE_CONTROL"})
    return pd.DataFrame(rows)

SP=re.compile(r"^NIFTY\s+(?P<strike>\d+)\s+(?P<type>CE|PE)\s+(?P<day>\d+)\s+(?P<mon>[A-Z]{3})\s+(?P<year>\d{2})$",re.I); CP=re.compile(r"^NIFTY(?P<yy>\d{2})(?P<m>\d)(?P<dd>\d{2})(?P<strike>\d+)(?P<type>CE|PE)$",re.I); MON={m:i for i,m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(),1)}
def parse_option_symbol(s):
    m=SP.match(str(s).strip().upper())
    if m:
      g=m.groupdict()
      try:e=date(2000+int(g["year"]),MON[g["mon"]],int(g["day"]))
      except (ValueError,KeyError):return None
      return {"strike":int(g["strike"]),"option_type":g["type"],"expiry":e.isoformat()}
    m=CP.match(str(s).strip().upper())
    if m:
      g=m.groupdict()
      try:e=date(2000+int(g["yy"]),int(g["m"]),int(g["dd"]))
      except ValueError:return None
      return {"strike":int(g["strike"]),"option_type":g["type"],"expiry":e.isoformat()}
    return None

def map_diagnostic_options(e,o,s):
    if e.empty or o.empty:return pd.DataFrame()
    p=o.symbol.map(parse_option_symbol);q=o[p.notna()].copy()
    if q.empty:return pd.DataFrame()
    q=pd.concat([q,pd.DataFrame(p[p.notna()].tolist(),index=q.index)],axis=1);q.expiry=pd.to_datetime(q.expiry).dt.date;q["session_date"]=q.timestamp.dt.date;out=[]
    for _,r in e.iterrows():
      sig=pd.Timestamp(r.signal_time);sig=sig.tz_localize(IST) if sig.tzinfo is None else sig;typ="CE" if r.side=="LONG" else "PE";atm=round(float(r.spot)/50)*50
      u=q[(q.session_date==sig.date())&(q.option_type==typ)&(q.expiry>=sig.date())]
      if u.empty:continue
      ex=u.expiry.min();u=u[u.expiry==ex];st=min(u.strike.unique(),key=lambda x:(abs(x-atm),x));x=u[u.strike==st].sort_values("timestamp")
      a=x[(x.timestamp>sig)&(x.timestamp<=sig+pd.Timedelta(minutes=5))&(x.ask>0)&(x.bid>0)&(x.ask>=x.bid)]
      if a.empty:continue
      en=a.iloc[0];target=en.timestamp+pd.Timedelta(minutes=s.option_hold_minutes);b=x[(x.timestamp>=target)&(x.timestamp<=target+pd.Timedelta(minutes=2))&(x.ask>0)&(x.bid>0)&(x.ask>=x.bid)]
      if b.empty:continue
      exr=b.iloc[0];gross=(float(exr.bid)/float(en.ask)-1)*100;out.append({**r.to_dict(),"expiry":ex.isoformat(),"strike":int(st),"option_type":typ,"strike_identity":"EXACT_ATM" if st==atm else "NEAREST_STRIKE_PROXY","entry_time":en.timestamp.isoformat(),"exit_time":exr.timestamp.isoformat(),"entry_ask":float(en.ask),"exit_bid":float(exr.bid),"gross_return_pct":gross,"net_return_primary_pct":gross-s.primary_friction_pct,"net_return_severe_pct":gross-s.severe_friction_pct})
    return pd.DataFrame(out)

def summary(e,m):
    counts=e.groupby(["family","side"]).size().rename("count").reset_index().to_dict("records") if len(e) else [];metrics=[]
    if len(m):
      for (f,side,i),g in m.groupby(["family","side","strike_identity"]):
       v=g.net_return_primary_pct;metrics.append({"family":f,"side":side,"strike_identity":i,"trades":len(g),"sessions":g.session.nunique(),"mean_net_return_pct":float(v.mean()),"median_net_return_pct":float(v.median()),"win_rate":float((v>0).mean())})
    return {"event_counts":counts,"option_metrics":metrics}

def choose_verdict(inv:Sequence[SourceInventory],s:FrozenSpec):
    n=sum(x.complete_market_sessions for x in inv);b=[]
    if n<s.minimum_sessions:b.append(f"INSUFFICIENT_INDEPENDENT_COMPLETE_SESSIONS_{n}_LT_{s.minimum_sessions}")
    if not sum(x.positive_index_volume_rows for x in inv):b.append("MISSING_CAUSAL_NIFTY_UNDERLYING_VOLUME")
    if not sum(x.constituent_rows for x in inv):b.append("MISSING_NIFTY_CONSTITUENT_PARTICIPATION")
    if not sum(x.option_rows for x in inv):b.append("MISSING_REAL_NIFTY_OPTION_QUOTES")
    if not b:return "RESEARCH_ELIGIBLE_NOT_YET_EVALUATED",b
    k=[]
    if any(x.startswith("INSUFFICIENT") for x in b):k.append("INSUFFICIENT_SESSIONS")
    if "MISSING_CAUSAL_NIFTY_UNDERLYING_VOLUME" in b:k.append("MISSING_UNDERLYING_VOLUME")
    if "MISSING_NIFTY_CONSTITUENT_PARTICIPATION" in b:k.append("MISSING_CONSTITUENTS")
    if "MISSING_REAL_NIFTY_OPTION_QUOTES" in b:k.append("MISSING_OPTION_QUOTES")
    return "DATA_BLOCKED_"+"_AND_".join(k),b

def load_source(p):
    r=pd.read_csv(p,low_memory=False) if p.suffix.lower() in {".csv",".txt"} else pd.read_parquet(p);return canonicalise_ticks(r)
def run(frames,root,s):
    root.mkdir(parents=True,exist_ok=True);(root/"evidence").mkdir(exist_ok=True);inv=[inventory_source(p,t) for p,t in frames]
    idx=pd.concat([t[t.kind=="NIFTY_INDEX"] for _,t in frames],ignore_index=True);opt=pd.concat([t[t.kind=="NIFTY_OPTION"] for _,t in frames],ignore_index=True);ct=pd.concat([t[t.kind=="NIFTY_CONSTITUENT_CANDIDATE"] for _,t in frames],ignore_index=True)
    b=resample_index_bars(idx,s.event_bar_minutes);cb=resample_constituent_bars(ct,s.event_bar_minutes);pe=generate_primary_events(b,cb,s);de=diagnostic_events(b,s);pm=map_diagnostic_options(pe,opt,s);dm=map_diagnostic_options(de,opt,s);part=participation_frame(cb,b,s.minimum_constituents);v,blocks=choose_verdict(inv,s)
    r={"study_id":STUDY_ID,"generated_at":datetime.now().astimezone().isoformat(),"verdict":v,"blockers":blocks,"claim_boundary":{"structural_edge_claimed":False,"holdout_opened":False,"production_strategy_modified":False,"broker_api_called":False,"order_action":False,"diagnostic_price_control_can_certify":False},"frozen_spec":asdict(s),"source_inventory":[asdict(x) for x in inv],"aggregate":{"source_files":len(inv),"input_rows":sum(x.rows for x in inv),"unique_sessions":idx.session.nunique(),"complete_sessions":sum(x.complete_market_sessions for x in inv),"index_rows":len(idx),"option_rows":len(opt),"constituent_rows":len(ct),"positive_index_volume_rows":int((idx.volume.fillna(0)>0).sum()),"five_minute_index_bars":len(b),"five_minute_constituent_bars":len(cb),"participation_available_rows":int(part.participation_available.sum()),"primary_event_rows":len(pe)},"primary_events":summary(pe,pm),"diagnostic_controls":summary(de,dm),"next_legitimate_step":"Supply an immutable multi-session NIFTY constituent corpus; never substitute option volume, tick count, or synthetic breadth."}
    (root/"frozen_spec.json").write_text(json.dumps(asdict(s),indent=2,default=str)+"\n");(root/"data_manifest.json").write_text(json.dumps([asdict(x) for x in inv],indent=2,default=str)+"\n");(root/"evidence"/"report.json").write_text(json.dumps(r,indent=2,default=str)+"\n")
    if len(pe):pe.to_csv(root/"evidence"/"primary_events.csv",index=False)
    if len(pm):pm.to_csv(root/"evidence"/"primary_option_ledger.csv",index=False)
    if len(de):de.to_csv(root/"evidence"/"diagnostic_events.csv",index=False)
    if len(dm):dm.to_csv(root/"evidence"/"diagnostic_option_ledger.csv",index=False)
    return r
def main():
    p=argparse.ArgumentParser();p.add_argument("--ticks",nargs="+",type=Path,required=True);p.add_argument("--output-root",type=Path,required=True);a=p.parse_args();r=run([(x,load_source(x)) for x in a.ticks],a.output_root,FrozenSpec());print(json.dumps({"verdict":r["verdict"],"blockers":r["blockers"],"aggregate":r["aggregate"]},indent=2));return 0 if r["verdict"].startswith("DATA_BLOCKED_") else 2
if __name__=="__main__":raise SystemExit(main())
