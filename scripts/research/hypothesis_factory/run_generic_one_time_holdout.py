#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,random,sys
from pathlib import Path
from statistics import mean

def sha256(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load_module(path,name):
 spec=importlib.util.spec_from_file_location(name,path)
 if spec is None or spec.loader is None:raise RuntimeError('module_spec_failed')
 m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def authority(x,label):
 if x.get('runtime_authority')!='NONE' or x.get('broker_actions_permitted') is not False or x.get('edge_claimed') is True:raise ValueError(label+':authority_violation')
def f(r,k):
 try:return float(r[k])
 except:return float('nan')
def trade_returns(mod,rows,idx,pid,cfg,cost):
 rets=[];i=min(idx) if idx else 0;end=max(idx) if idx else -1
 while i<=end:
  if i not in idx:i+=1;continue
  d=mod.direction(pid,rows,i,cfg)
  if not d:i+=1;continue
  en=i+1;ex=en+cfg['horizon_bars'];sess=rows[i]['session']
  if en not in idx or ex not in idx or rows[en]['session']!=sess or rows[ex]['session']!=sess:i+=1;continue
  p0=f(rows[en],'banknifty_close');p1=f(rows[ex],'banknifty_close')
  if math.isfinite(p0) and math.isfinite(p1) and p0>0:rets.append(d*(p1/p0-1)*10000-float(cost))
  i=ex+1
 return rets
def metrics(xs):
 if not xs:return {'trades':0,'mean_net_bps':None,'win_rate':None,'total_net_bps':None}
 return {'trades':len(xs),'mean_net_bps':mean(xs),'win_rate':sum(x>0 for x in xs)/len(xs),'total_net_bps':sum(xs)}
def signflip_pvalue(xs,iterations,seed):
 if not xs:return None
 obs=mean(xs);rng=random.Random(seed);ge=0
 for _ in range(iterations):
  m=sum(x if rng.random()<0.5 else -x for x in xs)/len(xs)
  if m>=obs:ge+=1
 return (ge+1)/(iterations+1)
def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--freeze',required=True);ap.add_argument('--robustness-output',required=True);ap.add_argument('--development-runner',required=True);ap.add_argument('--campaign-policy',default='research/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1.json');ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--output',required=True);a=ap.parse_args(argv)
 root=Path(a.repo_root).resolve();fp=root/a.freeze;rpout=root/a.robustness_output;runner=root/a.development_runner;pp=root/a.campaign_policy;ds=root/a.dataset;out=root/a.output;res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'holdout_outcomes_accessed':False}
 try:
  fr=json.loads(fp.read_text());rob=json.loads(rpout.read_text());pol=json.loads(pp.read_text());authority(fr,'freeze');authority(rob,'robustness');authority(pol,'policy')
  if rob.get('status')!='ROBUSTNESS_COMPLETE' or rob.get('holdout_outcomes_accessed') is not False:raise ValueError('robustness_state_invalid')
  mod=load_module(runner,'generic_holdout_generation_runner');loader=getattr(mod,'load',None) or getattr(mod,'load_rows',None)
  if loader is None or not hasattr(mod,'direction'):raise ValueError('runner_contract_missing')
  rows=loader(ds);sessions=sorted({r['session'] for r in rows});n80=int(len(sessions)*(fr['split_contract']['development_fraction']+fr['split_contract']['validation_fraction']));hs=set(sessions[n80:]);idx={i for i,r in enumerate(rows) if r['session'] in hs};gate=pol['holdout_gate'];base=float(fr['execution_contract']['base_round_trip_cost_bps']);mt=pol['multiple_testing_policy'];iters=int(mt['signflip_iterations']);cands=[];robmap={c['passport_id']:c for c in rob.get('candidates',[])}
  for pid in rob.get('advanced_passport_ids',[]):
   cfg=robmap[pid]['configuration'];xs=trade_returns(mod,rows,idx,pid,cfg,base);m=metrics(xs);reasons=[]
   if m['trades']<gate['minimum_trades']:reasons.append('INSUFFICIENT_HOLDOUT_TRADES')
   if gate['require_positive_mean_net_bps'] and (m['mean_net_bps'] is None or m['mean_net_bps']<=0):reasons.append('NONPOSITIVE_HOLDOUT_MEAN')
   if gate['require_positive_total_net_bps'] and (m['total_net_bps'] is None or m['total_net_bps']<=0):reasons.append('NONPOSITIVE_HOLDOUT_TOTAL')
   seed=int(hashlib.sha256((fr['generation_id']+'|'+pid).encode()).hexdigest()[:16],16);p=signflip_pvalue(xs,iters,seed)
   cands.append({'passport_id':pid,'configuration':cfg,'verdict':'HOLDOUT_PASS' if not reasons else 'HOLDOUT_FAIL','reasons':reasons,'metrics':m,'raw_one_sided_signflip_pvalue':p,'signflip_iterations':iters})
  adv=[c['passport_id'] for c in cands if c['verdict']=='HOLDOUT_PASS'];res.update({'status':'HOLDOUT_COMPLETE','generation_id':fr['generation_id'],'dataset_sha256':sha256(ds),'generation_sha256':sha256(fp),'robustness_evidence_sha256':sha256(rpout),'campaign_policy_sha256':sha256(pp),'holdout_sessions':len(hs),'holdout_outcomes_accessed':True,'candidates':cands,'advanced_count':len(adv),'advanced_passport_ids':adv,'verdict':'HOLDOUT_PASS' if adv else 'HOLDOUT_FAIL','next_action':'RUN_CAMPAIGN_MULTIPLE_TESTING_CERTIFICATION' if adv else 'CLOSE_GENERATION_HOLDOUT_FAIL'})
 except Exception as e:res['error']=f'{type(e).__name__}:{e}'
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='HOLDOUT_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
