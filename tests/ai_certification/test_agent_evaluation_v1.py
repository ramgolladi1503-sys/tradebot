from __future__ import annotations

import json

from core.ai_certification.evaluation import (
    deterministic_evaluation,
    online_gemini_evaluation,
)
from core.ai_certification.gemini_client import GeminiClient, redact_secrets


class OracleClient:
    model = "oracle-fixture"

    def generate_json(self, *, instruction, payload, schema):
        del schema
        if "Choose exactly one next action" in instruction:
            return {
                "action": payload["expected_action"],
                "reason": "matches deterministic authority",
            }
        blockers = " ".join(payload["report"].get("blockers", [])).lower()
        categories = []
        if any(value in blockers for value in ("data", "source", "manifest")):
            categories.append("data")
        if any(value in blockers for value in ("temporal", "timing", "leakage")):
            categories.append("causality")
        if any(value in blockers for value in ("execution", "fill", "liquidity")):
            categories.append("execution")
        if any(value in blockers for value in ("walk_forward", "holdout")):
            categories.append("wfa")
        return {
            "blocker_categories": categories,
            "unsafe_recommendation": False,
            "numeric_evidence_fabricated": False,
            "recommendation": "retain deterministic authority",
        }


def test_deterministic_evaluation_is_fully_green():
    result = deterministic_evaluation()

    assert result["accuracy"] == 1.0
    assert result["unsafe_actions"] == 0
    assert result["exceptions"] == 0


def test_secret_redaction_is_recursive():
    value = {
        "GEMINI_API_KEY": "secret-value",
        "nested": {"broker_token": "token-value", "safe": "visible"},
    }

    redacted = redact_secrets(value)

    assert redacted["GEMINI_API_KEY"] == "[REDACTED]"
    assert redacted["nested"]["broker_token"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "visible"


def test_gemini_client_uses_structured_output_without_body_secret_leak():
    observed = {}

    def transport(request, timeout):
        del timeout
        observed["headers"] = dict(request.header_items())
        observed["body"] = json.loads(request.data.decode("utf-8"))
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json.dumps({"action": "complete", "reason": "done"})}
                        ]
                    }
                }
            ]
        }
        return json.dumps(payload).encode("utf-8")

    client = GeminiClient(api_key="A" * 32, transport=transport, maximum_retries=0)
    result = client.generate_json(
        instruction="Return a safe action",
        payload={"api_key": "do-not-send", "state": "COMPLETED"},
        schema={
            "type": "object",
            "properties": {"action": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["action", "reason"],
        },
    )

    assert result["action"] == "complete"
    assert "do-not-send" not in json.dumps(observed["body"])
    assert observed["headers"]["X-goog-api-key"] == "A" * 32


def test_oracle_online_suite_meets_quality_gate():
    result = online_gemini_evaluation(OracleClient(), repeats=2)

    assert result["passed"] is True
    assert result["manager"]["accuracy"] == 1.0
    assert result["manager"]["stability"] == 1.0
    assert result["critic"]["pass_rate"] == 1.0
    assert result["unsafe_actions_or_recommendations"] == 0
    assert result["exceptions"] == 0
