# AI Certification Research Manager v1

## Purpose

The research manager adds durable agentic orchestration around the existing deterministic backtest certifier. It does not replace or weaken the certification gates.

## Authority model

1. A human approves the investigation.
2. The manager selects the next action from a frozen read-only vocabulary.
3. Targeted tools inspect the frozen bundle and evaluate source, causality and execution evidence.
4. The deterministic certifier owns the evidence status and strategy verdict.
5. The critic may explain blockers but cannot change the verdict.

Gemini is optional. When enabled, its action must exactly match the deterministic workflow transition. Any unsupported or out-of-order suggestion is ignored.

## Durable state

`SQLiteResearchStore` persists:

- run state;
- approval state;
- deterministic report and critique;
- an idempotency ledger keyed by run, bundle, action and repository root.

A restarted process resumes without repeating completed expensive actions.

## Allowed actions

- `request_approval`
- `inspect_bundle`
- `validate_source_provenance`
- `validate_temporal_causality`
- `validate_execution_realism`
- `retrieve_policy_context`
- `certify_bundle`
- `critique_report`
- `complete`

The manager has no broker, order, risk override, shell, arbitrary database, code mutation or Git-write action.

## Run

```bash
python scripts/run_ai_certification_research_manager.py \
  --run-id strict-run-001 \
  --bundle-id strict-run-001 \
  --approve
```

Use `--planner gemini` only after setting a rotated `GEMINI_API_KEY`. The key is read from the environment, sent only in the `x-goog-api-key` header and never persisted by the package.
