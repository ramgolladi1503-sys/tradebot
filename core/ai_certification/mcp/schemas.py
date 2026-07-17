from __future__ import annotations

from typing import Any

from .contracts import JSON_SCHEMA_DRAFT


def bundle_input_schema() -> dict[str, Any]:
    return object_schema(
        {
            "bundle_id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 200,
                "pattern": r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$",
                "description": "Relative bundle identifier under the allowlisted evidence root.",
            }
        },
        required=("bundle_id",),
    )


def retrieval_input_schema() -> dict[str, Any]:
    return object_schema(
        {
            "query": {"type": "string", "minLength": 1, "maxLength": 2_000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 4},
        },
        required=("query",),
    )


def empty_input_schema() -> dict[str, Any]:
    return object_schema({}, required=())


def inspect_output_schema() -> dict[str, Any]:
    return object_schema(
        {
            "run_id": nullable_string(),
            "strategy_id": nullable_string(),
            "repository_commit": nullable_string(),
            "policy_version": nullable_string(),
            "artifacts": string_array(),
            "bundle_digest": sha256_schema(),
            "available_gates": string_array(),
            "available_tools": string_array(),
            "mcp_contract_version": {"type": "string"},
            "mcp_protocol_version": {"type": "string"},
            "mcp_contract_digest": sha256_schema(),
        },
        required=(
            "run_id",
            "strategy_id",
            "repository_commit",
            "policy_version",
            "artifacts",
            "bundle_digest",
            "available_gates",
            "available_tools",
            "mcp_contract_version",
            "mcp_protocol_version",
            "mcp_contract_digest",
        ),
    )


def gate_output_schema() -> dict[str, Any]:
    return object_schema(
        {
            "gate": {"type": "string", "minLength": 1},
            "status": {
                "type": "string",
                "enum": ["PASS", "FAIL", "UNEVALUATED", "ERROR"],
            },
            "reason_code": {"type": "string", "minLength": 1},
            "summary": {"type": "string", "minLength": 1},
            "mandatory": {"type": "boolean"},
            "evidence_refs": {
                "type": "array",
                "items": object_schema(
                    {
                        "artifact": {"type": "string"},
                        "pointer": {"type": "string"},
                        "sha256": nullable_sha256_schema(),
                    },
                    required=("artifact", "pointer", "sha256"),
                ),
            },
            "details": {"type": "object", "additionalProperties": True},
        },
        required=(
            "gate",
            "status",
            "reason_code",
            "summary",
            "mandatory",
            "evidence_refs",
            "details",
        ),
    )


def retrieval_output_schema() -> dict[str, Any]:
    return object_schema(
        {
            "query": {"type": "string"},
            "results": {
                "type": "array",
                "maxItems": 8,
                "items": object_schema(
                    {
                        "citation": {"type": "string"},
                        "authority": {"type": "integer"},
                        "heading": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    required=("citation", "authority", "heading", "text"),
                ),
            },
        },
        required=("query", "results"),
    )


def certification_output_schema() -> dict[str, Any]:
    return object_schema(
        {
            "report": object_schema(
                {
                    "schema_version": {"type": "string"},
                    "run_id": {"type": "string"},
                    "strategy_id": {"type": "string"},
                    "evidence_certification": {"type": "string"},
                    "strategy_verdict": {"type": "string"},
                    "policy_version": {"type": "string"},
                    "repository_commit": {"type": "string"},
                    "bundle_digest": sha256_schema(),
                    "trace_id": sha256_schema(),
                    "gates": {"type": "object", "additionalProperties": True},
                    "blockers": string_array(),
                    "warnings": string_array(),
                    "knowledge_refs": string_array(),
                },
                required=(
                    "schema_version",
                    "run_id",
                    "strategy_id",
                    "evidence_certification",
                    "strategy_verdict",
                    "policy_version",
                    "repository_commit",
                    "bundle_digest",
                    "trace_id",
                    "gates",
                    "blockers",
                    "warnings",
                    "knowledge_refs",
                ),
            ),
            "outputs": object_schema(
                {
                    "json": {"type": "string"},
                    "markdown": {"type": "string"},
                },
                required=("json", "markdown"),
            ),
        },
        required=("report", "outputs"),
    )


def policy_output_schema() -> dict[str, Any]:
    return object_schema({}, required=(), additional_properties=True)


def object_schema(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...],
    additional_properties: bool = False,
) -> dict[str, Any]:
    return {
        "$schema": JSON_SCHEMA_DRAFT,
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": additional_properties,
    }


def string_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}, "uniqueItems": True}


def nullable_string() -> dict[str, Any]:
    return {"type": ["string", "null"]}


def sha256_schema() -> dict[str, Any]:
    return {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def nullable_sha256_schema() -> dict[str, Any]:
    return {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}
