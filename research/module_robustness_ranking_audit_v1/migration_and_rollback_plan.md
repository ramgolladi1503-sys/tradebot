# Migration And Rollback Plan

Roll out repairs in read-only evidence mode first. Preserve old fields while adding lifecycle IDs. Roll back actionability changes by keeping new trace fields but disabling stricter UI/order gates until fixtures pass.
