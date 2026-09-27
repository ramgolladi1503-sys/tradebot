# Final controlled-discovery readiness — 2026-09-27

## BLOCKED_WITH_EXACT_DEPENDENCY

The PR #936 prototype is **not ready for a controlled strategy hunt**. This work repaired an unsafe verifier aggregation path and validated its isolated tests, but the brief's mandatory end-to-end requirements remain incomplete. `NO_CERTIFIED_EDGE` remains the only supported strategy disposition.

## Acceptance status

| Gate | Status | Evidence / blocker |
|---|---|---|
| A — baseline, provenance, safety inventory | PARTIAL | `BASELINE_AND_SAFETY_MAP.md`; public PR/base identities and dirty canonical checkout recorded. OS-enforced protected-data sandbox and complete authoritative family census not verified. |
| B — reuse/dependency audit | PARTIAL | `DEPENDENCY_ADOPTION_DECISIONS.md`; Pydantic/Pandera/Hypothesis isolated set pinned for Python 3.12 macOS arm64. CI/Linux lock and all selected-library POCs not complete. |
| C — source fidelity + EDGE-65/67 bridge | BLOCK | `contracts.py` schema and registry metadata bridge exist. `verify_strategy_spec` intentionally returns BLOCKED; no authenticated source-review/evidence producer or extract/review/freeze/inspect CLI. |
| D — independent mathematical oracle | PARTIAL | `reference_math.py` contains a separately written scalar SMA-seeded EMA/crossover oracle with hand-calculated and future-mutation tests. It is not compared with a production indicator implementation. Authentic historical references for #1/#17 remain unavailable; no authentic fixtures invented. |
| E — PIT causality/data authority | PARTIAL | Synthetic OHLCV checks require instrument/contract identity and validate timestamps per identity; `FixtureValidationReport` keeps `DATA_SHAPE_PASS` separate from source authentication and execution-quote authority, both `NOT_VERIFIED`. PIT/survivorship and quote authority are absent. |
| F — execution/cost parity | PARTIAL | `reference_execution.py` independently replays synthetic quote tapes with data availability, next permissible quote, contract identity, buy-only entry, bid/ask, slippage and fees. Eleven mutation/acceptance tests pass. No comparison to TradeBot's production research backtest exists; historical quote validity remains unproven. |
| G — statistics/exposure controls | PARTIAL | Under separate Hermes contract, `_monte_carlo()` now uses seeded trade-level resampling with replacement; 9 synthetic tests pass. It remains IID and does not handle serial dependence; full trial denominator remains unavailable and DSR/PBO stay `NOT_ESTIMABLE`. |
| H — evidence-bound official gateway | BLOCK | Prototype is not wired to official research entry points; caller flags were removed from its report function, but no evidence producer/access state machine exists. |
| I — adversarial acceptance | PARTIAL | 30 gateway contract/data/registry/math tests, 11 synthetic execution tests, and 9 Monte Carlo tests pass in isolated environments. No OS-denied protected path test, official API bypass inventory, production parity, or clean CI run. |
| J — independent audit/release | BLOCK | No independent reviewer signoff. Default PR CI currently fails collecting gateway tests because the workflow does not install Pydantic. Task instructions protect CI and root dependency files, so no such edit was made. |

## Work completed

- Inspected PR #936 at `35d46108c05ccd11bfd66fdfd4f453f15690c120`, based on current `origin/main` `0f95e60335ddcadbe397e5ca837946ed8b1cdec7` (full exact base SHA is in `READINESS_STATE.json`).
- Preserved the canonical dirty checkout; all edits were made in `/Users/madhuram/.codex/worktrees/pr936-verification-gateway/tradebot`.
- Added a Hermes architecture contract before GSD implementation.
- Replaced boolean aggregation with an always-blocked report API. The function rejects caller pass flags by signature and self-asserted reviewer strings do not produce a pass.
- Added digest-mutation, forged-flag, review-string, timezone-aware shape and naive-time rejection tests.
- Added required instrument/contract identity and per-contract timestamp checks; kept shape success separate from source and execution quote status.
- Added a standalone SMA-seeded EMA/crossover scalar oracle with explicit warm-up and strict crossing behavior, hand-checkable numeric assertions, and future-mutation invariance tests. It is synthetic methodology only, not evidence that any source strategy is faithfully translated.
- Added `reference_execution.py`, an independent Decimal-based synthetic quote-tape replay that blocks pre-decision fills, quote publication before event, crossed quotes, contract mismatches, non-buy entries, and negative costs. It accounts for bid/ask, explicit basis-point slippage and fees. It has no live/broker integration and is not compared to a TradeBot production backtest.
- Repaired the exact Monte Carlo defect under [a separate Hermes contract](../../docs/research/PR936_MONTE_CARLO_RESAMPLING_CONTRACT.md): fixed-seed `random.Random.choices` bootstrap with replacement, preserving minimum sample omission and report fields. Its 9 tests pass. This is an IID descriptive diagnostic, not dependence-aware inference.
- Pinned the isolated dependency set and wrote a platform-specific lock and dependency decision record.
- Added baseline/safety map and machine-readable DAG checkpoint.

Focused command and result:

```sh
PYTHONPATH=. /tmp/pr936-verification-venv/bin/python -m pytest -q -o addopts='' \
  tests/research/test_verification_gateway_contracts.py \
  tests/research/test_verification_gateway_data.py \
  tests/research/test_verification_gateway_registry_bridge.py \
  tests/research/test_verification_gateway_reference_math.py
# 30 passed, 12 warnings

PYTHONPATH=. /opt/anaconda3/bin/python -m pytest -q -o addopts='' \
  tests/test_research_pipeline_monte_carlo.py
# 9 passed, 1 warning

PYTHONPATH=. /tmp/pr936-verification-venv/bin/python -m pytest -q -o addopts='' \
  tests/research/test_verification_gateway_reference_execution.py
# 11 passed, 1 warning
```

The current remote PR CI is not green: the default workflow installs root requirements and pandas only, while all three new tests import Pydantic. The run failed collection with three `ModuleNotFoundError: No module named 'pydantic'` errors. The dependency/CI installation must be proposed through a separately authorized protected-path change; no CI gates were weakened.

## Exact dependencies and resume commands

1. **Dependency/CI owner:** authorize a narrow follow-up that installs the research-only locked set in an isolated gateway CI job (or an equivalent safe path), without modifying runtime dependency behavior. Then rerun PR checks on the resulting exact SHA.
2. **Research statistics owner:** review the completed Monte Carlo patch against its contract, especially IID-vs-dependent sample limits. A future dependence-aware method needs a separate spec, synthetic overlapping-label fixture, and a registered trial-denominator source. Keep DSR/PBO `NOT_ESTIMABLE` until the full search denominator is recoverable.
3. **Research platform owner:** supply authoritative source references for historical defects #1 and #17 and define source-review identity/signature authority. Until supplied, synthetic defect tests cannot be described as source fidelity.
4. **Security/deployment owner:** provide a disposable OS/container sandbox with no credential and protected-outcome read permissions, and demonstrate denied access attempts. Python API tests alone cannot prove this boundary.
5. Continue DAG from earliest blocked nodes; do not copy uncommitted canonical-checkout research files into PR #936 or claim the referenced local repairs are integrated.

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

No PR update/push, merge, protected outcome access, broker API, order action, runtime change, or live/paper action was performed. The separate PR #936 remains a draft. No new config keys or production migration were added. No PR-specific CI dependency workflow was changed due the explicit protected-path instructions. The isolated dependency lock and new test hooks are listed above. Risks still fail closed where evidence or permission authority is missing.
