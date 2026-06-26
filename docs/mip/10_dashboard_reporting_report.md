# Agent 10 Report: Dashboard & Reporting 

## Objective
To expose the Market Intelligence Platform (MIP) data to the user without implying trading edge or generating false confidence.

## Allowed vs Forbidden Terminology

The reporting module (whether terminal output, web UI, or log summary) must strictly sanitize its vocabulary.

### Allowed Labels
- "Advisory market context"
- "Uncalibrated"
- "Not a trade signal"
- "No execution influence"
- "No ranking influence"
- "Extraction Parsing Confidence" (strictly constrained to the parser's success rate, not trade success rate)
- "Calibration Status"

### Forbidden Labels (Strictly blocked)
- "Edge"
- "Chance"
- "Win probability"
- "Confidence score" (when referring to the candidate's chance of profit)
- "Sure trade"
- "High probability"
- "Guaranteed"

## Proposed Dashboard Views

1. **Source Health**: Displays which registries (RBI, SEBI, NSE) are currently returning 200 OK vs blocked by `robots.txt` or rate limits.
2. **Crawler Health**: Shows fallback utilization (e.g., degraded to `http_fetcher.py` because `Crawl4AI` failed).
3. **Latest Advisory Events**: A ticker of recent parsed events with explicit tags: `[UNCALIBRATED]`, `[ADVISORY-ONLY]`.
4. **Factor Breakdown**: Displays the underlying `EvidenceValue` strings and reason codes so humans can audit why an event was extracted.
5. **Replay Validation Status**: Shows the date range and sample size of the last offline Replay engine calibration run.

No telemetry stream mapping to live PNL metrics will combine these advisory events unless they are `CALIBRATED`.
