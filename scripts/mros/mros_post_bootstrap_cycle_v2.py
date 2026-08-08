#!/usr/bin/env python3
"""Acceptance-complete wrapper for the S004-S110 autonomous cycle."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import mros_post_bootstrap_cycle as base
from mros_program_catalog import sprint_spec,sprint_acceptance

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
 data={'schema_version':'mros-controlled-sprint-contract-v1','manual_version':'1.0','manual_sha256':'53350c3f60f2046180726077b0c18fb52222d6826d4d6e10fc746a46ab80cb39','sprint':s.sprint,'milestone':s.milestone,'work_package':s.wp,'phase':s.phase,'objective':s.objective,'product_context':s.product_context,'primary_risk':s.primary_risk,'scope_lock':f'Only work required for {s.wp}; adjacent milestones/WPs are Parking Lot items.','assurance_tier':s.assurance_tier,'criteria':criteria,'runtime_authority':'NONE','m9_status':'NOT_STARTED'}
 (auth/p).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8');base.commit_auth(auth,[p],f'mros({s.sprint}): freeze controlled sprint contract [skip ci]');return p

base.freeze_contract=freeze_contract
cycle=base.cycle

def main():
 p=argparse.ArgumentParser();p.add_argument('--authority-repo',required=True,type=Path);p.add_argument('--queue-repo',required=True,type=Path);p.add_argument('--state-root',required=True,type=Path);a=p.parse_args()
 try:print(json.dumps(cycle(a.authority_repo.resolve(),a.queue_repo.resolve(),a.state_root.resolve()),sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'POST_BOOTSTRAP_CYCLE_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
