# Ariadne Failure Clustering

Ariadne is a static/local failure text clusterer for CI and pytest output.

It is designed to reduce symptom-driven PR loops by grouping failures that share root-cause signals before any remediation plan is considered.

## Scope

Ariadne reads failure text and groups failures by stable signals:

- fixture
- missing field
- safety boundary
- runtime flow step
- candidate/ranking concept
- normalized error text
- module fallback

## Non-goals

Ariadne does not:

- create PRs
- auto-fix code
- call external agents
- run live runtime
- call brokers
- mutate repository files

## Confidence

Clusters emit one of three confidence values:

- `CONFIRMED`: repeated failures share a strong proof-backed signal.
- `LIKELY`: one proof-backed failure has a useful root-cause signal.
- `UNKNOWN`: the cluster lacks enough proof for a fix contract.

## Fix Contracts

Ariadne can build a fix contract only when a cluster has proof and confidence is not `UNKNOWN`.

If a cluster lacks proof, the contract is blocked with:

```text
proof_required_before_fix_contract
```

This prevents patch suggestions from being generated from weak or unproven failure text.

## Example

Four failures with the same fixture lookup issue are grouped into one fixture cluster. Unrelated candidate schema, safety-boundary, or runtime-flow failures are kept separate.
