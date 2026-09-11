# Kite depth protocol authority v1

Broker: Zerodha Kite Connect, WebSocket API v3.

Primary references:

- https://kite.trade/docs/connect/v3/websocket/
- https://github.com/zerodha/pykiteconnect/blob/master/kiteconnect/ticker.py

Protocol facts: full packet 184 bytes; depth region bytes 64..184; ten 12-byte depth entries; first five are `buy`, next five are `sell`. Each entry carries unsigned quantity (4 bytes), price (4 bytes, scaled), orders (2 bytes), and padding.

Active parser: `kiteconnect` 5.2.0, `kiteconnect/ticker.py`, SHA256 `5b491b554eb31f419ef8bdc93ae26672f1f6fd162eb6acefa83706eb29f6f87d`. The parser iterates `range(64, len(packet), 12)` and assigns `i >= 5` to sell.

Canonical internal schema: `KiteTop5DepthV1`, exactly five fixed-field levels per side, fields `quantity`, `price`, `orders`. Malformed cardinality or field range is rejected as `KITE_DEPTH_PROTOCOL_VIOLATION`; no truncation or padding occurs.

Wire bounds: `DEPTH_ENTRY_WIRE_BYTES=12`, `TOTAL_DEPTH_WIRE_BYTES=120`, `FULL_MODE_PACKET_BYTES=184`, `DEPTH_LEVELS_PER_SIDE=5`, `TOTAL_DEPTH_LEVELS=10`.

The live source is the Kite v3 WebSocket full-mode path in `core/kite_depth_ws.py`. No alternate authoritative depth source was found in that live path. This is broker-provided market depth, not a full exchange order book.
