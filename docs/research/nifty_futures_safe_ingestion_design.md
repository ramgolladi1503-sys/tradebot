# NIFTY futures safe ingestion design

## Goal

Convert the current exploratory authenticated NIFTY futures validation into a reproducible ingestion workflow that is credential-safe by default and auditable without exposing secrets.

This design does not fetch data. It defines the contract for doing so safely later.

## Current state

The repo already contains:

- authenticated NIFTY futures validation notes
- source inventory / shortlist / rejection logs
- a reference VWAP note
- a session validation note
- scripts for fetching Upstox instruments and auditing candle files

The weakness is not the lack of narrative evidence. The weakness is that the authenticated fetch path is not yet formalized as a token-safe, reproducible pipeline with a clear public/private artifact split.

## Safety rules

The workflow must:

- read `UPSTOX_ACCESS_TOKEN` only from the environment
- fail closed if `UPSTOX_ACCESS_TOKEN` is missing or empty
- never print the token
- never write the token to any report or artifact
- never silently fall back to an unauthenticated source when the authenticated source is required
- never treat an ephemeral `/tmp` artifact as durable evidence

If the token is unavailable, the run must stop with a blocked verdict and a reason code such as `MISSING_UPSTOX_ACCESS_TOKEN`.

## Proposed workflow

### 1. Resolve the source contract

Inputs:

- `UPSTOX_ACCESS_TOKEN`
- target instrument metadata
- date range
- candle interval

Checks:

- confirm the requested instrument exists in the instrument master or an approved mapping
- confirm the request is for the intended NIFTY futures contract, not a spot index or options artifact

Output:

- a small public-safe request manifest containing the instrument identity, date range, and request mode

### 2. Fetch the raw candle data

Behavior:

- use the authenticated Upstox API path only when `UPSTOX_ACCESS_TOKEN` is present
- keep the raw response private by default
- write raw payloads only to an ignored private directory unless an explicit approval is later granted to promote a subset into committed evidence

Required recorded metadata:

- source
- instrument key, redacted if needed
- date range
- candle count
- SHA256 of the raw artifact
- fetch timestamp
- whether the fetch was authenticated
- whether the fetch succeeded or was blocked

### 3. Validate the candle file

Validation should confirm:

- chronological integrity
- no duplicate timestamps
- expected intraday granularity
- non-flat series sanity
- non-synthetic provenance
- required OHLCV fields
- volume semantics

The validation output should never depend on hidden state. It should be reproducible from the stored raw artifact and the validator version.

### 4. Compute reference VWAP

The VWAP formula should be recorded explicitly in the report. Use a standard cumulative VWAP definition:

- cumulative typical price numerator or close-price-based numerator as defined by the existing validation method
- cumulative volume denominator
- same session boundary rules as the validator

The report must say which exact formula was used for the reference VWAP and whether the result is derived from:

- raw fetched candles
- a validated local cached artifact
- a public-safe committed sample

### 5. Separate public-safe and private artifacts

Public-safe artifacts can be committed:

- source inventory
- shortlist
- rejection log
- search log
- validation report without secrets
- SHA256-only metadata
- candle count / date range / instrument identity

Private artifacts must stay ignored unless explicitly approved:

- raw authenticated API responses
- token-bearing request logs
- any file that could be replayed to reconstruct the token or session
- any temp file under `/tmp`

Recommended layout:

- public report: `docs/data_acquisition/NIFTY_FUTURES_*.md`
- private raw artifacts: `.runtime/nifty_futures_ingestion/<run_id>/...`

## Durable metadata to write

Every successful run should persist a small metadata record containing:

- `source`
- `instrument_key_redacted`
- `date_range`
- `candle_count`
- `sha256`
- `vwap_formula`
- `validation_status`
- `authenticated` boolean
- `artifact_policy` (`public_safe`, `private_only`, or `blocked`)
- `source_path`
- `created_at_utc`

This metadata should be enough to audit the run without exposing the token or raw response.

## What the public-safe report should contain

The report should explain:

- which source was used
- why it was accepted or rejected
- what was validated
- what remains blocked
- whether the result is evidence-grade or exploratory

It should not contain:

- the token
- bearer headers
- raw response bodies
- session cookies
- private filesystem paths that only make sense on one machine

## What must remain private or ignored

Keep these out of committed docs unless explicitly approved:

- raw Upstox fetch output
- per-request auth headers
- raw instrument dumps that are not meant for publication
- any cache that is only valid for one authenticated session
- any `/tmp` artifact

If a private artifact is useful for analysis, it should be referenced only by an opaque run ID and a SHA256 digest in the public-safe report.

## Fail-closed behavior

The pipeline must stop with a blocked status when any of these are true:

- `UPSTOX_ACCESS_TOKEN` is missing
- the instrument cannot be resolved
- the candle file fails validation
- the fetched artifact cannot be hashed
- the run would have to guess provenance
- the run would have to infer a missing field that matters to reproducibility

## Recommended implementation shape

Use a small wrapper script or module that:

1. reads the token from `UPSTOX_ACCESS_TOKEN`
2. fetches the candles
3. writes raw private artifacts under an ignored run directory
4. computes the SHA256 and metadata
5. emits a public-safe report
6. returns a blocked verdict instead of guessing when any required field is missing

Do not merge this with strategy logic, replay logic, or trade execution logic.

## Verdict

`SAFE_INGESTION_DESIGN_READY`

The workflow is defined as a reproducible, credential-safe ingestion contract. It still needs an implementation that obeys the artifact policy and fail-closed rules.

