#!/usr/bin/env python3
"""Bounded immutable research lifecycle for hypothesis discovery and certification.

This module separates discovery from certification and makes terminal decisions durable.
It never grants runtime authority or broker permissions.

States:
  DISCOVERED -> CANDIDATE_OF_RECORD -> CERTIFICATION_RUNNING -> VALIDATED_RESEARCH
                                              \-> REJECTED (terminal)
  DISCOVERED -> REJECTED (terminal)

A closed search domain may only be reopened under a different information_set_id.
Changing rules, thresholds, dataset hashes, or costs creates a new candidate identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TERMINAL = {"REJECTED", "VALIDATED_RESEARCH"}
ALLOWED = {
    "DISCOVERED": {"CANDIDATE_OF_RECORD", "REJECTED"},
    "CANDIDATE_OF_RECORD": {"CERTIFICATION_RUNNING", "REJECTED"},
    "CERTIFICATION_RUNNING": {"VALIDATED_RESEARCH", "REJECTED"},
    "REJECTED": set(),
    "VALIDATED_RESEARCH": set(),
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(spec: dict[str, Any]) -> str:
    immutable = {
        "instrument": spec.get("instrument"),
        "family": spec.get("family"),
        "direction": spec.get("direction"),
        "parameters": spec.get("parameters", {}),
        "entry_rule": spec.get("entry_rule"),
        "exit_rule": spec.get("exit_rule"),
        "cost_bps": spec.get("cost_bps"),
        "dataset_sha256": spec.get("dataset_sha256"),
        "information_set_id": spec.get("information_set_id"),
    }
    return hashlib.sha256(canonical_json(immutable).encode()).hexdigest()


def new_candidate(spec: dict[str, Any]) -> dict[str, Any]:
    fp = fingerprint(spec)
    candidate_id = "COR-" + fp[:16].upper()
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "tradebot-bounded-candidate-v1",
        "candidate_id": candidate_id,
        "candidate_fingerprint": fp,
        "state": "DISCOVERED",
        "immutable_spec": spec,
        "history": [{"state": "DISCOVERED", "at_utc": now, "reason": "created"}],
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }


def assert_integrity(record: dict[str, Any]) -> None:
    expected = fingerprint(record["immutable_spec"])
    if record.get("candidate_fingerprint") != expected:
        raise ValueError("candidate_fingerprint_mismatch")
    expected_id = "COR-" + expected[:16].upper()
    if record.get("candidate_id") != expected_id:
        raise ValueError("candidate_id_mismatch")
    if record.get("runtime_authority") != "NONE" or record.get("broker_actions_allowed") is not False:
        raise ValueError("runtime_or_broker_authority_forbidden")


def transition(record: dict[str, Any], new_state: str, reason: str) -> dict[str, Any]:
    assert_integrity(record)
    old = str(record.get("state"))
    if new_state not in ALLOWED.get(old, set()):
        raise ValueError(f"illegal_transition:{old}->{new_state}")
    out = json.loads(json.dumps(record))
    out["state"] = new_state
    out.setdefault("history", []).append({"state": new_state, "at_utc": datetime.now(timezone.utc).isoformat(), "reason": reason})
    if new_state == "VALIDATED_RESEARCH":
        out["certification"] = "VALIDATED_RESEARCH"
    elif new_state == "REJECTED":
        out["certification"] = "REJECTED"
    assert_integrity(out)
    return out


def close_search_domain(*, domain_id: str, information_set_id: str, dataset_sha256: str,
                        generations: list[dict[str, Any]]) -> dict[str, Any]:
    if not generations:
        raise ValueError("no_discovery_generations")
    bad = []
    total_hypotheses = 0
    for g in generations:
        total_hypotheses += int(g.get("hypotheses", 0))
        survivors = int(g.get("admissible_candidates", g.get("promising_not_certified", -1)))
        if survivors != 0:
            bad.append({"generation_id": g.get("generation_id"), "admissible_candidates": survivors})
        if g.get("dataset_sha256") and g.get("dataset_sha256") != dataset_sha256:
            raise ValueError("generation_dataset_sha_mismatch")
    if bad:
        raise ValueError(f"domain_has_admissible_candidates:{bad}")
    return {
        "schema_version": "tradebot-search-domain-closure-v1",
        "domain_id": domain_id,
        "information_set_id": information_set_id,
        "dataset_sha256": dataset_sha256,
        "status": "NO_CANDIDATE_FOUND_IN_SEARCH_DOMAIN",
        "closed": True,
        "closed_at_utc": datetime.now(timezone.utc).isoformat(),
        "generation_count": len(generations),
        "total_hypotheses_evaluated": total_hypotheses,
        "generations": generations,
        "reopen_rule": "NEW_INFORMATION_SET_ID_REQUIRED",
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new-candidate")
    n.add_argument("--spec", required=True); n.add_argument("--output", required=True)
    t = sub.add_parser("transition")
    t.add_argument("--record", required=True); t.add_argument("--state", required=True, choices=sorted(ALLOWED)); t.add_argument("--reason", required=True); t.add_argument("--output")
    c = sub.add_parser("close-domain")
    c.add_argument("--domain-id", required=True); c.add_argument("--information-set-id", required=True); c.add_argument("--dataset-sha256", required=True); c.add_argument("--generations", required=True); c.add_argument("--output", required=True)
    a = p.parse_args(argv)
    if a.cmd == "new-candidate":
        payload = new_candidate(json.loads(Path(a.spec).read_text(encoding="utf-8"))); write(Path(a.output), payload); print(json.dumps(payload, indent=2)); return 0
    if a.cmd == "transition":
        src = Path(a.record); payload = transition(json.loads(src.read_text(encoding="utf-8")), a.state, a.reason); write(Path(a.output or a.record), payload); print(json.dumps(payload, indent=2)); return 0
    gens = json.loads(Path(a.generations).read_text(encoding="utf-8"))
    payload = close_search_domain(domain_id=a.domain_id, information_set_id=a.information_set_id, dataset_sha256=a.dataset_sha256, generations=gens)
    write(Path(a.output), payload); print(json.dumps(payload, indent=2)); return 0

if __name__ == "__main__":
    raise SystemExit(main())
