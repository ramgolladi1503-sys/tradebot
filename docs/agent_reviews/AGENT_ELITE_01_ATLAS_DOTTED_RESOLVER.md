# AGENT-ELITE-01 — Atlas Dotted Runtime Function Resolver

mode: REVIEW
candidate_id: AGENT-ELITE-01-ATLAS-DOTTED-RUNTIME-RESOLVER
decision: review_pending
reason: atlas_static_runtime_wiring_dotted_symbol_resolution
timestamp: 2026-05-28T11:10:00Z
source: docs/agent_reviews/AGENT_ELITE_01_ATLAS_DOTTED_RESOLVER.md
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #373
Parent: #372

## Agent Work Contract

This PR implements AGENT-ELITE-01 only.

The work improves Atlas runtime-wiring static analysis so dotted configured runtime symbols are resolved as the longest existing module prefix plus an optional function/class symbol. It must not import Tradebot runtime modules, execute startup code, call brokers, place orders, change strategies, alter ranking, or modify dashboard behavior.

## Scope Guard

Allowed:

- Update `tools/repo_forensics/runtime_wiring.py`.
- Add focused tests in `tests/test_repo_forensics_runtime_wiring.py`.
- Add this agent-review evidence file.

Not allowed:

- Runtime execution.
- Broker calls.
- Live order behavior.
- Strategy/ranking behavior changes.
- Dashboard/UI changes.
- Broad repo-forensics refactor.
- Test skip/xfail.

## High-Risk Path Review

This PR touches static repo-forensics tooling only.

High-risk Tradebot paths intentionally unchanged:

- `core/kite_client.py`
- `core/execution_engine.py`
- `core/execution_router.py`
- `core/risk_engine.py`
- `core/orchestrator.py`
- `strategies/`
- `dashboard/`
- `config/`

The scanner still reads files statically and does not import target runtime modules.

## Grill Me Review

Question: Does this PR make runtime startup green?

Answer: No. It only removes scanner false failures for dotted function/class references. Real missing modules or symbols still fail.

Question: Could this hide a missing symbol?

Answer: No. If a module exists but the configured symbol is missing, the status is `FAIL` with `symbol_missing:<module_path>:<symbol>`.

Question: Could this call broker/live code?

Answer: No. Symbol detection uses file reads and `ast.parse`; it does not import the module.

Question: Is this too broad?

Answer: No. The patch is limited to Atlas runtime-wiring resolution and focused tests.

## Hermes Review

The contract is intentionally narrow:

- Shell and explicit file paths preserve file-exists behavior.
- Dotted runtime paths resolve using the longest existing module prefix.
- Remaining dotted suffix is treated as a symbol path.
- Existing module without symbol passes as module presence proof.
- Existing module with missing symbol fails.
- Unknown non-dotted references remain `UNKNOWN`, not fake `PASS`.

## GSD Review

Smallest safe implementation:

- Add immutable `DottedStepResolution` result object.
- Replace naive dotted split with longest-existing-module-prefix lookup.
- Keep all checks static/read-only.
- Add tests for function, class, missing symbol, missing module, and shell entrypoint behavior.

Files changed:

- `tools/repo_forensics/runtime_wiring.py`
- `tests/test_repo_forensics_runtime_wiring.py`
- `docs/agent_reviews/AGENT_ELITE_01_ATLAS_DOTTED_RESOLVER.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_runtime_wiring.py -q
```

Recommended gate command:

```bash
PYTHONPATH=. python scripts/run_repo_forensics_pr_gate.py --repo . --config .gsd-forensics.yaml
```

Safety assertions:

- No runtime import of target modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard changes.

## Acceptance Proof

The tests added/updated prove:

- dotted function symbol resolves to `symbol_defined:<module_path>:<function>`
- dotted class symbol resolves to `symbol_defined:<module_path>:<class>`
- missing module still reports `module_file_missing`
- existing module with missing symbol reports `symbol_missing`
- shell entrypoint file checks remain unchanged

## Runtime Proof Required After Merge

No live runtime proof is required for this PR. This is static scanner behavior only.

After merge, repo-forensics baseline/runtime wiring output should show fewer false module-file-missing findings for configured dotted function/class references.

## What This PR Does Not Prove

- Does not prove live startup succeeds.
- Does not prove broker readiness.
- Does not prove candidate quality.
- Does not prove ranking correctness.
- Does not prove profitability.
- Does not prove EDGE-98 historical dataset behavior.

## Human Approval

Required before merge.
