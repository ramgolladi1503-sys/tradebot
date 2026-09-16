#!/usr/bin/env python3
"""Offline release manager; input files are primitives, never PASS authority."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.certified_release_store import ReleaseStore, ReleaseStoreError
from core.release_certification import certify, promote
from core.release_change_impact import DependencyEvidence
from core.release_rebootstrap import certify_rebootstrap, promote_rebootstrap
from scripts.verify_release_manager import verify, verify_rebootstrap


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _graph(path: Path) -> DependencyEvidence:
    p=json.loads(path.read_text(encoding="utf-8")); return DependencyEvidence(edges={k:frozenset(v) for k,v in p["edges"].items()}, critical_roots=frozenset(p["critical_roots"]), bounded_roots=frozenset(p["bounded_roots"]), complete=bool(p["complete"]), unresolved=frozenset(p.get("unresolved", [])))


def _manifest(path: Path) -> dict[str, object]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict) or "gates" in v or any(not isinstance(k,str) for k in v): raise ReleaseStoreError("primitive_manifest_invalid")
    return v


def cmd_init(a):
    s=ReleaseStore(a.state_root)
    if s.read() is not None: raise ReleaseStoreError("release_store_already_initialized")
    p={"promotion_status":"CERTIFIED", **s.record_verified_selection(candidate_sha=a.certified_sha,evidence_sha256=a.evidence_sha256,expected_event=None)}
    if a.output:_write_json(a.output,p)
    print(json.dumps(p,indent=2,sort_keys=True)); return 0


def cmd_certify(a):
    r=certify(a.repo,a.candidate,ReleaseStore(a.state_root),_graph(a.dependency_graph),primitive_root=a.primitive_root,primitive_manifest=_manifest(a.primitive_manifest))
    if a.output:_write_json(a.output,r)
    print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r["verdict"]=="PASS" else 2


def cmd_verify(a):
    p=verify(a.state_root,repo=a.repo,certification=a.certification,dependency_graph=a.dependency_graph,primitive_root=a.primitive_root,primitive_manifest=a.primitive_manifest)
    if a.output:_write_json(a.output,p)
    print(json.dumps(p,indent=2,sort_keys=True)); return 0 if p["independent_release_verifier_pass"] else 2


def cmd_promote(a):
    r=json.loads(a.certification.read_text()); att=json.loads(a.attestation.read_text()); p=promote(r,ReleaseStore(a.state_root),att)
    if a.output:_write_json(a.output,p)
    print(json.dumps(p,indent=2,sort_keys=True)); return 0


def cmd_rebootstrap_certify(a):
    r=certify_rebootstrap(a.repo,a.candidate,ReleaseStore(a.state_root),_graph(a.dependency_graph),primitive_root=a.primitive_root,primitive_manifest=_manifest(a.primitive_manifest),reason=a.reason)
    if a.output:_write_json(a.output,r)
    print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r["verdict"]=="PASS" else 2


def cmd_rebootstrap_verify(a):
    p=verify_rebootstrap(a.state_root,repo=a.repo,certification=a.certification,dependency_graph=a.dependency_graph,primitive_root=a.primitive_root,primitive_manifest=a.primitive_manifest)
    if a.output:_write_json(a.output,p)
    print(json.dumps(p,indent=2,sort_keys=True)); return 0 if p["independent_release_verifier_pass"] else 2


def cmd_rebootstrap_promote(a):
    r=json.loads(a.certification.read_text()); att=json.loads(a.attestation.read_text()); p=promote_rebootstrap(r,ReleaseStore(a.state_root),att)
    if a.output:_write_json(a.output,p)
    print(json.dumps(p,indent=2,sort_keys=True)); return 0


def common_cert(p):
    p.add_argument("--repo",type=Path,required=True);p.add_argument("--state-root",type=Path,required=True);p.add_argument("--candidate",required=True);p.add_argument("--dependency-graph",type=Path,required=True);p.add_argument("--primitive-root",type=Path,required=True);p.add_argument("--primitive-manifest",type=Path,required=True);p.add_argument("--output",type=Path)


def common_verify(p):
    p.add_argument("--state-root",type=Path,required=True);p.add_argument("--repo",type=Path,required=True);p.add_argument("--certification",type=Path,required=True);p.add_argument("--dependency-graph",type=Path,required=True);p.add_argument("--primitive-root",type=Path,required=True);p.add_argument("--primitive-manifest",type=Path,required=True);p.add_argument("--output",type=Path)


def main():
    parser=argparse.ArgumentParser(prog="tradebot-release-manager"); sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("init");p.add_argument("--state-root",type=Path,required=True);p.add_argument("--certified-sha",required=True);p.add_argument("--evidence-sha256",required=True);p.add_argument("--output",type=Path);p.set_defaults(handler=cmd_init)
    p=sub.add_parser("certify");common_cert(p);p.set_defaults(handler=cmd_certify)
    p=sub.add_parser("verify");common_verify(p);p.set_defaults(handler=cmd_verify)
    p=sub.add_parser("promote");p.add_argument("--state-root",type=Path,required=True);p.add_argument("--certification",type=Path,required=True);p.add_argument("--attestation",type=Path,required=True);p.add_argument("--output",type=Path);p.set_defaults(handler=cmd_promote)
    p=sub.add_parser("rebootstrap-certify");common_cert(p);p.add_argument("--reason",required=True);p.set_defaults(handler=cmd_rebootstrap_certify)
    p=sub.add_parser("rebootstrap-verify");common_verify(p);p.set_defaults(handler=cmd_rebootstrap_verify)
    p=sub.add_parser("rebootstrap-promote");p.add_argument("--state-root",type=Path,required=True);p.add_argument("--certification",type=Path,required=True);p.add_argument("--attestation",type=Path,required=True);p.add_argument("--output",type=Path);p.set_defaults(handler=cmd_rebootstrap_promote)
    a=parser.parse_args(); return int(a.handler(a))

if __name__=="__main__": raise SystemExit(main())
