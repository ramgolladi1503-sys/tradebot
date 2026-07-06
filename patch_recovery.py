import re

with open("core/opportunity_engine.py", "r") as f:
    content = f.read()

patch = """    if is_fallback or planning_only or source_flags.get("quote_source") == "REST_RECOVERY" or source_flags.get("recovered_fallback"):
        if isinstance(candidate, dict):
            candidate["execution_allowed"] = False
            candidate["mode"] = "advisory_only"
        else:
            setattr(candidate, "execution_allowed", False)
            setattr(candidate, "mode", "advisory_only")
        return "ADVISORY_ONLY"
"""

content = content.replace(
    "    if is_fallback or planning_only:\n        return \"ADVISORY_ONLY\"\n",
    patch
)

with open("core/opportunity_engine.py", "w") as f:
    f.write(content)
