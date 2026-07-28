# Runbook

```bash
python -m pytest -q tests/research/test_conditional_precursor_discrimination_v2.py
python scripts/run_conditional_precursor_discrimination_v2.py --repo-root "$PWD"
```

The runner exits non-zero for unresolved LFS pointers, manifest mismatch, unreadable parquet, or failure to reproduce the prior campaign.
