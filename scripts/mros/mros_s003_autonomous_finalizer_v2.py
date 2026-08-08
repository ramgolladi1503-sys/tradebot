#!/usr/bin/env python3
"""Compatibility wrapper binding the S003 finalizer to trusted queue-history authorization."""
from __future__ import annotations
from pathlib import Path
import mros_s003_autonomous_finalizer as finalizer

_ORIG_LOAD=finalizer.load_mod
QUEUE_REPO=Path('/Users/madhuram/.mros-agent-bridge/queue')
CANONICAL_NATIVE='research/evidence/sprints/S003/S003_AUTONOMOUS_NATIVE_EVIDENCE.json'

class _AdvanceProxy:
    def __init__(self,real):self.real=real
    def authorize(self,**kw):
        review=kw.get('review') or {};audit=kw.get('audit') or {};rm=kw.get('review_manifest') or {};am=kw.get('audit_manifest') or {}
        sprint=str(kw.get('sprint') or 'S003');rr=str(review.get('review_round') or rm.get('round') or '');ar=str(audit.get('audit_round') or am.get('round') or '')
        review_path=Path('research/evidence/sprints/S003/agent_queue/manifests')/f'{sprint}_{rr}_REVIEW_POPULATION.json'
        audit_path=Path('research/evidence/sprints/S003/agent_queue/manifests')/f'{sprint}_{ar}_AUDIT_POPULATION.json'
        kw.pop('review_receipts',None);kw.pop('audit_receipts',None)
        return self.real.authorize(**kw,queue_repo=QUEUE_REPO,review_manifest_path=review_path,audit_manifest_path=audit_path,review_round=rr,audit_round=ar,expected_native_ref=CANONICAL_NATIVE)

def load_mod_v2(auth:Path,name:str):
    real=_ORIG_LOAD(auth,name)
    return _AdvanceProxy(real) if name=='advance_program' else real

def main()->int:
    finalizer.load_mod=load_mod_v2
    return finalizer.main()

if __name__=='__main__':raise SystemExit(main())
