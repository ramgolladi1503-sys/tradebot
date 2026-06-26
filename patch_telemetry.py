import re

with open("core/htf_paper_telemetry.py", "r") as f:
    content = f.read()

replacement = """    strike = _get_val(trade, "strike")
    opt_type = _get_val(trade, "type", _get_val(trade, "option_type"))
    
    if not strike or not opt_type:
        direction = str(_get_val(trade, "direction", "")).upper()
        fallback_type = "CE" if "CALL" in direction else "PE" if "PUT" in direction else ""
        for opt in chain:
            if fallback_type and opt.get("type") != fallback_type:
                continue
            strike = opt.get("strike")
            opt_type = opt.get("type")
            break"""

content = re.sub(r'    strike = _get_val\(trade, "strike"\)\n    opt_type = _get_val\(trade, "type", _get_val\(trade, "option_type"\)\)', replacement, content, flags=re.DOTALL)

with open("core/htf_paper_telemetry.py", "w") as f:
    f.write(content)
