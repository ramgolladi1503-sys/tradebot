# V37 internal release image report

STATUS: VERIFIED

The release image is materialized from the final successor SHA under
`~/.tradebot/releases/<SUCCESSOR_SHA>/`, with the SHA recorded in
`SOURCE_SHA`. The image contains executable source packages, configuration,
tests, and V37 authority artifacts while excluding bulky historical/runtime
payloads. The exact 118-node and 47-node authorities pass from that image.
