# Governed Research and Exact Registry Pipeline Review

mode: RESEARCH
candidate_id: STRATEGY_PIPELINE_RESEARCH_REGISTRY_V1
decision: DRAFT_REVIEW_REQUIRED
reason: Replace the blocked Research stage and fake Registry success with exact governed inputs, signed stage artifacts, and cryptographic upstream lineage.
timestamp: 2026-07-22T18:40:00Z
is_order_action: false
broker_api_called: false
source: agent/strategy-pipeline-research-registry-v1

## Agent Work Contract

Implement only the first two engine-specific repairs above the truthfulness foundation. Research must accept exactly one integrity-valid governed run manifest and its frozen hypothesis. Registry must accept exactly one declared strategy implementation file and the signed Research result manifest from the same pipeline run. Both stages must emit run-scoped artifacts and internally hashed engine result manifests.

## Scope Guard

In scope: common adapter runtime, governed Research adapter and command, exact Registry adapter and command, pipeline wiring for those commands, exact argument enforcement, Research-to-Registry manifest chaining, verified blocked diagnostic artifacts inherited from the foundation, and focused behavioral tests.

Out of scope: strategy signal logic, thresholds, broker APIs, order actions, live mode, risk or feed behavior, dashboards, Truth-engine formula comparison, outcome replay, statistics, certification, and Drift.

Changed files are limited to `core/strategy_pipeline`, two research-only scripts, strategy-pipeline tests, and this review document. Existing governed research and strategy contract models are consumed but not weakened.

## Grill Me Review

- Can Research use an arbitrary legacy hypothesis inventory? No. It requires the exact `manifest.json` and `hypothesis_frozen.json` from one governed research run.
- Can a hypothesis modified after freezing pass? No. The governed event chain and hypothesis contract hash are independently verified.
- Can Research accept an extra undeclared file? No. Its input set must equal the governed manifest and frozen hypothesis paths exactly.
- Can Registry scan for a convenient implementation? No. The caller must declare one exact Python file under `strategies/`, and its SHA-256 is bound into the result.
- Can Registry consume an unrelated or stale Research report? No. It requires the signed `research.result.json` for the same strategy and pipeline run, then verifies the Research output artifact hash and decision.
- Can a future Truth mismatch be retained without weakening fail-closed behavior? Yes, but only as a hash-verified blocked diagnostic artifact.
- Does Registry certification prove the implementation matches its rules? No. That remains the responsibility of the next Truth stage.

## Hermes Review

Both adapters accept only `RESEARCH` or `PAPER` execution mode. Result manifests are constrained to `runtime/strategy_pipeline/<strategy>/<run>/`. No broker client, execution engine, order function, live configuration, risk gate, feed gate, or dashboard action is imported or modified. Every output states that live execution is unavailable.

## GSD Review

The old Research stage was permanently blocked despite a governed research store existing, while Registry could return SUCCESS without executing an adapter. This change makes both stages real and narrow: Research proves frozen pre-outcome integrity; Registry proves one canonical strategy contract and file lineage. Their signed manifests form the first two links of the repaired pipeline chain.

## QA / Safety Review

Focused local validation:

- `PYTHONPATH=. pytest -q tests/strategy_pipeline/test_pipeline_engine.py tests/strategy_pipeline/test_pipeline_blocked_artifacts.py tests/strategy_pipeline/test_research_registry_stage_adapters.py` -> `30 passed`.

Covered behavior includes forged input hashes, governed-hypothesis tampering, undeclared Research scope, signed Research result creation, unrelated Registry upstream rejection, exact implementation file hashing, contract hashing, same-run lineage, live-authority denial, argument enforcement, upstream manifest chaining, verified blocked diagnostic artifacts, blocked diagnostic tampering, and the full foundation regression suite.

Full repository CI and governance gates must pass on one immutable stacked PR head.

## Acceptance Proof

Acceptance requires the focused 30-test suite, Python compilation, direct Research command smoke, direct Registry command smoke, and every repository workflow to pass. The Research smoke must produce `FROZEN_HYPOTHESIS_VERIFIED`. The Registry smoke must produce `CANONICAL_STRATEGY_CONTRACT_VERIFIED`. A tampered hypothesis, wrong strategy file, wrong run ID, changed input hash, unrelated Research manifest, or tampered blocked diagnostic artifact must fail closed.

## Runtime Proof Required After Merge

Create a disposable governed run, freeze a hypothesis, and declare its manifest and hypothesis files as exact Research inputs. Run Research and retain its signed manifest. Then declare one exact strategy implementation file as the Registry external input; the orchestrator must add the Research manifest hash automatically. Confirm the next Truth stage blocks until it receives its own repaired adapter and signed evidence contract.

## What This PR Does Not Prove

This change does not prove structural edge, profitability, market-data quality, causal signal implementation, realistic fills, costs, statistical significance, WFA, holdout results, certification, paper performance, or Drift readiness. It proves only governed Research integrity and canonical Registry lineage.

## Human Approval

Human review is required before merge. This stacked PR grants no paper or live trading authority, performs no automatic merge, and cannot call a broker or create an order action.
