#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,itertools,json,math
from pathlib import Path
from statistics import mean
EXPECTED_DATASET_SHA='66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32'

def sha256(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def f(r,k):
 try:return float(r[k])
 except:return float('nan')
def sgn(x):return 1 if x>0 else -1 if x<0 else 0
def load(p):
 with open(p,newline='',encoding='utf-8') as h:rows=list(csv.DictReader(h))
 req={'timestamp','session','banknifty_open','banknifty_high','banknifty_low','banknifty_close','nifty_ret_1_bps','sensex_ret_1_bps'}
 if not rows or not req.issubset(rows[0]):raise ValueError('dataset_schema_mismatch')
 return rows
def grid(g,hs):
 ks=sorted(g)
 for vals in itertools.product(*(g[k] for k in ks)):
  base=dict(zip(ks,vals))
  for h in hs:yield {**base,'horizon_bars':int(h)}
def bnret(rows,i):
 if i<1 or rows[i-1]['session']!=rows[i]['session']:return float('nan')
 a=f(rows[i-1],'banknifty_close');b=f(rows[i],'banknifty_close')
 return (b/a-1)*10000 if math.isfinite(a) and math.isfinite(b) and a>0 else float('nan')
def brange(rows,i):
 o=f(rows[i],'banknifty_open');h=f(rows[i],'banknifty_high');l=f(rows[i],'banknifty_low')
 return ((h-l)/o)*10000 if all(math.isfinite(x) for x in (o,h,l)) and o>0 and h>=l else float('nan')
def prior_values(rows,i,n,fn):
 if i-n<0:return None
 sess=rows[i]['session'];vals=[]
 for j in range(i-n,i):
  if rows[j]['session']!=sess:return None
  x=fn(rows,j)
  if not math.isfinite(x):return None
  vals.append(x)
 return vals
def leader_pair(rows,i):
 n=f(rows[i],'nifty_ret_1_bps');s=f(rows[i],'sensex_ret_1_bps')
 return n,s

def direction(pid,rows,i,c):
 r=bnret(rows,i)
 if pid.startswith('HUNT_V8_'):
  if not math.isfinite(r) or sgn(r)==0:return 0
  if pid in ('HUNT_V8_RANGE_SHOCK_CONTINUATION','HUNT_V8_RANGE_SHOCK_REVERSAL'):
   n=int(c['lookback_bars']);prev=prior_values(rows,i,n,brange);cur=brange(rows,i)
   if not prev or not math.isfinite(cur):return 0
   avg=sum(prev)/len(prev)
   if avg<=0 or cur<avg*float(c['range_ratio']):return 0
   return sgn(r) if pid.endswith('CONTINUATION') else -sgn(r)
  if pid=='HUNT_V8_COMPRESSION_RELEASE_CONTINUATION':
   n=int(c['lookback_bars']);prev=prior_values(rows,i,n,brange);cur=brange(rows,i)
   if not prev or not math.isfinite(cur) or len(prev)<4:return 0
   half=len(prev)//2;early=mean(prev[:half]);late=mean(prev[half:])
   if early<=0 or late>early*float(c['compression_ratio']) or cur<=early:return 0
   return sgn(r)
  if pid=='HUNT_V8_TWO_BAR_VOLATILITY_CLIMAX_FADE':
   if i<2 or rows[i-1]['session']!=rows[i]['session']:return 0
   prev6=prior_values(rows,i-1,6,brange)
   if not prev6:return 0
   base=mean(prev6);rp=bnret(rows,i-1);cr=brange(rows,i);pr=brange(rows,i-1)
   if base<=0 or not all(math.isfinite(x) for x in (rp,cr,pr)) or sgn(rp)==0 or sgn(rp)!=sgn(r):return 0
   return -sgn(r) if min(cr,pr)>=base*float(c['range_ratio']) else 0
 if pid.startswith('HUNT_V9_'):
  n,s=leader_pair(rows,i)
  if not all(math.isfinite(x) for x in (n,s,r)):return 0
  if pid in ('HUNT_V9_BANKNIFTY_UNDERPERFORMER_CATCHUP','HUNT_V9_BANKNIFTY_OUTPERFORMER_FADE'):
   if sgn(n)==0 or sgn(n)!=sgn(s):return 0
   d=sgn(n);leader=float(c['leader_bps']);gap=float(c['rank_gap_bps'])
   if min(abs(n),abs(s))<leader or sgn(r)!=d:return 0
   lavg=(abs(n)+abs(s))/2.0
   if pid.endswith('CATCHUP'):
    return d if lavg-abs(r)>=gap else 0
   return -d if abs(r)-lavg>=gap else 0
  if pid=='HUNT_V9_LEADER_REVERSAL_WITH_BANKNIFTY_LAG':
   if i<1 or rows[i-1]['session']!=rows[i]['session']:return 0
   pn,ps=leader_pair(rows,i-1);thr=float(c['leader_reversal_bps']);lag=float(c['bn_lag_bps'])
   if not all(math.isfinite(x) for x in (pn,ps)):return 0
   if sgn(n)==0 or sgn(n)!=sgn(s) or sgn(pn)==0 or sgn(pn)!=sgn(ps) or sgn(n)==sgn(pn):return 0
   if min(abs(n),abs(s),abs(pn),abs(ps))<thr or abs(r)>lag:return 0
   return sgn(n)
  if pid=='HUNT_V9_DISAGREEMENT_TO_CONSENSUS_TRANSITION':
   if i<1 or rows[i-1]['session']!=rows[i]['session']:return 0
   pn,ps=leader_pair(rows,i-1);thr=float(c['consensus_bps'])
   if not all(math.isfinite(x) for x in (pn,ps)) or sgn(pn)==0 or sgn(ps)==0 or sgn(pn)==sgn(ps):return 0
   if sgn(n)==0 or sgn(n)!=sgn(s) or sgn(r)!=sgn(n) or min(abs(n),abs(s))<thr:return 0
   return sgn(n)
 if pid.startswith('HUNT_V10_'):
  n,s=leader_pair(rows,i)
  if not all(math.isfinite(x) for x in (n,s,r)):return 0
  look=int(c['lookback_bars']);pairs=[]
  if i-look<0:return 0
  sess=rows[i]['session']
  for j in range(i-look,i):
   if rows[j]['session']!=sess:return 0
   a,b=leader_pair(rows,j)
   if not all(math.isfinite(x) for x in (a,b)):return 0
   pairs.append(1 if sgn(a)!=0 and sgn(a)==sgn(b) else 0)
  frac=sum(pairs)/len(pairs)
  if pid in ('HUNT_V10_HIGH_AGREEMENT_REGIME_CONTINUATION','HUNT_V10_HIGH_AGREEMENT_REGIME_BANKNIFTY_FADE'):
   if frac<float(c['agreement_fraction']) or sgn(n)==0 or sgn(n)!=sgn(s) or sgn(r)!=sgn(n):return 0
   return sgn(n) if pid.endswith('CONTINUATION') else -sgn(n)
  if pid=='HUNT_V10_LOW_AGREEMENT_BREAK_TO_CONSENSUS':
   if frac>float(c['max_prior_agreement']) or sgn(n)==0 or sgn(n)!=sgn(s) or sgn(r)!=sgn(n):return 0
   return sgn(n)
  if pid=='HUNT_V10_CONSENSUS_BREAKDOWN_BANKNIFTY_REVERSAL':
   if frac<float(c['min_prior_agreement']) or sgn(n)==0 or sgn(s)==0 or sgn(n)==sgn(s) or i<1:return 0
   pr=bnret(rows,i-1)
   if not math.isfinite(pr) or sgn(pr)==0 or sgn(r)==0 or sgn(pr)==sgn(r):return 0
   return sgn(r)
 raise ValueError('unknown_passport:'+pid)

def evaluate(rows,idx,pid,c,cost):
 rets=[];i=min(idx) if idx else 0;end=max(idx) if idx else -1
 while i<=end:
  if i not in idx:i+=1;continue
  d=direction(pid,rows,i,c)
  if not d:i+=1;continue
  en=i+1;ex=en+int(c['horizon_bars']);sess=rows[i]['session']
  if en not in idx or ex not in idx or rows[en]['session']!=sess or rows[ex]['session']!=sess:i+=1;continue
  p0=f(rows[en],'banknifty_close');p1=f(rows[ex],'banknifty_close')
  if not(math.isfinite(p0) and math.isfinite(p1) and p0>0):i+=1;continue
  rets.append(d*(p1/p0-1)*10000-float(cost));i=ex+1
 if not rets:return {'trades':0,'mean_net_bps':None,'win_rate':None,'total_net_bps':None}
 return {'trades':len(rets),'mean_net_bps':mean(rets),'win_rate':sum(x>0 for x in rets)/len(rets),'total_net_bps':sum(rets)}

def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--freeze',required=True);ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--output',required=True);a=ap.parse_args(argv)
 root=Path(a.repo_root).resolve();fp=root/a.freeze;ds=root/a.dataset;out=root/a.output;res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'validation_accessed':False,'holdout_accessed':False}
 try:
  fr=json.loads(fp.read_text());gid=fr.get('generation_id','')
  if gid not in {'HUNT_V8_GENERATION_FREEZE','HUNT_V9_GENERATION_FREEZE','HUNT_V10_GENERATION_FREEZE'}:raise ValueError('generation_id_mismatch')
  if fr.get('dataset_sha256')!=EXPECTED_DATASET_SHA or sha256(ds)!=EXPECTED_DATASET_SHA:raise ValueError('dataset_hash_mismatch')
  rows=load(ds);sessions=sorted({r['session'] for r in rows});nd=int(len(sessions)*fr['split_contract']['development_fraction']);dev=set(sessions[:nd]);idx={i for i,r in enumerate(rows) if r['session'] in dev};hs=fr['execution_contract']['development_horizons_bars'];cost=fr['execution_contract']['base_round_trip_cost_bps'];gate=fr['development_gate'];cands=[]
  for p in fr['passports']:
   arr=[{'config':c,'metrics':evaluate(rows,idx,p['passport_id'],c,cost)} for c in grid(p['grid'],hs)];elig=[x for x in arr if x['metrics']['trades']>=gate['minimum_trades'] and x['metrics']['mean_net_bps'] is not None and x['metrics']['mean_net_bps']>0];elig.sort(key=lambda x:(x['metrics']['mean_net_bps'],x['metrics']['trades']),reverse=True);nom=elig[0] if elig else None;cands.append({'passport_id':p['passport_id'],'configs_tested':len(arr),'development_status':'NOMINATED_FOR_VALIDATION' if nom else 'REJECTED_IN_DEVELOPMENT','nomination':nom,'all_development_results':arr})
  nv=int(len(sessions)*fr['split_contract']['validation_fraction']);res.update({'status':'DEVELOPMENT_SCREEN_COMPLETE','generation_id':gid,'dataset_sha256':sha256(ds),'generation_sha256':sha256(fp),'sessions_total':len(sessions),'development_sessions':nd,'validation_sessions_reserved':nv,'holdout_sessions_reserved':len(sessions)-nd-nv,'candidates':cands,'nominated_count':sum(x['development_status']=='NOMINATED_FOR_VALIDATION' for x in cands),'parameters_tuned':False})
 except Exception as e:res['error']=f'{type(e).__name__}:{e}'
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='DEVELOPMENT_SCREEN_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
