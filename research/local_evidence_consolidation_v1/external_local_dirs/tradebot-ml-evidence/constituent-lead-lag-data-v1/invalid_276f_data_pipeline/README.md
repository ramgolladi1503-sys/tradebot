# Invalid Data Pipeline Classification

**Classification:** `INVALID_DATA_ACQUISITION_EVIDENCE`

## Reasons:

*   `scripts/phase3_verify_data.py` records guessed endpoints, hard-coded API V2, hard-coded NIFTY association, fallback=true, empty session coverage, and a dummy “Completed” report.
*   `scripts/phase3_build_plan.py` fetches only seven estimated weekdays, ignores exchange holidays, and can include an incomplete current session.
*   `scripts/phase4_fetch.py` reads `../tradebot/.env`, has no CLI date range, no request timeout, incomplete retry handling, no response-contract validation, and ambiguous checksum semantics.
*   `scripts/phase5_validate.py` does not perform full OHLC, duplicate, five-minute-boundary, session-completeness, or checksum validation.
*   `scripts/phase6_normalize.py` hard-codes rejection of 2026-07-23, omits the required session column, and is not a general completed-session implementation.
*   `scripts/phase2_resolve_instruments.py` uses deprecated Upstox CSV data and does not prove unique EQ/index resolution through instrument type, segment, ISIN, and ambiguity checks.
*   `tests/research/test_upstox_v3_fetch.py` tests handwritten snippets and pandas behavior rather than importing and testing the real pipeline.
*   Seven days cannot activate the frozen 20-session z-score warm-up.
*   Authoritative point-in-time weights remain absent.

The latest code from commit `276f15ee351618ab6b275185d0dcc26adedabf1e` may remain useful only as disposable debugging history. It is not authoritative evidence.
