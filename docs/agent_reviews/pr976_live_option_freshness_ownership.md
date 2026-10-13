# PR #976: Live Option Freshness Ownership Review

## Agent Work Contract

- `source_agent`: `grill_me`, `hermes`, and `gsd` stages were applied by role-assigned agents; role identities are not cryptographically authenticated.
- `action`: `AUDIT_RISK`, `DEFINE_CONTRACT`, `GENERATE_PATCH`, `GENERATE_TESTS`, and `FIX_TEST_FAILURE`.
- `title`: Bind option freshness to confirmed local subscription ownership.
- `scope`: `core/kite_depth_ws.py`, the installed `core/depth_subscription_engine.py` path, focused regression tests, and claim/work-item evidence.
- `requested_paths`: the runtime and test paths listed in the work item.
- `allowed_paths`: the exact set in the work item; no credentials, order/broker, strategy, risk-gate, or live configuration path changed.
- `forbidden_paths`: `main.py`, `run_live.sh`, credentials, broker/order paths, risk gates, strategies, and `runtime/live/`.
- `expected_tests`: the targeted callback, stability, refresh, token, launch-universe, and evidence-contract pytest command recorded in the work item.
- `acceptance_proof`: 249 passed and 1 skipped in the targeted suite; compile, evidence JSON parsing, and `git diff --check` passed locally. Remote exact-head CI is tracked separately and is not claimed green here.

## Scope Guard

The change separates desired resolver proposals from applied subscription truth. Option freshness consumes only validated CE/PE contracts in a `KNOWN` snapshot for the current socket generation. Cash observation tokens retain their observation mapping and cannot satisfy option freshness. Local subscribe/FULL-mode calls do not prove remote exchange delivery.

No orders or broker APIs were called. No credentials, environment files, risk gates, strategy thresholds, or live configuration were modified. No live process was restarted or stopped.

## Grill Me Review

The adversarial review initially found that launch-plan activation cleared production token-to-symbol mappings and that pre-prune resolver rows could include tokens outside the final subscription. Both findings were fixed by constructing production-only launch metadata from the post-prune, post-budget set. The final review confirmed the production mapping, cash observation mapping, index-only mutation, and proposal-versus-applied assertions. The initial source review reported no blocking implementation finding; the test-proof follow-up identified a reconnect assertion gap, which is now covered by explicit ownership assertions.

## Hermes Review

The contract is generation-bound and fail-closed: a candidate build changes only desired identities; `KNOWN` is published only after complete synchronous local API reconciliation; disconnect, stale generation, queued, partial, or failed mutation paths remain `UNKNOWN`. The installed sidecar passes a canonical production-only resolution to launch-plan activation and adds observation identities separately. The implementation does not claim broker or exchange delivery.

## GSD Review

The implementation covers callback ownership checks, sidecar staging and freshness readers, serialized subscription mutations, close/error/reconnect invalidation, and `on_connect` failure-state preservation. Regression coverage includes invalid/unknown ownership, queued and partial mutations, stale generation, sidecar proposal isolation, pruned production options, index-only mutations, reconnect, and failed replay. No unrelated runtime subsystem was edited.

## QA / Safety Review

The original implementation-focused targeted suite completed with 249 passed and 1 skipped. After aligning legacy regression fixtures, the five affected test files passed 177 tests, and the added reconnect-ownership assertions passed in a 15-test candidate/reconnect run. Modified Python modules and test modules compiled. Three evidence JSON documents parsed, and `git diff --check` passed. The full expanded focused command was interrupted by the execution session ending without a captured result; do not treat it as passed. Independent review found and closed the sidecar mapping issue before the candidate was committed.

The first broad run exposed legacy fixture failures because those tests inferred applied option truth from token-to-symbol mappings. Fixtures were updated to establish a KNOWN snapshot where their assertions require applied option health; tests that lack applied ownership retain fail-closed expectations. The post-fix local five-file regression slice reported 177 passed. A broader focused command including mutation, token, launch-universe, and evidence-contract tests was attempted, but the execution session ended without a captured result. Its outcome is unknown and must not be represented as a pass.

Independent QA noted that some state-rendering fixtures seed KNOWN via the private commit helper without exercising socket API methods, and the candidate-safety test stubs the observed adapter callback. These are fixture/interface checks only. Separate mutation tests exercise subscribe and FULL mode calls and assert resulting ownership. The reconnect test now additionally asserts KNOWN state, the active generation, and exact expected option token identities. Do not characterize every fixture as proof of API application.

## Current PR / CI Status

At committed head `a683240ca3c374e365fb2748377cdf2e6b65f713`, GitHub `unit_tests` failed 16 tests and Trusted Base failed for incomplete lifecycle history/state/evidence. The local test-only corrections have not yet been pushed or run by GitHub. The `pr818-live-flow-freeze-target` check also fails; the user explicitly authorized ignoring that check. No authorization was given to bypass unit-test failures or Trusted Base. Exact-head CI and delivery lifecycle remain blockers.

## Acceptance Proof

- Observation cash ticks cannot enter option freshness.
- Option readers intersect only the current-generation KNOWN contract snapshot.
- Proposal construction preserves the prior applied snapshot.
- Queued, failed, partial, disconnected, and stale-generation mutation paths do not publish KNOWN.
- Index-only subscription mutation preserves option ownership.
- Failed connect replay remains `SUBSCRIBE_FAILED`.
- Production symbol identity survives installed sidecar launch-plan activation after prune/budget filtering.

## Runtime Proof Required After Merge

After merge, an independently authorized observation run must confirm that selected CE/PE ticks update freshness, observation cash ticks do not, and reconnect/mutation failures remain blocked until a new full replay is locally confirmed. Capture the deployed commit, process identities, socket generation, and evidence hashes. This PR alone does not authorize or perform a restart.

## What This PR Does Not Prove

It does not prove exchange delivery, overall feed readiness, strategy correctness, live restart safety, or that any currently running process loaded this code. It does not resolve the separate tick-store WAL checkpoint-busy observation. The material implementation claim remains `UNVERIFIED` pending delivery lifecycle and exact-head CI evidence.

## Human Approval

The user explicitly approved expanding the scoped fix across `core/kite_depth_ws.py` and `core/depth_subscription_engine.py`, authorized opening a PR, and later authorized automatic merge when the PR is mergeable, with the PR818 check ignored. This does not authorize bypassing other failing checks or incomplete Trusted Base evidence, and does not authorize restarting the live process.

## High-Risk Path Review

`core/kite_depth_ws.py` and `core/depth_subscription_engine.py` are feed/WebSocket paths. The change narrows freshness attribution and makes uncertain subscription state fail closed. It preserves feed freshness and mutation guards, adds no broker/order action, and does not alter live mode, credentials, risk thresholds, or kill switches. Rollback is a normal revert of this PR; no runtime state is changed by reverting the source.
