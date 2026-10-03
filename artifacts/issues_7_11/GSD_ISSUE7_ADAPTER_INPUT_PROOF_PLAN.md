# GSD Plan — Issue 7 verified adapter-input proof

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, UPDATE_DOCS
**title:** Assert exact verified T-1 values reach the real shadow adapters
**scope:** `docs/agent_reviews/issues_7_11_hermes_issue7_adapter_input_proof.md`

## Work

- Baseline existing Scenario A test: passed 1 test at exact worktree HEAD `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`.
- Add assertions in `tests/test_market_heritage_graph.py` comparing the verified T-1 loader fields (prior futures key/close and overnight close/SMA200) with adapter state. Separately assert a nonempty current expiry from a synthetic launch-plan input reaches the Opening Drive adapter; expiry is not a T-1 loader field.
- Run the focused Scenario A test and adjacent heritage/registry tests.
- Record tests-only evidence in graph and ledgers. Keep historical T-1 authority UNKNOWN.

## Safety

No production files, data files, configuration, strategy behavior, feed, risk, broker, order, live, or token-universe changes. Synthetic fixture only; no source-authority claim.

## Independent verifier follow-up

The verifier found the current target-expiry constructor value was not asserted and that the mutation script accepted any one test failure as a kill. Test a nonempty synthetic launch-plan expiry separately from T-1 loader fields, and require the intended assertion failure in both adapter-input and mixed-symbol mutation harnesses.

## Acceptance

The exact T-1 value-to-adapter assertions and separate nonempty launch-plan expiry assertion pass; adapter dispatch remains; both mutation harnesses fail specifically at their intended assertions; all authority markers remain closed; and adjacent heritage tests pass. This is partial offline evidence only; it cannot close Issue 7 historical source authority.

Fresh verifier follow-up: the initial generic failure predicate and a `None` expiry fixture would not demonstrate expiry routing. The acceptance fixture now supplies a nonempty synthetic launch-plan expiry (distinct from the T-1 loader), asserts the real adapter retains it, and the temp-copy mutant corrupts expiry to `None`. The harness requires the exact expiry assertion and `AssertionError`; it passes only after that expected failure. Existing Issue 7 calendar/assembler harness also passed 5/5 mutants.
