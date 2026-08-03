from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping

import requests

from .contracts import (
    AgentAction,
    AgentActionType,
    Assertion,
    ClaimKind,
    FindingProposal,
    Severity,
    ToolRequest,
)

ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action_type", "tool_request", "finding", "stop_reason"],
    "properties": {
        "action_type": {"type": "string", "enum": ["TOOL", "PROPOSE_FINDING", "STOP"]},
        "tool_request": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["tool_name", "arguments", "rationale"],
                    "properties": {
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                        "rationale": {"type": "string"},
                    },
                },
            ]
        },
        "finding": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "title", "stage", "severity", "claim_kind", "narrative", "assertions",
                        "evidence_ids", "business_effect", "recommended_action", "confidence",
                    ],
                    "properties": {
                        "title": {"type": "string"},
                        "stage": {"type": "string"},
                        "severity": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
                        "claim_kind": {"type": "string", "enum": [item.value for item in ClaimKind]},
                        "narrative": {"type": "string"},
                        "assertions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["evidence_id", "path", "operator", "expected"],
                                "properties": {
                                    "evidence_id": {"type": "string"},
                                    "path": {"type": "string"},
                                    "operator": {"type": "string", "enum": ["eq", "ne", "gt", "ge", "lt", "le", "contains", "not_contains", "truthy", "is_none"]},
                                    "expected": {},
                                },
                            },
                        },
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "business_effect": {"type": "string"},
                        "recommended_action": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            ]
        },
        "stop_reason": {"type": "string"},
    },
}

SYSTEM_INSTRUCTIONS = """You are the bounded TradeBot reliability investigator.
You may choose only tools listed in the context. During LIVE_OBSERVE every tool is read-only.
Never claim profitability, causality, or a root cause without evidence. A deterministic factual
finding must include machine-checkable assertions over evidence IDs returned by tools. If evidence
is missing, request a tool or stop with insufficient_evidence. Never request order, broker-write,
threshold-change, restart, patch, merge, or deployment actions. Keep investigations minimal.
"""


class OpenAIReasoner:
    """Responses API reasoner. Output remains untrusted until AssertionVerifier confirms it."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        timeout_sec: float = 30.0,
        post: Callable[..., Any] | None = None,
    ):
        self.model = str(model or os.getenv("TRADEBOT_AGENT_MODEL") or "gpt-5-mini")
        self.api_key = str(api_key or os.getenv("OPENAI_API_KEY") or "")
        self.timeout_sec = float(timeout_sec)
        self._post = post or requests.post
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY_missing")

    def next_action(self, context: Mapping[str, Any]) -> AgentAction:
        body = {
            "model": self.model,
            "store": False,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_INSTRUCTIONS}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(dict(context), sort_keys=True, default=str)}]},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "tradebot_reliability_action",
                    "description": "One bounded reliability-agent action",
                    "schema": ACTION_SCHEMA,
                    "strict": True,
                }
            },
        }
        response = self._post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=self.timeout_sec,
        )
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        data = response.json() if hasattr(response, "json") else response
        raw = _extract_output_text(data)
        parsed = json.loads(raw)
        return _parse_action(parsed)


def _extract_output_text(data: Mapping[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return str(data["output_text"])
    for item in data.get("output") or []:
        if not isinstance(item, Mapping):
            continue
        for content in item.get("content") or []:
            if isinstance(content, Mapping) and isinstance(content.get("text"), str):
                return str(content["text"])
    raise RuntimeError("openai_response_missing_output_text")


def _parse_action(row: Mapping[str, Any]) -> AgentAction:
    action_type = AgentActionType(str(row.get("action_type")))
    tool_request = None
    finding = None
    if isinstance(row.get("tool_request"), Mapping):
        payload = row["tool_request"]
        tool_request = ToolRequest(
            tool_name=str(payload.get("tool_name") or ""),
            arguments=dict(payload.get("arguments") or {}),
            rationale=str(payload.get("rationale") or ""),
        )
    if isinstance(row.get("finding"), Mapping):
        payload = row["finding"]
        assertions = tuple(
            Assertion(
                evidence_id=str(item.get("evidence_id") or ""),
                path=str(item.get("path") or ""),
                operator=str(item.get("operator") or ""),
                expected=item.get("expected"),
            )
            for item in payload.get("assertions") or []
            if isinstance(item, Mapping)
        )
        finding = FindingProposal(
            title=str(payload.get("title") or ""),
            stage=str(payload.get("stage") or ""),
            severity=Severity(str(payload.get("severity") or "P3")),
            claim_kind=ClaimKind(str(payload.get("claim_kind") or ClaimKind.UNVERIFIED_HYPOTHESIS.value)),
            narrative=str(payload.get("narrative") or ""),
            assertions=assertions,
            evidence_ids=tuple(str(item) for item in payload.get("evidence_ids") or []),
            business_effect=str(payload.get("business_effect") or ""),
            recommended_action=str(payload.get("recommended_action") or ""),
            confidence=float(payload.get("confidence") or 0.0),
        )
    return AgentAction(
        action_type=action_type,
        tool_request=tool_request,
        finding=finding,
        stop_reason=str(row.get("stop_reason") or ""),
    )
