#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,subprocess
from pathlib import Path
AUTH='research/mros-program-v1';QUEUE='automation/mros-agent-queue-v1';STATE='research/program/MROS_PROGRAM_STATE.yaml';ROOT=Path('research/evidence/sprints/S003/agent_queue');MANIFEST=ROOT/'manifests/S003_R003_REVIEW_POPULATION.json'
ROLES={'R01':('contract_compliance','Attack frozen requirements, strict schemas, invariants, evidence binding, and acceptance criteria.'),'R02':('negative_control','Attack malformed inputs, zero/boolean counts, wrong sprint/round, stale refs, denominator gaps, and fail-open transitions.'),'R03':('adversarial_red_team','Independently search for any remaining material fail-open path, fabricated-evidence path, authority bypass, or regression missed by R01/R02.')}
class E(RuntimeError):pass
def git(r,*a,check=True):
 p=subprocess.run(['git',*a],cwd=r,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
 if check and p.returncode!=0:raise E(f"GIT_FAILED:{' '.join(a)}:{(p.stderr or p.stdout).strip()}")
 return p.stdout.strip()
def candidate(s):
 m=re.search(r'(?m)^\s*bootstrap_repaired_candidate:\s*["\']?([0-9a-f]{40})',s)
 if not m:raise E('REPAIRED_CANDIDATE_MISSING')
 return m.group(1)
def exists(r,p):return subprocess.run(['git','cat-file','-e',f'origin/{QUEUE}:{p}'],cwd=r,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--authority-repo',required=True,type=Path);ap.add_argument('--queue-repo',required=True,type=Path);n=ap.parse_args();a=n.authority_repo.resolve();q=n.queue_repo.resolve();git(a,'fetch','origin',AUTH,QUEUE);git(q,'fetch','origin',QUEUE,AUTH)
 s=git(a,'show',f'origin/{AUTH}:{STATE}')
 if 'active_sprint_status: BOARD_BOOTSTRAP_R003_REVIEW_PREPARATION' not in s:return 3
 h=candidate(s)
 if git(q,'rev-parse','--abbrev-ref','HEAD')!='mros-agent-queue-worker':raise E('WRONG_QUEUE_WORKTREE_BRANCH')
 if git(q,'status','--porcelain'):raise E('QUEUE_WORKTREE_NOT_CLEAN')
 git(q,'rebase',f'origin/{QUEUE}')
 if exists(q,MANIFEST.as_posix()):return 3
 members=[];files=[]
 for rid,(role,obj) in ROLES.items():
  packet=(ROOT/f'packets/S003_R003_{rid}.md').as_posix();out=(ROOT/f'results/S003_R003_{rid}.json').as_posix();receipt=(ROOT/f'receipts/S003_R003_{rid}.json').as_posix();reqp=(ROOT/f'requests/S003_R003_{rid}.json').as_posix()
  members.append({'execution_role_id':rid,'semantic_role':role,'packet_path':packet,'output_path':out,'receipt_path':receipt})
  pt=f'''# MROS S003 Bootstrap Review R003 — {rid}\n\nCandidate head: `{h}`\nRound: `R003`\nSemantic role: `{role}`\nObjective: {obj}\n\nReview the exact candidate independently. Do not modify candidate files and do not read peer conclusions. Return ONLY one JSON object conforming to `research/review_board/REVIEW_SCHEMA.json`. Bind sprint=S003, round=R003, candidate_head={h}, role={role}, execution_role_id={rid}, transport=mac_git_mailbox, packet_path={packet}, output_path={out}, runtime_authority=NONE, broker_actions=NONE, independence booleans=true, and execution_job_id=MROS_JOB_ID. Any CRITICAL/MAJOR/UNKNOWN blocks; do not majority-vote it away.\n'''
  req={'schema_version':1,'request_id':f'S003-R003-{rid}-{h[:8]}','created_by':'mros-autonomous-supervisor','created_at':'2026-08-08','job_type':'reviewer','role_id':rid,'candidate_sha':h,'packet_path':packet,'output_path':out,'backend':'codex'}
  for p,t in ((packet,pt),(reqp,json.dumps(req,sort_keys=True,indent=2)+'\n')):
   x=q/p;x.parent.mkdir(parents=True,exist_ok=True);x.write_text(t,encoding='utf-8');files.append(p)
 m={'schema_version':'mros-agent-population-v1','job_type':'reviewer','candidate_head':h,'sprint':'S003','round':'R003','frozen_before_execution':True,'expected_count':3,'members':members,'created_by':'mros-autonomous-supervisor','runtime_authority':'NONE'};mp=q/MANIFEST;mp.parent.mkdir(parents=True,exist_ok=True);mp.write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');files.append(MANIFEST.as_posix())
 git(q,'add','--',*files);git(q,'commit','-m',f'mros(S003): freeze adaptive R003 reviewer quorum {h[:8]} [skip ci]');git(q,'fetch','origin',QUEUE);git(q,'rebase',f'origin/{QUEUE}');git(q,'push','origin',f'HEAD:{QUEUE}');print(json.dumps({'status':'R003_REVIEW_POPULATION_QUEUED','candidate':h,'reviewers':3},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
