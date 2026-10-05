"""Offline JSON CLI; it never contacts GitHub, CI, or trading services."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
from pathlib import Path

from .evidence import canonical_json
from .models import (Defect, DefectSeverity, DefectStatus, Evidence, EvidenceStatus,
                     EvidenceType, WorkItem, WorkItemType)
from .orchestrator import DeliveryOrchestrator
from .roles import DeliveryRole
from .states import DeliveryState
from .validators import work_item_from_dict, work_item_to_dict


def _read(path: Path) -> WorkItem:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError(f"invalid JSON number: {value}")
    if path.is_symlink():
        raise ValueError("refusing to follow a symlinked work-item file")
    with path.open("r", encoding="utf-8") as stream:
        return work_item_from_dict(json.load(stream, object_pairs_hook=unique_object,
                                             parse_constant=reject_constant))


def _write_atomic(path: Path, item: WorkItem, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json(work_item_to_dict(item)) + "\n"
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(name, path, follow_symlinks=False)
            os.unlink(name)
        else:
            os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tradebot-delivery")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create a canonical empty work-item JSON file")
    create.add_argument("path", type=Path)
    create.add_argument("work_item_id")
    create.add_argument("type", choices=[x.value for x in WorkItemType])
    create.add_argument("title")
    for name in ("validate", "readiness", "allowed-next-states"):
        p = sub.add_parser(name)
        p.add_argument("path", type=Path)
    transition = sub.add_parser("transition")
    transition.add_argument("path", type=Path)
    transition.add_argument("target", choices=[x.value for x in DeliveryState])
    transition.add_argument("--role", required=True, choices=[x.value for x in DeliveryRole])
    transition.add_argument("--actor", required=True)
    transition.add_argument("--timestamp", required=True, help="ISO-8601 with timezone")
    transition.add_argument("--reason", required=True)
    transition.add_argument("--evidence-id", action="append", default=[])
    evidence = sub.add_parser("add-evidence")
    evidence.add_argument("path", type=Path)
    evidence.add_argument("evidence_id")
    evidence.add_argument("evidence_type", choices=[x.value for x in EvidenceType])
    evidence.add_argument("--role", required=True, choices=[x.value for x in DeliveryRole])
    evidence.add_argument("--actor", required=True)
    evidence.add_argument("--timestamp", required=True)
    evidence.add_argument("--status", default="PASS", choices=[x.value for x in EvidenceStatus])
    evidence.add_argument("--summary", required=True)
    evidence.add_argument("--ref", action="append", required=True)
    evidence.add_argument("--check", action="append", default=[], metavar="NAME=STATUS")
    defect = sub.add_parser("add-defect")
    defect.add_argument("path", type=Path)
    defect.add_argument("defect_id")
    defect.add_argument("severity", choices=[x.value for x in DefectSeverity])
    defect.add_argument("title")
    defect.add_argument("--role", required=True,
                        choices=[DeliveryRole.QA_ENGINEER.value, DeliveryRole.UAT_REVIEWER.value])
    defect.add_argument("--actor", required=True)
    defect.add_argument("--timestamp", required=True)
    defect.add_argument("--reason", required=True)
    defect.add_argument("--step", action="append", required=True)
    defect.add_argument("--expected", required=True)
    defect.add_argument("--actual", required=True)
    defect.add_argument("--evidence-id", action="append", required=True)
    defect_update = sub.add_parser("advance-defect")
    defect_update.add_argument("path", type=Path)
    defect_update.add_argument("defect_id")
    defect_update.add_argument("target", choices=[x.value for x in DefectStatus])
    defect_update.add_argument("--role", required=True, choices=[x.value for x in DeliveryRole])
    defect_update.add_argument("--actor", required=True)
    defect_update.add_argument("--timestamp", required=True)
    defect_update.add_argument("--reason", required=True)
    defect_update.add_argument("--evidence-ref", default="")
    defect_update.add_argument("--regression-result", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            lock_path = args.path.with_name(args.path.name + ".lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a", encoding="utf-8") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                if args.path.exists():
                    raise ValueError("refusing to overwrite an existing work-item file")
                item = WorkItem(work_item_id=args.work_item_id, type=WorkItemType(args.type),
                                parent_epic="", parent_feature="", title=args.title)
                _write_atomic(args.path, item, exclusive=True)
                print(args.path)
                return 0
        # Serialize local writers so a stale concurrent reader cannot overwrite
        # an update. The lock protects only this CLI's cooperating processes.
        lock_path = args.path.with_name(args.path.name + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            item = _read(args.path)
            orchestrator = DeliveryOrchestrator(item)
            if args.command == "validate":
                print(json.dumps({"valid": True, "work_item_id": item.work_item_id,
                                  "state": item.current_state.value}, sort_keys=True))
            elif args.command == "readiness":
                print(json.dumps(orchestrator.readiness(), sort_keys=True))
            elif args.command == "allowed-next-states":
                print(json.dumps(orchestrator.allowed_next_states()))
            elif args.command == "transition":
                updated = orchestrator.transition(args.target, acting_role=args.role, actor=args.actor,
                                                  timestamp=args.timestamp, reason=args.reason,
                                                  evidence_ids=args.evidence_id)
                _write_atomic(args.path, updated)
                print(updated.current_state.value)
            elif args.command == "add-evidence":
                checks = []
                for pair in args.check:
                    if "=" not in pair:
                        raise ValueError("--check must use NAME=STATUS")
                    checks.append(tuple(pair.split("=", 1)))
                ev = Evidence(args.evidence_id, item.work_item_id, EvidenceType(args.evidence_type),
                              DeliveryRole(args.role), args.actor, args.timestamp,
                              EvidenceStatus(args.status), args.summary, tuple(args.ref),
                              check_results=tuple(checks))
                updated = orchestrator.add_evidence(ev)
                _write_atomic(args.path, updated)
                print(args.evidence_id)
            elif args.command == "add-defect":
                item_defect = Defect(args.defect_id, item.work_item_id,
                                     DefectSeverity(args.severity), args.title,
                                     tuple(args.step), args.expected, args.actual,
                                     tuple(args.evidence_id))
                updated = orchestrator.add_defect(item_defect, actor_role=DeliveryRole(args.role),
                                                   actor=args.actor, timestamp=args.timestamp,
                                                   reason=args.reason)
                _write_atomic(args.path, updated)
                print(args.defect_id)
            elif args.command == "advance-defect":
                updated = orchestrator.advance_defect(args.defect_id, DefectStatus(args.target),
                                                       actor_role=DeliveryRole(args.role), actor=args.actor,
                                                       timestamp=args.timestamp, reason=args.reason,
                                                       evidence_ref=args.evidence_ref,
                                                       regression_result=args.regression_result)
                _write_atomic(args.path, updated)
                print(args.target)
            return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"tradebot-delivery: blocked: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
