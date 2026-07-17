from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
MCP_PROTOCOL_VERSION = "2025-11-25"
MCP_CONTRACT_VERSION = "1.0.0"
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_SCOPE_RE = re.compile(r"^[a-z][a-z0-9:_-]{1,127}$")


class MCPContractError(ValueError):
    """Raised when an MCP contract is invalid or incompatible."""


@dataclass(frozen=True, order=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "SemanticVersion":
        parts = value.split(".")
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise MCPContractError(f"invalid semantic version: {value!r}")
        parsed = cls(*(int(part) for part in parts))
        if min(parsed.major, parsed.minor, parsed.patch) < 0:
            raise MCPContractError(f"invalid semantic version: {value!r}")
        return parsed

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ToolAnnotations:
    title: str
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise MCPContractError("tool annotation title cannot be empty")
        if self.read_only and self.destructive:
            raise MCPContractError("a read-only tool cannot be destructive")

    def to_mcp_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "readOnlyHint": self.read_only,
            "destructiveHint": self.destructive,
            "idempotentHint": self.idempotent,
            "openWorldHint": self.open_world,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "read_only": self.read_only,
            "destructive": self.destructive,
            "idempotent": self.idempotent,
            "open_world": self.open_world,
        }


@dataclass(frozen=True)
class ToolExecutionPolicy:
    task_support: str = "forbidden"
    timeout_seconds: int = 30
    maximum_request_bytes: int = 16_384
    maximum_response_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        if self.task_support not in {"forbidden", "optional", "required"}:
            raise MCPContractError(f"unsupported task support: {self.task_support}")
        if self.timeout_seconds <= 0:
            raise MCPContractError("timeout_seconds must be positive")
        if self.maximum_request_bytes <= 0 or self.maximum_response_bytes <= 0:
            raise MCPContractError("payload limits must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_support": self.task_support,
            "timeout_seconds": self.timeout_seconds,
            "maximum_request_bytes": self.maximum_request_bytes,
            "maximum_response_bytes": self.maximum_response_bytes,
        }


@dataclass(frozen=True)
class ToolContract:
    name: str
    title: str
    description: str
    contract_version: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    annotations: ToolAnnotations
    execution: ToolExecutionPolicy
    required_scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _TOOL_NAME_RE.fullmatch(self.name):
            raise MCPContractError(f"invalid MCP tool name: {self.name!r}")
        if not self.title.strip() or not self.description.strip():
            raise MCPContractError(f"tool {self.name} requires title and description")
        SemanticVersion.parse(self.contract_version)
        _validate_object_schema(self.input_schema, label=f"{self.name}.input_schema")
        _validate_object_schema(self.output_schema, label=f"{self.name}.output_schema")
        if not self.required_scopes:
            raise MCPContractError(f"tool {self.name} requires at least one scope")
        if tuple(sorted(set(self.required_scopes))) != self.required_scopes:
            raise MCPContractError(f"tool {self.name} scopes must be unique and sorted")
        invalid_scopes = [scope for scope in self.required_scopes if not _SCOPE_RE.fullmatch(scope)]
        if invalid_scopes:
            raise MCPContractError(f"tool {self.name} has invalid scopes: {invalid_scopes}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "contract_version": self.contract_version,
            "mcp_protocol_version": MCP_PROTOCOL_VERSION,
            "input_schema": _copy_json(self.input_schema),
            "output_schema": _copy_json(self.output_schema),
            "annotations": self.annotations.to_dict(),
            "execution": self.execution.to_dict(),
            "required_scopes": list(self.required_scopes),
        }

    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict())).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def contracts_digest(contracts: tuple[ToolContract, ...]) -> str:
    payload = [contract.to_dict() for contract in contracts]
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def is_backward_compatible(previous: ToolContract, current: ToolContract) -> bool:
    try:
        assert_backward_compatible(previous, current)
    except MCPContractError:
        return False
    return True


def assert_backward_compatible(previous: ToolContract, current: ToolContract) -> None:
    if previous.name != current.name:
        raise MCPContractError("tool names differ")
    old_version = SemanticVersion.parse(previous.contract_version)
    new_version = SemanticVersion.parse(current.contract_version)
    if old_version.major != new_version.major:
        raise MCPContractError("major contract versions differ")
    if new_version < old_version:
        raise MCPContractError("contract version cannot move backwards")
    _assert_input_schema_compatible(previous.input_schema, current.input_schema)
    _assert_output_schema_compatible(previous.output_schema, current.output_schema)
    _assert_annotations_not_weakened(previous.annotations, current.annotations)
    if previous.required_scopes != current.required_scopes:
        raise MCPContractError("required scopes changed without a major version")
    if current.execution.timeout_seconds > previous.execution.timeout_seconds:
        raise MCPContractError("tool timeout expanded without a major version")
    if current.execution.maximum_request_bytes > previous.execution.maximum_request_bytes:
        raise MCPContractError("request payload budget expanded without a major version")
    if current.execution.maximum_response_bytes > previous.execution.maximum_response_bytes:
        raise MCPContractError("response payload budget expanded without a major version")
    if current.execution.task_support != previous.execution.task_support:
        raise MCPContractError("task support changed without a major version")


def _validate_object_schema(schema: Mapping[str, Any], *, label: str) -> None:
    if schema.get("type") != "object":
        raise MCPContractError(f"{label} must have object root")
    if schema.get("$schema") != JSON_SCHEMA_DRAFT:
        raise MCPContractError(f"{label} must declare JSON Schema 2020-12")
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, Mapping):
        raise MCPContractError(f"{label}.properties must be an object")
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise MCPContractError(f"{label}.required must be a list of strings")
    unknown_required = sorted(set(required) - set(properties))
    if unknown_required:
        raise MCPContractError(f"{label} requires unknown properties: {unknown_required}")
    if "additionalProperties" not in schema:
        raise MCPContractError(f"{label} must state additionalProperties explicitly")


def _assert_input_schema_compatible(previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    old_properties = previous.get("properties", {})
    new_properties = current.get("properties", {})
    for name, old_schema in old_properties.items():
        if name not in new_properties or new_properties[name] != old_schema:
            raise MCPContractError(f"input property changed or removed: {name}")
    old_required = set(previous.get("required", []))
    new_required = set(current.get("required", []))
    if not new_required.issubset(old_required):
        raise MCPContractError("a new required input was introduced")
    if previous.get("additionalProperties") is True and current.get("additionalProperties") is False:
        raise MCPContractError("input additionalProperties became more restrictive")


def _assert_output_schema_compatible(previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    old_properties = previous.get("properties", {})
    new_properties = current.get("properties", {})
    for name, old_schema in old_properties.items():
        if name not in new_properties or new_properties[name] != old_schema:
            raise MCPContractError(f"output property changed or removed: {name}")
    old_required = set(previous.get("required", []))
    new_required = set(current.get("required", []))
    if not old_required.issubset(new_required):
        raise MCPContractError("a previously required output became optional")


def _assert_annotations_not_weakened(previous: ToolAnnotations, current: ToolAnnotations) -> None:
    if previous.read_only and not current.read_only:
        raise MCPContractError("read-only guarantee was weakened")
    if not previous.destructive and current.destructive:
        raise MCPContractError("destructive behavior was introduced")
    if previous.idempotent and not current.idempotent:
        raise MCPContractError("idempotency guarantee was weakened")
    if not previous.open_world and current.open_world:
        raise MCPContractError("closed-world guarantee was weakened")


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))
