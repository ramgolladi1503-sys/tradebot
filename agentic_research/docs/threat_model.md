# Threat model

## Protected assets

- Broker credentials and API keys
- Production strategy parameters
- Risk limits and execution gates
- Historical evidence integrity
- Certification verdict integrity
- Research budget and tool-call limits

## Major threats and controls

| Threat | Example | Control |
| --- | --- | --- |
| Prompt injection in repository content | Instruction text tries to force approval | Treat text as untrusted evidence; sanitize patterns; structured action enum |
| Metric fabrication | LLM invents profit factor | Metrics originate only from deterministic tools and carry hashes |
| Authority escalation | Planner requests a forbidden action | Allow-list plus manager rejection; no matching MCP tool exists |
| Judge override | Critic says approve | Deterministic judge owns the verdict and maps blocker categories explicitly |
| Duplicate expensive work | Restart repeats WFA | SQLite idempotency key over research ID, tool and canonical arguments |
| Data laundering | Zero-volume corpus used for volume claim | Dataset and legacy-report gates fail closed |
| Automated overfitting | Agent searches thousands of combinations | Maximum three proposals; no auto-execution; human approval required |
| Repeating dead hypotheses | Same idea renamed | Durable semantic fingerprint excludes proposal ID and status |
| Secret leakage to model | State contains credentials | Secret-bearing keys removed from model evidence view |

## Residual risks

- Pattern-based prompt-injection filtering is not a complete security boundary. The primary control is tool allow-listing and deterministic authority separation.
- An online model evaluation must be rerun after model or prompt changes.
- Local users with filesystem access can alter evidence; immutable external artifact storage and signed manifests are later hardening work.
