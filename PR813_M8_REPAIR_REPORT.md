# PR813 M8 repair report

Original candidate: `702ec1d24267281f6b961b0f52be0c3dd953dd89`.

The independent review identified two major defects. First, websocket observation callback/tick acceptance still required reconnect-generation equality. Second, MEG live-bar provenance still rejected reconnect-generation mismatch. Both decisions now require current `feed_epoch`; reconnect generation remains diagnostic metadata only. Missing or stale feed epoch fails closed.

The repair also propagates `feed_epoch` into observation-plan state, feed-session identity, subscription evidence, and live-bar provenance. Existing session, universe, token, lifecycle, and non-live provenance protections remain in force.

No live runtime, broker API, or order action was used. Independent re-review is required after the repaired commit.
