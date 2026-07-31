# Whole-TradeBot QA Certification V1 — Independent Review Record

## Purpose

Establish a fail-closed QA certification campaign for the complete authoritative TradeBot runtime rather than certifying one isolated module or relying on aggregate pytest count.

## Scope

The campaign covers nine system areas:

1. runtime startup and authentication;
2. feed/WebSocket lifecycle and market-data truth;
3. orchestration and decision flow;
4. trade builder and instrument resolution;
5. risk, manual approval, review queue and execution boundary;
6. persistence, reconciliation and recovery;
7. candidate scoring, ranking and capital selection;
8. dashboard, observability and operator truth;
9. feature, strategy, replay and ML truth.

Research-only utilities are outside the production certificate unless they are authoritative in a live, paper or replay decision path.

## Files changed

- `.github/workflows/qa-whole-tradebot-certification.yml`
- `tools/qa_certification/__init__.py`
- `tools/qa_certification/whole_tradebot_manifest.py`
- `tools/qa_certification/evaluate_coverage.py`
- `tests/qa/test_whole_tradebot_coverage_evaluator.py`
- `tests/qa/test_whole_tradebot_cross_module_truth.py`
- `docs/agent_reviews/whole_tradebot_certification_v1.md`

## Tests and gates introduced

- Fail-closed module-manifest validation.
- Per-module line and branch coverage evaluation.
- Full deterministic pytest run with `sitecustomize.py` removed.
- Test-family ownership checks for behavior, safety, edge, regression, UI read models, replay, chaos and broker firewall.
- Cross-module tests for:
  - fallback rows remaining advisory-only;
  - fallback rows receiving no execution authority or capital;
  - ranking separating strong and weak opportunities;
  - deterministic replay without input mutation;
  - late risk failure overriding earlier top rank;
  - manual approval consumption exactly once;
  - operator pools keeping fallback rows out of executable opportunities.
- Same-commit 1,000-cycle feed/reconnect resource certification.
- Independent Bandit and dependency vulnerability evidence.
- Final certificate assembly that fails unless every prerequisite succeeds on one immutable SHA.

## Initial evidence

The first workflow execution intentionally started from a red baseline and exposed the following:

- The nine-area manifest resolved to real repository modules with no duplicate targets.
- Existing behavior, safety, edge and regression families collected tests.
- Replay, chaos, broker-firewall and UI-read-model families initially collected zero tests.
- The first cross-module run failed because its QA fixture passed a field that does not exist in the immutable `Trade` schema; this was a test defect, not a product defect, and was corrected.
- The runtime Bandit scan produced 41 medium/high findings: 9 high and 32 medium.
- Findings requiring real remediation include unsafe archive extraction, untrusted XML parsing, permissive database modes and unrestricted URL schemes.
- Identity/deduplication SHA-1 or MD5 uses require explicit non-security intent rather than blanket suppression.
- The ordinary `requirements.txt` installation still resolves KiteConnect with vulnerable Autobahn 19.11.2. A separate patched-wheel proof does not make the default installation path secure.

## UI and ranking evidence boundary

The uploaded operator view showed recovered fallback rows and weakly separated confidence values with similar visual importance. The campaign therefore does not treat a dashboard filter as a fix. It requires evidence that:

- fallback rows cannot enter the executable pool;
- ranked quality changes ordering materially;
- the UI reads the canonical executable and advisory pools separately;
- late risk truth overrides ranking;
- capital is assigned only after execution truth passes.

## Risks

- Tier-A 100% line/branch targets are expected to reveal substantial untested runtime behavior.
- A green deterministic suite alone does not establish live market, broker, restart or reconciliation truth.
- The default dependency installation remains insecure until the patched KiteConnect path becomes canonical and compatible.
- Security findings must be triaged by exploitability with negative controls; they must not be dismissed solely because Bandit is noisy.
- A same-SHA controlled-live observation still requires valid credentials and operator approval and must never place an unauthorized order.

## Scope guard

- No strategy thresholds, expected profitability or edge claims are changed by this campaign.
- No live order is placed.
- No broker call is permitted by the certification tests.
- The PR remains draft and stacked on the QA foundation branch.

## Independent verdict

`NOT_CERTIFIED`

The campaign now covers the entire authoritative TradeBot runtime, but the repository has not yet met the complete-system coverage, security, replay, chaos, broker-firewall, UI-read-model, dependency and controlled-runtime evidence requirements. A certificate must remain unavailable until every hard gate passes on the same immutable commit.

## Next action

Use the fail-closed coverage report and complete security artifacts to repair one critical area at a time, beginning with unsafe input handling and the candidate/ranking/operator-truth chain. Re-run the complete workflow after each evidence-backed correction; do not weaken thresholds to obtain a green status.
