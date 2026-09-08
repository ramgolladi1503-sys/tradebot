# V37 depth queue bound

`MAX_DEPTH_QUEUE_ITEM_BYTES=742` and
`MAX_DEPTH_QUEUE_BYTES=12,156,928` (`742 * 16,384`). The item contains the
618-byte maximum canonical ten-level depth record plus the bounded timestamp,
token, imbalance, and receipt envelope. Admission occurs before queue put.
