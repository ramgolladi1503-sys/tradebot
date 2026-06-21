# Strategy Truth Bug Register

| Strategy Name | Bug Category | Description | Status |
|---|---|---|---|
| HTF_OPENING_DRIVE_CONT | IMPLEMENTATION_BUG_FOUND | Rejects valid bullish and bearish inputs due to structure mapping logic errors. Fails to safely return `Rejection` on `NaN` data. | UNRESOLVED |
| HTF_15M_TREND_CONT | IMPLEMENTATION_BUG_FOUND | Rejects valid bearish inputs due to structure mapping logic errors. | UNRESOLVED |
| HTF_FAILED_BREAKOUT_REVERSAL | IMPLEMENTATION_BUG_FOUND | Miscalculates expected mapping direction target. | UNRESOLVED |
| HTF_PDH_PDL_HOLD | IMPLEMENTATION_BUG_FOUND | Rejects valid bullish inputs. | UNRESOLVED |
| ALL HTF STRATEGIES | PIPELINE_MUTATION_FOUND | HTF_BYPASSES_MAIN_SAFETY_GATES: HTF paths run via an isolated script (`run_htf_real_paper_monitor.py`) and completely bypass `TradeBuilder`, Phase-2 fallbacks, and Execution Gates. | UNRESOLVED |
| ALL HTF STRATEGIES | IMPLEMENTATION_BUG_FOUND | HTF_MISSING_DATA_FAILS_WITH_INDEXERROR: Missing dataframe logic raises unhandled `IndexError` rather than correctly failing closed via a `Rejection` object. | UNRESOLVED |
