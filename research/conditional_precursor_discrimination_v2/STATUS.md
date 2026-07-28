# Campaign Status

Current gate: `VERIFY_CONSOLIDATED_EVIDENCE_AND_REPRODUCE_PRIOR_CAMPAIGN`

The conditional-discrimination stage is intentionally blocked until GitHub Actions confirms that:

1. PR #723 Git LFS objects resolve to real files;
2. consolidation manifest hashes and byte sizes match;
3. preserved parquet files are readable;
4. prior reverse-causal counts and family definitions reproduce;
5. focused evidence-verification tests pass.

No holdout has been opened. No production implementation is allowed.
