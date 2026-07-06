import re

with open("core/opportunity_engine.py", "r") as f:
    content = f.read()

bad_snippet = """        try:
        from core.kite_depth_ws import get_stale_active_trade_tokens
        stale_active = get_stale_active_trade_tokens()
        entry_token = _safe_float(_get_value(candidate, "instrument_token"))
        if entry_token and int(entry_token) in stale_active:
            execution_allowed = False
            if "tradable_reasons_blocking" in candidate:
                candidate["tradable_reasons_blocking"].append("ENTRY_QUOTE_STALE")
            elif hasattr(candidate, "tradable_reasons_blocking"):
                candidate.tradable_reasons_blocking.append("ENTRY_QUOTE_STALE")
    except ImportError:
        pass"""

good_snippet = """    try:
        from core.kite_depth_ws import get_stale_active_trade_tokens
        stale_active = get_stale_active_trade_tokens()
        entry_token = _safe_float(_get_value(candidate, "instrument_token"))
        if entry_token and int(entry_token) in stale_active:
            execution_allowed = False
            if isinstance(candidate, dict):
                if "tradable_reasons_blocking" not in candidate:
                    candidate["tradable_reasons_blocking"] = []
                candidate["tradable_reasons_blocking"].append("ENTRY_QUOTE_STALE")
            elif hasattr(candidate, "tradable_reasons_blocking"):
                if candidate.tradable_reasons_blocking is None:
                    candidate.tradable_reasons_blocking = []
                candidate.tradable_reasons_blocking.append("ENTRY_QUOTE_STALE")
    except ImportError:
        pass"""

content = content.replace(bad_snippet, good_snippet)

with open("core/opportunity_engine.py", "w") as f:
    f.write(content)
