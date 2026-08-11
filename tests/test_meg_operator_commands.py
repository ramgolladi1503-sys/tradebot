import json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).parents[1]
STATUS=ROOT/"scripts/status_meg_live_observation_v1.py"
STOP=ROOT/"scripts/stop_meg_live_observation_v1.py"

def run(script, root, *extra): return subprocess.run([sys.executable,str(script),"--evidence-root",str(root),*extra],capture_output=True,text=True)

def test_status_missing_root_is_explicit(tmp_path):
    assert run(STATUS,tmp_path/"missing").returncode == 2

def test_stop_validates_identity_and_is_idempotent(tmp_path):
    root=tmp_path/"session"; root.mkdir()
    (root/"process_identity.json").write_text(json.dumps({"run_id":"r1","pid":__import__('os').getpid(),"producer_sha":"c1","state":"RUNNING"}))
    assert run(STOP,root,"--run-id","wrong").returncode == 1
    assert run(STOP,root,"--run-id","r1","--producer-sha","c1").returncode == 0
    assert run(STOP,root,"--run-id","r1","--producer-sha","c1").returncode == 0

def test_status_reports_factual_unknown_drain(tmp_path):
    root=tmp_path/"session"; root.mkdir()
    (root/"process_identity.json").write_text(json.dumps({"run_id":"r1","pid":999999,"producer_sha":"c1","state":"RUNNING"}))
    result=run(STATUS,root); assert result.returncode == 0; assert '"drain_complete": "UNKNOWN"' in result.stdout
