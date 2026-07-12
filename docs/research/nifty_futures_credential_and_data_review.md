# NIFTY futures credential and data review

## Verdict

`SECRET_REFERENCE_FOUND`

I found references to authenticated Upstox usage in committed documentation, but I did not find an exposed secret value in the scanned tracked files.

## What was inspected

Tracked files reviewed:

- `docs/data_acquisition/NIFTY_FUTURES_AUTHENTICATED_FETCH.md`
- `docs/data_acquisition/NIFTY_FUTURES_REFERENCE_VWAP.md`
- `docs/data_acquisition/NIFTY_FUTURES_SESSION_VALIDATION.md`
- `docs/data_acquisition/NIFTY_FUTURES_REJECTION_LOG.md`
- `docs/data_acquisition/NIFTY_FUTURES_SEARCH_LOG.md`
- `docs/data_acquisition/NIFTY_FUTURES_SELECTED_DATASET.md`
- `docs/data_acquisition/NIFTY_FUTURES_SHORTLIST.md`
- `docs/data_acquisition/NIFTY_FUTURES_SOURCE_INVENTORY.md`
- `docs/data_acquisition/NIFTY_FUTURES_SOURCE_SCORECARD.csv`
- `scripts/fetch_upstox_instruments.py`
- `scripts/audit_upstox_candle_files.py`
- `runtime/strategy_validation/**` reports referencing NIFTY futures / Upstox / replay blockers

## Credential findings

### Reference-only findings

- `docs/data_acquisition/NIFTY_FUTURES_AUTHENTICATED_FETCH.md:9` contains the text `Upstox access token`.
- `docs/data_acquisition/NIFTY_FUTURES_AUTHENTICATED_FETCH.md:15` contains `Instrument Token: NSE_FO|61093`.
- `scripts/fetch_upstox_instruments.py` references Upstox instrument download behavior but does not expose a token value.
- `scripts/audit_upstox_candle_files.py` references Upstox candle validation logic but does not expose a token value.

### No secret value found

I did not find a committed bearer token, API key, or obvious credential string in the scanned tracked files.

## Data artifacts found

Committed, public-safe documentation artifacts:

- authenticated fetch note for NIFTY futures
- reference VWAP note
- session validation note
- source inventory / shortlist / rejection log / search log / scorecard

Committed runtime validation artifacts:

- multiple `runtime/strategy_validation/**` reports showing replay and WFA blocker states
- those reports are evidence artifacts, not raw source data dumps

No `/tmp` artifact was referenced in the inspected NIFTY futures docs.

## Reproducibility assessment

The NIFTY futures validation is only partially reproducible from committed/public-safe files.

What is reproducible:

- the documented source inventory and rejection reasoning
- the existence of the claimed validation path
- the session and VWAP narrative in the committed docs

What is not reproducible from the repo alone:

- the authenticated Upstox fetch itself
- the private access-token-backed API response
- any evidence that depends on a live authenticated session

The `SESSION_VALIDATION` note also records that official NSE daily reconciliation was unavailable because the Bhavcopy URL returned `404` for that date.

## Evidence grade

Current NIFTY futures validation is best treated as:

`EXPLORATORY_WITH_DOCUMENTED_AUTHENTICATED_FETCH`

It is not fully evidence-grade for an unauthenticated reader, because the core fetch step depends on an authenticated Upstox session.

## Recommended next step

Move the validated NIFTY futures source into a durable, reproducible ingestion path that records:

- source URL or API contract
- exact file hash of the fetched artifact
- fetch timestamp
- whether the fetch required authentication
- whether the artifact is committed, cached, or ephemeral

That would make the validation auditable without depending on a hidden session.

