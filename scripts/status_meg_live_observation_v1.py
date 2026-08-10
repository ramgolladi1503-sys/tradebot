#!/usr/bin/env python3
"""Read one explicit MEG observation session status without mutation."""
from __future__ import annotations
import argparse, json, os, shutil, sys
from pathlib import Path

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--evidence-root", required=True, type=Path); a=p.parse_args()
    root=a.evidence_root.expanduser().resolve(); identity=root/"process_identity.json"
    if not identity.is_file():
        print(json.dumps({"verdict":"SESSION_NOT_FOUND","evidence_root":str(root)}, sort_keys=True)); return 2
    try: data=json.loads(identity.read_text())
    except Exception:
        print(json.dumps({"verdict":"MALFORMED_SESSION_STATE","evidence_root":str(root)}, sort_keys=True)); return 1
    pid=data.get("pid"); running=False
    if isinstance(pid,int) and pid>0:
        try: os.kill(pid,0); running=True
        except OSError: running=False
    shutdown={}
    path=root/"shutdown_drain.json"
    if path.is_file():
        try: shutdown=json.loads(path.read_text())
        except Exception: return 1
    out={**data,"process_running":running,"shutdown_started":path.is_file(),
         "drain_complete":shutdown.get("shutdown_drain_complete","UNKNOWN"),
         "sealed":(root/"SEALED").is_file(),"disk_free_bytes":shutil.disk_usage(root).free,
         "verdict":"OK"}
    print(json.dumps(out, indent=2, sort_keys=True, default=str)); return 0
if __name__ == "__main__": raise SystemExit(main())
