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
- Scope: Print bounded, ASCII-safe Git status rows when protected-base checkout cleanliness fails; retain the current fail-closed stop before candidate fetch, archive, or verifier execution.
- Requested paths:
  - `.github/workflows/frozen-head-exact-sha-certification.yml`
  - `tests/governance/test_evidence_contract.py`
  - `docs/agent_reviews/pr972_trusted_base_dirty_checkout_diagnostics.md`
- Allowed paths: the three requested paths above only.
- Forbidden paths/behaviors: broker, order, execution, risk, strategy, credentials, secrets, live configuration, live runtime behavior, gate bypasses, candidate execution, or changes outside the allowed paths.
- Expected tests: exercise the extracted workflow step on clean, dirty tracked, dirty untracked, excessive-row, oversized-row, and invalid-byte fixtures; prove dirty state prevents fetch/archive/output and that file contents/secrets are not logged.
- Acceptance proof: local `tests/governance/test_evidence_contract.py` run, exact-head hosted CI, and agent-review evidence validation. Hosted CI for the hardened commit is pending until pushed.

## Scope Guard

Verdict: PASS

- Full base/head SHA checks and exact protected-base HEAD comparison remain unchanged.
- Dirty checkout remains a hard failure before candidate fetch, candidate archive, candidate-root creation, or `GITHUB_OUTPUT` write.
- Diagnostics are status metadata only: no file contents or candidate payload are read.
- No credentials, secrets, broker APIs, orders, execution, risk gates, strategies, or live behavior are changed.
- The gate is not waived, skipped, or reported as passing on dirty state.

## High-Risk Path Review

Verdict: NOT APPLICABLE

No trading runtime, feed implementation, broker, execution, order, risk, strategy, credential, or live configuration path is changed. The workflow edit only improves the error detail for an existing CI preflight.

## Grill Me Review

Verdict: PASS

An independent read-only adversarial review confirmed the diff retains the fail-closed sequence, does not add a bypass or fake pass, and logs only status metadata before exiting. The review flagged missing explicit output-bound coverage; that gap was addressed with tests for 22 dirty rows and a long path. The diagnostic's root runner-side cause remains unknown until the updated workflow runs from protected `main` and emits the path rows.

## Hermes Review

Verdict: PASS

The acceptance invariants are:

1. Dirty protected-base state stops before fetch, archive, candidate directory creation, output, and verifier execution.
2. At most 20 status rows are printed; each rendered row is ASCII-safe and at most 512 characters, and additional rows are counted.
3. Status rows are escaped; file content, environment values, and secrets are not printed.
4. Clean checkouts still validate exact SHAs, fetch the requested candidate SHA, and archive it as inert data.

The check caps emitted diagnostics; `git status` output is still buffered before formatting, as it was for the prior boolean cleanliness check. This does not change gate behavior or introduce an unbounded log.

## GSD Review

Verdict: PASS

Implemented only the workflow diagnostic and behavioral tests, plus this required PR evidence packet. Tests execute the actual shell step extracted from the workflow. No runtime wiring, live-mode changes, broker calls, or gate changes were introduced.

## QA / Safety Review

Verdict: PASS

Independent QA re-review confirmed the fail-closed order and the rendered-output bounds. Tests now cover modified and untracked paths, newline escaping, 22 dirty entries, long-row truncation, content and environment-sentinel non-disclosure, no fetch/archive/output on dirty state, and a non-UTF-8 path where supported. The non-UTF-8 fixture is skipped only when the local filesystem rejects such a filename with `EILSEQ`.

No live, broker, order, risk, credential, or strategy behavior is affected.

## Acceptance Proof

Local validation on this worktree:

```bash
python3 -m pytest -q -p no:cacheprovider -c /dev/null --confcutdir=tests/governance tests/governance/test_evidence_contract.py
git diff --check
```

Results:

- Evidence-contract suite: 86 passed, 1 skipped (local macOS filesystem rejects non-UTF-8 path bytes).
- `git diff --check`: passed.
- Exact-head hosted CI for the hardened commit: pending; earlier PR #972 CI failed this mandatory evidence-file check before this packet existed and does not validate the hardened tests.

## Runtime Proof Required After Merge

After this PR is merged into protected `main`, rerun the trusted-base evidence coverage for PR #971 against that updated base. Confirm the diagnostic identifies the dirty status rows while the gate still exits before candidate preparation. Investigate and fix any runner-side dirty paths in a separate scoped change; do not bypass or soften the clean-checkout check.

## What This PR Does Not Prove

1. It does not identify the underlying reason the hosted protected-base checkout was dirty; that requires the new log output from a run using the updated base workflow.
2. It does not make PR #971's existing trusted-base failure pass.
3. It does not certify live readiness, market-feed recovery, strategy behavior, profitability, or broker/order behavior.
4. It does not waive PR #971's separate check or review requirements.

## Human Approval

Normal GitHub review and branch-protection requirements remain in force. No human approval or merge has been recorded for this PR.
