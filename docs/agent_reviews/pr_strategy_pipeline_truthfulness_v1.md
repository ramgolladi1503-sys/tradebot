# Strategy Pipeline Truthfulness Foundation Review

mode: RESEARCH
candidate_id: STRATEGY_PIPELINE_TRUTHFULNESS_V1
decision: DRAFT_REVIEW_REQUIRED
reason: Replace placeholder success semantics with run-scoped, hash-verified, fail-closed engine contracts before individual engine activation.
timestamp: 2026-07-22T18:00:00Z
is_order_action: false
broker_api_called: false
source: agent/strategy-pipeline-truthfulness-v1

## Agent Work Contract

Repair only the foundational truthfulness layer of `core/strategy_pipeline`. A successful engine must identify the exact run and strategy, bind exact input hashes, emit at least one allowed output artifact, provide output hashes, carry an explicit verdict, and load through an internally hashed result manifest. Missing adapters, missing manifests, wrong lineage, tampering, or bare process exit code zero must block or fail. Each downstream engine must also consume the hash of every required upstream engine result manifest. A blocked, failed, or degraded engine may attach a diagnostic artifact only when its path and SHA-256 also verify.

## Scope Guard

In scope: pipeline context, engine result models, state finalization, run-scoped artifact location, result-manifest integrity, upstream manifest chaining, diagnostic artifact verification, pipeline validator, orchestration command construction, cache validation, Drift separation, and focused regression tests.

Out of scope: broker APIs, order execution, live configuration, risk logic, market feeds, dashboards, strategy thresholds, research hypothesis content, real Registry adapter implementation, statistical formulas, certification gate policy, and live-drift data production.

Files changed are limited to `core/strategy_pipeline/*`, `tests/strategy_pipeline/*`, and this review document. No production trading path is intentionally modified.

## Grill Me Review

- Can a subprocess return code of zero make an engine pass? No. A run-scoped signed result manifest and verified output artifacts are required.
- Can the pipeline reuse any file that happens to exist? No. Cache reuse requires an explicit caller-selected result manifest whose run, strategy, input hashes, internal hash, and outputs validate.
- Can Registry claim it followed Research solely because Research has a SUCCESS state? No. The Registry input contract receives the exact SHA-256 of Research's signed result manifest.
- Can a blocked engine attach an unverified mismatch report? No. Any diagnostic artifact supplied by a non-success result is verified under the same output-path and hash rules.
- Can Outcomes or Statistics choose the newest filesystem artifact? No. Exact caller-provided arguments and inputs are mandatory.
- Can an incomplete or degraded run become global SUCCESS? No. State finalization preserves DEGRADED and blocks incomplete required stages.
- Can initial certification require live Drift evidence? No. Drift is excluded by default and is opt-in for a later lifecycle run.

## Hermes Review

The change remains research-only. `PipelineValidator` rejects LIVE execution mode and LIVE environment variables. Output artifacts must remain under explicitly allowed research/report/runtime roots. The orchestrator does not import broker clients or create order actions. Individual engine scripts remain unable to claim success until they adopt the result-manifest contract.

## GSD Review

The previous orchestrator contained three false-confidence mechanisms: no-op validation, path-existence cache success, and subprocess-exit-code success. It also supplied hard-coded Outcome paths, selected the newest Statistics evidence file, treated Registry as successful without execution, overwrote DEGRADED as SUCCESS, made Drift mandatory during initial certification, did not cryptographically bind downstream stages to upstream evidence, and could not retain verified diagnostic artifacts for blocked stages. This PR removes those behaviors without claiming the individual engines are now certified.

## QA / Safety Review

Focused local validation:

- `PYTHONPATH=. pytest -q tests/strategy_pipeline/test_pipeline_engine.py tests/strategy_pipeline/test_pipeline_blocked_artifacts.py` -> `24 passed`.

The suite covers research-only defaults, LIVE rejection, exact input hashing, missing input failure, run-scoped manifest paths, manifest round-trip, internal manifest forgery, missing artifacts, output tampering, verified blocked diagnostics, blocked diagnostic tampering, DEGRADED preservation, Drift opt-in, upstream manifest lineage binding, exact Outcomes and Statistics arguments, bare zero-exit rejection, missing Registry adapter blocking, invalid mocked success conversion, verified cache reuse, wrong-strategy cache rejection, full verified research-only completion, and truthful blocker propagation.

Full repository CI is required on the immutable PR head before merge.

## Acceptance Proof

Acceptance requires all repository workflows to pass on one immutable head. The focused suite must remain green, no existing safety gate may be weakened, and the changed-file diff must remain within the declared scope. A manual smoke run should block at the first engine that does not emit the new signed result manifest rather than reporting success.

## Runtime Proof Required After Merge

After merge, create a disposable research run with a frozen hypothesis. Confirm that the current Research script exits without a compliant manifest and the pipeline reports `RESULT_MANIFEST_MISSING`. Then repair Research and Registry in a separate PR so they emit valid manifests. Confirm that live execution remains unavailable and no broker interaction occurs.

## What This PR Does Not Prove

This PR does not prove a profitable strategy, structural edge, valid historical data, realistic option fills, statistical significance, WFA stability, holdout performance, certification readiness, or live-drift readiness. It does not complete the Research, Registry, Truth, Outcomes, Statistics, Certification, or Drift engine-specific repairs. It establishes the contract that prevents those later engines from overstating completion.

## Human Approval

Human review is required before merge. This change grants no live execution authority and performs no automatic merge, deployment, broker interaction, or strategy promotion.
