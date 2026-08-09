#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math
from pathlib import Path

def authority(x,label):
 if x.get('runtime_authority')!='NONE' or x.get('broker_actions_permitted') is not False:raise ValueError(label+':authority_violation')
def ledger_config_count(path):
 total=0
 if not path.exists():return 0
 for line in path.read_text(encoding='utf-8').splitlines():
  if not line.strip():continue
  x=json.loads(line)
  if x.get('event')=='DEVELOPMENT_COMPLETE':total+=int(x.get('configs_tested',0) or 0)
 return total
def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--holdout-output',required=True);ap.add_argument('--campaign-policy',default='research/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1.json');ap.add_argument('--ledger',default='research/evidence/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1_LEDGER.jsonl');ap.add_argument('--output',required=True);a=ap.parse_args(argv)
 root=Path(a.repo_root).resolve();hp=root/a.holdout_output;pp=root/a.campaign_policy;lp=root/a.ledger;out=root/a.output;res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False}
 try:
  h=json.loads(hp.read_text());p=json.loads(pp.read_text());authority(h,'holdout');authority(p,'policy')
  if h.get('status')!='HOLDOUT_COMPLETE' or h.get('holdout_outcomes_accessed') is not True:raise ValueError('holdout_state_invalid')
  mt=p['multiple_testing_policy'];alpha=float(mt['familywise_alpha']);tests=max(1,ledger_config_count(lp));cands=[]
  for c in h.get('candidates',[]):
   if c.get('verdict')!='HOLDOUT_PASS':continue
   raw=c.get('raw_one_sided_signflip_pvalue');corr=min(1.0,float(raw)*tests) if raw is not None else None;ok=corr is not None and corr<=alpha
   cands.append({'passport_id':c['passport_id'],'configuration':c['configuration'],'holdout_metrics':c['metrics'],'raw_pvalue':raw,'bonferroni_tests':tests,'corrected_pvalue':corr,'familywise_alpha':alpha,'verdict':'STRUCTURAL_EDGE_CANDIDATE_FOUND' if ok else 'MULTIPLE_TESTING_CORRECTION_FAIL'})
  adv=[c for c in cands if c['verdict']=='STRUCTURAL_EDGE_CANDIDATE_FOUND'];res.update({'status':'CERTIFICATION_COMPLETE','holdout_evidence':str(a.holdout_output),'campaign_configurations_counted':tests,'candidates':cands,'verdict':'STRUCTURAL_EDGE_CANDIDATE_FOUND' if adv else 'REJECTED','edge_claimed':False,'interpretation':'A passing result is a research structural-edge candidate under this campaign policy, not runtime authority or broker authorization.'})
 except Exception as e:res['error']=f'{type(e).__name__}:{e}'
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 0 if res['status']=='CERTIFICATION_COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
