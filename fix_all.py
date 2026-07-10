import re

# 1. core/kite_depth_ws.py
with open('core/kite_depth_ws.py', 'r') as f:
    ws_content = f.read()

ws_content = ws_content.replace(
"""        if to_subscribe:
            ws.subscribe(to_subscribe)
            ws.set_mode(ws.MODE_FULL, to_subscribe)""",
"""        if to_subscribe:
            try:
                from twisted.internet import reactor
                reactor.callFromThread(ws.subscribe, to_subscribe)
                reactor.callFromThread(ws.set_mode, ws.MODE_FULL, to_subscribe)
            except ImportError:
                ws.subscribe(to_subscribe)
                ws.set_mode(ws.MODE_FULL, to_subscribe)"""
)
ws_content = ws_content.replace(
"""        try:
            if hasattr(ws, "unsubscribe"):
                ws.unsubscribe(to_unsubscribe)
        except Exception as exc:""",
"""        try:
            if hasattr(ws, "unsubscribe"):
                try:
                    from twisted.internet import reactor
                    reactor.callFromThread(ws.unsubscribe, to_unsubscribe)
                except ImportError:
                    ws.unsubscribe(to_unsubscribe)
        except Exception as exc:"""
)
with open('core/kite_depth_ws.py', 'w') as f:
    f.write(ws_content)

# 2. core/blocker_lifecycle.py
with open('core/blocker_lifecycle.py', 'r') as f:
    blocker_content = f.read()

blocker_content = blocker_content.replace(
"""    elif subscribed_count > 0 and (age_sec is None or age_sec > feed_limit):
        no_live_fault = True
        no_live_reason = "option_tick_age_exceeded\"""",
"""    elif subscribed_count > 0 and latest_option_tick_ts is None:
        no_live_fault = True
        no_live_reason = "option_tick_age_exceeded_critical\""""
)
blocker_content = blocker_content.replace(
"""    stale_fault = bool(subscribed_count > 0 and latest_option_tick_ts is not None and age_sec is not None and age_sec > feed_limit)""",
"""    stale_fault = bool(subscribed_count > 0 and latest_option_tick_ts is not None and age_sec is not None and age_sec > max(60.0, float(feed_limit) * 10.0))"""
)
with open('core/blocker_lifecycle.py', 'w') as f:
    f.write(blocker_content)

# 3. core/opportunity_engine.py
with open('core/opportunity_engine.py', 'r') as f:
    opp_content = f.read()

# I will find where execution_allowed is first defined near spread_ok
if "execution_allowed = bool(_get_value(candidate, \"execution_allowed\", False))" in opp_content:
    # Need to replace the first occurrence or all relevant occurrences
    parts = opp_content.split("execution_allowed = bool(_get_value(candidate, \"execution_allowed\", False))\n    tradable = bool(_get_value(candidate, \"tradable\", False))\n")
    if len(parts) > 1:
        new_opp = parts[0] + "execution_allowed = bool(_get_value(candidate, \"execution_allowed\", False))\n    tradable = bool(_get_value(candidate, \"tradable\", False))\n\n    if source_flags.get(\"quote_source\") == \"REST_RECOVERY\" or source_flags.get(\"recovered_fallback\"):\n        execution_allowed = False\n        if isinstance(candidate, dict):\n            candidate[\"execution_allowed\"] = False\n            candidate[\"mode\"] = \"advisory_only\"\n        elif hasattr(candidate, \"execution_allowed\"):\n            setattr(candidate, \"execution_allowed\", False)\n            setattr(candidate, \"mode\", \"advisory_only\")\n" + parts[1]
        
        # also the second one if it exists
        if len(parts) > 2:
            new_opp += "execution_allowed = bool(_get_value(candidate, \"execution_allowed\", False))\n    tradable = bool(_get_value(candidate, \"tradable\", False))\n\n    if source_flags.get(\"quote_source\") == \"REST_RECOVERY\" or source_flags.get(\"recovered_fallback\"):\n        execution_allowed = False\n        if isinstance(candidate, dict):\n            candidate[\"execution_allowed\"] = False\n            candidate[\"mode\"] = \"advisory_only\"\n        elif hasattr(candidate, \"execution_allowed\"):\n            setattr(candidate, \"execution_allowed\", False)\n            setattr(candidate, \"mode\", \"advisory_only\")\n" + parts[2]
            
        with open('core/opportunity_engine.py', 'w') as f:
            f.write(new_opp)
            
