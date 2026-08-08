#!/usr/bin/env python3
"""One deterministic MROS supervisor transition step."""
from __future__ import annotations
import argparse,json,re,subprocess
from pathlib import Path
from mros_state_transition_engine import commit_transition,recover_stranded_transition
AUTH="research/mros-program-v1";QUEUE="automation/mros-agent-queue-v1"
RESULT_ROOT="research/evidence/sprints/S003/agent_queue/results";RECEIPT_ROOT="research/evidence/sprints/S003/agent_queue/receipts"
STATE_PATH="research/program/MROS_PROGRAM_STATE.yaml";EVID_PATH="research/evidence/sprints/S003/S003_BOARD_CALIBRATION_NATIVE_EVIDENCE_SUPERVISOR.md"
TRANSITION_MESSAGE="mros(S003): supervisor consume repaired Board calibration pass [skip ci]"
class StepError(RuntimeError):pass
def git(repo:Path,*args:str,check:bool=True)->str:
 p=subprocess.run(["git",*args],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False)
 if check and p.returncode!=0:raise StepError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
 return p.stdout.strip()
def show(repo:Path,ref:str,path:str)->str:return git(repo,"show",f"{ref}:{path}")
def queue_files(repo:Path,prefix:str)->list[str]:return [x for x in git(repo,"ls-tree","-r","--name-only",f"origin/{QUEUE}",prefix).splitlines() if x]
def expected_candidate(state:str)->str|None:
 for key in ("expected_candidate","bootstrap_repaired_candidate","bootstrap_calibration_candidate"):
  m=re.search(rf'(?m)^\s*{re.escape(key)}:\s*["\']?([0-9a-f]{{40}})',state)
  if m:return m.group(1)
 return None
def metrics(text:str)->dict:
 out={"summary":"UNKNOWN","python":"UNKNOWN","command":"UNKNOWN"}
 m=re.search(r"(?m)^PYTHON_VERSION:\s*`([^`]+)`",text);out["python"]=m.group(1) if m else "UNKNOWN"
 m=re.search(r"(?m)^COMMAND:\s*`([^`]+)`",text);out["command"]=m.group(1) if m else "UNKNOWN"
 m=re.search(r"(?m)^SUMMARY\s*\|\s*(.+)$",text);out["summary"]=m.group(1).strip() if m else "UNKNOWN"
 mm=re.search(r"(?m)^METRICS\s*\|\s*(\{.+\})$",text)
 if mm:
  try:out["metrics"]=json.loads(mm.group(1))
  except Exception:out["metrics_raw"]=mm.group(1)
 return out
def successful_calibrations(repo:Path,expected:str|None)->list[dict]:
 out=[]
 for path in queue_files(repo,RESULT_ROOT):
  name=Path(path).name
  if not re.fullmatch(r"S003_CALIBRATION_R\d+\.md",name):continue
  text=show(repo,f"origin/{QUEUE}",path)
  if "CALIBRATION_EXECUTION_RESULT=PASS" not in text or "S003_BOARD_DETERMINISTIC_CALIBRATION_PASS" not in text:continue
  m=re.search(r"`([0-9a-f]{40})`",text)
  if not m:continue
  candidate=m.group(1)
  if expected and candidate!=expected:continue
  role=re.search(r"S003_CALIBRATION_(R\d+)\.md",name).group(1);receipt=f"{RECEIPT_ROOT}/S003_CALIBRATION_{role}.json"
  try:r=json.loads(show(repo,f"origin/{QUEUE}",receipt))
  except Exception:continue
  job=r.get("job") if isinstance(r,dict) else None
  if not isinstance(job,dict) or job.get("state")!="SUCCEEDED" or job.get("exit_code")!=0 or job.get("candidate_sha")!=candidate:continue
  out.append({"role":role,"candidate":candidate,"result_path":path,"receipt_path":receipt,"text":text,"finished_at":float(job.get("finished_at") or 0),"job_id":job.get("job_id"),"metrics":metrics(text)})
 return sorted(out,key=lambda x:x["finished_at"])
def replace_scalar(text:str,key:str,value:str)->str:
 pat=rf"(?m)^({re.escape(key)}:\s*).*$"
 if re.search(pat,text):return re.sub(pat,rf"\g<1>{value}",text,count=1)
 raise StepError(f"STATE_KEY_MISSING:{key}")
def replace_indented_scalar(text:str,key:str,value:str)->str:
 pat=rf"(?m)^(\s+{re.escape(key)}:\s*).*$"
 if re.search(pat,text):return re.sub(pat,rf"\g<1>{value}",text,count=1)
 raise StepError(f"STATE_KEY_MISSING:{key}")
def apply_calibration(repo:Path,cal:dict)->int:
 state_file=repo/STATE_PATH;state=state_file.read_text(encoding="utf-8")
 if "bootstrap_calibration_status: PASS" in state and cal["candidate"] in state:return 3
 state=replace_scalar(state,"program_status","ACTIVE");state=replace_scalar(state,"active_sprint_status","BOARD_BOOTSTRAP_R002_REVIEW_PREPARATION")
 state=replace_indented_scalar(state,"bootstrap_calibration_status","PASS")
 if re.search(r"(?m)^\s+bootstrap_calibration_candidate:",state):state=replace_indented_scalar(state,"bootstrap_calibration_candidate",f'"{cal["candidate"]}"')
 state=replace_indented_scalar(state,"bootstrap_independent_review_status","READY_TO_FREEZE_AND_LAUNCH_R002")
 state_file.write_text(state,encoding="utf-8")
 evidence=repo/EVID_PATH;evidence.parent.mkdir(parents=True,exist_ok=True);met=cal["metrics"]
 evidence.write_text(f'''# S003 Board Calibration — Supervisor-Consumed Native Evidence\n\nCandidate: `{cal["candidate"]}`\n\nQueue result: `{cal["result_path"]}`\n\nQueue receipt: `{cal["receipt_path"]}`\n\nExecution role: `{cal["role"]}`\n\nJob ID: `{cal["job_id"]}`\n\nPython: `{met.get("python","UNKNOWN")}`\n\nCommand: `{met.get("command","UNKNOWN")}`\n\nSummary: `{met.get("summary","UNKNOWN")}`\n\nThe queue result explicitly contains `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS` and `CALIBRATION_EXECUTION_RESULT=PASS`. The matching receipt records successful exact-head isolated Mac execution with exit code 0.\n\nThis artifact is calibration evidence only. It does not authorize the Review Board or Audit Board. Runtime authority remains `NONE`. M9 remains `NOT_STARTED`.\n''',encoding="utf-8")
 parent=git(repo,"rev-parse","HEAD")
 result=commit_transition(repo=repo,lock_path=Path.home()/".mros-agent-bridge/state/authority-writer.lock",expected_parent=parent,changed_paths=[STATE_PATH,EVID_PATH],message=TRANSITION_MESSAGE)
 print(json.dumps({"transition":"CALIBRATION_PASS_CONSUMED","candidate":cal["candidate"],"summary":met.get("summary"),"commit":result.commit_sha},sort_keys=True));return 0
def parse_args():
 p=argparse.ArgumentParser();p.add_argument("--repo",required=True,type=Path);p.add_argument("--health",type=Path);p.add_argument("--once",action="store_true");return p.parse_args()
def main()->int:
 a=parse_args();repo=a.repo.resolve();git(repo,"fetch","origin",AUTH,QUEUE)
 recovered=recover_stranded_transition(repo=repo,lock_path=Path.home()/".mros-agent-bridge/state/authority-writer.lock",message=TRANSITION_MESSAGE)
 if recovered:
  print(json.dumps({"transition":"STRANDED_CALIBRATION_TRANSITION_PUBLISHED","commit":recovered.commit_sha},sort_keys=True));return 0
 git(repo,"merge","--ff-only",f"origin/{AUTH}")
 state=(repo/STATE_PATH).read_text(encoding="utf-8")
 if not re.search(r"(?m)^active_sprint:\s*S003\s*$",state):return 3
 expected=expected_candidate(state);cals=successful_calibrations(repo,expected)
 if not cals:return 3
 return apply_calibration(repo,cals[-1])
if __name__=="__main__":raise SystemExit(main())
