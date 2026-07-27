# TradeBot Agentic QA Evidence Auditor

This package is a read-only control plane over frozen TradeBot research evidence. It does not trade, modify strategies, alter risk controls, call a broker, or own profitability claims.

## Authority model

1. Deterministic code owns every pass/fail decision and the final verdict.
2. Agents may critique, explain, categorize, and recommend the next test.
3. Agents cannot override failed controls or missing evidence.
4. Human approval remains mandatory before promotion to paper or controlled deployment.

## Build evidence from the existing certification bundle

```bash
PYTHONPATH=. python scripts/build_agentic_qa_evidence.py \
  /path/to/frozen/certification_bundle \
  --output-dir .runtime/agentic_qa/source-run-sidecar
```

The adapter maps only facts supported by the frozen source artifacts. It creates a separate hashed sidecar bundle and never modifies the source bundle. Missing facts stay missing and therefore withhold certification.

## Run

```bash
PYTHONPATH=. python scripts/run_agentic_qa_audit.py \
  .runtime/agentic_qa/source-run-sidecar \
  --output .runtime/agentic_qa/audit_report.json \
  --evaluation-output .runtime/agentic_qa/agent_evaluation.json
```

A bundle must contain `run_manifest.json` or the existing `bundle_manifest.json`. The existing exporter format `artifact_path -> sha256` and the explicit `{path, sha256}` format are both supported. Declared artifacts must remain relative to the bundle root. JSON artifacts are merged into the audit context.

## Verdicts

- `CONTROL_PLANE_CERTIFIED`: all 70 controls pass.
- `CONDITIONALLY_CERTIFIED`: only non-hard controls are failed or missing.
- `INSUFFICIENT_EVIDENCE`: a hard control lacks evidence.
- `REJECTED`: a hard control fails.
- `AUDITOR_ERROR`: the auditor could not safely evaluate the bundle.

## Non-claims

A passing control-plane audit does not prove structural edge, profitability, paper-trading readiness, or live-trading readiness. Those require separate evidence and promotion gates.
