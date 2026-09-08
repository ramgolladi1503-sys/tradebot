#!/usr/bin/env python3
"""Offline Release Manager V1 command surface."""
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
    return DependencyEvidence(
        edges={key: frozenset(value) for key, value in payload["edges"].items()},
        critical_roots=frozenset(payload["critical_roots"]),
        bounded_roots=frozenset(payload["bounded_roots"]),
        complete=bool(payload["complete"]),
        unresolved=frozenset(payload.get("unresolved", [])),
    )


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gate_result(path: Path) -> dict[str, bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    gates = payload.get("gates", payload)
    results: dict[str, bool] = {}
    for key, value in gates.items():
        if isinstance(value, bool):
            results[str(key)] = value
            continue
        if not isinstance(value, dict):
            results[str(key)] = False
            continue
        evidence_path = value.get("evidence_path")
        evidence_sha256 = value.get("evidence_sha256")
        evidence_ok = True
        if evidence_path or evidence_sha256:
            if not evidence_path or not evidence_sha256:
                evidence_ok = False
            else:
                evidence_ok = _sha256(Path(evidence_path)) == evidence_sha256
        results[str(key)] = bool(value.get("pass")) and evidence_ok
    return results


def cmd_init(args: argparse.Namespace) -> int:
    store = ReleaseStore(args.state_root)
    if store.read() is not None:
        raise ReleaseStoreError("release_store_already_initialized")
    event = store.record_verified_selection(
        candidate_sha=args.certified_sha,
        evidence_sha256=args.evidence_sha256,
        expected_event=None,
    )
    payload = {"promotion_status": "CERTIFIED", **event}
    if args.output:
        _write_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_certify(args: argparse.Namespace) -> int:
    gates = _gate_result(args.gates)
    result = certify(
        args.repo,
        args.candidate,
        ReleaseStore(args.state_root),
        _graph(args.dependency_graph),
        gate_runner=lambda gate: gates.get(gate, False),
    )
    if args.output:
        _write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 2


def cmd_promote(args: argparse.Namespace) -> int:
    result = json.loads(args.certification.read_text(encoding="utf-8"))
    evidence = args.certification.read_bytes()
    payload = promote(result, ReleaseStore(args.state_root), evidence)
    if args.output:
        _write_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    payload = verify(args.state_root, repo=args.repo, certification=args.certification)
    if args.output:
        _write_json(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["independent_release_verifier_pass"] else 2


def main() -> int:
    parser = argparse.ArgumentParser(prog="tradebot-release-manager")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--state-root", type=Path, required=True)
    init.add_argument("--certified-sha", required=True)
    init.add_argument("--evidence-sha256", required=True)
    init.add_argument("--output", type=Path)
    init.set_defaults(handler=cmd_init)

    cert = sub.add_parser("certify")
    cert.add_argument("--repo", type=Path, required=True)
    cert.add_argument("--state-root", type=Path, required=True)
    cert.add_argument("--candidate", required=True)
    cert.add_argument("--dependency-graph", type=Path, required=True)
    cert.add_argument("--gates", type=Path, required=True)
    cert.add_argument("--output", type=Path)
    cert.set_defaults(handler=cmd_certify)

    prom = sub.add_parser("promote")
    prom.add_argument("--state-root", type=Path, required=True)
    prom.add_argument("--certification", type=Path, required=True)
    prom.add_argument("--output", type=Path)
    prom.set_defaults(handler=cmd_promote)

    ver = sub.add_parser("verify")
    ver.add_argument("--state-root", type=Path, required=True)
    ver.add_argument("--repo", type=Path)
    ver.add_argument("--certification", type=Path)
    ver.add_argument("--output", type=Path)
    ver.set_defaults(handler=cmd_verify)

    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
