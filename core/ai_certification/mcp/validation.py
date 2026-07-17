from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import ToolContract
from .registry import get_tool_contract


class MCPContractValidationError(ValueError):
    """Raised when a tool request or structured result violates its contract."""

    def __init__(self, message: str, *, path: str = "$") -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def validate_tool_input(tool_name: str, payload: Mapping[str, Any]) -> None:
    contract = get_tool_contract(tool_name)
    _validate(payload, contract.input_schema, path="$")
    _enforce_payload_budget(payload, contract, request=True)


def validate_tool_output(tool_name: str, payload: Mapping[str, Any]) -> None:
    contract = get_tool_contract(tool_name)
    _validate(payload, contract.output_schema, path="$")
    _enforce_payload_budget(payload, contract, request=False)


def _enforce_payload_budget(
    payload: Mapping[str, Any],
    contract: ToolContract,
    *,
    request: bool,
) -> None:
    try:
        size = len(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise MCPContractValidationError("payload is not canonical JSON") from exc
    limit = (
        contract.execution.maximum_request_bytes
        if request
        else contract.execution.maximum_response_bytes
    )
    if size > limit:
        direction = "request" if request else "response"
        raise MCPContractValidationError(
            f"{direction} payload exceeds {limit} bytes",
            path="$",
        )


def _validate(value: Any, schema: Mapping[str, Any], *, path: str) -> None:
    if "enum" in schema and value not in schema["enum"]:
        raise MCPContractValidationError(
            f"value must be one of {schema['enum']!r}",
            path=path,
        )

    allowed_types = schema.get("type")
    if isinstance(allowed_types, str):
        allowed = (allowed_types,)
    elif isinstance(allowed_types, Sequence) and not isinstance(allowed_types, (str, bytes)):
        allowed = tuple(str(item) for item in allowed_types)
    else:
        allowed = ()
    if allowed and not any(_matches_type(value, kind) for kind in allowed):
        raise MCPContractValidationError(
            f"expected type {allowed!r}, got {type(value).__name__}",
            path=path,
        )
    if value is None:
        return

    if _matches_type(value, "object") and "object" in allowed:
        _validate_object(value, schema, path=path)
    elif _matches_type(value, "array") and "array" in allowed:
        _validate_array(value, schema, path=path)
    elif _matches_type(value, "string") and "string" in allowed:
        _validate_string(value, schema, path=path)
    elif _matches_type(value, "integer") and "integer" in allowed:
        _validate_number(value, schema, path=path)
    elif _matches_type(value, "number") and "number" in allowed:
        _validate_number(value, schema, path=path)


def _validate_object(value: Mapping[str, Any], schema: Mapping[str, Any], *, path: str) -> None:
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    missing = [name for name in required if name not in value]
    if missing:
        raise MCPContractValidationError(
            f"missing required properties: {sorted(missing)}",
            path=path,
        )
    additional = schema.get("additionalProperties", True)
    unknown = sorted(set(value) - set(properties))
    if unknown and additional is False:
        raise MCPContractValidationError(
            f"unexpected properties: {unknown}",
            path=path,
        )
    for name, item in value.items():
        item_schema = properties.get(name)
        if item_schema is not None:
            _validate(item, item_schema, path=f"{path}.{name}")
        elif isinstance(additional, Mapping):
            _validate(item, additional, path=f"{path}.{name}")


def _validate_array(value: Sequence[Any], schema: Mapping[str, Any], *, path: str) -> None:
    if isinstance(value, (str, bytes, bytearray)):
        raise MCPContractValidationError("expected array", path=path)
    if "minItems" in schema and len(value) < int(schema["minItems"]):
        raise MCPContractValidationError("array has too few items", path=path)
    if "maxItems" in schema and len(value) > int(schema["maxItems"]):
        raise MCPContractValidationError("array has too many items", path=path)
    if schema.get("uniqueItems"):
        fingerprints = [
            json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False)
            for item in value
        ]
        if len(fingerprints) != len(set(fingerprints)):
            raise MCPContractValidationError("array items must be unique", path=path)
    item_schema = schema.get("items")
    if isinstance(item_schema, Mapping):
        for index, item in enumerate(value):
            _validate(item, item_schema, path=f"{path}[{index}]")


def _validate_string(value: str, schema: Mapping[str, Any], *, path: str) -> None:
    if "minLength" in schema and len(value) < int(schema["minLength"]):
        raise MCPContractValidationError("string is shorter than minLength", path=path)
    if "maxLength" in schema and len(value) > int(schema["maxLength"]):
        raise MCPContractValidationError("string is longer than maxLength", path=path)
    pattern = schema.get("pattern")
    if pattern and re.fullmatch(str(pattern), value) is None:
        raise MCPContractValidationError("string does not match required pattern", path=path)


def _validate_number(value: int | float, schema: Mapping[str, Any], *, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise MCPContractValidationError("number must be finite", path=path)
    if "minimum" in schema and value < schema["minimum"]:
        raise MCPContractValidationError("number is below minimum", path=path)
    if "maximum" in schema and value > schema["maximum"]:
        raise MCPContractValidationError("number is above maximum", path=path)


def _matches_type(value: Any, kind: str) -> bool:
    if kind == "null":
        return value is None
    if kind == "object":
        return isinstance(value, Mapping)
    if kind == "array":
        return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False
