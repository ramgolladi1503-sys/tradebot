#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

DEFAULT_LEDGER='research/evidence/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1_LEDGER.jsonl'
DEFAULT_STATE='research/evidence/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1_STATE.json'
DEFAULT_CANON='research/evidence/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1_LEDGER_CANONICAL.jsonl'
DEFAULT_SEAL='research/evidence/strategy_certification/SEALED_RESEARCH_CAMPAIGN_V1_SEAL.json'


def sha256(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def read_jsonl(p:Path):
 out=[]
 for line in p.read_text(encoding='utf-8').splitlines():
  if line.strip():out.append(json.loads(line))
 return out

def event_key(x):
 event=x.get('event');gid=x.get('generation_id')
 if event in {'DEVELOPMENT_COMPLETE','VALIDATION_COMPLETE','ROBUSTNESS_COMPLETE','HOLDOUT_COMPLETE','CERTIFICATION_COMPLETE','GENERATION_CLOSED','BLOCKED'}:
  return (event,gid)
 if event=='CAMPAIGN_STOP':
  return (event,x.get('reason'),x.get('generations_processed'),x.get('total_configs'))
 return ('RAW',json.dumps(x,sort_keys=True,separators=(',',':')))

def main(argv=None):
 ap=argparse.ArgumentParser();ap.add_argument('--repo-root',default='.');ap.add_argument('--ledger',default=DEFAULT_LEDGER);ap.add_argument('--state',default=DEFAULT_STATE);ap.add_argument('--canonical-output',default=DEFAULT_CANON);ap.add_argument('--seal-output',default=DEFAULT_SEAL);a=ap.parse_args(argv)
 root=Path(a.repo_root).resolve();lp=root/a.ledger;sp=root/a.state;cp=root/a.canonical_output;op=root/a.seal_output
 res={'status':'FAIL_CLOSED','runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False}
 try:
  if not lp.exists() or not sp.exists():raise ValueError('campaign_evidence_missing')
  state=json.loads(sp.read_text());
  if state.get('runtime_authority')!='NONE' or state.get('broker_actions_permitted') is not False or state.get('edge_claimed') is True:raise ValueError('state_authority_violation')
  if state.get('status')!='CAMPAIGN_EXHAUSTED_NO_EDGE':raise ValueError('campaign_not_terminal_no_edge')
  events=read_jsonl(lp);seen=set();canon=[];duplicates=[]
  for e in events:
   k=event_key(e)
   if k in seen:duplicates.append(e);continue
   seen.add(k);canon.append(e)
  # Keep exactly the most informative terminal stop: highest generations processed / total configs.
  stops=[e for e in canon if e.get('event')=='CAMPAIGN_STOP']
  nonstops=[e for e in canon if e.get('event')!='CAMPAIGN_STOP']
  if stops:
   terminal=max(stops,key=lambda x:(int(x.get('generations_processed',0) or 0),int(x.get('total_configs',0) or 0)))
   canon=nonstops+[terminal]
  cp.parent.mkdir(parents=True,exist_ok=True);cp.write_text(''.join(json.dumps(e,sort_keys=True)+'\n' for e in canon),encoding='utf-8')
  dev={e['generation_id']:int(e.get('configs_tested',0) or 0) for e in canon if e.get('event')=='DEVELOPMENT_COMPLETE'}
  closed={e['generation_id']:e.get('reason') for e in canon if e.get('event')=='GENERATION_CLOSED'}
  holdout_generations=[e['generation_id'] for e in canon if e.get('event')=='HOLDOUT_COMPLETE']
  seal={
   'schema_version':1,'status':'CAMPAIGN_V1_SEALED_NO_EDGE','campaign_id':state.get('campaign_id'),'runtime_authority':'NONE','broker_actions_permitted':False,'edge_claimed':False,
   'campaign_state_sha256':sha256(sp),'source_ledger_sha256':sha256(lp),'canonical_ledger_sha256':sha256(cp),'source_events':len(events),'canonical_events':len(canon),'duplicate_events_removed':len(events)-len(canon),
   'generations_processed':state.get('generations_processed'),'total_frozen_configurations_tested':state.get('total_frozen_configurations_tested'),'development_configurations_by_generation':dev,'generation_closure_reasons':closed,
   'holdout_generations':holdout_generations,'holdout_outcomes_accessed':bool(holdout_generations),'terminal_reason':state.get('reason'),
   'interpretation':'Campaign V1 is closed as negative evidence. No structural edge was established. Canonicalization removes duplicate orchestration events only; it does not alter generation results or reopen any reserved data.'
  }
  op.write_text(json.dumps(seal,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(seal,indent=2));return 0
 except Exception as e:
  res['error']=f'{type(e).__name__}:{e}';op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(res,indent=2,sort_keys=True)+'\n');print(json.dumps(res,indent=2));return 2
if __name__=='__main__':raise SystemExit(main())
