import re

with open('core/blocker_lifecycle.py', 'r') as f:
    content = f.read()

# Fix NO_LIVE_OPTION_FEED to not trigger on simple age_sec > feed_limit
# The user specified that absence of ticks doesn't mean the feed is dead.
new_content = content.replace(
"""    elif subscribed_count > 0 and (age_sec is None or age_sec > feed_limit):
        no_live_fault = True
        no_live_reason = "option_tick_age_exceeded\"""",
"""    elif subscribed_count > 0 and latest_option_tick_ts is None:
        # Only treat it as dead if we never received ANY option ticks since connection
        # The realtime decision_dag handles cycle-by-cycle age_sec > 2.0.
        no_live_fault = True
        no_live_reason = "option_tick_age_exceeded_critical\""""
)

# Fix STALE_OPTION_LTP to not use a 10s TTL for normal tick gaps.
# We set stale_fault to False, because decision_dag realtime check is sufficient,
# or we use a higher threshold so it doesn't trigger on normal illiquidity.
new_content = new_content.replace(
"""    stale_fault = bool(subscribed_count > 0 and latest_option_tick_ts is not None and age_sec is not None and age_sec > feed_limit)""",
"""    # Don't trigger a 10s TTL blocker for normal tick gaps, decision_dag handles cycle-level freshness.
    stale_fault = bool(subscribed_count > 0 and latest_option_tick_ts is not None and age_sec is not None and age_sec > max(60.0, float(feed_limit) * 10.0))"""
)

with open('core/blocker_lifecycle.py', 'w') as f:
    f.write(new_content)
