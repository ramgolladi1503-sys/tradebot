# PR #968 NSE Option Contract Authority Review

## Agent Work Contract

- `source_agent`: `grill_me`, `hermes`, `gsd`, `qa`
- `action`: `AUDIT_RISK`, `DEFINE_CONTRACT`, `GENERATE_PATCH`, `VERIFY_TESTS`
- `title`: Bind Sentinel option quotes to the NSE-listed F&O contract master
- `scope`: The NSE and Upstox option-contract identity, expiry selection, capture evidence, quote resolution, and late-day option subscription refresh changed in this PR.
- `requested_paths`: `core/nse_fo_contract_master.py`, `core/upstox_capture/late_day_option_refresh.py`, `scripts/run_live_feed_advisor.py`, `scripts/upstox_daily_live_capture_and_stitch.py`, and their focused tests.
- `allowed_paths`: Those implementation and test paths plus this review record.
- `forbidden_paths`: Credentials, environment files, order/broker APIs, WAL data, live process control, and unscoped strategy thresholds.
- `expected_tests`: NSE parser/fetch/manifest tests, option-identity tests, capture/refresh tests, Python compilation, and whitespace validation.
- `acceptance_proof`: Exact NSE report-listing bytes and NSE/Upstox source snapshots are persisted and rehashed; each authorized quote must map uniquely by provider key, symbol, expiry, strike, option type, and NSE instrument ID to an eligible, non-deleted NSE OPTIDX row.

## Scope Guard

The code obtains the dated NSE F&O MII contract file selected by the official NSE report listing. It uses the contract's published expiry, parses the MII expiry epoch and strike units, and checks permitted-to-trade, deletion, normal-market status, and eligibility. It binds the Upstox complete instrument snapshot to the same exact contract tuple. Missing, stale, malformed, ambiguous, or hash-mismatched evidence prevents option authorization; index capture can continue.

This scope does not select CE versus PE based on market direction, select strikes using liquidity/Greeks/OI, change entry/exit/stop-loss logic, or claim profitability. It adds no inferred expiry calendar or quote-age threshold. It does not make orders, call broker APIs, change credentials, or enable live execution.

## Grill Me Review

The adversarial review found a late-refresh failure path that reported new subscriptions after `subscribe` raised and prevented retry. The implementation now mutates the subscription map only after `subscribe` returns successfully; failure returns zero and the caller leaves the refresh eligible for retry. The review also identified that NSE normal-market status and eligibility must be checked, empty selected mappings must not be labeled fully verified, and the report listing must be persisted and rechecked. These were addressed and covered by focused negative tests.

Residual risk: the Upstox subscribe method returning successfully proves request acceptance by the client call, not that every instrument subsequently produced ticks. Capture completeness still requires separate runtime evidence. The PR818 frozen-baseline CI gate also reports existing governance drift; this review does not waive or bypass that gate.

## Hermes Review

The contract is a three-source binding: (1) hashed NSE report listing authorizes the dated official file; (2) hashed NSE and Upstox snapshots prove the exact static identity; (3) captured tick token and symbol plus manifest hash must match that identity before quote resolution. All evidence is retained beside the capture and re-verified by the advisor. Unknown and ambiguous states fail closed. Expiry is read from NSE's published contract row, not calculated from weekday conventions.

## GSD Review

The implementation is limited to the declared files and preserves the existing SIM/PAPER/LIVE boundary. Late refresh operates only on contracts already verified against both masters. No risk threshold, strategy direction, order path, broker adapter, credential, or live process behavior was changed. Empty option mappings are represented as `SOURCE_VERIFIED_NO_ELIGIBLE_MAPPINGS`; this does not authorize a candidate.

## High-Risk Path Review

This PR changes feed capture/subscription and quote-resolution code. The changed paths were reviewed for fail-closed contract identity, source provenance, retry behavior, and absence of order/broker calls. The source-level subscription API is used only for market-data subscriptions. Tests exercise parser rejects, source/hash mismatch, identity ambiguity, missing NSE match, non-authoritative spot, and failed late subscription. No code in this change places, modifies, cancels, or exits an order. No risk gate, kill switch, or SIM/PAPER/LIVE boundary is weakened.

The repository's independent `pr818-live-flow-freeze-target` check fails with `PR818_FROZEN_MAIN_BASELINE_DRIFT` on files outside this scoped patch. That is a governance blocker to PR acceptance and is intentionally left unresolved here; this evidence does not characterize the overall PR as merge-ready.

## QA / Safety Review

- `python -m py_compile` on all changed Python implementation and test files: passed.
- `pytest -q tests/test_nse_fo_contract_master.py tests/test_upstox_daily_live_capture.py tests/test_option_identity_resolution.py`: 47 passed.
- `git diff --check`: passed.
- `read_only=true` for source and runtime inspection.
- `is_order_action=false`.
- `broker_api_called=false`.
- `allowed_for_live_execution=false`.
- No live process was stopped, restarted, or launched.
- No WAL or live runtime data was edited.

## Acceptance Proof

Commit `f8f4da90552cdebac6d643df18ef8403d23f34e8` contains the seven scoped implementation/test files plus this review record in the follow-up commit. Focused local validation passed as listed above. On the prior exact PR head `f8f4da90552cdebac6d643df18ef8403d23f34e8`, GitHub's `agent-review-evidence` check failed because the mandatory review record was absent; this document is intended to satisfy that evidence requirement. The `pr818-live-flow-freeze-target` check failed with frozen-main baseline drift and remains an explicit unresolved governance blocker. Other CI checks were still running at the time of this review record; do not infer they passed.

## Runtime Proof Required After Merge

Before claiming Monday/live readiness, a human-observed market-data capture must prove, for the exact deployed SHA and session date: the selected NSE report dates and file identity; successful fetch and hashes of the report listing, NSE file, and Upstox master; manifest verification; exact selected contract rows; option subscription acknowledgment and received ticks; tick manifest hashes; candidate denominator and no-candidate reasons; and the advisor's quote/candidate audit rows. Any missing artifact, mismatched hash, or absent run identity is `UNKNOWN`/unverified, not a pass. No order action is authorized by this PR.

## What This PR Does Not Prove

This work does not prove that the new code is deployed, that a future live run has complete option ticks, that any candidate should trade, that a strategy has positive expectancy, or that exits/stops are correct. It does not independently certify the wider pre-existing changes in PR #968. GitHub CI is not complete, and the frozen-baseline governance failure remains.

## Human Approval

The user explicitly requested that the NSE expiry check be implemented in PR #968 and previously authorized pushing the updated work to PR #968. That authorization is limited to the scoped repository change and PR update. It does not authorize merge, deployment, live restart, broker use, or order actions.
