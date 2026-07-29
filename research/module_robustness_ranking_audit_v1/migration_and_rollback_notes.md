# Migration And Rollback Notes

Stricter row identity and fallback policies can reduce displayed/actionable counts and reorder ranks. Roll out behind read-only evidence gates first, then require `ranking_snapshot_id` and `candidate_id` for actionable UI controls. Roll back by leaving the stricter fields in evidence but disabling actionability changes until replay parity is explained.
