# Order Safety Declaration

As required by repository AGENTS.md trading safety laws:

```text
read_only = true
is_order_action = false
broker_api_called = false
allowed_for_live_execution = false
orders_placed = 0
orders_modified = 0
orders_cancelled = 0
broker_write_authority = false
order_authority = false
```

No live order was placed, modified, cancelled, or routed to any broker.
