# V33C internal release image decision

`INTERNAL_RELEASE_IMAGE_REQUIRED=true` for full emergency continuation, but it is not prepared in V33C because that would be a separate exact-SHA release-image operation. `INTERNAL_RELEASE_IMAGE_READY=false`. Until this is resolved, source-volume loss selects controlled shutdown only.
