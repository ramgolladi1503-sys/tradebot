#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path

def sha256(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load_module(path,name):
 spec=importlib.util.spec_from_file_location(name,path)
 if spec is None or spec.loader is None:raise RuntimeError('module_spec_failed')
 m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def authority(x,label):
 if x.get('runtime_authority')!='NONE' or x.get('broker_actions_permitted') is not False or x.get('edge_claimed') is True:raise ValueError(label+':authority_violation')
def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--freeze',required=True);ap.add_argument('--development-output',required=True);ap.add_argument('--development-runner',required=True);ap.add_argument('--campaign-policy',default='research/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1.json');ap.add_argument('--dataset',default='research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv');ap.add_argument('--output',required=True);a=ap.parse_args(argv)
 root=Path(a.repo_root).resolve();fp=root/a.freeze;dp=root/a.development_output;rp=root/a.development_runner;pp=root/a.campaign_policy;ds=root/a.dataset;out=root/a.output
 res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,'holdout_outcomes_accessed':False}
 try:
  fr=json.loads(fp.read_text());dev=json.loads(dp.read_text());pol=json.loads(pp.read_text());authority(fr,'freeze');authority(dev,'development');authority(pol,'policy')
  if dev.get('status')!='DEVELOPMENT_SCREEN_COMPLETE':raise ValueError('development_not_complete')
  if dev.get('validation_accessed') is not False or dev.get('holdout_accessed') is not False:raise ValueError('reserved_data_already_accessed')
  if sha256(ds)!=fr.get('dataset_sha256'):raise ValueError('dataset_hash_mismatch')
  mod=load_module(rp,'generic_validation_generation_runner');loader=getattr(mod,'load',None) or getattr(mod,'load_rows',None)
  if loader is None or not hasattr(mod,'evaluate'):raise ValueError('runner_contract_missing')
  rows=loader(ds);sessions=sorted({r['session'] for r in rows});nd=int(len(sessions)*fr['split_contract']['development_fraction']);nv=int(len(sessions)*fr['split_contract']['validation_fraction']);vs=set(sessions[nd:nd+nv]);idx={i for i,r in enumerate(rows) if r['session'] in vs};cost=fr['execution_contract']['base_round_trip_cost_bps'];gate=pol['global_validation_gate'];cands=[]
  noms=[c for c in dev.get('candidates',[]) if c.get('development_status')=='NOMINATED_FOR_VALIDATION' and c.get('nomination')]
  for c in noms:
   pid=c['passport_id'];cfg=c['nomination']['config'];m=mod.evaluate(rows,idx,pid,cfg,cost);reasons=[]
   if m['trades']<gate['minimum_trades']:reasons.append('INSUFFICIENT_VALIDATION_TRADES')
   if gate['require_positive_mean_net_bps'] and (m['mean_net_bps'] is None or m['mean_net_bps']<=0):reasons.append('NONPOSITIVE_VALIDATION_MEAN')
   if gate['require_positive_total_net_bps'] and (m['total_net_bps'] is None or m['total_net_bps']<=0):reasons.append('NONPOSITIVE_VALIDATION_TOTAL')
   cands.append({'passport_id':pid,'configuration':cfg,'verdict':'VALIDATION_PASS' if not reasons else 'VALIDATION_FAIL','reasons':reasons,'metrics':m})
  adv=[x['passport_id'] for x in cands if x['verdict']=='VALIDATION_PASS']
  res.update({'status':'VALIDATION_FAMILY_COMPLETE','generation_id':fr['generation_id'],'dataset_sha256':sha256(ds),'generation_sha256':sha256(fp),'development_evidence_sha256':sha256(dp),'campaign_policy_sha256':sha256(pp),'validation_sessions':nv,'candidates_evaluated':len(cands),'candidates':cands,'advanced_count':len(adv),'advanced_passport_ids':adv,'parameters_tuned':False,'next_action':'RUN_PRE_HOLDOUT_ROBUSTNESS' if adv else 'CLOSE_GENERATION_NO_CANDIDATE_ADVANCED'})
 except Exception as e:res['error']=f'{type(e).__name__}:{e}'
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='VALIDATION_FAMILY_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
