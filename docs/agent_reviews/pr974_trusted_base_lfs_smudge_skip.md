# PR #974 — Trusted-Base LFS Smudge Skip

## Evidence Contract Fields

- mode: CI_INFRASTRUCTURE_REPAIR
- candidate_id: pr974-trusted-base-lfs-smudge-skip
- decision: REVIEW_ONLY
- reason: Keep exact-SHA candidate preparation inert without hydrating unrelated LFS datasets.
- source_agent: gsd
- action: GENERATE_PATCH
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- PR: #974
- Branch: `ram/trusted-base-lfs-smudge-skip`
- Title: Prevent trusted-base LFS hydration timeout.
- Scope: Set `GIT_LFS_SKIP_SMUDGE=1` only for the trusted candidate-preparation step and assert the guard is present.
- Requested paths:
  - `.github/workflows/frozen-head-exact-sha-certification.yml`
  - `tests/test_frozen_head_exact_sha_workflow.py`
  - `docs/agent_reviews/pr974_trusted_base_lfs_smudge_skip.md`
- Allowed paths: the three requested paths above only.
- Forbidden paths/behaviors: broker, order, strategy, feed runtime, credentials, secrets, live configuration, LFS object mutation, candidate execution, verifier bypass, or changes outside the allowed paths.
- Expected tests: workflow contract test proving the trusted candidate-preparation step sets `GIT_LFS_SKIP_SMUDGE=1` and still uses exact-SHA `git archive` preparation.
- Acceptance proof: focused test suite, agent-review evidence validator, `git diff --check`, and an exact-head protected-base rerun after this workflow reaches `main`.

## Scope Guard

Verdict: PASS

- The workflow continues to validate full event SHAs, checkout HEAD, and clean protected-base state before fetching or preparing the candidate.
- Only LFS smudging during the inert candidate-preparation step is skipped. Git checkout, runtime jobs, and other workflows are unchanged.
- The archive remains bound to `HEAD_SHA`; candidate code is not executed by this step.
- The evidence coverage verifier remains enabled and fail-closed. No required status check is removed or weakened.
- No broker, order, execution, risk, strategy, credential, or live behavior is changed.

## High-Risk Path Review

Verdict: PASS

The change is limited to the protected CI workflow and its contract test. It does not modify trading runtime paths or production configuration. LFS pointer blobs remain the Git-tree representation supplied to the verifier; if that representation is insufficient for a claim, the verifier must fail and the workflow change must be revised rather than bypassed.

## Grill Me Review

Verdict: PASS

Adversarial review of run 38312156241 shows the exact candidate fetch completed, followed immediately by repeated LFS `Downloading ... .parquet` messages during candidate preparation; the step then timed out at 15 minutes. The likely cause is Git LFS smudging while preparing the archive. This patch confines skip-smudge to that preparation step. A post-merge exact-head run must confirm that downloads stop and the trusted verifier still produces its normal result. Any verifier failure remains blocking; this patch does not convert it into a pass.

## Hermes Review

Verdict: PASS

The contract is to evaluate the candidate Git tree at the event's exact SHA as inert data. Git LFS payload hydration is not part of that Git-tree identity and was causing unrelated data downloads. `GIT_LFS_SKIP_SMUDGE=1` leaves pointers at their committed representation during the candidate-preparation step, avoids hydrating every referenced dataset, and does not alter the commit SHA or bypass the trusted verifier. Keep this variable scoped to that step only.

## GSD Review

Verdict: PASS

Implementation changes one environment entry in the trusted candidate-preparation step and adds a focused workflow assertion. No runtime wiring, live-mode change, broker call, order action, or test weakening is included.

## QA / Safety Review

Verdict: PASS

- `tests/test_frozen_head_exact_sha_workflow.py`: 5 passed locally.
- The test confirms the candidate-preparation step sets `GIT_LFS_SKIP_SMUDGE=1` and still archives the exact candidate SHA.
- No data files, LFS objects, credentials, runtime processes, or broker interfaces were changed or accessed.
- The hosted trusted-base check on this bootstrap PR is not treated as proof of the new behavior because it runs the protected workflow from the current base.

## Acceptance Proof

Local validation:

```bash
pytest -q tests/test_frozen_head_exact_sha_workflow.py
git diff --check origin/main...HEAD
```

Results: 5 passed; diff check passed. Hosted checks for the exact PR head are still running. The prior PR #971 trusted-base run timed out while downloading LFS objects; that confirms the failure mode but does not validate this patch.

## Runtime Proof Required After Merge

After this workflow reaches `main`, rerun trusted-base evidence coverage for PR #971 at its exact head. Confirm the candidate-preparation logs contain no bulk LFS downloads, the archive retains the candidate Git-tree representation, candidate preparation completes within its timeout, and the base verifier produces its normal result. Preserve every failure as a failure; do not skip verification or infer live readiness from CI.

## What This PR Does Not Prove

1. It does not prove the new behavior until a trusted-base run executes the updated workflow from `main`.
2. It does not certify the strategy, feed recovery, live readiness, market-data edge, or profitability.
3. It does not waive PR #971's trusted-base requirement or the repository's required unit and health checks.
4. It does not prove that any individual LFS dataset is present, valid, or suitable for research.

## Human Approval

The trusted-base check for this bootstrap PR may remain UNVERIFIED because its event uses the currently protected base workflow, which reproduces the LFS-hydration timeout before this change can apply. The user's prior authorization to merge PR #972 with its trusted-base check UNVERIFIED was specific to #972; no authorization to merge #974 in that state is assumed. Obtain a direct merge decision if this check remains UNVERIFIED after all other required checks pass.
