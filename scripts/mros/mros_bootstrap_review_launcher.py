#!/usr/bin/env python3
"""Freeze and enqueue the S003 bootstrap R002 reviewer population.

This launcher is deterministic and idempotent. It only runs after repository
state declares R002 review preparation, and it freezes exactly 10 fresh reviewer
jobs R01-R10 against the repaired exact candidate. It never evaluates reviews.
"""
from __future__ import annotations
import argparse,json,re,subprocess,time
from pathlib import Path
AUTH='research/mros-program-v1';QUEUE='automation/mros-agent-queue-v1'
STATE='research/program/MROS_PROGRAM_STATE.yaml';ROOT=Path('research/evidence/sprints/S003/agent_queue')
MANIFEST=ROOT/'manifests/S003_R002_REVIEW_POPULATION.json'
ROLES={
'R01':('contract_compliance','Attack frozen requirements, interfaces, schemas, invariants, vocabulary, and acceptance criteria.'),
'R02':('negative_control','Attack malformed, missing, ambiguous, invalid-enum, illegal-transition, and unsupported inputs.'),
'R03':('evidence_provenance','Attack missing/stale/mismatched provenance, unsupported completion, and evidence reuse across repaired heads.'),
'R04':('authority_promotion','Attack stage skipping, obsolete authority, caller-controlled gates, illegal terminal-state promotion, and evidence-free promotion.'),
'R05':('causal_time','Attack future information, leakage, future-derived membership, post-event features, and timestamp ambiguity.'),
'R06':('denominator_search_integrity','Attack denominator laundering, outcome-aware exclusion, hidden multiplicity, and search-family redefinition.'),
'R07':('runtime_boundary','Attack attempts to create research authority from runtime, broker, strategy, risk, live execution, or production behavior.'),
'R08':('qa_verification','Attack tautological tests, weak assertions, missing equivalence classes/boundaries, and string-existence-only verification.'),
'R09':('architecture_no_drift','Attack dependency/scope drift, premature later-sprint work, unnecessary architecture, and S003/M2/M9 contamination.'),
'R10':('adversarial_red_team','Assume other reviewers missed the strongest falsifier and attempt to destroy acceptance.'),
}
class LaunchError(RuntimeError): pass
def git(repo:Path,*args:str,check=True)->str:
 p=subprocess.run(['git',*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
 if check and p.returncode!=0: raise LaunchError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
 return p.stdout.strip()
def candidate(state:str)->str:
 m=re.search(r'(?m)^\s*bootstrap_repaired_candidate:\s*["\']?([0-9a-f]{40})',state)
 if not m: raise LaunchError('REPAIRED_CANDIDATE_MISSING')
 return m.group(1)
def ensure_queue_worktree(repo:Path):
 branch=git(repo,'rev-parse','--abbrev-ref','HEAD')
 if branch!='mros-agent-queue-worker': raise LaunchError(f'WRONG_QUEUE_WORKTREE_BRANCH:{branch}')
 if git(repo,'status','--porcelain'): raise LaunchError('QUEUE_WORKTREE_NOT_CLEAN')
def exists_remote(repo:Path,path:str)->bool:
 return subprocess.run(['git','cat-file','-e',f'origin/{QUEUE}:{path}'],cwd=repo,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def main()->int:
 a=argparse.ArgumentParser();a.add_argument('--authority-repo',required=True,type=Path);a.add_argument('--queue-repo',required=True,type=Path);ns=a.parse_args()
 auth=ns.authority_repo.resolve();q=ns.queue_repo.resolve();git(auth,'fetch','origin',AUTH,QUEUE);git(q,'fetch','origin',QUEUE,AUTH)
 state=git(auth,'show',f'origin/{AUTH}:{STATE}')
 if 'active_sprint_status: BOARD_BOOTSTRAP_R002_REVIEW_PREPARATION' not in state and 'bootstrap_independent_review_status: READY_TO_FREEZE_AND_LAUNCH_R002' not in state:return 3
 head=candidate(state); ensure_queue_worktree(q); git(q,'rebase',f'origin/{QUEUE}')
 manifest_path=str(MANIFEST)
 if exists_remote(q,manifest_path): return 3
 members=[];files=[]
 for rid,(semantic,obj) in ROLES.items():
  packet=(ROOT/f'packets/S003_R002_{rid}.md').as_posix();output=(ROOT/f'results/S003_R002_{rid}.json').as_posix();receipt=(ROOT/f'receipts/S003_R002_{rid}.json').as_posix();request=(ROOT/f'requests/S003_R002_{rid}.json').as_posix()
  members.append({'execution_role_id':rid,'semantic_role':semantic,'packet_path':packet,'output_path':output,'receipt_path':receipt})
  packet_text=f'''# MROS S003 Bootstrap Review R002 — {rid}\n\nCandidate head: `{head}`\nRound: `R002`\nSemantic role: `{semantic}`\nObjective: {obj}\n\nIndependently attack the exact candidate at the frozen head. Read repository evidence directly. Do not modify candidate files. Do not read peer review conclusions. Return ONLY one JSON object conforming to `research/review_board/REVIEW_SCHEMA.json`. Bind `sprint=S003`, `round=R002`, `candidate_head={head}`, `role={semantic}`, `execution_role_id={rid}`, `transport=mac_git_mailbox`, `packet_path={packet}`, `output_path={output}`, `runtime_authority=NONE`, `broker_actions=NONE`, and independence booleans true. `execution_job_id` must be the MROS_JOB_ID environment value. Findings must contain evidence and falsifiers. UNKNOWN is legal and blocking when evidence is insufficient.\n'''
  req={'schema_version':1,'request_id':f'S003-R002-{rid}-{head[:8]}','created_by':'mros-autonomous-supervisor','created_at':'2026-08-08','job_type':'reviewer','role_id':rid,'candidate_sha':head,'packet_path':packet,'output_path':output,'backend':'codex'}
  for path,text in ((packet,packet_text),(request,json.dumps(req,sort_keys=True,indent=2)+'\n')):
   p=q/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8');files.append(path)
 manifest={'schema_version':'mros-agent-population-v1','job_type':'reviewer','candidate_head':head,'sprint':'S003','round':'R002','frozen_before_execution':True,'expected_count':len(members),'members':members,'created_by':'mros-autonomous-supervisor','runtime_authority':'NONE'}
 mp=q/MANIFEST;mp.parent.mkdir(parents=True,exist_ok=True);mp.write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8');files.append(manifest_path)
 git(q,'add','--',*files);staged=set(git(q,'diff','--cached','--name-only').splitlines())
 if staged!=set(files): git(q,'reset'); raise LaunchError('QUEUE_COMMIT_SCOPE_VIOLATION')
 git(q,'commit','-m',f'mros(S003): freeze and queue R002 reviewer population {head[:8]} [skip ci]');git(q,'fetch','origin',QUEUE);git(q,'rebase',f'origin/{QUEUE}');git(q,'push','origin',f'HEAD:{QUEUE}')
 print(json.dumps({'status':'R002_REVIEW_POPULATION_QUEUED','candidate':head,'reviewers':len(members),'queue_head':git(q,'rev-parse','HEAD')},sort_keys=True));return 0
if __name__=='__main__': raise SystemExit(main())
