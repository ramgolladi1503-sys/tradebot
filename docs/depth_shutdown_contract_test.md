# Depth Shutdown Contract

The focused test suite covers empty shutdown, queued backlog, batch processing, writer failure, and repeated shutdown behavior. Successful drains require zero pending rows, zero queue depth, accepted rows equal durable rows, and a joined worker. A writer failure marks durability degraded and is not counted as durable.

Result: `PASS` (`44 passed`).
