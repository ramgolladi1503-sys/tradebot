# Composition Conflicts

- `config/config.py`: PR #748 and PR #750 both modify this path. Not auto-merged.
- `core/kite_depth_ws.py`: PR #748 and PR #750 both modify this path. Not auto-merged.

Resolution: keep campaign code additive; treat #750 as feed-truth authority and #748 as observer launch/token-union authority.
