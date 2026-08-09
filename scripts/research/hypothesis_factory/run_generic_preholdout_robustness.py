#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,inspect,json,math,sys
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
def groups(rows):
 out={}
 for i,r in enumerate(rows):out.setdefault(r['session'],[]).append(i)
 return out
def trade_returns(mod,rows,idx,pid,cfg,cost,mode='base'):
 rets=[];i=min(idx) if idx else 0;end=max(idx) if idx else -1;gs=groups(rows);sessions=sorted(gs);rot={s:sessions[(j+1)%len(sessions)] for j,s in enumerate(sessions)};local={i:k for s in sessions for k,i in enumerate(gs[s])}
 while i<=end:
  if i not in idx:i+=1;continue
  d=mod.direction(pid,rows,i,cfg)
  if not d:i+=1;continue
  en=i+1;ex=en+cfg['horizon_bars'];sess=rows[i]['session']
  if en not in idx or ex not in idx or rows[en]['session']!=sess or rows[ex]['session']!=sess:i+=1;continue
  if mode=='random_direction':
   h=int(hashlib.sha256(f'{pid}|{i}'.encode()).hexdigest()[:8],16);d=1 if h%2==0 else -1
  if mode=='session_permutation':
   target=rot[sess];le=local[en];lx=local[ex]
   if le>=len(gs[target]) or lx>=len(gs[target]):i=ex+1;continue
   en2=gs[target][le];ex2=gs[target][lx];p0=f(rows[en2],'banknifty_close');p1=f(rows[ex2],'banknifty_close')
  else:p0=f(rows[en],'banknifty_close');p1=f(rows[ex],'banknifty_close')
  if math.isfinite(p0) and math.isfinite(p1) and p0>0:rets.append(d*(p1/p0-1)*10000-float(cost))
  i=ex+1
 return rets
def metrics(xs):
 if not xs:return {'trades':0,'mean_net_bps':None,'win_rate':None,'total_net_bps':None}
 return {'trades':len(xs),'mean_net_bps':mean(xs),'win_rate':sum(x>0 for x in xs)/len(xs),'total_net_bps':sum(xs)}
def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--freeze',required=True);ap.add_argument('--validation-output',required=True);ap.add_argument('--development-runner',required=True);ap.add_argument('--campaign-policy',default='research/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1.json');ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--output',required=True);a=ap.parse_args(argv)
 root=Path(a.repo_root).resolve();fp=root/a.freeze;vp=root/a.validation_output;rp=root/a.development_runner;pp=root/a.campaign_policy;ds=root/a.dataset;out=root/a.output;res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'holdout_outcomes_accessed':False}
 try:
  fr=json.loads(fp.read_text());val=json.loads(vp.read_text());pol=json.loads(pp.read_text());authority(fr,'freeze');authority(val,'validation');authority(pol,'policy')
  if val.get('status')!='VALIDATION_FAMILY_COMPLETE' or val.get('holdout_outcomes_accessed') is not False:raise ValueError('validation_state_invalid')
  mod=load_module(rp,'generic_robustness_generation_runner');loader=getattr(mod,'load',None) or getattr(mod,'load_rows',None)
  if loader is None or not hasattr(mod,'direction'):raise ValueError('runner_contract_missing')
  rows=loader(ds);sessions=sorted({r['session'] for r in rows});n80=int(len(sessions)*(fr['split_contract']['development_fraction']+fr['split_contract']['validation_fraction']));allowed=set(sessions[:n80]);idx={i for i,r in enumerate(rows) if r['session'] in allowed};gate=pol['pre_holdout_robustness_gate'];costs=[float(x) for x in gate['cost_stress_bps']]
  eval_src=inspect.getsource(mod.evaluate);dir_src=inspect.getsource(mod.direction);source_controls={'NO_SAME_BAR_FILL':('en=i+1' in eval_src or 'entry=i+1' in eval_src or 'entry = i + 1' in eval_src),'FUTURE_BAR_SHIFT_MUST_NOT_AUTHORIZE_EDGE':not any(x in dir_src for x in ('rows[i+1]','rows[i + 1]'))}
  candidates=[]
  valmap={c['passport_id']:c for c in val.get('candidates',[])}
  for pid in val.get('advanced_passport_ids',[]):
   cfg=valmap[pid]['configuration'];stress={str(c):metrics(trade_returns(mod,rows,idx,pid,cfg,c,'base')) for c in costs};rnd=metrics(trade_returns(mod,rows,idx,pid,cfg,costs[0],'random_direction'));perm=metrics(trade_returns(mod,rows,idx,pid,cfg,costs[0],'session_permutation'));reasons=[]
   if not all(source_controls.values()):reasons.append('SOURCE_TIMING_CONTROL_FAIL')
   base=stress[str(costs[0])];mx=stress[str(costs[-1])]
   if gate.get('require_positive_mean_at_base_cost') and (base['mean_net_bps'] is None or base['mean_net_bps']<=0):reasons.append('NONPOSITIVE_BASE_ROBUSTNESS_MEAN')
   vals=[stress[str(c)]['mean_net_bps'] for c in costs]
   if gate.get('require_nonpositive_degradation_with_higher_cost') and any(vals[j] is None or vals[j+1] is None or vals[j+1]>vals[j]+1e-12 for j in range(len(vals)-1)):reasons.append('COST_STRESS_NONMONOTONIC')
   if gate.get('require_positive_mean_at_max_stress') and (mx['mean_net_bps'] is None or mx['mean_net_bps']<=0):reasons.append('FAILS_MAX_COST_STRESS')
   if rnd['mean_net_bps'] is not None and rnd['mean_net_bps']>float(gate.get('randomized_direction_null_max_mean_bps',0.0)):reasons.append('RANDOMIZED_DIRECTION_NULL_POSITIVE')
   if perm['mean_net_bps'] is not None and perm['mean_net_bps']>float(gate.get('session_permutation_null_max_mean_bps',0.0)):reasons.append('SESSION_PERMUTATION_NULL_POSITIVE')
   candidates.append({'passport_id':pid,'configuration':cfg,'verdict':'ROBUSTNESS_PASS' if not reasons else 'ROBUSTNESS_FAIL','reasons':reasons,'cost_stress':stress,'randomized_direction_null':rnd,'session_permutation_null':perm,'source_controls':source_controls})
  adv=[c['passport_id'] for c in candidates if c['verdict']=='ROBUSTNESS_PASS'];res.update({'status':'ROBUSTNESS_COMPLETE','generation_id':fr['generation_id'],'dataset_sha256':sha256(ds),'generation_sha256':sha256(fp),'validation_evidence_sha256':sha256(vp),'campaign_policy_sha256':sha256(pp),'candidates':candidates,'advanced_count':len(adv),'advanced_passport_ids':adv,'verdict':'ROBUSTNESS_PASS' if adv else 'ROBUSTNESS_FAIL','next_action':'OPEN_ONE_TIME_HOLDOUT' if adv else 'CLOSE_GENERATION_ROBUSTNESS_FAIL'})
 except Exception as e:res['error']=f'{type(e).__name__}:{e}'
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='ROBUSTNESS_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
