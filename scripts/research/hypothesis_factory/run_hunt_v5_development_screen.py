#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,itertools,json,math
from pathlib import Path
from statistics import mean
EXPECTED_DATASET_SHA='66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32';EXPECTED_GENERATION='HUNT_V5_GENERATION_FREEZE'
def sha256(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def f(r,k):
 try:return float(r[k])
 except:return float('nan')
def sgn(x):return 1 if x>0 else -1 if x<0 else 0
def load(p):
 with open(p,newline='',encoding='utf-8') as h:rows=list(csv.DictReader(h))
 req={'timestamp','session','banknifty_close','banknifty_ret_1_bps','banknifty_from_open_bps','nifty_from_open_bps','sensex_from_open_bps'}
 if not rows or not req.issubset(rows[0]):raise ValueError('dataset_schema_mismatch')
 return rows
def grid(g,hs):
 ks=sorted(g)
 for vals in itertools.product(*(g[k] for k in ks)):
  b=dict(zip(ks,vals))
  for h in hs:yield {**b,'horizon_bars':int(h)}
def bar_index(rows,i):
 sess=rows[i]['session'];j=i
 while j>0 and rows[j-1]['session']==sess:j-=1
 return i-j
def direction(pid,rows,i,c):
 r=rows[i];br=f(r,'banknifty_ret_1_bps');bfo=f(r,'banknifty_from_open_bps');nfo=f(r,'nifty_from_open_bps');sfo=f(r,'sensex_from_open_bps')
 if not all(math.isfinite(x) for x in (br,bfo,nfo,sfo)):return 0
 if pid=='HUNT_V5_OPENING_DRIFT_PERSISTENCE':
  if bar_index(rows,i)>c['max_bar_index'] or abs(bfo)<c['open_bps'] or sgn(bfo)==0:return 0
  return sgn(bfo) if sgn(br)==sgn(bfo) else 0
 if pid=='HUNT_V5_OPENING_DRIFT_FADE':
  if bar_index(rows,i)>c['max_bar_index'] or abs(bfo)<c['open_bps'] or sgn(bfo)==0:return 0
  return sgn(br) if sgn(br)==-sgn(bfo) and sgn(br)!=0 else 0
 if pid=='HUNT_V5_LEADER_OPEN_CONSENSUS':
  if sgn(nfo)==0 or sgn(nfo)!=sgn(sfo) or min(abs(nfo),abs(sfo))<c['leader_open_bps']:return 0
  return sgn(nfo) if sgn(br)==sgn(nfo) else 0
 if pid=='HUNT_V5_BANKNIFTY_OPEN_DISLOCATION_FADE':
  if sgn(nfo)==0 or sgn(nfo)!=sgn(sfo) or sgn(bfo)!=-sgn(nfo) or abs(bfo)<c['dislocation_bps']:return 0
  return sgn(nfo)
 raise ValueError('unknown_passport:'+pid)
def evaluate(rows,idx,pid,c,cost):
 rets=[];i=min(idx) if idx else 0;end=max(idx) if idx else -1
 while i<=end:
  if i not in idx:i+=1;continue
  d=direction(pid,rows,i,c)
  if not d:i+=1;continue
  en=i+1;ex=en+c['horizon_bars'];sess=rows[i]['session']
  if en not in idx or ex not in idx or rows[en]['session']!=sess or rows[ex]['session']!=sess:i+=1;continue
  p0=f(rows[en],'banknifty_close');p1=f(rows[ex],'banknifty_close')
  if not(math.isfinite(p0) and math.isfinite(p1) and p0>0):i+=1;continue
  rets.append(d*(p1/p0-1)*10000-float(cost));i=ex+1
 if not rets:return {'trades':0,'mean_net_bps':None,'win_rate':None,'total_net_bps':None}
 return {'trades':len(rets),'mean_net_bps':mean(rets),'win_rate':sum(x>0 for x in rets)/len(rets),'total_net_bps':sum(rets)}
def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--freeze',default='research/strategy_certification/passports/HUNT_V5_GENERATION_FREEZE.json');ap.add_argument('--output',default='research/evidence/strategy_certification/HUNT_V5_DEVELOPMENT_SCREEN.json');a=ap.parse_args(argv);root=Path(a.repo_root).resolve();ds=root/a.dataset;fp=root/a.freeze;out=root/a.output
 res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'validation_accessed':False,'holdout_accessed':False}
 try:
  fr=json.loads(fp.read_text());
  if fr.get('generation_id')!=EXPECTED_GENERATION:raise ValueError('generation_id_mismatch')
  if fr.get('dataset_sha256')!=EXPECTED_DATASET_SHA or sha256(ds)!=EXPECTED_DATASET_SHA:raise ValueError('dataset_hash_mismatch')
  rows=load(ds);sessions=sorted({r['session'] for r in rows});nd=int(len(sessions)*fr['split_contract']['development_fraction']);dev=set(sessions[:nd]);idx={i for i,r in enumerate(rows) if r['session'] in dev};hs=fr['execution_contract']['development_horizons_bars'];cost=fr['execution_contract']['base_round_trip_cost_bps'];gate=fr['development_gate'];cands=[]
  for p in fr['passports']:
   arr=[{'config':c,'metrics':evaluate(rows,idx,p['passport_id'],c,cost)} for c in grid(p['grid'],hs)];elig=[x for x in arr if x['metrics']['trades']>=gate['minimum_trades'] and x['metrics']['mean_net_bps'] is not None and x['metrics']['mean_net_bps']>0];elig.sort(key=lambda x:(x['metrics']['mean_net_bps'],x['metrics']['trades']),reverse=True);nom=elig[0] if elig else None;cands.append({'passport_id':p['passport_id'],'configs_tested':len(arr),'development_status':'NOMINATED_FOR_VALIDATION' if nom else 'REJECTED_IN_DEVELOPMENT','nomination':nom,'all_development_results':arr})
  nv=int(len(sessions)*fr['split_contract']['validation_fraction']);res.update({'status':'DEVELOPMENT_SCREEN_COMPLETE','dataset_sha256':sha256(ds),'generation_sha256':sha256(fp),'sessions_total':len(sessions),'development_sessions':nd,'validation_sessions_reserved':nv,'holdout_sessions_reserved':len(sessions)-nd-nv,'candidates':cands,'nominated_count':sum(x['development_status']=='NOMINATED_FOR_VALIDATION' for x in cands),'parameters_tuned':False})
 except Exception as e:res['error']=f'{type(e).__name__}:{e}'
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='DEVELOPMENT_SCREEN_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
