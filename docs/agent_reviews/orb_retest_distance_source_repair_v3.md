# ORB Retest Distance Source Repair v3

Verified baseline: `a48176fc245375f15e316493364915ec37439e29`

Approved repair: `retest_distance_pct` is calculated from `setup.retest_bar.close` to `setup.normalized_boundary_value`.

Before equation:

```text
retest_distance_pct = abs(setup.breakout_bar.close - setup.normalized_boundary_value) / abs(setup.normalized_boundary_value)
```

After equation:

```text
retest_distance_pct = abs(setup.retest_bar.close - setup.normalized_boundary_value) / abs(setup.normalized_boundary_value)
```

Preserved equation:

```text
breakout_distance_pct = directional_distance(setup.breakout_bar.close, setup.normalized_boundary_value)
```

Temporal candidate presence changed: `NO`

Thresholds changed: `NO`

Strategy identity changed: `NO`

Evidence fields added:

```text
breakout_close
retest_close
continuation_close
retest_distance_source
breakout_distance_source
```

Validation:

```bash
pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py
python3 -m py_compile strategies/movement/opening_range_breakout.py tests/test_opening_range_retest_temporal_fixture_contract.py
ruff check strategies/movement/opening_range_breakout.py tests/test_opening_range_retest_temporal_fixture_contract.py
git diff --check
```

Result: `PASS`
