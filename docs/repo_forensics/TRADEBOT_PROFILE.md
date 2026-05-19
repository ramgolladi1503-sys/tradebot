# TradeBot GSD Forensics Profile

## Purpose

This profile defines the parameters used by all TradeBot repo-forensics and code-excellence agents.

Agent names alone do nothing. Their value comes from strict parameters:

- entrypoints
- critical modules
- expected runtime flows
- protected safety boundaries
- evidence fields
- test reality rules
- root-cause clustering rules
- remediation contract requirements
- production hardening constraints

The canonical machine-readable profile is:

```text
.gsd-forensics.yaml
```

## Why Parameters Were Added in GSD-FOR-02

GSD-FOR-01 established the architecture contract and templates.

GSD-FOR-02 is the correct place to add parameters because agents need project-specific facts before they can scan or judge anything effectively.

Without this profile, the agents would be generic names.

With this profile, they know what TradeBot must protect.

## Real Runtime Facts Used

The profile is based on current TradeBot runtime structure:

- `run_live.sh` validates Kite configuration/token, forces `TRADING_MODE=LIVE` and `EXECUTION_MODE=LIVE`, and starts `main.py`.
- `main.py` runs runtime boot safety, Kite startup credential validation, startup security, readiness checks, and then creates `Orchestrator`.
- `Orchestrator` imports/coordinates market data, trade builder, risk engine, execution guard, execution engine, execution router, review queue, decision pipeline, runtime snapshots, and live monitoring components.
- `dashboard/streamlit_app.py` is a headless-safe dashboard entrypoint that bootstraps `streamlit_app_runtime.py` only when appropriate.
- Recent main includes fallback-contract execution firewall work, so fallback/execution safety is a first-class audit parameter.

## Agent Parameter Summary

| Agent | Parameter Focus |
|---|---|
| Grill Me | fake confidence, weak assumptions, missing proof |
| Hermes | scope, safety, protected boundaries |
| GSD | delivery evidence, next action, gate completion |
| Scope Guard | in-scope/out-of-scope/file boundaries |
| Argus | entrypoints, files, critical modules, dead/duplicate paths |
| Atlas | runtime flow and caller-chain proof |
| Minerva | test reality, fake tests, missing negative tests |
| Cerberus | SIM/PAPER/LIVE, broker boundaries, non-action fields |
| Evidence Auditor | required decision/evidence fields |
| Architecture Drift | stale/duplicate/conflicting paths |
| Ariadne | root-cause clustering and confidence levels |
| Daedalus | remediation contracts and fix boundaries |
| Vulcan | scoped production hardening only after Daedalus contract |

## Critical Entry Points

Required:

```text
run_live.sh
main.py
dashboard/streamlit_app.py
```

Optional / context:

```text
dashboard/streamlit_app_runtime.py
premarket.py
run_all.sh
scripts/run_paper_replay.py
```

## Expected Live Startup Flow

```text
run_live.sh
  -> main.py
  -> enforce_runtime_boot_safety
  -> validate_kite_startup_credentials
  -> run_readiness_check
  -> Orchestrator
  -> run_live_monitoring
```

If risk/readiness/broker/evidence boundaries cannot be proven, the status must be `UNKNOWN`, not `PASS`.

## Candidate-to-Decision Flow

```text
market_data
  -> strategy_signal
  -> candidate_generation
  -> data_quality_gate
  -> candidate_finalization
  -> opportunity_scoring
  -> ranking
  -> no_trade_or_gatekeeper
  -> risk_evaluation
  -> execution_boundary
  -> review_queue_or_evidence
```

Required proof areas:

- fallback policy
- ranking consumed by runtime
- execution boundary non-action evidence
- risk gate before execution
- evidence write path

## Trade Quality Parameters

The profile watches for these known quality issues:

- fallback data becoming executable
- stale feed becoming executable
- ranking output not consumed
- confidence scores clustered too tightly
- raw strategy rows displayed as opportunities
- BUY/SELL imbalance without regime reason
- missing spread/slippage/latency/liquidity consideration

Fallback policy:

```text
fallback data may be displayable
fallback data must not be executable
fallback data must not create broker intent
fallback data must emit a reason
```

## Safety Parameters

Safety rules protect:

- no broker calls from repo-forensics tooling
- no LIVE behavior introduced by scanner/review work
- no paper/SIM path importing live broker placement
- read-only outputs preserve `is_order_action=false`
- read-only outputs preserve `broker_api_called=false`
- LIVE startup requires explicit safety/readiness markers

## Evidence Parameters

Required evidence fields:

```text
mode
candidate_id
decision
reason
timestamp
is_order_action
broker_api_called
source
```

Weak evidence examples:

```json
{"status": "ok", "safe": true}
```

Good evidence must explain what happened, why, whether it was an order action, and whether the broker was called.

## Quality Gates

- CRITICAL blocks merge.
- HIGH requires fix or explicit waiver.
- UNKNOWN requires explanation.
- Shape-only tests cannot be the only proof.
- Every code change requires Scope Guard.
- Every Vulcan hardening patch requires a Daedalus contract.

## What This Profile Does Not Do

This profile does not implement scanners yet.

It provides the project-specific parameters those scanners and review agents need.

Implementation begins in:

```text
GSD-FOR-03 — Repo Cartographer Scanner
```

## Next PR

After GSD-FOR-02:

```text
GSD-FOR-03 — Repo Cartographer Scanner
```

That PR should start reading this profile and producing repo map evidence without importing/executing TradeBot runtime modules.
