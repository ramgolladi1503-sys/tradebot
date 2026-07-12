# OOS context contract implementation

## Summary

The replay-only candidate handoff runner now accepts explicit OOS partition context from command/config arguments and propagates it through the replay-context proof path.

## Supported explicit inputs

- `is_oos`
- `oos_label`
- `oos_source`
- `partition_id`
- `split_name`

## Validation rules

The runner fails closed when explicit OOS context is partial or inconsistent:

- `is_oos=true` requires `oos_label=OOS`
- `is_oos=false` requires `oos_label=IS`
- `oos_source` is required whenever explicit OOS context is supplied
- a partial context missing the core fields is blocked
- invalid labels are blocked

## Propagation

When explicit OOS context is valid, it is preserved in:

- replay context bundle evidence
- runtime handoff payload
- candidate journal row
- replay audit JSON output

The runner does not infer OOS from dates, filenames, or source paths.

## Safety

- production artifacts remain isolated by default
- explicit OOS context does not mark candidate proof successful by itself
- candidate emission still must occur naturally
