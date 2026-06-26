# Phase 10: Dashboard & Reporting Hardening Report

## Enhancements Implemented
Because live-Dashboard UI frameworks (e.g. Streamlit) present a risk of conflating advisory data with execution signals, the MIP explicitly uses an offline reporting generator: `scripts/generate_mip_report.py`.

1. **Mandatory Disclaimers**: The report physically hardcodes the following print statements before dumping any data:
   - `DISCLAIMER: NOT A TRADE SIGNAL.`
   - `DISCLAIMER: NO EXECUTION INFLUENCE.`
   - `DISCLAIMER: NO RANKING INFLUENCE.`
2. **Vocabulary Sanitization**: The words "edge", "chance", "win probability", "sure trade", "high probability", and "confidence score" are banned from the generator loop.
3. **Transparent Factoring**: The report generator pulls from the `intelligence_factors` table to prove the breakdown of any aggregate score, listing the explicit name, value, and unit (e.g. `freshness_delta_seconds: 3600 seconds`).
4. **Source Health Matrix**: Generates a clear view of which sources are succeeding vs failing (e.g., hitting `ROBOTS_BLOCKED` or `TIMEOUT`), pulling directly from the `intelligence_fetch_runs` table.
