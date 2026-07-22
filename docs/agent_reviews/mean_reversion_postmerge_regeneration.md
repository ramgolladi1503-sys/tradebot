# Mean Reversion Post-Merge Regeneration Review

mode: RESEARCH_EVIDENCE_REGENERATION
candidate_id: MEAN_REVERSION_POSTMERGE_RERUN_V1
decision: DRAFT_REVIEW_REQUIRED
reason: Regenerate all affected mean-reversion and shared WFA evidence after PRs 689 and 690 repaired causal, accounting, audit, and fold-isolation defects.
timestamp: 2026-07-22T12:45:00+05:30
is_order_action: false
broker_api_called: false
source: Immutable private release `upstox-corpus-v1` and merged commit `c6d1240ff506210be15f8647bad0ee677b4870a7`

## Agent Work Contract

Run a read-only research regeneration against the immutable private Upstox corpus. Verify the archive and every parquet byte before use. Rebuild Phase 4 evidence twice, run the full parameter-discovery grid, run the repaired shared WFA twice, compare semantic outputs, and publish evidence as a GitHub Actions artifact. Do not alter strategy logic, thresholds, broker integration, feeds, risk controls, dashboard behavior, production configuration, or order permissions.

## Scope Guard

In scope:

- frozen corpus download and SHA-256 verification;
- underlying candle inventory and input-authority artifacts;
- focused merged regression tests;
- two independent Phase 4 regenerations;
- all mandatory Phase 4 audits and vertical-slice reports;
- full-grid mean-reversion parameter discovery;
- shared certified WFA on frozen NIFTY candles;
- semantic determinism and artifact hashing;
- a machine-readable post-merge summary.

Out of scope:

- strategy parameter changes or optimization outside the existing frozen grid;
- paper or live activation;
- broker or order calls;
- production runtime changes;
- rescuing or promoting a historical verdict without regenerated evidence;
- consuming any new confirmation or future holdout data.

## Grill Me Review

1. Can mutable local files influence the rerun? No. The workflow downloads a tagged private release, verifies the archive digest, verifies the release sidecar, inventories every expected parquet path, and recalculates every parquet SHA-256.
2. Can a failed or empty Phase 4 audit silently pass? No. The repaired audit chain writes explicit classifications, and vertical-slice validation consumes every required audit report.
3. Can one run be presented as deterministic evidence? No. Phase 4 and shared WFA each run twice from reset output directories and must produce matching semantic outputs.
4. Can parameter discovery use a different accounting lane from the audits? No. The merged code consumes the declared `pnl_model_used_for_gate` and computes expectancy and profit factor from that lane.
5. Can an incomplete WFA fold set reach holdout selection? No. The repaired WFA rejects incomplete or no-trade folds before final parameter selection.
6. Can regeneration authorize execution? No. Summary and generated reports preserve all paper, live, broker-order, and execution permissions as false.

## Hermes Review

Interface and compatibility boundaries:

- the workflow invokes existing merged scripts through their public command-line contracts;
- no production module is edited;
- input authority is written only under `runtime/strategy_validation/MEAN_REVERSION_EXTENSION` inside the disposable runner;
- generated evidence is uploaded read-only and is not committed to `main`;
- the parameter-discovery grid, train/validation/holdout dates, and strategy risk contract remain unchanged;
- WFA uses the merged whole-session fold builder with `workers=1` for deterministic execution.

## GSD Review

The workflow is ordered as a fail-closed evidence chain:

1. obtain and verify immutable corpus bytes;
2. build frozen input authority;
3. run focused regressions;
4. regenerate Phase 4 twice;
5. compare semantic hashes;
6. execute the full parameter grid;
7. execute shared WFA twice;
8. build summary and artifact manifest;
9. upload evidence even when a later stage fails.

Each stage uses `set -euo pipefail`; authoritative commands do not suppress errors.

## QA / Safety Review

Focused regression coverage includes:

- causal and fail-closed Phase 4 audits;
- whole-session WFA and incomplete-fold rejection;
- conservative same-candle stop handling and candle-end exit timestamps;
- separation of underlying-index and delta-option proxy accounting lanes;
- rejection of nonpositive holding intervals.

Safety boundaries:

- no secrets are printed;
- the corpus token is used only by `gh release download`;
- no broker module or order endpoint is invoked;
- no live, paper, or execution permission is changed;
- no generated evidence is promoted automatically.

## Acceptance Proof

Acceptance requires one immutable workflow head with:

- corpus archive SHA-256 match;
- sidecar SHA-256 match;
- exact parquet inventory match;
- every parquet digest verified;
- focused tests passing;
- Phase 4 run A and run B completed;
- Phase 4 semantic manifests identical;
- full-grid report emitted;
- shared WFA run A and run B identical;
- final summary and artifact hash manifest emitted;
- evidence artifact uploaded;
- repository CI, Code Excellence, CodeQL, Portfolio, Forensics, review-evidence, and registry checks green.

A strategy-level FAILED or BLOCKED result is an acceptable research outcome. Workflow success means the evidence was regenerated correctly, not that the strategy is profitable.

## Runtime Proof Required After Merge

This branch does not need to merge before the evidence workflow runs. After successful regeneration, download the workflow artifact and independently inspect:

- `postmerge_regeneration_summary.json`;
- `phase4_semantic_hash_manifest.json`;
- both Phase 4 output directories;
- the full-grid parameter report;
- both shared WFA reports;
- `artifact_hash_manifest.json`.

Any future rerun must use the same corpus tag and archive digest unless a new immutable corpus release is explicitly approved.

## What This PR Does Not Prove

- It does not prove structural edge or profitability.
- It does not certify executable option fills.
- It does not validate new or unfrozen market data.
- It does not authorize paper or live trading.
- It does not automatically reverse any historical rejection.
- It does not establish that every unrelated backtest engine is correct.

## Human Approval

Human review is required before merging this evidence workflow. The workflow may run on the branch and publish read-only evidence before merge. Review must confirm the immutable corpus identity, unchanged strategy contracts, semantic determinism, exact result classifications, and absence of any execution-capable change.
