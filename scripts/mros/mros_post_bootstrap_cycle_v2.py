#!/usr/bin/env python3
"""Acceptance-complete wrapper for the S004-S110 autonomous cycle."""
from __future__ import annotations
import argparse,datetime,json,sys
from pathlib import Path
import mros_post_bootstrap_cycle as base
from mros_program_catalog import sprint_spec,sprint_acceptance


def utc_now()->str:
 return datetime.datetime.now(datetime.timezone.utc).isoformat()


def freeze_contract(auth:Path,n:int)->Path:
 s=sprint_spec(n);p=base.contract_path(s.sprint)
 if (auth/p).is_file():
  data=base.read_json(auth/p)
  expected=[x for x in sprint_acceptance(n)]
  actual=[c.get('requirement') for c in data.get('criteria',[]) if isinstance(c,dict)]
  if actual!=expected:raise base.CycleError(f'FROZEN_CONTRACT_ACCEPTANCE_MISMATCH:{s.sprint}')
  return p
 (auth/p).parent.mkdir(parents=True,exist_ok=True)
 criteria=[{'id':f'{s.sprint}-AC-{i:03d}','requirement':x} for i,x in enumerate(sprint_acceptance(n),1)]
 data={'schema_version':'mros-controlled-sprint-contract-v1','manual_version':'1.0','manual_sha256':'53350c3f60f2046180726077b0c18fb52222d6826d4d6e10fc746a46ab80cb39','sprint':s.sprint,'milestone':s.milestone,'work_package':s.wp,'phase':s.phase,'objective':s.objective,'product_context':s.product_context,'primary_risk':s.primary_risk,'scope_lock':f'Only work required for {s.wp}; adjacent milestones/WPs are Parking Lot items.','assurance_tier':s.assurance_tier,'criteria':criteria,'frozen_at_utc':utc_now(),'runtime_authority':'NONE','m9_status':'NOT_STARTED'}
 (auth/p).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8');base.commit_auth(auth,[p],f'mros({s.sprint}): freeze controlled sprint contract [skip ci]');return p


_original_finalize=base.finalize

def finalize(auth:Path,n:int,cand:str,rr:str,review:dict,ar:str,audit:dict,native_ref:str):
 s=sprint_spec(n);contract=base.read_json(auth/base.contract_path(s.sprint));started=contract.get('frozen_at_utc');accepted=utc_now()
 result=_original_finalize(auth,n,cand,rr,review,ar,audit,native_ref)
 elapsed=None
 if isinstance(started,str):
  try:elapsed=max(0.0,(datetime.datetime.fromisoformat(accepted)-datetime.datetime.fromisoformat(started)).total_seconds())
  except Exception:elapsed=None
 threshold=3600 if s.assurance_tier=='FULL' else 1800
 speed=base.evidence_dir(s.sprint)/f'{s.sprint}_AUTONOMOUS_SPEED_EVIDENCE.json'
 data={'schema_version':'mros-autonomous-sprint-speed-v1','sprint':s.sprint,'milestone':s.milestone,'work_package':s.wp,'assurance_tier':s.assurance_tier,'candidate_head':cand,'contract_frozen_at_utc':started,'accepted_at_utc':accepted,'elapsed_seconds':elapsed,'fast_enough_threshold_seconds':threshold,'fast_enough':bool(elapsed is not None and elapsed<=threshold),'controller_path':'AUTONOMOUS_IMPLEMENT_VALIDATE_REVIEW_AUDIT_ACCEPT_ADVANCE','review_round':rr,'review_decision':review.get('decision'),'audit_round':ar,'audit_decision':audit.get('decision'),'repair_generations':base.repair_generation(auth,s.sprint),'manual_intervention_required':False,'runtime_authority':'NONE','m9_status':'NOT_STARTED'}
 (auth/speed).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8');sha=base.commit_auth(auth,[speed],f'mros({s.sprint}): seal autonomous sprint speed evidence [skip ci]');result['speed_evidence']=speed.as_posix();result['speed_evidence_commit']=sha;result['elapsed_seconds']=elapsed;result['fast_enough']=data['fast_enough'];return result


base.freeze_contract=freeze_contract
base.finalize=finalize
cycle=base.cycle


def main():
 p=argparse.ArgumentParser();p.add_argument('--authority-repo',required=True,type=Path);p.add_argument('--queue-repo',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path);a=p.parse_args()
 try:print(json.dumps(cycle(a.authority_repo.resolve(),a.queue_repo.resolve(),a.state_root.resolve()),sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'POST_BOOTSTRAP_CYCLE_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
