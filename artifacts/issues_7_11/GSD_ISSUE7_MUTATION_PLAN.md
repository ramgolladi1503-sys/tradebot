# GSD Stage 2 Plan — Issue 7 T-1 Assembler Mutations

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Mutation-test Issue 7 fail-closed assembler guards
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**Hermes contract:** `docs/agent_reviews/issues_7_11_hermes_issue7_mutation.md`

## Files

- `docs/agent_reviews/issues_7_11_hermes_issue7_mutation.md`: contract and mutation scope.
- `artifacts/issues_7_11/GSD_ISSUE7_MUTATION_PLAN.md`: execution and acceptance record.
- `scripts/verify_issues_7_11_issue7_mutations.py`: isolated temporary-copy mutation runner.

## Baseline

`python3 -m pytest -q tests/test_market_heritage_graph.py::test_t1_assembler_fails_closed_on_incomplete_or_mismatched_evidence` → 5 passed, 1 warning. This includes wrong source date, future availability, missing field, and neighboring incomplete/mismatched cases.

## Execution

1. Read the exact guard anchors from `core/market_heritage_graph.py` and target cases from `tests/test_market_heritage_graph.py`.
2. Copy the source module and target test file into a temporary package. Extend only that package's module search path to use unchanged repository dependencies.
3. Mutate one guard at a time: prior-date comparison, decision-epoch comparison, and required-field completeness check.
4. Run only the matching existing parameterized test for each mutant with bytecode writes disabled and a bounded timeout.
5. Treat a passing mutant, missing target test, import/collection error, or timeout as harness failure.
6. Remove the temporary directory automatically; confirm source checksums/diff remain unchanged.

## Acceptance and limits

All three mutants are killed by their corresponding behavior test; the unmodified targeted test remains green. No production file or prerequisite value changes. This closes only these three Issue 7 assembler mutation cases. Calendar holiday/source stager mutations and source-authority gates remain open/UNKNOWN.
