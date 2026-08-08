#!/usr/bin/env python3
from __future__ import annotations
import re
from datetime import datetime

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PY_RE = re.compile(r"^\d+\.\d+\.\d+$")
REPOSITORY = "ramgolladi1503-sys/tradebot"
BRANCH = "research/mros-program-v1"
REQUIRED = (
    "repository","branch","head","validator","python_version","command",
    "checks","passed","failed","exit_code","timestamp",
)


def validate_native_evidence(data: object, candidate_head: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["NATIVE_EVIDENCE_OBJECT_REQUIRED"]
    for key in REQUIRED:
        if key not in data:
            errors.append(f"NATIVE_MISSING:{key}")
    if errors:
        return errors
    if data.get("repository") != REPOSITORY:
        errors.append("NATIVE_REPOSITORY_MISMATCH")
    if data.get("branch") != BRANCH:
        errors.append("NATIVE_BRANCH_MISMATCH")
    head = data.get("head")
    if not isinstance(head, str) or not SHA_RE.fullmatch(head):
        errors.append("NATIVE_HEAD_INVALID")
    elif head != candidate_head:
        errors.append("NATIVE_HEAD_MISMATCH")
    validator = data.get("validator")
    command = data.get("command")
    if not isinstance(validator, str) or not validator.startswith("scripts/mros/") or not validator.endswith(".py"):
        errors.append("NATIVE_VALIDATOR_INVALID")
    if not isinstance(command, str) or not command.strip():
        errors.append("NATIVE_COMMAND_INVALID")
    elif isinstance(validator, str) and validator not in command:
        errors.append("NATIVE_COMMAND_VALIDATOR_MISMATCH")
    py = data.get("python_version")
    if not isinstance(py, str) or not PY_RE.fullmatch(py):
        errors.append("NATIVE_PYTHON_VERSION_INVALID")
    for key in ("checks","passed","failed","exit_code"):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"NATIVE_{key.upper()}_TYPE_INVALID")
    if all(isinstance(data.get(k), int) and not isinstance(data.get(k), bool) for k in ("checks","passed","failed","exit_code")):
        checks, passed, failed, exit_code = data["checks"], data["passed"], data["failed"], data["exit_code"]
        if checks <= 0:
            errors.append("NATIVE_CHECKS_NONPOSITIVE")
        if passed < 0 or failed < 0 or passed + failed != checks:
            errors.append("NATIVE_COUNTS_INCONSISTENT")
        if failed != 0 or passed != checks or exit_code != 0:
            errors.append("NATIVE_VALIDATION_NOT_PASS")
    ts = data.get("timestamp")
    if not isinstance(ts, str) or not ts.strip():
        errors.append("NATIVE_TIMESTAMP_INVALID")
    else:
        try:
            datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            errors.append("NATIVE_TIMESTAMP_INVALID")
    return errors


def native_pass(data: object, candidate_head: str) -> bool:
    return not validate_native_evidence(data, candidate_head)
