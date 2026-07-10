import re

with open("core/movement_contract.py", "r") as f:
    text = f.read()

replacement = """def context_from_dict(payload: dict[str, Any]) -> StrategyContext:
    if not isinstance(payload, dict):
        raise MovementContractError("context_payload_not_dict")
    import dataclasses
    valid_keys = {f.name for f in dataclasses.fields(StrategyContext)}
    valid_payload = {k: v for k, v in payload.items() if k in valid_keys}
    return StrategyContext(**valid_payload)"""

text = re.sub(r'def context_from_dict\(payload: dict\[str, Any\]\) -> StrategyContext:\n.*?return StrategyContext\(\*\*payload\)', replacement, text, flags=re.DOTALL)

with open("core/movement_contract.py", "w") as f:
    f.write(text)

with open("core/candidate_pool_orchestrator.py", "r") as f:
    text = f.read()
text = text.replace("ctx = StrategyContext(**ctx)", "from core.movement_contract import context_from_dict\n        ctx = context_from_dict(ctx)")
with open("core/candidate_pool_orchestrator.py", "w") as f:
    f.write(text)

with open("core/runtime_snapshot_producer.py", "r") as f:
    text = f.read()
text = text.replace("ctx = StrategyContext(**ctx_data)", "from core.movement_contract import context_from_dict\n            ctx = context_from_dict(ctx_data)")
with open("core/runtime_snapshot_producer.py", "w") as f:
    f.write(text)
