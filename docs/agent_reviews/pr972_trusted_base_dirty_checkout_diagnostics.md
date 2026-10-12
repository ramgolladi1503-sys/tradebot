# PR #972 — Trusted-Base Dirty Checkout Diagnostics

## Evidence Contract Fields

- mode: CI_DIAGNOSTICS_ONLY
- candidate_id: pr972-trusted-base-dirty-checkout-diagnostics
- decision: REVIEW_ONLY
- reason: Make the existing protected-base clean-checkout refusal diagnosable without weakening its gate.
- source_agent: codex
- action: GENERATE_PATCH
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- PR: #972
- Branch: `ram/trusted-base-dirty-checkout-diagnostics`
- Scope: Run a bounded, fail-closed protected-base cleanliness probe; print bounded, ASCII-safe Git status rows on dirty checkout; retain the stop before candidate fetch, archive, or verifier execution.
- Requested paths:
  - `.github/workflows/frozen-head-exact-sha-certification.yml`
  - `tests/governance/test_evidence_contract.py`
  - `docs/agent_reviews/pr972_trusted_base_dirty_checkout_diagnostics.md`
- Allowed paths: the three requested paths above only.
- Forbidden paths/behaviors: broker, order, execution, risk, strategy, credentials, secrets, live configuration, live runtime behavior, gate bypasses, candidate execution, or changes outside the allowed paths.
- Expected tests: exercise the extracted workflow step on clean, dirty tracked, dirty untracked, nested untracked directory, excessive-row, oversized-row, invalid-byte (where supported), timeout, invalid timeout, status-error/control-character stderr, and over-cap stdout fixtures; prove unsafe states prevent fetch/archive/output and that file contents/secrets are not logged.
- Acceptance proof: focused local behavior tests and `git diff --check`; exact-head hosted CI and agent-review evidence validation are required after push. Existing hosted run executes the old protected-base workflow and cannot validate these unpushed changes.

## Scope Guard

Verdict: PASS

- Full base/head SHA checks and exact protected-base HEAD comparison remain unchanged.
- Dirty checkout remains a hard failure before candidate fetch, candidate archive, candidate-root creation, or `GITHUB_OUTPUT` write.
- Diagnostics are status metadata only: no file contents or candidate payload are read. Git status stdout is streamed to a runner temporary file with a 1 MiB hard cap; stderr is discarded. The probe timeout defaults to 30 seconds and accepts only finite values in `(0, 300]` from `TRUSTED_CHECKOUT_STATUS_TIMEOUT_SECONDS`. The complete candidate-preparation step has a 15-minute workflow timeout. Invalid timeout values, output overflow, Git errors, and timeouts fail closed before fetch/archive/output.
- No credentials, secrets, broker APIs, orders, execution, risk gates, strategies, or live behavior are changed.
- The gate is not waived, skipped, or reported as passing on dirty state.

## High-Risk Path Review

Verdict: NOT APPLICABLE

No trading runtime, feed implementation, broker, execution, order, risk, strategy, credential, or live configuration path is changed. The workflow edit only improves the error detail for an existing CI preflight.

## Grill Me Review

Verdict: PASS

The final adversarial review confirmed streamed status output is capped at 1 MiB, the full candidate-preparation step has a 15-minute timeout, malformed or unbounded probe timeouts fail closed, Git stderr is suppressed, and dirty/error/timeout/overflow states stop before fetch/archive/output. The diagnostic's root runner-side cause remains unknown until the updated workflow runs from protected `main` and emits the path rows.

## Hermes Review

Verdict: PASS

The acceptance invariants are:

1. Dirty protected-base state stops before fetch, archive, candidate directory creation, output, and verifier execution.
2. At most 20 status rows are printed; each rendered row is ASCII-safe and at most 512 characters, and additional rows are counted.
3. Status rows are escaped; file content, environment values, and secrets are not printed.
4. Clean checkouts still validate exact SHAs, fetch the requested candidate SHA, and archive it as inert data.

The checker streams status output into a temporary file capped at 1 MiB instead of retaining it in shell memory. Git stderr is sent to `DEVNULL`, so subprocess diagnostics and control characters are never echoed. The checker prints at most 20 escaped rows, truncates each rendered row to 512 characters, and fails closed on invalid timeout, output overflow, timeout, or status-command errors before candidate preparation. The enclosing step also has a 15-minute limit.

## GSD Review

Verdict: PASS

Implemented only the workflow diagnostic and behavioral tests, plus this required PR evidence packet. Tests execute the actual shell step extracted from the workflow. No runtime wiring, live-mode changes, broker calls, or gate changes were introduced.

## QA / Safety Review

Verdict: PASS

Independent QA re-review confirmed the fail-closed order and the rendered-output bounds. Tests cover modified and untracked paths, nested-directory collapsing, newline escaping, 22 dirty entries, long-row truncation, finite-timeout validation, timeout, status errors with control characters, stdout cap overflow, content and environment-sentinel non-disclosure, no fetch/archive/output on unsafe status, and a non-UTF-8 path where supported. The non-UTF-8 fixture is skipped only when the local filesystem rejects such a filename with `EILSEQ`.

No live, broker, order, risk, credential, or strategy behavior is affected.

## Acceptance Proof

Local validation on this worktree:

```bash
python3 -m pytest -q tests/governance/test_evidence_contract.py -k 'trusted_candidate_prep or trusted_evidence_workflow_does_not_persist_checkout_credentials'
git diff --check
```

Results:

- Trusted-candidate-preparation focused tests: 19 passed, 1 skipped, 77 deselected. The skip is the existing non-UTF-8-path fixture on a filesystem that rejects that path.
- `git diff --check`: passed.
- Exact-head hosted CI for the hardened commit: pending until pushed. The currently running trusted-base check was launched using the old protected-base workflow and is recorded UNVERIFIED for this patch; it is not a pass.

## Runtime Proof Required After Merge

After this PR is merged into protected `main`, rerun the trusted-base evidence coverage for PR #971 against that updated base. Confirm the diagnostic identifies the dirty status rows while the gate still exits before candidate preparation. Investigate and fix any runner-side dirty paths in a separate scoped change; do not bypass or soften the clean-checkout check.

## What This PR Does Not Prove

1. It does not identify the underlying reason the hosted protected-base checkout was dirty; that requires the new log output from a run using the updated base workflow.
2. It does not make PR #971's existing trusted-base failure pass.
3. It does not certify live readiness, market-feed recovery, strategy behavior, profitability, or broker/order behavior.
4. It does not waive PR #971's separate check or review requirements.

## Human Approval

The user authorized merging PR #972 with its trusted-base check UNVERIFIED after all other required checks pass. This is not a check waiver or a pass claim. The repository's main-branch approval requirements were separately changed by explicit user authorization; the required status checks remain in force.
