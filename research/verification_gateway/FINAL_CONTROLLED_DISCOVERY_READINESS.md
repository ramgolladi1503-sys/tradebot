# Final controlled-discovery readiness — 2026-09-27

## BLOCKED_WITH_EXACT_DEPENDENCY

The PR #936 prototype is **not ready for a controlled strategy hunt**. This work repaired an unsafe verifier aggregation path and validated its isolated tests, but the brief's mandatory end-to-end requirements remain incomplete. `NO_CERTIFIED_EDGE` remains the only supported strategy disposition.

## Acceptance status

| Gate | Status | Evidence / blocker |
|---|---|---|
| A — baseline, provenance, safety inventory | PARTIAL | `BASELINE_AND_SAFETY_MAP.md`; public PR/base identities and dirty canonical checkout recorded. OS-enforced protected-data sandbox and complete authoritative family census not verified. |
| B — reuse/dependency audit | PARTIAL | `DEPENDENCY_ADOPTION_DECISIONS.md`; Pydantic/Pandera/Hypothesis isolated set pinned for Python 3.12 macOS arm64. CI/Linux lock and all selected-library POCs not complete. |
| C — source fidelity + EDGE-65/67 bridge | BLOCK | `contracts.py` schema and registry metadata bridge exist. `verify_strategy_spec` intentionally returns BLOCKED; no authenticated source-review/evidence producer or extract/review/freeze/inspect CLI. |
| D — independent mathematical oracle | PARTIAL | `reference_math.py` contains a separately written scalar SMA-seeded EMA/crossover oracle with hand-calculated and future-mutation tests. It agrees to 1e-12 with the existing pure in-memory EMA indicator on synthetic prefixes; this is indicator arithmetic only, not source strategy/entry/exit translation. Authentic historical references for #1/#17 remain unavailable; no authentic fixtures invented. |
| E — PIT causality/data authority | PARTIAL | Synthetic OHLCV checks require instrument/contract identity and validate timestamps per identity; `FixtureValidationReport` keeps `DATA_SHAPE_PASS` separate from source authentication and execution-quote authority, both `NOT_VERIFIED`. PIT/survivorship and quote authority are absent. |
| F — execution/cost parity | PARTIAL | `reference_execution.py` independently replays synthetic quote tapes with data availability, next permissible quote, contract identity, buy-only entry, bid/ask, slippage and fees. Twelve mutation/acceptance tests pass. No comparison to TradeBot's production research backtest exists; historical quote validity remains unproven. |
| G — statistics/exposure controls | PARTIAL | `_monte_carlo()` uses seeded trade-level resampling with replacement; 9 synthetic tests pass. Candidate ML outer and nested walk-forward plus feature-ablation partitions purge unresolved labels, apply configured `embargo_ms`, and fail closed if outer folds lose required training-session support; 9 focused splitter/ablation regressions, 15 full candidate ML tests, and 86 offline analytics tests pass. Resampling remains IID; full trial denominator remains unavailable and DSR/PBO stay `NOT_ESTIMABLE`. |
| H — evidence-bound official gateway | BLOCK | [Static inventory](ENTRYPOINT_STATIC_INVENTORY_20260927.md) found 5 `scripts/research` command candidates and 46 outcome/ledger-reference script candidates, but this is not an owner-reviewed complete call graph. `run_strategy_pipeline_research.py` and `run_governed_strategy_research.py` remain separate; `core/analytics/walk_forward_pipeline.py` reads the outcomes directory directly. No central gateway or OS read-path restriction exists. |
| I — adversarial acceptance | PARTIAL | 52 gateway contract/data/registry/math/execution tests and 9 Monte Carlo tests pass in isolated environments. No OS-denied protected path test, official API bypass test, full research-entrypoint inventory, or clean CI run. |
| J — independent audit/release | BLOCK | No independent end-to-end release signoff. At the latest exact-SHA snapshot (`32b26a1e582a098486abbf3642323d310b16218c`), focused `candidate_ml_v2`, replay-ledger proxy training, `verify`, CodeQL, security, and several contract checks passed. Default `unit_tests` remained pending. `real_market_corpus_pilot` failed before training because the repository Git LFS budget was exhausted; base-authority, protected live-flow, and Netlify checks also failed. See [remote CI record](REMOTE_CI_STATUS_20260927.md). CI and root dependency files remain protected and unchanged. |

## Work completed

- Inspected PR #936 at `35d46108c05ccd11bfd66fdfd4f453f15690c120`, based on current `origin/main` `0f95e60335ddcadbe397e5ca837946ed8b1cdec7` (full exact base SHA is in `READINESS_STATE.json`).
- Preserved the canonical dirty checkout; all edits were made in `/Users/madhuram/.codex/worktrees/pr936-verification-gateway/tradebot`.
- Added a Hermes architecture contract before GSD implementation.
- Replaced boolean aggregation with an always-blocked report API. The function rejects caller pass flags by signature and self-asserted reviewer strings do not produce a pass.
- Added digest-mutation, forged-flag, review-string, timezone-aware shape and naive-time rejection tests.
- Added required instrument/contract identity and per-contract timestamp checks; kept shape success separate from source and execution quote status.
- Added a standalone SMA-seeded EMA/crossover scalar oracle with explicit warm-up and strict crossing behavior, hand-checkable numeric assertions, and future-mutation invariance tests. It is synthetic methodology only, not evidence that any source strategy is faithfully translated.
- Compared the reference SMA-seeded EMA against `core.indicators_live.compute_indicators()` over each prefix of one synthetic candle tape; values agree to 1e-12. The pure indicator function was invoked with in-memory synthetic data only; no strategy/runtime or broker path was executed.
- Added `reference_execution.py`, an independent Decimal-based synthetic quote-tape replay that blocks pre-decision fills, quote publication before event, crossed quotes, contract mismatches, non-buy entries, and negative costs. It accounts for bid/ask, explicit basis-point slippage and fees. It has no live/broker integration and is not compared to a TradeBot production backtest.
- Added a static candidate inventory for research CLIs and outcome/ledger access paths. It also confirms a direct outcome-directory read in `core/analytics/walk_forward_pipeline.py`; no candidate scripts or outcome paths were run/read. This is evidence of an unresolved bypass surface, not complete entrypoint enumeration.
- Repaired the exact Monte Carlo defect under [a separate Hermes contract](../../docs/research/PR936_MONTE_CARLO_RESAMPLING_CONTRACT.md): fixed-seed `random.Random.choices` bootstrap with replacement, preserving minimum sample omission and report fields. Its 9 tests pass. This is an IID descriptive diagnostic, not dependence-aware inference.
- Added a narrow purged/embargoed walk-forward contract. The existing candidate ML splitter now removes unresolved outcome intervals relative to the earliest test decision, and certification accepts an explicit `embargo_ms` setting; synthetic overlap and embargo fixtures cover both conditions. This does not implement combinatorial purged CV or create evidence of statistical independence.
- Applied the same outcome-time purge, explicit embargo, and configured row purge to certification's feature-ablation and nested train/validation partitions after independent review found bypasses. Outer folds fail closed when purging removes configured minimum session support. Synthetic tests demonstrate exclusions inside embargo, retention outside it, and support failure.
- Independent read-only review iterated through the embargo fixture, ablation bypass, nested split, and surviving-session support checks; each reported issue was corrected and the final reviewer found no remaining issue in node G's scoped files.
- Audited the post-hoc regime-selection playbook and historical HTF narrative. The generic playbook/checklist now preserve all-regime parents and negative trials and label outcome-selected restrictions as exposed child hypotheses; the historical narrative is marked non-authoritative. Individual historical trial-family denominators and untouched prospective evidence remain unavailable, so this does not validate the HTF candidate.
- Pinned the isolated dependency set and wrote a platform-specific lock and dependency decision record.
- Added baseline/safety map and machine-readable DAG checkpoint.

Focused command and result:

```sh
PYTHONPATH=. /tmp/pr936-verification-venv/bin/python -m pytest -q -o addopts='' \
  tests/research/test_verification_gateway_contracts.py \
  tests/research/test_verification_gateway_data.py \
  tests/research/test_verification_gateway_registry_bridge.py \
  tests/research/test_verification_gateway_reference_math.py
# 42 passed, 1 warning

PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q -o addopts='' \
  tests/test_research_pipeline_monte_carlo.py
# 9 passed, 1 warning

PYTHONPATH=. /tmp/pr936-verification-venv/bin/python -m pytest -q -o addopts='' \
  tests/research/test_verification_gateway_reference_execution.py
# 11 passed, 1 warning
```

The earlier default workflow collection failure remains documented for its original SHA. Latest PR checks are recorded in `REMOTE_CI_STATUS_20260927.md`; focused checks passed, but unit tests were pending and merge blockers remained at the snapshot.

## Exact dependencies and resume commands

1. **Repository/LFS owner:** restore the repository LFS budget or provide an authorized, provenance-preserving source for the explicitly selected corpus objects; then rerun the corpus pilot and verify it materializes data before any training is considered.
2. **Dependency/CI owner:** authorize a narrow follow-up that installs the research-only locked set in an isolated gateway CI job (or an equivalent safe path), without modifying runtime dependency behavior. Then rerun PR checks on the resulting exact SHA.
3. **Research statistics owner:** review the completed Monte Carlo patch against its contract, especially IID-vs-dependent sample limits. A future dependence-aware method needs a separate spec, synthetic overlapping-label fixture, and a registered trial-denominator source. Keep DSR/PBO `NOT_ESTIMABLE` until the full search denominator is recoverable.
4. **Research platform owner:** source/audit a complete official-entrypoint call graph, then separately authorize routing each entrypoint through the evidence gateway. The static scan found direct filesystem paths; it is not a bypass test.
5. **Research platform owner:** supply authoritative source references for historical defects #1 and #17 and define source-review identity/signature authority. Until supplied, synthetic defect tests cannot be described as source fidelity.
6. **Security/deployment owner:** provide a disposable OS/container sandbox with no credential and protected-outcome read permissions, and demonstrate denied access attempts. Python API tests alone cannot prove this boundary.
7. Continue DAG from earliest blocked nodes; do not copy uncommitted canonical-checkout research files into PR #936 or claim the referenced local repairs are integrated.

Suggested commands after these dependencies are met:

```sh
cd /Users/madhuram/.codex/worktrees/pr936-verification-gateway/tradebot
python -m json.tool research/verification_gateway/READINESS_STATE.json
PYTHONPATH=. .venv-research-verify/bin/python -m pytest -q -o addopts='' \
  tests/research/test_verification_gateway_contracts.py \
  tests/research/test_verification_gateway_data.py \
  tests/research/test_verification_gateway_registry_bridge.py \
  tests/research/test_verification_gateway_reference_math.py \
  tests/research/test_verification_gateway_reference_execution.py
PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q -o addopts='' \
  tests/test_research_pipeline_monte_carlo.py
```

PR #936 remains draft and blocked at head `32b26a1e582a098486abbf3642323d310b16218c`; no merge occurred. The CI snapshot is recorded in `REMOTE_CI_STATUS_20260927.md`. No protected outcomes were read locally, no broker API or order action occurred, and no live/paper behavior, risk boundary, runtime path, root dependency manifest, or CI workflow was changed. Readiness remains `BLOCKED_WITH_EXACT_DEPENDENCY`; `NO_CERTIFIED_EDGE` remains unchanged.
