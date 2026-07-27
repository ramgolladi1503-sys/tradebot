# Agentic QA 70-Control Evidence Auditor v1

mode: REVIEW
candidate_id: AGENTIC-QA-70-CONTROLS-V1
decision: DRAFT_REVIEW_REQUIRED
reason: Add a fail-closed, read-only evidence-auditing control plane without changing TradeBot live execution architecture.
timestamp: 2026-07-18T06:15:00+05:30
is_order_action: false
broker_api_called: false
source: agent/tradebot-agentic-qa-70-controls-v1

## Agent Work Contract

Add an isolated `core.agentic_qa` package based on current `main`. Implement exactly 70 deterministic controls, a frozen evidence-bundle interface, advisory-agent validation, focused regression tests, operator documentation, and CI authority checks. Preserve the existing `core.ai_certification` verdict authority and treat missing mandatory evidence as a hard stop.

Primary ownership:

- `core/agentic_qa/**`
- `scripts/run_agentic_qa_audit.py`
- `scripts/build_agentic_qa_evidence.py`
- `tests/agentic_qa/test_evidence_auditor.py`
- `configs/agentic_qa_policy.json`
- `docs/agentic_qa/**`
- `.github/workflows/agentic-qa-evidence-auditor.yml`

## Scope Guard

The branch is additive and based on `main` commit `5d93b51fa74d58ad80751211ca8cf1c6d814c60d`. It does not modify orchestrator, market feed, strategies, ranking, risk, execution, broker integration, `OptionBacktestEngine`, the existing walk-forward implementation, or root dependencies.

The new package has no broker, order, shell, arbitrary database-write, runtime mutation, or Git-write capability. It reads frozen evidence and writes only requested audit outputs. Deterministic code owns the final verdict; agents are advisory only.

## Grill Me Review

1. Can an LLM approve a failed strategy or override a deterministic result?
   - No. Advisory output is rejected when its verdict differs from the deterministic report.
2. Can the package place, cancel, or modify an order?
   - No broker or order tool exists in the package.
3. Can a crafted manifest read files outside the bundle root?
   - No. Absolute paths and parent traversal are rejected before file access.
4. Can artifact content be changed after hashing without detection?
   - No. Expected and observed SHA-256 values are compared and a mismatch rejects the bundle.
5. Can missing WFA or execution evidence be silently treated as passing?
   - No. The adapter maps only grounded values. Missing mandatory keys produce `INSUFFICIENT_EVIDENCE`.
6. Can an agent invent metrics or citations?
   - Unsupported fields, verdict changes, missing citations, and unresolved citations are rejected.
7. Does 70/70 on the synthetic fixture prove structural edge?
   - No. It proves deterministic control behavior only.
8. Does the branch disturb live architecture?
   - No. The changed-file boundary contains only the isolated package, tests, scripts, config, docs, and workflow.

## Hermes Review

- Existing `core.ai_certification` remains the source certification authority.
- `core.agentic_qa` is a read-only evidence and governance sidecar.
- The 70 controls have stable IDs, severities, hard-fail classifications, deterministic rules, and reason codes.
- Frozen artifacts are path-contained, existence-checked, and hash-verified.
- Agent reviews use a closed schema and must agree with the deterministic verdict.
- Recursive secret redaction is applied before advisory content is accepted.
- The adapter refuses to fabricate unavailable evidence.
- The package explicitly withholds profitability and live-readiness claims.

## GSD Review

Implemented:

- seven control domains with ten controls each;
- deterministic fail-closed verdict engine;
- `CONTROL_PLANE_CERTIFIED`, `CONDITIONALLY_CERTIFIED`, `INSUFFICIENT_EVIDENCE`, `REJECTED`, and `AUDITOR_ERROR` outcomes;
- run/bundle manifest support;
- relative-path containment;
- artifact existence and SHA-256 verification;
- canonical bundle digest;
- existing certification-bundle adapter;
- advisory review schema and validation;
- verdict-override and citation guardrails;
- adversarial agent evaluation;
- policy and JSON schemas;
- reproducible CLIs;
- threat model, runbook, scorecard, and 70-point implementation matrix;
- dedicated CI workflow and read-only AST authority scan.

## QA / Safety Review

Focused automated evidence proves:

- the catalog contains contiguous IDs `AQ-01` through `AQ-70`;
- every control has explicit policy metadata;
- a complete fixture evaluates all 70 deterministic controls;
- future-feature access is rejected;
- missing mandatory WFA evidence withholds certification;
- hash tampering is rejected;
- parent-path traversal is rejected;
- a deterministic advisory review is accepted;
- agent verdict override is rejected;
- fabricated evidence citations are rejected;
- five adversarial review mutations are rejected for the expected reason;
- the existing-certification adapter maps known gates and leaves unavailable controls absent;
- package and scripts compile;
- the AST gate denies dynamic execution and non-allowlisted import surfaces.

## High-Risk Path Review

No live high-risk path is modified.

- feed and WebSocket code: unchanged
- strategy formulas and registry: unchanged
- candidate ranking: unchanged
- risk gates and kill switch: unchanged
- execution engine: unchanged
- broker and order APIs: unchanged
- option backtest and WFA engines: unchanged
- production database schemas: unchanged

## Acceptance Proof

Required before merge:

- `PYTHONPATH=. pytest -q -o addopts='' tests/agentic_qa` passes;
- `python -m compileall -q core/agentic_qa` passes;
- both new scripts compile;
- dedicated read-only AST authority gate passes;
- Code Excellence Minerva, Cerberus, and Evidence gates pass;
- Agent Review Evidence Gate passes;
- existing repository `tests`, `ci`, Portfolio CI, CodeQL, and policy gates are green;
- PR diff remains isolated to the declared 25 additive files;
- a real frozen TradeBot certification/WFA bundle is audited before operational claims are made.

## Runtime Proof Required After Merge

1. Export one real frozen strict-WFA evidence bundle from the existing pipeline.
2. Build grounded Agentic QA evidence using the fail-closed adapter.
3. Run all 70 controls and archive the report, hashes, source commit, and policy version.
4. Add secure online-model evaluation and publish measured agent scorecards.
5. Run paper-mode soak and incident drills for stale feed, rejected fills, loss limits, and restart recovery.
6. Obtain named human approval before any controlled-deployment promotion.

## What This PR Does Not Prove

- It does not prove structural edge or profitability.
- It does not prove paper-trading or live-trading readiness.
- It does not prove that manually asserted evidence is true; production evidence must come from deterministic pipeline artifacts.
- It does not claim online LLM quality when online evaluation has not run.
- It does not authorize automated promotion or live orders.

## Human Approval

The pull request remains draft. No automatic merge is authorized. Human review is required after all current-head CI checks are green and the exact diff boundary and real-bundle evidence plan have been reviewed.
