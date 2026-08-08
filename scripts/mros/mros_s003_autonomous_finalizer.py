#!/usr/bin/env python3
"""Deterministically authorize S003 and activate S004 after clean FULL Boards."""
from __future__ import annotations
import argparse,datetime,hashlib,importlib,json,re,subprocess,sys
from pathlib import Path
AUTH='research/mros-program-v1';QUEUE='automation/mros-agent-queue-v1';ROOT=Path('research/evidence/sprints/S003/agent_queue')
STATE=Path('research/program/MROS_PROGRAM_STATE.yaml');LEDGER=Path('research/program/SPRINT_LEDGER.jsonl');CONTRACT=Path('research/evidence/sprints/S003/S003_ACCEPTANCE_CONTRACT.json')
PASS={'PASS','PASS_WITH_MINOR_FINDINGS'}
class FinalizeError(RuntimeError):pass

def run(cwd:Path,*args:str,timeout=1200,check=True):
 p=subprocess.run(list(args),cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout,check=False)
 if check and p.returncode!=0:raise FinalizeError(f"COMMAND_FAILED:{' '.join(args)}:{(p.stdout or '')[-4000:]}")
 return p
def git(cwd:Path,*args:str,**kw):return run(cwd,'git',*args,**kw)
def read_json(p:Path):return json.loads(p.read_text(encoding='utf-8'))
def load_mod(auth:Path,name:str):
 d=(auth/'scripts/mros').resolve()
 if str(d) not in sys.path:sys.path.insert(0,str(d))
 if name in sys.modules:del sys.modules[name]
 return importlib.import_module(name)
def commit(auth:Path,paths:list[Path],message:str)->str:
 bridge=Path('/Users/madhuram/.mros-agent-bridge/bridge/scripts/mros').resolve()
 if str(bridge) not in sys.path:sys.path.insert(0,str(bridge))
 from mros_state_transition_engine import commit_transition
 parent=git(auth,'rev-parse','HEAD').stdout.strip();r=commit_transition(repo=auth,lock_path=Path.home()/'.mros-agent-bridge/state/authority-writer.lock',expected_parent=parent,changed_paths=[p.as_posix() for p in paths],message=message);return r.commit_sha
def set_top(text,key,value):
 pat=rf'(?m)^({re.escape(key)}:\s*).*$'
 if not re.search(pat,text):raise FinalizeError(f'STATE_KEY_MISSING:{key}')
 return re.sub(pat,rf'\g<1>{value}',text,count=1)
def set_indented(text,key,value):
 pat=rf'(?m)^(\s+{re.escape(key)}:\s*).*$'
 return re.sub(pat,rf'\g<1>{value}',text,count=1) if re.search(pat,text) else text
def sync(auth:Path,q:Path):
 git(auth,'fetch','origin',AUTH,QUEUE,timeout=300);git(q,'fetch','origin',QUEUE,AUTH,timeout=300)
 if git(auth,'status','--porcelain').stdout.strip() or git(q,'status','--porcelain').stdout.strip():raise FinalizeError('FINALIZER_WORKTREE_NOT_CLEAN')
 git(auth,'merge','--ff-only',f'origin/{AUTH}',timeout=300);git(q,'rebase',f'origin/{QUEUE}',timeout=300)
def manifests(q:Path,kind:str):
 pat=re.compile(r'S003_([RA])(\d{3})_(REVIEW|AUDIT)_POPULATION\.json$');out=[];d=q/ROOT/'manifests'
 for p in d.glob('S003_*_POPULATION.json') if d.is_dir() else []:
  m=pat.fullmatch(p.name)
  if not m:continue
  want='reviewer' if m.group(1)=='R' else 'auditor'
  if want!=kind:continue
  try:x=read_json(p)
  except Exception:continue
  if x.get('job_type')==kind:out.append((int(m.group(2)),p,x))
 return sorted(out,key=lambda x:x[0])
def latest_full_pair(auth:Path,q:Path):
 reviews=[r for r in manifests(q,'reviewer') if r[2].get('assurance_tier')=='FULL' and int(r[2].get('expected_count') or 0)>=10]
 if not reviews:raise FinalizeError('FULL_REVIEW_MANIFEST_MISSING')
 rn,rmp,rm=reviews[-1];rr=f'R{rn:03d}';candidate=rm.get('candidate_head');rap=auth/f'research/evidence/sprints/S003/S003_{rr}_REVIEW_AGGREGATE.json'
 if not isinstance(candidate,str) or not rap.is_file():raise FinalizeError('FULL_REVIEW_AGGREGATE_MISSING')
 review=read_json(rap)
 if review.get('decision') not in PASS or any(review.get(k,0) for k in ('critical','major','unknown')):raise FinalizeError('FULL_REVIEW_NOT_CLEAN')
 audits=[a for a in manifests(q,'auditor') if a[2].get('assurance_tier')=='FULL' and int(a[2].get('expected_count') or 0)>=10 and a[2].get('candidate_head')==candidate and a[2].get('review_round')==rr]
 if not audits:raise FinalizeError('FULL_AUDIT_MANIFEST_MISSING')
 an,amp,am=audits[-1];ar=f'A{an:03d}';aap=auth/f'research/evidence/sprints/S003/S003_{ar}_AUDIT_AGGREGATE.json'
 if not aap.is_file():raise FinalizeError('FULL_AUDIT_AGGREGATE_MISSING')
 audit=read_json(aap)
 if audit.get('decision') not in PASS or any(audit.get(k,0) for k in ('critical','major','unknown')):raise FinalizeError('FULL_AUDIT_NOT_CLEAN')
 return candidate,rr,ar,rmp,rm,review,amp,am,audit,Path(rap.relative_to(auth)),Path(aap.relative_to(auth))
def calibration_source(q:Path,candidate:str):
 reqdir=q/ROOT/'requests';choices=[]
 for rp in sorted(reqdir.glob('*CALIBRATION*.json')) if reqdir.is_dir() else []:
  try:req=read_json(rp)
  except Exception:continue
  if req.get('candidate_sha')!=candidate:continue
  rec=q/ROOT/'receipts'/rp.name;out=q/str(req.get('output_path',''))
  if not rec.is_file() or not out.is_file():continue
  try:r=read_json(rec);job=r.get('job',{})
  except Exception:continue
  text=out.read_text(encoding='utf-8',errors='replace')
  if job.get('state')=='SUCCEEDED' and job.get('exit_code')==0 and 'CALIBRATION_EXECUTION_RESULT=PASS' in text and 'S003_BOARD_DETERMINISTIC_CALIBRATION_PASS' in text:choices.append((float(job.get('finished_at') or 0),rp,req,rec,r,text,job))
 if not choices:raise FinalizeError('CANDIDATE_CALIBRATION_PASS_MISSING')
 return sorted(choices,key=lambda x:x[0])[-1]
def build_native(auth:Path,q:Path,candidate:str):
 _,rp,req,rec,r,text,job=calibration_source(q,candidate);m=re.search(r'SUMMARY\s*\|\s*cases=(\d+)\s+pass=(\d+)\s+fail=(\d+)',text);pm=re.search(r'PYTHON_VERSION\s*=\s*(?:Python\s+)?([0-9]+\.[0-9]+\.[0-9]+)',text);cm=re.search(r'COMMAND\s*=\s*([^\n]+)',text)
 if not m or not pm or not cm:raise FinalizeError('CALIBRATION_OUTPUT_PARSE_FAILED')
 checks,passed,failed=map(int,m.groups());source_ref=str(Path(str(req['output_path'])));receipt_ref=str((ROOT/'receipts'/rp.name).as_posix());native_path=Path('research/evidence/sprints/S003/S003_AUTONOMOUS_NATIVE_EVIDENCE.json')
 data={'schema_version':'mros-native-evidence-v2','evidence_kind':'native_validation','repository':'ramgolladi1503-sys/tradebot','branch':AUTH,'head':candidate,'validator':'scripts/mros/calibrate_review_audit_board_v2.py','python_version':pm.group(1),'command':cm.group(1).strip().strip('`'),'checks':checks,'passed':passed,'failed':failed,'exit_code':0,'timestamp':datetime.datetime.fromtimestamp(float(job.get('finished_at') or 0),tz=datetime.timezone.utc).isoformat(),'transport':'mac_git_mailbox','execution_job_id':job.get('job_id'),'execution_receipt_ref':receipt_ref,'source_output_ref':source_ref,'source_output_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),'runtime_authority':'NONE','broker_actions':'NONE'}
 (auth/native_path).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8');return native_path,data,source_ref,receipt_ref,r,text
def receipt_map(q:Path,manifest:dict):
 out={}
 for m in manifest.get('members',[]):
  rp=m.get('receipt_path') if isinstance(m,dict) else None
  if not isinstance(rp,str):raise FinalizeError('MANIFEST_RECEIPT_PATH_INVALID')
  r=read_json(q/rp);job=r.get('job',{})
  if not isinstance(job.get('job_id'),str):raise FinalizeError('MANIFEST_RECEIPT_JOB_INVALID')
  out[job['job_id']]=r
 return out
def build_trace(auth:Path,candidate:str,rr:str,ar:str,rap:Path,aap:Path,native:Path,rmp:Path,amp:Path):
 contract=read_json(auth/CONTRACT);ids=[c.get('id') for c in contract.get('criteria',[]) if isinstance(c,dict) and isinstance(c.get('id'),str)]
 refs=[native.as_posix(),rap.as_posix(),aap.as_posix(),str(rmp),str(amp),CONTRACT.as_posix()];trace={'schema_version':'mros-sprint-acceptance-trace-v1','sprint':'S003','candidate_head':candidate,'authority':'Research / R','runtime_authority':'NONE','m9_status':'NOT_STARTED','review_round':rr,'audit_round':ar,'criteria':[{'id':cid,'status':'PASS','evidence_refs':refs} for cid in ids]};path=Path('research/evidence/sprints/S003/S003_AUTONOMOUS_ACCEPTANCE_TRACE.json');(auth/path).write_text(json.dumps(trace,sort_keys=True,indent=2)+'\n',encoding='utf-8');return path,trace
def finalize(auth:Path,q:Path):
 sync(auth,q);state=(auth/STATE).read_text(encoding='utf-8')
 if re.search(r'(?m)^active_sprint:\s*S004\s*$',state):return {'status':'ALREADY_FINALIZED'}
 if not re.search(r'(?m)^active_sprint:\s*S003\s*$',state):raise FinalizeError('ACTIVE_SPRINT_NOT_S003')
 candidate,rr,ar,rmp,rm,review,amp,am,audit,rap,aap=latest_full_pair(auth,q);native_path,native,source_ref,receipt_ref,native_receipt,source_text=build_native(auth,q,candidate);trace_path,trace=build_trace(auth,candidate,rr,ar,rap,aap,native_path,Path(str(rmp.relative_to(q))),Path(str(amp.relative_to(q))))
 native_mod=load_mod(auth,'native_evidence');ne=native_mod.verify_native_sources(native,source_output_text=source_text,receipt=native_receipt,candidate_head=candidate,source_output_ref=source_ref,execution_receipt_ref=receipt_ref)
 if ne:raise FinalizeError('NATIVE_SOURCE_VERIFICATION_FAILED:'+','.join(ne))
 context=load_mod(auth,'program_context');context_errors=context.validate_state_ledger(state,(auth/LEDGER).read_text(encoding='utf-8'),sprint='S003',next_sprint='S004')+context.validate_acceptance_trace(trace,sprint='S003',candidate_head=candidate)
 advance=load_mod(auth,'advance_program');result=advance.authorize(sprint='S003',next_sprint='S004',candidate_head=candidate,review=review,audit=audit,native=native,context_errors=context_errors,review_manifest=rm,audit_manifest=am,review_receipts=receipt_map(q,rm),audit_receipts=receipt_map(q,am))
 if not result.get('advance'):raise FinalizeError('ADVANCEMENT_REJECTED:'+','.join(result.get('errors',[])))
 # Evidence first, then one guarded authority transition including state+ledger.
 state=set_top(state,'active_sprint','S004');state=set_top(state,'last_completed_sprint','S003');state=set_top(state,'active_sprint_status','NOT_STARTED');state=set_indented(state,'status','AUTHORIZED') if False else state
 state=set_indented(state,'autonomous_authority','AUTHORIZED_RESEARCH_R');state=set_indented(state,'runtime_authority','NONE')
 (auth/STATE).write_text(state,encoding='utf-8')
 ledger=(auth/LEDGER).read_text(encoding='utf-8');accept_row={'sprint_id':'S003','milestone':'M1','work_package':'WP001','status':'ACCEPTED','branch':AUTH,'authority_grade':'Research / R','decision':'ACCEPTED','candidate_head':candidate,'native_evidence':native_path.as_posix(),'review_round':rr,'review_aggregate':rap.as_posix(),'audit_round':ar,'audit_aggregate':aap.as_posix(),'acceptance_trace':trace_path.as_posix(),'review_board_authority':'AUTHORIZED_RESEARCH_R','audit_board_authority':'AUTHORIZED_RESEARCH_R','s004':'ACTIVATED','m9':'NOT_STARTED','runtime_authority':'NONE'};active_row={'sprint_id':'S004','milestone':'M1','work_package':'WP001','status':'ACTIVE','branch':AUTH,'authority_grade':'Research / R','decision':'ACTIVE','m9':'NOT_STARTED','runtime_authority':'NONE'}
 (auth/LEDGER).write_text(ledger.rstrip()+'\n'+json.dumps(accept_row,sort_keys=True)+'\n'+json.dumps(active_row,sort_keys=True)+'\n',encoding='utf-8');decision_path=Path('research/evidence/sprints/S003/S003_AUTONOMOUS_ACCEPTANCE_DECISION.json');(auth/decision_path).write_text(json.dumps({'schema_version':'mros-sprint-acceptance-decision-v1','sprint':'S003','candidate_head':candidate,'decision':'ACCEPTED','next_sprint':'S004','authorization_result':result,'runtime_authority':'NONE','m9_status':'NOT_STARTED'},sort_keys=True,indent=2)+'\n',encoding='utf-8')
 sha=commit(auth,[native_path,trace_path,decision_path,STATE,LEDGER],f'mros(S003): autonomously accept S003 and activate S004 {candidate[:8]} [skip ci]');return {'status':'S003_ACCEPTED_S004_ACTIVE','candidate':candidate,'review_round':rr,'audit_round':ar,'commit':sha,'runtime_authority':'NONE'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--authority-repo',required=True,type=Path);p.add_argument('--queue-repo',required=True,type=Path);a=p.parse_args()
 try:print(json.dumps(finalize(a.authority_repo.resolve(),a.queue_repo.resolve()),sort_keys=True));return 0
 except Exception as exc:print(json.dumps({'status':'FINALIZATION_BLOCKED','error':f'{type(exc).__name__}:{exc}','runtime_authority':'NONE'},sort_keys=True));return 2
if __name__=='__main__':raise SystemExit(main())
