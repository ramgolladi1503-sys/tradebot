import re

with open("core/opportunity_engine.py", "r") as f:
    content = f.read()

patch = """    try:
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
        pass

    if execution_allowed and tradable and executable_truth and execution_ok and fresh_quote_ok and liquidity_ok and spread_ok:"""

content = content.replace(
    "if execution_allowed and tradable and executable_truth and execution_ok and fresh_quote_ok and liquidity_ok and spread_ok:",
    patch
)

with open("core/opportunity_engine.py", "w") as f:
    f.write(content)
