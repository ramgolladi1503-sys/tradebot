# CI Test Tiering and Feed Soak Separation

## Agent Work Contract

- mode: OFFLINE_TEST
- candidate_id: ci_test_tiering_feed_soak_separation
- decision: PASS
- reason: ordinary PR workflows exclude feed smoke, extended soak, and certification tiers while dedicated workflows preserve short feed checks and scheduled/manual 50-100/1000-cycle evidence
- timestamp: 2026-07-16T20:55:00+05:30
- is_order_action: false
- broker_api_called: false
- source: pytest.ini, tests/conftest.py, tests/test_feed_soak_tiering_policy.py, and .github/workflows

Objective: prevent certification-grade reconnect resource tests from making every pull request wait for multiple full-suite 100/1000-cycle runs.

## Scope Guard

Intended changes are limited to:

- `pytest.ini`
- `tests/conftest.py`
- `tests/test_feed_soak_tiering_policy.py`
- `.github/workflows/ci.yml`
- `.github/workflows/tests.yml`
- `.github/workflows/feed-smoke.yml`
- `.github/workflows/feed-resource-soak.yml`
- this review document

No production feed, strategy, risk, ranking, execution, broker, or dashboard code is changed. Existing reconnect resource tests remain executable and their assertions are unchanged.

## Grill Me Review

Challenge: does this change hide feed failures from pull requests?

Answer: no. Feed-related paths trigger the short `Feed Smoke` workflow. The 50-100-cycle resource checks run in the `feed_soak` tier, and the 1000-cycle checks run in the `certification` tier. Ordinary unrelated pull requests no longer execute those expensive subprocess profiles twice.

Challenge: can a future contributor accidentally add another long `run_profile` test to the default gate?

Answer: `tests/test_feed_soak_tiering_policy.py` parses the feed resource test module and requires every literal profile with at least 50 cycles to appear in the extended-soak set and every profile with at least 1000 cycles to appear in the certification set.

## Hermes Review

The test ownership contract is explicit:

- default pytest: deterministic non-integration, non-feed-tier tests;
- path-filtered PR feed smoke: short feed lifecycle checks;
- nightly/manual soak: 50-100-cycle resource checks;
- weekly/manual certification: 1000-cycle proofs.

Existing required `ci` and `tests` workflow/job names are preserved to avoid silently breaking branch protection.

## GSD Review

The smallest safe architecture was chosen:

1. register three pytest markers;
2. centrally classify the existing resource module during collection;
3. use exact marker expressions in ordinary workflows;
4. create dedicated feed smoke and resource-soak workflows;
5. cancel obsolete ordinary PR runs after a new commit.

The resource harness and production feed implementation are not redesigned.

## QA / Safety Review

- Long tests are not deleted.
- Assertions and resource thresholds are unchanged.
- Default local `pytest` no longer unexpectedly starts certification profiles.
- Dedicated workflows override default marker options explicitly with `-o addopts=''`.
- Scheduled/manual runs upload their pytest logs even on failure.
- Feed smoke runs only when feed lifecycle, storage, marker, or workflow paths change.
- Ordinary workflow timeout is reduced to 15 minutes so a newly introduced slow default test fails visibly instead of consuming an hour.

## Acceptance Proof

Static contract evidence:

- `pytest.ini` excludes `feed_smoke`, `feed_soak`, and `certification` by default.
- both existing ordinary workflows use the same explicit fast marker expression;
- `Feed Smoke` selects `feed_smoke and not feed_soak and not certification`;
- nightly soak selects `feed_soak and not certification`;
- weekly certification selects `certification`;
- the AST policy test enforces long-profile tier membership;
- Repo Forensics and Code Excellence passed on the initial PR execution;
- the first `Feed Smoke` execution was triggered, proving the path filter recognizes this change.

Final workflow conclusions are recorded by GitHub Actions on PR #658 before merge approval.

## Runtime Proof Required After Merge

Observe the first unrelated pull request and confirm its ordinary `ci` and `tests` jobs do not collect `tests/test_feed_reconnect_resource_soak.py`. Observe the first feed-related pull request and confirm `Feed Smoke` runs. Confirm the next scheduled soak creates a log artifact, and manually dispatch the certification tier when a fresh 1000-cycle proof is required.

## What This PR Does Not Prove

- It does not prove live or paper broker feed correctness.
- It does not replace the existing 1000-cycle certification evidence.
- It does not prove every non-feed test completes within 15 minutes forever.
- It does not consolidate the two historical ordinary workflows into one because their check names may be referenced by branch protection.
- It does not change reconnect, persistence, descriptor, or websocket behavior.

## Human Approval

Human approval is required before merge. Reviewers should verify the repository branch-protection contexts still appear, the ordinary jobs finish without collecting feed-resource profiles, and the dedicated smoke workflow passes.
