# Market Event Graph Independent Recertification V2 Review

mode: RESEARCH_RECERTIFICATION
candidate_id: MARKET_EVENT_GRAPH_INDEPENDENT_RECERTIFICATION_V2
decision: DRAFT_REVIEW_REQUIRED
reason: Independently audit and recertify the already-frozen Market Event Graph mechanism without rerunning discovery or rebuilding the certification architecture.
timestamp: 2026-08-07T16:40:00Z
is_order_action: false
broker_api_called: false
source: PR_805_BRANCH_AND_FOCUSED_GITHUB_ACTIONS_AUDIT
allowed_for_live_execution: false

## Agent Work Contract

Recertify the already-frozen Market Event Graph reversal mechanism as a thin adapter over the existing hardened Pattern Atlas certification helpers. Preserve the graph and train-only thresholds exactly. Audit the legacy return-timing contract, recompute economic evidence from recorded delayed-entry and exit prices when the original physical dataset is supplied, forbid reuse of the consumed original holdout as an independent final test, and require a genuinely later dataset for independent certification. Do not rerun graph discovery, tune thresholds, broaden the mechanism, modify production trading behavior, or merge the branch.

## Scope Guard

In scope: frozen MEG graph/threshold authority, legacy ledger reconciliation, physical archive/hash verification, delayed-entry return reconstruction, deterministic evidence hashes, independent-data chronology, PRE_CAS/POST_CAS separation, focused behavioral tests, and fail-closed certification gates.

Out of scope: production trading paths, execution/risk/ranking changes, strategy registry promotion, option-edge claims, paper/live activation, graph rediscovery, threshold optimization, and merging.

## Grill Me Review

1. Is the original holdout an untouched final test? No. It was already used for candidate acceptance after a search over 11,258 graph-direction pairs.
2. Can V2 reuse `future_return_15` on the signal row as delayed-entry execution truth? No. The preserved ledgers show that value generally differs from the return implied by the recorded delayed entry and exit prices.
3. Can V2 change the frozen graph or train thresholds to restore earlier results? No. Any threshold or graph mismatch fails closed.
4. Can PRE_CAS and POST_CAS independent sessions be pooled? No. A dataset crossing the 2026-08-03 CAS boundary is rejected.
5. Does a positive corrected result on the original validation/holdout certify the mechanism independently? No. Those partitions are diagnostic-only because the holdout has already been consumed.
6. Does an underlying result authorize options, shadow, paper, live, or orders? No. Those remain separate blocked authorities.

## Hermes Review

This PR depends on the hardened Pattern Atlas branch specifically to reuse shared bootstrap confidence intervals, concentration controls, semantic hashing, and evidence-writing utilities. It does not fork or duplicate the full research architecture. The new code is limited to MEG-specific authority checks, timing reconstruction, independent chronology, and regime separation.

## GSD Review

The branch adds one MEG recertification adapter, one CAS-regime guard wrapper, two focused test files, one research contract, one focused workflow, and this review record. The frozen CE graph remains `breadth_down_1:HIGH -> index_breadth_divergence:LOW -> breadth_down_1:LOW`. The frozen train thresholds remain unchanged. No production runtime module or strategy implementation is modified.

## QA / Safety Review

Focused GitHub Actions run `31198245945` passed 31/31 behavioral tests. Tests prove that the graph trigger does not depend on `future_return_15`, a full 15-bar hold is measured from the delayed entry, consumed holdout dates are rejected as independent evidence, mixed PRE_CAS/POST_CAS datasets fail closed, and winner-concentrated evidence fails robustness. The preserved-ledger audit executed on the same run and found 286 mismatches across 287 historical ledger rows between reported gross return and the return implied by recorded delayed entry/exit prices. No safety or promotion gate was weakened.

## High-Risk Path Review

The principal high-risk path here is research authority contamination: treating a signal-row future-return column as delayed-entry economics, reusing a consumed holdout, or pooling across the CAS boundary. V2 blocks all three. No production path outside research evidence generation is changed. `allowed_for_live_execution` remains false.

## Acceptance Proof

Current focused proof is GitHub Actions run `31198245945`, which completed successfully with 31 passing tests and produced the ledger-audit artifact `market-event-graph-independent-recertification-v2-ledger-audit`. The audit verdict is `LEGACY_MEG_EXECUTION_ECONOMICS_SUPERSEDED` with semantic SHA-256 `54701345d230c10b8394f0c70ea6fff585097b442051550c55cf89cd9d981b8a`. Full acceptance additionally requires the repository governance checks to pass on one immutable PR head and the physical original archive to be recomputed using the V2 timing contract.

## Runtime Proof Required After Merge

No production runtime proof is authorized by this research PR. If this code were ever merged after human approval, only a read-only research execution should be performed against the verified physical archive `causal-market-state-v1-evidence-v3.zip`, checking archive SHA-256 `fde3f5c74f12bf59d80d39012bffd89a9411954b9207561f92b792ade31099b3`, internal dataset SHA-256 `30f3d399404a299da6cb99b600a3f2b7346deb74653d5f4a8ebf8849ebefe73c`, exact frozen-threshold reproduction, and deterministic evidence outputs. No production trading path is part of this proof.

## What This PR Does Not Prove

This PR does not prove that the MEG mechanism has a structural edge. It does not validate the earlier MEG profit figures, because those economics have been superseded by the ledger timing audit. It does not provide an untouched independent dataset, option-premium edge, strike/expiry mapping, achievable fills, shadow readiness, paper readiness, live readiness, or order authority.

## Human Approval

Human review is required before any merge. The PR must remain draft and unmerged while research authority is incomplete. No evidence from this branch may be promoted into production trading behavior without a separate narrowly scoped change, fresh independent evidence, passing governance gates, and explicit human approval.
