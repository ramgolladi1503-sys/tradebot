# Issue 10 advisory reader mutation results

**source_agent:** gsd
**action:** UPDATE_DOCS
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**branch:** `ram/issues-7-11-graph-repair`

## Baseline

Command:

```text
pytest -q tests/core/test_runtime_snapshot_producer.py::test_runtime_snapshot_advisory_fails_closed_on_in_place_rewrite_during_read tests/core/test_runtime_snapshot_producer.py::test_runtime_snapshot_advisory_uses_lf_only_as_jsonl_record_delimiter tests/analytics/test_issues_7_11_eod_row_parity.py
```

Result: **3 passed, 1 warning in 1.53s**.

## Isolated mutation run

Command:

```text
python3 scripts/verify_issues_7_11_issue10_mutations.py
```

Result: **2/2 targeted mutants killed**.

- `disable_in_place_mutation_detection` — the in-place rewrite test failed under the mutant.
- `split_on_unicode_line_separators` — the U+2028-in-string test failed under the mutant.
- The script requires the intended test to appear with one assertion failure; import/collection errors and timeouts do not count as killed mutants.
- All mutations ran in temporary copies with bytecode caching disabled. Temporary copies were removed after the run.

## Integrity

- `core/runtime_snapshot_producer.py` SHA-256: `1ec337c2297914b00bd77cb9389bacc568d9f461c46a2d8914ff46ab2ac4dcf2`
- `tests/core/test_runtime_snapshot_producer.py` SHA-256: `27224308ed5b853ab0472aec6ead5b65982e319d8b402488e58c256d6ac6b4f9`
- The mutation runner independently checked both checkout hashes after the isolated runs; they were unchanged.
- `git diff --check`: clean.

## Limits

This verifies two Issue 10 reader guards only. It does not prove concurrent multi-process writer atomicity, captured/live EOD parity, unknown-desk routing policy, or campaign-wide mutation closure. No runtime, broker, order, risk, strategy, feed, config, or token-universe behavior changed.
