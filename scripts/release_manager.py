#!/usr/bin/env python3
"""Offline release manager; input files are primitives, never PASS authority."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.certified_release_store import ReleaseStore, ReleaseStoreError
from core.release_certification import certify, promote
from core.release_change_impact import DependencyEvidence
from scripts.verify_release_manager import verify


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _graph(path: Path) -> DependencyEvidence:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DependencyEvidence(edges={key: frozenset(value) for key, value in payload["edges"].items()},
                              critical_roots=frozenset(payload["critical_roots"]),
                              bounded_roots=frozenset(payload["bounded_roots"]), complete=bool(payload["complete"]),
                              unresolved=frozenset(payload.get("unresolved", [])))


def _manifest(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or "gates" in value or any(not isinstance(key, str) for key in value):
        raise ReleaseStoreError("primitive_manifest_invalid")
    return value


def cmd_init(args: argparse.Namespace) -> int:
    store = ReleaseStore(args.state_root)
    if store.read() is not None:
        raise ReleaseStoreError("release_store_already_initialized")
    event = store.record_verified_selection(candidate_sha=args.certified_sha, evidence_sha256=args.evidence_sha256, expected_event=None)
    payload = {"promotion_status": "CERTIFIED", **event}
    if args.output: _write_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True)); return 0


def cmd_certify(args: argparse.Namespace) -> int:
    result = certify(args.repo, args.candidate, ReleaseStore(args.state_root), _graph(args.dependency_graph),
                     primitive_root=args.primitive_root, primitive_manifest=_manifest(args.primitive_manifest))
    if args.output: _write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result["verdict"] == "PASS" else 2


def cmd_verify(args: argparse.Namespace) -> int:
    payload = verify(args.state_root, repo=args.repo, certification=args.certification,
                     dependency_graph=args.dependency_graph, primitive_root=args.primitive_root,
                     primitive_manifest=args.primitive_manifest)
    if args.output: _write_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True)); return 0 if payload["independent_release_verifier_pass"] else 2


def cmd_promote(args: argparse.Namespace) -> int:
    result = json.loads(args.certification.read_text(encoding="utf-8"))
    attestation = json.loads(args.attestation.read_text(encoding="utf-8"))
    payload = promote(result, ReleaseStore(args.state_root), attestation)
    if args.output: _write_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True)); return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="tradebot-release-manager")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); init.add_argument("--state-root", type=Path, required=True); init.add_argument("--certified-sha", required=True); init.add_argument("--evidence-sha256", required=True); init.add_argument("--output", type=Path); init.set_defaults(handler=cmd_init)
    cert = sub.add_parser("certify"); cert.add_argument("--repo", type=Path, required=True); cert.add_argument("--state-root", type=Path, required=True); cert.add_argument("--candidate", required=True); cert.add_argument("--dependency-graph", type=Path, required=True); cert.add_argument("--primitive-root", type=Path, required=True); cert.add_argument("--primitive-manifest", type=Path, required=True); cert.add_argument("--output", type=Path); cert.set_defaults(handler=cmd_certify)
    ver = sub.add_parser("verify"); ver.add_argument("--state-root", type=Path, required=True); ver.add_argument("--repo", type=Path, required=True); ver.add_argument("--certification", type=Path, required=True); ver.add_argument("--dependency-graph", type=Path, required=True); ver.add_argument("--primitive-root", type=Path, required=True); ver.add_argument("--primitive-manifest", type=Path, required=True); ver.add_argument("--output", type=Path); ver.set_defaults(handler=cmd_verify)
    prom = sub.add_parser("promote"); prom.add_argument("--state-root", type=Path, required=True); prom.add_argument("--certification", type=Path, required=True); prom.add_argument("--attestation", type=Path, required=True); prom.add_argument("--output", type=Path); prom.set_defaults(handler=cmd_promote)
    args = parser.parse_args(); return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
