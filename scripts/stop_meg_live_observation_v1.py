#!/usr/bin/env python3
"""Request governed MEG shutdown through the session control file."""
from __future__ import annotations
import argparse, json, os, tempfile
from pathlib import Path

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--evidence-root",required=True,type=Path); p.add_argument("--run-id"); p.add_argument("--producer-sha"); a=p.parse_args()
    root=a.evidence_root.expanduser().resolve(); identity=root/"process_identity.json"
    if not identity.is_file(): print("SESSION_NOT_FOUND"); return 2
    try: data=json.loads(identity.read_text())
    except Exception: print("MALFORMED_SESSION_STATE"); return 1
    if a.run_id and a.run_id != data.get("run_id"): print("IDENTITY_MISMATCH"); return 1
    if a.producer_sha and a.producer_sha != data.get("producer_sha"): print("IDENTITY_MISMATCH"); return 1
    pid=data.get("pid")
    if data.get("state") == "STOPPED" or (root/"shutdown_drain.json").is_file(): print("STOP_ALREADY_COMPLETED"); return 0
    if not isinstance(pid,int) or pid <= 0:
        print("IDENTITY_UNVERIFIED"); return 1
    try: os.kill(pid,0)
    except OSError: print("PROCESS_NOT_RUNNING"); return 1
    target=root/"STOP_REQUESTED"
    if not target.exists():
        fd,tmp=tempfile.mkstemp(prefix=".STOP_REQUESTED.",dir=root); os.close(fd); os.replace(tmp,target)
    print("STOP_REQUEST_ACCEPTED"); return 0
if __name__ == "__main__": raise SystemExit(main())
