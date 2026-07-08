import re

with open("core/opportunity_engine.py", "r") as f:
    content = f.read()

bad_snippet = """    execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
    tradable = bool(_get_value(candidate, "tradable", False))"""

good_snippet = """    execution_allowed = bool(_get_value(candidate, "execution_allowed", False))
    tradable = bool(_get_value(candidate, "tradable", False))

    if source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        execution_allowed = False
        if isinstance(candidate, dict):
            candidate["execution_allowed"] = False
            candidate["mode"] = "advisory_only"
        elif hasattr(candidate, "execution_allowed"):
            setattr(candidate, "execution_allowed", False)
            setattr(candidate, "mode", "advisory_only")
    
    try:
        import json
        from core.log_writer import logs_dir
        health_path = logs_dir() / "feed_health.json"
        stale_active = []
        if health_path.exists():
            try:
                payload = json.loads(health_path.read_text(encoding="utf-8"))
                stale_active = payload.get("subscribed_stale_tokens", [])
            except Exception:
                pass

        entry_token = _safe_float(_get_value(candidate, "instrument_token"))
        if entry_token and int(entry_token) in stale_active:
            execution_allowed = False
            if isinstance(candidate, dict):
                candidate["execution_allowed"] = False
                if "tradable_reasons_blocking" not in candidate:
                    candidate["tradable_reasons_blocking"] = []
                candidate["tradable_reasons_blocking"].append("ENTRY_QUOTE_STALE")
            elif hasattr(candidate, "execution_allowed"):
                setattr(candidate, "execution_allowed", False)
                if getattr(candidate, "tradable_reasons_blocking", None) is None:
                    candidate.tradable_reasons_blocking = []
                candidate.tradable_reasons_blocking.append("ENTRY_QUOTE_STALE")
    except Exception:
        pass"""

content = content.replace(bad_snippet, good_snippet)

with open("core/opportunity_engine.py", "w") as f:
    f.write(content)
