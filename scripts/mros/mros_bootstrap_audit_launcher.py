#!/usr/bin/env python3
"""Freeze and enqueue S003 bootstrap A001 auditor population after R002 review PASS."""
from __future__ import annotations
import argparse,json,re,subprocess
from pathlib import Path
AUTH='research/mros-program-v1';QUEUE='automation/mros-agent-queue-v1'
STATE='research/program/MROS_PROGRAM_STATE.yaml';ROOT=Path('research/evidence/sprints/S003/agent_queue')
MANIFEST=ROOT/'manifests/S003_A001_AUDIT_POPULATION.json'
ROLES={
'A01':('evidence_chain','Trace every acceptance claim to exact artifacts, commands, native evidence, and candidate SHA.'),
'A02':('review_independence','Verify reviewers were genuinely independent from implementation and did not repair candidate code.'),
'A03':('acceptance_criteria','Verify every mandatory acceptance criterion is individually evidenced rather than inferred from prose.'),
'A04':('regression','Verify the sprint did not break earlier accepted contracts, invariants, or evidence obligations.'),
'A05':('program_state','Verify ledgers, program state, accepted heads, Git history, and evidence manifests agree.'),
'A06':('scope_no_drift','Verify no out-of-scope S003/M2/M9/runtime/strategy/broker/risk work was introduced.'),
'A07':('scientific_integrity','Verify Unknown, Rejected, negative results, failed reviews, and dissent remain preserved honestly.'),
'A08':('reproducibility','Verify material results can be reproduced from recorded inputs, versions, commands, and exact head.'),
'A09':('authority','Verify authority grades and acceptance language do not exceed supporting evidence.'),
'A10':('adversarial_acceptance','Attempt to prove the proposed sprint acceptance decision itself is invalid.'),
}
class LaunchError(RuntimeError):pass
def git(repo:Path,*args:str,check=True)->str:
 p=subprocess.run(['git',*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
 if check and p.returncode!=0:raise LaunchError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
 return p.stdout.strip()
def ensure_queue(q:Path):
 if git(q,'rev-parse','--abbrev-ref','HEAD')!='mros-agent-queue-worker':raise LaunchError('WRONG_QUEUE_WORKTREE_BRANCH')
 if git(q,'status','--porcelain'):raise LaunchError('QUEUE_WORKTREE_NOT_CLEAN')
def exists_remote(q:Path,path:str)->bool:return subprocess.run(['git','cat-file','-e',f'origin/{QUEUE}:{path}'],cwd=q,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--authority-repo',required=True,type=Path);ap.add_argument('--queue-repo',required=True,type=Path);ns=ap.parse_args();auth=ns.authority_repo.resolve();q=ns.queue_repo.resolve()
 git(auth,'fetch','origin',AUTH,QUEUE);git(q,'fetch','origin',QUEUE,AUTH);state=git(auth,'show',f'origin/{AUTH}:{STATE}')
 if 'active_sprint_status: BOARD_BOOTSTRAP_R002_REVIEW_PASS_A001_AUDIT_PREPARATION' not in state:return 3
 m=re.search(r'(?m)^\s*bootstrap_repaired_candidate:\s*["\']?([0-9a-f]{40})',state)
 if not m:raise LaunchError('CANDIDATE_MISSING');head=m.group(1)
 review_aggregate='research/evidence/sprints/S003/S003_BOARD_BOOTSTRAP_R002_REVIEW_AGGREGATE.json';acceptance='research/evidence/sprints/S003/S003_ACCEPTANCE_CONTRACT.json';native='research/evidence/sprints/S003/S003_BOARD_CALIBRATION_NATIVE_EVIDENCE_SUPERVISOR.md'
 ensure_queue(q);git(q,'rebase',f'origin/{QUEUE}')
 if exists_remote(q,MANIFEST.as_posix()):return 3
 members=[];files=[]
 for rid,(semantic,obj) in ROLES.items():
  packet=(ROOT/f'packets/S003_A001_{rid}.md').as_posix();output=(ROOT/f'results/S003_A001_{rid}.json').as_posix();receipt=(ROOT/f'receipts/S003_A001_{rid}.json').as_posix();request=(ROOT/f'requests/S003_A001_{rid}.json').as_posix()
  members.append({'execution_role_id':rid,'semantic_role':semantic,'packet_path':packet,'output_path':output,'receipt_path':receipt})
  packet_text=f'''# MROS S003 Bootstrap Audit A001 — {rid}\n\nCandidate head: `{head}`\nRound: `A001`\nAudited review round: `R002`\nSemantic role: `{semantic}`\nObjective: {obj}\n\nAudit the exact candidate and the completed R002 review evidence independently. You may read the R002 aggregate and individual review artifacts because this is an auditor role. Do not modify candidate files. Return ONLY one JSON object conforming to `research/review_board/AUDIT_SCHEMA.json`. Bind `sprint=S003`, `round=A001`, `candidate_head={head}`, `role={semantic}`, `execution_role_id={rid}`, `transport=mac_git_mailbox`, `packet_path={packet}`, `output_path={output}`, `runtime_authority=NONE`, `broker_actions=NONE`, independence booleans true, `audited_review_round=R002`, and include the exact native-validation evidence reference and audited acceptance criteria. `execution_job_id` must equal MROS_JOB_ID. UNKNOWN is legal and blocking. Review aggregate: `{review_aggregate}`. Acceptance contract: `{acceptance}`. Native/calibration evidence: `{native}`.\n'''
  req={'schema_version':1,'request_id':f'S003-A001-{rid}-{head[:8]}','created_by':'mros-autonomous-supervisor','created_at':'2026-08-08','job_type':'auditor','role_id':rid,'candidate_sha':head,'packet_path':packet,'output_path':output,'backend':'codex'}
  for path,text in ((packet,packet_text),(request,json.dumps(req,sort_keys=True,indent=2)+'\n')):
   p=q/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8');files.append(path)
 manifest={'schema_version':'mros-agent-population-v1','job_type':'auditor','candidate_head':head,'sprint':'S003','round':'A001','frozen_before_execution':True,'expected_count':len(members),'members':members,'created_by':'mros-autonomous-supervisor','audited_review_round':'R002','review_aggregate_ref':review_aggregate,'acceptance_contract_ref':acceptance,'native_evidence_ref':native,'runtime_authority':'NONE'}
 mp=q/MANIFEST;mp.parent.mkdir(parents=True,exist_ok=True);mp.write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8');files.append(MANIFEST.as_posix())
 git(q,'add','--',*files);staged=set(git(q,'diff','--cached','--name-only').splitlines())
 if staged!=set(files):git(q,'reset');raise LaunchError('QUEUE_COMMIT_SCOPE_VIOLATION')
 git(q,'commit','-m',f'mros(S003): freeze and queue A001 auditor population {head[:8]} [skip ci]');git(q,'fetch','origin',QUEUE);git(q,'rebase',f'origin/{QUEUE}');git(q,'push','origin',f'HEAD:{QUEUE}')
 print(json.dumps({'status':'A001_AUDIT_POPULATION_QUEUED','candidate':head,'auditors':len(members),'queue_head':git(q,'rev-parse','HEAD')},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
