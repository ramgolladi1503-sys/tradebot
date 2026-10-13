# PR978 Observed Shutdown Drain Review

## Agent Work Contract
- `source_agent`: gsd; `action`: scoped lifecycle repair; `title`: reserve shared persistence shutdown budget.
- `scope`: deadline allocation and focused tests only.
- `requested_paths`: `core/kite_read_only_observation_runtime.py`, `tests/test_kite_read_only_observation_runtime.py`.
- `allowed_paths`: the two scoped paths plus this review record and the captured-run work item.
- `forbidden_paths`: broker/order/risk/feed configuration, live runtime operations, credentials, and strategy thresholds.
- Expected proof: focused lifecycle tests, exact-head CI, fail-closed incomplete state.

## Scope Guard
Changed source is limited to the existing read-only observation lifecycle; no broker imports, order actions, live enablement, feed freshness changes, or risk changes.

## Grill Me Review
Observed evidence: captured `shutdown_drain.json` reports a 30-second deadline exhausted and zero budgets passed to tick, depth, and runtime persistence shutdown. Source inspection shows the optional pre-drain loop uses that same deadline before worker shutdown calls. This supports the deadline-allocation RCA. It does not explain the separate tick worker failure, passive checkpoint backlog, or upstream feed interruption. The change must not imply those causes were repaired.

## Hermes Review
Contract: bound pre-drain to 10% of the configured shared window, reserve the rest for persistence shutdown, and apportion remaining time across the three existing shutdown APIs. Keep existing incomplete-accounting behavior `FAILED`/`PARTIAL`. No new persistence mechanism or runtime wiring.

## GSD Review
Patch: cap the optional pre-drain loop; recompute slices from remaining time for tick, depth, and runtime workers. Focused tests exercise quick returns and calls consuming their entire slices; unresolved work remains visibly incomplete.

## QA / Safety Review
`pytest -q tests/test_kite_read_only_observation_runtime.py` passed locally: 22 passed. `git diff --check` passed. Independent reviewer agent found no P1/P2 issue in the revised patch. These checks are not an authenticated human review and do not prove production behavior.

## Acceptance Proof
Local focused tests pass. Hosted exact-head CI for `5392e70777f774b798cecfa92ff2c327ba43911d` is still running or has failed evidence gates; no acceptance or merge proof is claimed. The work item remains `UNVERIFIED` and at `BACKLOG`; repository lifecycle evidence is incomplete.

## Runtime Proof Required After Merge
A future controlled shutdown observation must verify each worker receives nonzero budget, report actual completion/accounting, and preserve partial status on unresolved work. No runtime restart or live run was performed in this PR.

## What This PR Does Not Prove
It does not identify the tick worker failure cause, WAL checkpoint reader/cause, missing provider tick cause, or prove feed recovery, data quality, trading readiness, or successful live operation. It does not clear Trusted Base lifecycle findings.

## Human Approval
No authenticated human reviewer or approver is recorded. Role labels in local workflow evidence do not authenticate people. Merge remains subject to required repository checks and normal review.
